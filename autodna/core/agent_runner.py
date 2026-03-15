import sys
import subprocess
import time
import os
from pathlib import Path

CODEX_PLATFORMS = {"CODEX", "CODEX_APP", "CODEX_DESKTOP", "CODEX_CLI", "OPENAI"}


def _resolve_platform() -> str:
    env_platform = os.environ.get("AUTODNA_PLATFORM")
    if env_platform:
        return env_platform
    if os.environ.get("CODEX_SHELL") == "1":
        return "CODEX"
    origin = os.environ.get("CODEX_INTERNAL_ORIGINATOR", "")
    if origin and "CODEX" in origin.upper():
        return "CODEX"
    platform_file = Path("platform/ACTIVE")
    if platform_file.exists():
        content = platform_file.read_text().strip()
        if content:
            return content
    return "GEMINI"


def _is_codex_platform(platform_name: str) -> bool:
    return platform_name.strip().upper() in CODEX_PLATFORMS


def _build_models(is_codex: bool) -> list[str]:
    # Models ordered by preference (below Gemini 3 per user request)
    DEFAULT_GEMINI_MODELS = "gemini-2.5-flash,gemini-2.5-pro,gemini-2.0-flash-exp,gemini-1.5-flash"
    default_models = DEFAULT_GEMINI_MODELS
    if is_codex:
        default_models = os.environ.get("AUTODNA_CODEX_MODELS", "")
    model_list_str = os.environ.get("AUTODNA_MODELS", default_models)
    models = [m.strip() for m in model_list_str.split(",") if m.strip()]
    if not models:
        if is_codex:
            models = [""]
        else:
            models = [m.strip() for m in DEFAULT_GEMINI_MODELS.split(",") if m.strip()]
    return models


def main():
    if len(sys.argv) < 3:
        print("Usage: python agent_runner.py <agent_name> <mission_string>")
        sys.exit(1)

    agent_name = sys.argv[1]
    mission = sys.argv[2]

    from autodna.core.cli_driver import get_driver

    platform_name = _resolve_platform()
    driver = get_driver(platform_name)
    is_codex = _is_codex_platform(platform_name)
    models = _build_models(is_codex)

    current_model_index: int = 0
    max_retries: int = 3
    retries: int = 0
    codex_failed = False

    while current_model_index < len(models):
        model = models[current_model_index]
        model_label = model if model else "default"
        print(f"[{agent_name}] Starting agent with model: {model_label} (Attempt {retries + 1})")

        # Build command dynamically
        cmd_list = driver.get_command(model, mission)

        # We read stdout and stderr via PIPE so we can parse it for errors AND echo it.
        # This prevents UnicodeEncodeError issues when printing characters the terminal can't handle natively.
        try:
            process = subprocess.Popen(
                cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, # Merge stderr into stdout
                text=True,
                encoding="utf-8",
                errors="replace"
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            if is_codex and not codex_failed:
                codex_failed = True
                print(f"[{agent_name}] Codex CLI unavailable ({exc}). Falling back to Gemini.")
                platform_name = "GEMINI"
                driver = get_driver(platform_name)
                is_codex = False
                models = _build_models(is_codex)
                current_model_index = 0
                retries = 0
                continue
            if isinstance(exc, FileNotFoundError):
                print(f"[{agent_name}] CLI unavailable: {cmd_list[0]}.")
            elif isinstance(exc, PermissionError):
                print(f"[{agent_name}] Permission denied launching CLI: {cmd_list[0]}.")
            else:
                print(f"[{agent_name}] Failed to launch CLI: {exc}.")
            sys.exit(1)

        quota_exhausted = False
        model_unavailable = False

        # Read the stream eagerly
        if process.stdout is not None:
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break

                if line:
                    # Echo to our own stdout (which symphony_start.py captures into the .log file or console)
                    sys.stdout.write(line)
                    sys.stdout.flush()

                    # Check for model availability / quota exhaustion text dynamically based on the driver
                    if "ModelNotFoundError" in line or "Requested entity was not found" in line:
                        model_unavailable = True
                        quota_exhausted = True
                        break
                    if driver.is_quota_exhausted(line):
                        quota_exhausted = True
                        break

        # Ensure process finishes or we kill it if we broke early due to quota
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

        if quota_exhausted:
            if model_unavailable:
                print(f"[{agent_name}] Model unavailable: {model_label}.")
            else:
                print(f"[{agent_name}] Quota exhausted for model {model_label}.")
            current_model_index += 1
            retries = 0
            if current_model_index < len(models):
                next_label = models[current_model_index] if models[current_model_index] else "default"
                print(f"[{agent_name}] Switching to fallback model: {next_label}")
                time.sleep(2) # Brief cooldown before rapid-reboot
            else:
                print(f"[{agent_name}] All fallback models exhausted. Cannot continue.")
                break
        else:
            # If the process exited for a reason *other* than quota (e.g. fatal code bug, user abort)
            exit_code = process.returncode
            if exit_code == 0:
                print(f"[{agent_name}] Agent exited cleanly.")
                break
            else:
                print(f"[{agent_name}] Agent crashed with code {exit_code}. Retrying...")
                retries += 1
                if retries >= max_retries:
                    print(f"[{agent_name}] Max retries reached for model {model_label}. Switching model.")
                    current_model_index += 1
                    retries = 0
                time.sleep(3)


if __name__ == "__main__":
    # Configure stdout to handle utf-8 safely regardless of terminal env (if supported)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
