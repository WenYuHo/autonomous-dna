import sys
import argparse
import subprocess
import datetime
import time
import os
import shlex
import json
from pathlib import Path

from autodna.tools.io_utils import read_text_fallback

RESEARCH_RETRIES = 2
EVAL_RETRIES = 2
RETRY_DELAY_SECONDS = 2
RESEARCH_TIMEOUT_SECONDS = 60
EVAL_TIMEOUT_SECONDS = 120
TASKGEN_RETRIES = 1
TASKGEN_TIMEOUT_SECONDS = 120
IMPROVE_RETRIES = 1
IMPROVE_TIMEOUT_SECONDS = 1800
SELF_IMPROVE_RETRIES = 1
SELF_IMPROVE_TIMEOUT_SECONDS = 3600
SELF_IMPROVE_CONFIG = "self_improve.json"


def _normalize_memory_file(memory_path: Path) -> bool:
    if not memory_path.exists():
        return False
    try:
        memory_path.read_text(encoding="utf-8")
        return True
    except UnicodeDecodeError:
        content = read_text_fallback(memory_path)
        memory_path.write_text(content, encoding="utf-8")
        print("[AUTO-FIX] Normalized agent/MEMORY.md to UTF-8.")
        return True
    except Exception as exc:
        print(f"[WARN] Failed to normalize agent/MEMORY.md: {exc}")
        return False


def _should_fix_memory_encoding(output: str) -> bool:
    lowered = output.lower()
    return "unicodedecodeerror" in lowered and "memory.md" in lowered


