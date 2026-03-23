import argparse
import os
import pathlib
import subprocess
import sys

GEMINI_PLATFORMS = {"GEMINI", "GEMINI_CLI", "GEMINI-CLI", "ANTIGRAVITY"}
GPU_LOCK_PATH = pathlib.Path("agent/GPU.lock")


def resolve_platform() -> str:
    env_platform = os.environ.get("AUTODNA_PLATFORM")
    if env_platform:
        return env_platform
    active = pathlib.Path("platform/ACTIVE")
    if active.exists():
        value = active.read_text(encoding="utf-8").strip()
        if value:
            return value
    return "GEMINI"


def _task_cli_hint() -> str:
    return "python -m autodna.cli"


def _sanitize_agent_name(agent_name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in agent_name.strip())
    return cleaned or "autodna"


def build_agent_mission(agent_name: str, task_id: int | None = None) -> str:
    cmd = _task_cli_hint()
    if task_id is not None:
        return (
            "Single-Agent Mode: Work only on "
            f"task {task_id}. Run `{cmd} tasks list` to confirm the queue state. "
            f"If task {task_id} is not already assigned to {agent_name}, claim it with "
            f"`{cmd} tasks claim {task_id} {agent_name}`. "
            f"Implement the task in the main workspace, run the relevant tests, and finish with "
            f"`{cmd} tasks complete {task_id}` after verification passes. "
            "Use `python tools/git_ops.py <TASK_ID> commit` before pushing if you need the managed git flow."
        )
    return (
        "Single-Agent Mode: Resume any task already assigned to you before claiming new work. "
        f"Use `{cmd} tasks list` to inspect the queue, claim one task with "
        f"`{cmd} tasks claim <id> {agent_name}`, run the relevant tests, and complete it with "
        f"`{cmd} tasks complete <id>` after verification passes. "
        "Stay in the main workspace."
    )


def launch_agent(agent_name: str, mission: str, color: str = "0A", headless: bool = False):
    safe_agent_name = _sanitize_agent_name(agent_name)
    safe_mission = mission.replace('"', "'").replace("\n", " ").strip()
    gpu_instruction = " [GPU SAFETY: Check agent/GPU.lock before use]"
    full_mission = safe_mission + gpu_instruction

    if headless:
        log_path = pathlib.Path.cwd() / "agent" / f"{safe_agent_name}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(str(log_path), "w", encoding="utf-8")

        creation_flags = 0x08000000
        platform_name = resolve_platform().strip().upper()
        if platform_name in GEMINI_PLATFORMS:
            creation_flags = 0

        subprocess.Popen(
            ["python", "-m", "autodna.core.agent_runner", safe_agent_name, full_mission],
            shell=False,
            cwd=".",
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
        )
        return log_path

    cmd = (
        f'start "AUTODNA-{safe_agent_name}" cmd /k '
        f'"color {color} && cd . && python -m autodna.core.agent_runner '
        f'{safe_agent_name} \\"{full_mission}\\""'
    )
    subprocess.run(cmd, shell=True)
    return None


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Autonomous DNA single-agent launcher")
    parser.add_argument("--agent-name", default=os.environ.get("AUTODNA_AGENT_NAME", "autodna"))
    parser.add_argument("--task-id", type=int, help="Optional task ID to focus on")
    parser.add_argument("--mission", help="Optional explicit mission string")
    parser.add_argument("--color", default="0A", help="Console color when running interactively")
    parser.add_argument("--headless", action="store_true", help="Launch in the background and write a log")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = _parse_args(argv)

    print("--- AUTONOMOUS DNA LAUNCHER ---")
    if not os.path.exists(".git"):
        print("Error: Not a git repository. Please run `git init` and commit first.")
        sys.exit(1)

    if GPU_LOCK_PATH.exists():
        GPU_LOCK_PATH.unlink()
        print("Cleared stale GPU lock.")

    mission = args.mission or build_agent_mission(args.agent_name, args.task_id)
    result = launch_agent(args.agent_name, mission, color=args.color, headless=args.headless)

    if args.headless:
        print(f"Single-agent automation is running in the background. Log: {result}")
    else:
        print("Single-agent automation is running in interactive mode.")


if __name__ == "__main__":
    main()
