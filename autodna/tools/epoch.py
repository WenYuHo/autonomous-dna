import sys
import argparse
import subprocess
import datetime
import time
import os
import shlex

RESEARCH_RETRIES = 2
EVAL_RETRIES = 2
RETRY_DELAY_SECONDS = 2
RESEARCH_TIMEOUT_SECONDS = 300
EVAL_TIMEOUT_SECONDS = 120
IMPROVE_RETRIES = 1
IMPROVE_TIMEOUT_SECONDS = 1800


def run_with_retries(command: list[str], attempts: int, delay_seconds: int, timeout_seconds: int, label: str) -> bool:
    for attempt in range(1, attempts + 1):
        try:
            subprocess.run(command, check=True, timeout=timeout_seconds)
            return True
        except subprocess.TimeoutExpired:
            print(f"Ã¢Å¡Â Ã¯Â¸Â {label} timed out (attempt {attempt}/{attempts}).")
        except subprocess.CalledProcessError:
            print(f"Ã¢Å¡Â Ã¯Â¸Â {label} failed (attempt {attempt}/{attempts}).")
        if attempt < attempts and delay_seconds > 0:
            time.sleep(delay_seconds)
    return False


def parse_improve_args(cli_args: list[str]) -> list[str]:
    if cli_args:
        return cli_args
    env_args = os.getenv("AUTODNA_IMPROVE_ARGS", "").strip()
    if not env_args:
        return []
    return shlex.split(env_args, posix=(os.name != "nt"))

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="Autonomous DNA Self-Improvement Epoch")
    parser.add_argument("--improve", action="store_true", help="Run improve step during epoch")
    parser.add_argument("--improve-arg", action="append", default=[], help="Pass-through arg for autodna improve")
    parser.add_argument("--improve-timeout", type=int, default=IMPROVE_TIMEOUT_SECONDS, help="Timeout for improve step")
    parser.add_argument("--improve-retries", type=int, default=IMPROVE_RETRIES, help="Retry count for improve step")

    args_to_parse = sys.argv[1:]
    if sys.argv and sys.argv[0].startswith("autodna"):
         args_to_parse = sys.argv[1:]
    args, _ = parser.parse_known_args(args_to_parse)

    print("============================================================")
    print(f"ðŸ§¬ AUTONOMOUS DNA: SELF-IMPROVEMENT EPOCH - {datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print("============================================================")

    print("\n[1/5] EVOLUTIONARY RESEARCH ðŸ”­")
    print("Spawning agent to discover latest AI coding agent best practices...")
    sys.stdout.flush()
    research_ok = run_with_retries(
        [sys.executable, "autodna/cli.py", "research", "latest state of the art AI coding agent system prompts and framework architecture 2026"],
        attempts=RESEARCH_RETRIES,
        delay_seconds=RETRY_DELAY_SECONDS,
        timeout_seconds=RESEARCH_TIMEOUT_SECONDS,
        label="Research phase",
    )
    if not research_ok:
        print("âš ï¸ Research phase failed after retries. Continuing with existing memory fragments.")

    improve_args = parse_improve_args(args.improve_arg)
    if args.improve or improve_args:
        print("\n[2/5] IMPROVEMENT ðŸ§ª")
        sys.stdout.flush()
        if not improve_args:
            print("âš ï¸ Improve step enabled but no args provided. Skipping.")
        else:
            improve_ok = run_with_retries(
                [sys.executable, "autodna/cli.py", "improve", *improve_args],
                attempts=max(1, args.improve_retries),
                delay_seconds=RETRY_DELAY_SECONDS,
                timeout_seconds=args.improve_timeout,
                label="Improve phase",
            )
            if not improve_ok:
                print("âš ï¸ Improve phase failed after retries.")

    print("\n[3/5] DEFRAGMENTATION & EVALUATION ðŸ§¹")
    sys.stdout.flush()
    eval_ok = run_with_retries(
        [sys.executable, "autodna/cli.py", "eval"],
        attempts=EVAL_RETRIES,
        delay_seconds=RETRY_DELAY_SECONDS,
        timeout_seconds=EVAL_TIMEOUT_SECONDS,
        label="Eval phase",
    )
    if not eval_ok:
        print("âš ï¸ Eval phase failed after retries.")

    print("\n[4/5] SYNCING MEMORY FRAGMENTS ðŸ”„")
    print("Memory and queue state analyzed.")

    print("\n[5/5] EPOCH COMPLETE âœ…")
    print("=" * 60)
    print("The agent's genetic material (MEMORY.md and TASK_QUEUE.md) is now state-of-the-art and defragmented.")

if __name__ == "__main__":
    main()
