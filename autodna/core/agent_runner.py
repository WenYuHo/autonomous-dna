import sys
import subprocess
import time
import os

def main():
    if len(sys.argv) < 3:
        print("Usage: python agent_runner.py <agent_name> <mission_string>")
        sys.exit(1)
        
    agent_name = sys.argv[1]
    mission = sys.argv[2]
    
    # Models ordered by preference (below Gemini 3 per user request)
    # Fallback Models (Configurable via environment variable)
    DEFAULT_MODELS = "gemini-2.5-pro,gemini-2.5-flash,gemini-1.5-pro,gemini-1.5-flash"
    MODEL_LIST_STR = os.environ.get("AUTODNA_MODELS", DEFAULT_MODELS)
    models = [m.strip() for m in MODEL_LIST_STR.split(",") if m.strip()]
        
    current_model_index: int = 0
    max_retries: int = 3
    retries: int = 0
    
    while current_model_index < len(models):
        model = models[current_model_index]
        print(f"[{agent_name}] 🔄 Starting agent with model: {model} (Attempt {retries + 1})")
        
        from autodna.core.cli_driver import get_driver
        from pathlib import Path
        
        # Determine Platform to instatiate the correct Driver
        platform_file = Path("platform/ACTIVE")
        platform_name = platform_file.read_text().strip() if platform_file.exists() else "GEMINI"
        driver = get_driver(platform_name)

        # Build command dynamically
        cmd_list = driver.get_command(model, mission)
        
        # We read stdout and stderr via PIPE so we can parse it for errors AND echo it.
        # This prevents UnicodeEncodeError issues when printing characters the terminal can't handle natively.
        process = subprocess.Popen(
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Merge stderr into stdout
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        quota_exhausted = False
        
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
                    
                    # Check for quota exhaustion text dynamically based on the driver
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
            print(f"[{agent_name}] ⚠️ Quota exhausted for model {model}.")
            current_model_index += 1
            retries = 0
            if current_model_index < len(models):
                print(f"[{agent_name}] 🔄 Switching to fallback model: {models[current_model_index]}")
                time.sleep(2) # Brief cooldown before rapid-reboot
            else:
                print(f"[{agent_name}] ❌ All fallback models exhausted. Cannot continue.")
                break
        else:
            # If the process exited for a reason *other* than quota (e.g. fatal code bug, user abort)
            exit_code = process.returncode
            if exit_code == 0:
                print(f"[{agent_name}] ✅ Agent exited cleanly.")
                break
            else:
                print(f"[{agent_name}] ❌ Agent crashed with code {exit_code}. Retrying...")
                retries += 1
                if retries >= max_retries:
                    print(f"[{agent_name}] ❌ Max retries reached for model {model}. Switching model.")
                    current_model_index += 1
                    retries = 0
                time.sleep(3)

if __name__ == "__main__":
    # Configure stdout to handle utf-8 safely regardless of terminal env (if supported)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