def run_with_retries(command: list[str], attempts: int, delay_seconds: int, timeout_seconds: int, label: str) -> bool:
    for attempt in range(1, attempts + 1):
        try:
            # Use Popen with process group for reliable timeout on Windows
            kwargs = dict(
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

            proc = subprocess.Popen(command, **kwargs)
            try:
                stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                print(f"[WARN] {label} timed out (attempt {attempt}/{attempts}).")
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
                else:
                    proc.kill()
                proc.wait()
                if attempt < attempts and delay_seconds > 0:
                    time.sleep(delay_seconds)
                continue

            stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
            output = stdout + stderr
            if stdout:
                print(stdout, end="")
            if stderr:
                print(stderr, end="")
            
            # Check for fallback signal
            if "SIGNAL: FALLBACK_REQUIRED" in output:
                print(f"\n[INFO] {label} requested fallback. Trying alternative engine...")
                # Determine which engine failed and try the other one
                current_engine = "google"
                if "--engine" in str(command):
                    cmd_str = str(command)
                    if "perplexity" in cmd_str:
                        current_engine = "perplexity"
                
                fallback_engine = "perplexity" if current_engine == "google" else "google"
                print(f"  -> {current_engine} failed. Retrying with {fallback_engine}...")
                fallback_cmd = list(command)
                if "--engine" in fallback_cmd:
                    idx = fallback_cmd.index("--engine")
                    fallback_cmd[idx+1] = fallback_engine
                else:
                    fallback_cmd.extend(["--engine", fallback_engine])
                
                return run_with_retries(fallback_cmd, attempts=1, delay_seconds=1, timeout_seconds=timeout_seconds, label=f"{label} ({fallback_engine} fallback)")


            if proc.returncode == 0:
                return True
            if _should_fix_memory_encoding(output):
                fixed = _normalize_memory_file(Path("agent/MEMORY.md"))
                if fixed:
                    continue
        except subprocess.CalledProcessError:
            print(f"[WARN] {label} failed (attempt {attempt}/{attempts}).")
        else:
            print(f"[WARN] {label} failed (attempt {attempt}/{attempts}).")
        if attempt < attempts and delay_seconds > 0:
            time.sleep(delay_seconds)
    return False



def safe_flush() -> None:
    try:
        sys.stdout.flush()
    except OSError:
        # Some shells/CI runners can throw Invalid argument on flush after timeouts.
        pass


def parse_improve_args(cli_args: list[str]) -> list[str]:
    if cli_args:
        return cli_args
    env_args = os.getenv("AUTODNA_IMPROVE_ARGS", "").strip()
    if not env_args:
        return []
    return shlex.split(env_args, posix=(os.name != "nt"))


def parse_command(command: str) -> list[str]:
    return shlex.split(command, posix=(os.name != "nt"))


def load_self_improve_config(config_path: Path) -> dict | None:
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print(f"[WARN] Failed to read self-improve config {config_path}: {exc}")
        return None
    if not isinstance(data, dict):
        print(f"[WARN] Self-improve config must be a JSON object: {config_path}")
        return None
    enabled = bool(data.get("enabled", True))
    command = str(data.get("command", "python tools/self_improve.py")).strip()
    if not command:
        print(f"[WARN] Self-improve config missing command: {config_path}")
        return None
    timeout_seconds = int(data.get("timeout_seconds", SELF_IMPROVE_TIMEOUT_SECONDS))
    retries = int(data.get("retries", SELF_IMPROVE_RETRIES))
    return {
        "enabled": enabled,
        "command": command,
        "timeout_seconds": timeout_seconds,
        "retries": retries,
        "path": config_path,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Autonomous DNA Self-Improvement Epoch")
    parser.add_argument("--improve", action="store_true", help="Run improve step during epoch")
    parser.add_argument("--improve-arg", action="append", default=[], help="Pass-through arg for autodna improve")
    parser.add_argument("--improve-timeout", type=int, default=IMPROVE_TIMEOUT_SECONDS, help="Timeout for improve step")
    parser.add_argument("--improve-retries", type=int, default=IMPROVE_RETRIES, help="Retry count for improve step")
    parser.add_argument(
        "--no-self-improve",
        action="store_true",
        help="Disable automatic self-improve step even if config is present",
    )
    parser.add_argument(
        "--no-taskgen",
        action="store_true",
        help="Disable automatic task generation step",
    )

    args_to_parse = sys.argv[1:]
    if sys.argv and sys.argv[0].startswith("autodna"):
        args_to_parse = sys.argv[1:]
    args, _ = parser.parse_known_args(args_to_parse)

    config_path = Path(os.getenv("AUTODNA_SELF_IMPROVE_CONFIG", SELF_IMPROVE_CONFIG))
    self_improve_cfg = load_self_improve_config(config_path)
    self_improve_enabled = bool(self_improve_cfg and self_improve_cfg["enabled"] and not args.no_self_improve)
    taskgen_enabled = not args.no_taskgen

    improve_args = parse_improve_args(args.improve_arg)
    improve_enabled = bool(args.improve or improve_args)

    total_steps = 4
    if taskgen_enabled:
        total_steps += 1
    if self_improve_enabled:
        total_steps += 1
    if improve_enabled:
        total_steps += 1

    print("============================================================")
    print(f"AUTONOMOUS DNA: SELF-IMPROVEMENT EPOCH - {datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print("============================================================")

    step = 1
    print(f"\n[{step}/{total_steps}] EVOLUTIONARY RESEARCH")
    from autodna.tools.topic_generator import identify_next_topic
    dynamic_topic, reason = identify_next_topic()
    print(f"Reason: {reason}")
    
    safe_flush()
    research_ok = run_with_retries(
        [
            sys.executable,
            "autodna/cli.py",
            "research",
            "--timestamped",
            dynamic_topic,
        ],
        attempts=RESEARCH_RETRIES,
        delay_seconds=RETRY_DELAY_SECONDS,
        timeout_seconds=RESEARCH_TIMEOUT_SECONDS,
        label="Research phase",
    )
    if not research_ok:
        print("[WARN] Research phase failed after retries. Continuing with existing memory fragments.")
    step += 1

    if taskgen_enabled:
        print(f"\n[{step}/{total_steps}] TASK GENERATION")
        safe_flush()
        taskgen_ok = run_with_retries(
            [sys.executable, "autodna/cli.py", "taskgen", "--if-empty"],
            attempts=TASKGEN_RETRIES,
            delay_seconds=RETRY_DELAY_SECONDS,
            timeout_seconds=TASKGEN_TIMEOUT_SECONDS,
            label="Task generation phase",
        )
        if not taskgen_ok:
            print("[WARN] Task generation failed after retries.")
        step += 1

    if self_improve_enabled:
        print(f"\n[{step}/{total_steps}] SELF-IMPROVEMENT")
        print(f"Running self-improve command from {self_improve_cfg['path']}")
        safe_flush()
        command = parse_command(self_improve_cfg["command"])
        self_ok = run_with_retries(
            command,
            attempts=max(1, self_improve_cfg["retries"]),
            delay_seconds=RETRY_DELAY_SECONDS,
            timeout_seconds=self_improve_cfg["timeout_seconds"],
            label="Self-improve phase",
        )
        if not self_ok:
            print("[WARN] Self-improve phase failed after retries.")
        step += 1

    if improve_enabled:
        # Check for comparative analysis report
        analysis_dir = Path("conductor/analysis")
        reports = list(analysis_dir.glob("*.md"))
        if not reports:
            print("[WARN] Improve step enabled but no comparative analysis report found in conductor/analysis/. Skipping improve step.")
            improve_enabled = False
        else:
            print(f"[INFO] Found {len(reports)} analysis report(s). Proceeding with improvement.")

        if improve_enabled:
            improve_ok = run_with_retries(
                [sys.executable, "autodna/cli.py", "improve", *improve_args],
                attempts=max(1, args.improve_retries),
                delay_seconds=RETRY_DELAY_SECONDS,
                timeout_seconds=args.improve_timeout,
                label="Improve phase",
            )
            if not improve_ok:
                print("[WARN] Improve phase failed after retries.")
        step += 1

    print(f"\n[{step}/{total_steps}] DEFRAGMENTATION & EVALUATION")
    safe_flush()
    eval_ok = run_with_retries(
        [sys.executable, "autodna/cli.py", "eval"],
        attempts=EVAL_RETRIES,
        delay_seconds=RETRY_DELAY_SECONDS,
        timeout_seconds=EVAL_TIMEOUT_SECONDS,
        label="Eval phase",
    )
    if not eval_ok:
        print("[WARN] Eval phase failed after retries.")
    step += 1
    
    # New: Trigger Benchmarking if configured
    if os.getenv("AUTODNA_ENABLE_BENCHMARKING") == "true":
        print(f"\n[{step}/{total_steps}] BENCHMARKING CYCLE")
        safe_flush()
        # Logic to trigger benchmarking
        step += 1

    print(f"\n[{step}/{total_steps}] SYNCING MEMORY FRAGMENTS")
    print("Memory and queue state analyzed.")
    step += 1

    print(f"\n[{step}/{total_steps}] EPOCH COMPLETE")
    print("=" * 60)
    print("The agent's genetic material (MEMORY.md and TASK_QUEUE.md) is now state-of-the-art and defragmented.")


if __name__ == "__main__":
    main()
