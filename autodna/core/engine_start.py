import os
import subprocess
import time
import sys
import pathlib

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def setup_junction(target_dir, folder_name):
    """Creates a Windows Junction to share the environment."""
    root_folder = os.path.join(os.getcwd(), folder_name)
    target_folder = os.path.join(target_dir, folder_name)
    
    if os.path.exists(root_folder) and not os.path.exists(target_folder):
        print(f"🔗 Linking {folder_name} to {target_dir}...")
        # /J creates a directory junction on Windows
        subprocess.run(f'mklink /J "{target_folder}" "{root_folder}"', shell=True)

def setup_worktree(name):
    if not os.path.exists(name):
        print(f"📂 Creating worktree: {name}...")
        subprocess.run(f"git worktree add {name} -b autodna-{name}", shell=True)
    
    # Share the environments to save RAM/Disk
    setup_junction(name, ".venv")
    setup_junction(name, "node_modules")
    setup_junction(name, "models") # Crucial for 2070 Super: share the heavy model files

def launch_agent(name, mission, color="0A", headless=False):
    # Avoid quotes and newlines in the mission string
    safe_mission = mission.replace('"', "'").replace("\n", " ").strip()
    gpu_instruction = " [GPU SAFETY: Check agent/GPU.lock before use]"
    full_mission = safe_mission + gpu_instruction
    
    # We use -p (non-interactive) in headless mode to force the CLI to run the command and exit
    if headless:
        print(f"🕵️  Launching {name} in background (headless)...")
        log_name = "manager.log" if name == "." else f"{name}.log"
        log_path = pathlib.Path.cwd() / "agent" / log_name
        log_file = open(str(log_path), "w", encoding="utf-8")
        # CREATE_NO_WINDOW = 0x08000000
        cmd_list = ["python", "-m", "autodna.core.agent_runner", name, full_mission]
        subprocess.Popen(cmd_list, shell=False, cwd=name, stdout=log_file, stderr=subprocess.STDOUT, creationflags=0x08000000)
        return log_path
    else:
        # Standard mode: Open interactive windows
        # Note: We must ensure the command is executed, so we prefix with /c if using cmd
        cmd = f'start "AUTODNA-{name}" cmd /k "color {color} && cd {name} && python -m autodna.core.agent_runner {name} \\"{full_mission}\\""'
        subprocess.run(cmd, shell=True)
        return None

def main():
    print("--- 🧬 AUTONOMOUS DNA ORCHESTRATOR ---")
    headless = "--headless" in sys.argv
    
    # 1. Clean up stale locks
    if os.path.exists("agent/GPU.lock"):
        os.remove("agent/GPU.lock")
        print("🔓 Cleared stale GPU lock.")

    # 2. Setup Worktrees & Junctions
    setup_worktree("worker-1")
    setup_worktree("worker-2")
    
    # 3. Launch Manager (Orchestrator)
    print(f"🚀 Launching Manager {'(Headless)' if headless else '(Blue)'}...")
    log_m = launch_agent(".", "Manager Mode: You are the TPM. Run `autodna tasks list` to see tasks. Tell worker-1 or worker-2 to claim specific task IDs. Merge branches when done.", "0B", headless=headless)
    
    time.sleep(3)
    
    # 4. Launch Workers
    print(f"🚀 Launching Worker 1 {'(Headless)' if headless else '(Green)'}...")
    log_1 = launch_agent("worker-1", "Worker-1: Run `autodna tasks list --status pending` to see your queue. Claim tasks via `autodna tasks claim <id> worker-1`. Complete via `autodna tasks complete <id>`. Stay in worker-1 folder.", "0A", headless=headless)
    
    time.sleep(3)
    
    print(f"🚀 Launching Worker 2 {'(Headless)' if headless else '(Yellow)'}...")
    log_2 = launch_agent("worker-2", "Worker-2: Run `autodna tasks list --status pending` to see your queue. Claim tasks via `autodna tasks claim <id> worker-2`. Complete via `autodna tasks complete <id>`. Stay in worker-2 folder.", "0E", headless=headless)

    if headless:
        print(f"\n✅ Autonomous DNA is running in background. Streaming logs below... (Press Ctrl+C to exit monitor loop)")
        print("--------------------------------------------------------------------------------")
        
        # Build file readers
        readers = {
            "MANAGER": open(str(log_m), "r", encoding="utf-8"),
            "WORKER-1": open(str(log_1), "r", encoding="utf-8"),
            "WORKER-2": open(str(log_2), "r", encoding="utf-8")
        }
        
        try:
            while True:
                for agent_name, f in readers.items():
                    line = f.readline()
                    if line:
                        stripped = line.strip()
                        if stripped:
                            print(f"[{agent_name}] {stripped}")
                time.sleep(0.05)
        except KeyboardInterrupt:
            print("\n🛑 Exiting live monitor. Autonomous DNA agents are still running in the background!")
    else:
        print(f"\n✅ Autonomous DNA is running in interactive mode.")

if __name__ == "__main__":
    main()
