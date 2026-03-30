import argparse
import os
import time
import sys
from pathlib import Path

# Fix Windows cp1252 encoding for emoji output (if called directly)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def is_text_file(filepath):
    """Basic heuristic to determine if a file is text or binary."""
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(1024)
            if b'\0' in chunk:
                return False  # Binary file usually contains null bytes

            # Additional check: try decoding as utf-8
            chunk.decode('utf-8')
            return True
    except Exception:
        return False

def get_ignore_list(directory: Path):
    """Simple parser for an optional .gitignore file in the root."""
    ignore_paths = [".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv"]
    gitignore = directory / ".gitignore"
    if gitignore.exists():
        try:
            with open(gitignore, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        # Keep it simple, just add the raw string for exact directory matches or extensions
                        ignore_paths.append(line.replace("/", ""))
        except Exception:
            pass
    return ignore_paths

def benchmark_directory(target_dir):
    target = Path(target_dir).resolve()
    if not target.exists() or not target.is_dir():
        print(f"❌ Error: Target directory '{target_dir}' does not exist or is not a directory.")
        return

    ignore_list = get_ignore_list(target)

    total_files = 0
    total_bytes = 0
    total_lines = 0

    start_time = time.time()

    print(f"🔍 Scanning directory: {target} ...\n")

    for root, dirs, files in os.walk(target):
        # Mutating dirs in place prevents os.walk from entering ignored directories
        dirs[:] = [d for d in dirs if d not in ignore_list]

        for file in files:
            # Basic ignore exclusions
            if file in ignore_list or any(file.endswith(ext) for ext in [".pyc", ".pyo", ".pyd", ".exe", ".dll"]):
                continue

            filepath = Path(root) / file

            # Double check ignore patterns that might be subpaths
            if any(ignored in filepath.parts for ignored in ignore_list):
                 continue

            if not is_text_file(filepath):
                continue

            try:
                stat = filepath.stat()
                total_bytes += stat.st_size
                total_files += 1

                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    total_lines += content.count('\n') + 1

            except Exception as e:
                # Silently skip files we can't read
                pass

    end_time = time.time()
    duration = end_time - start_time

    # Simple proxy tokenizer matching average BPE logic (1 token ~= 4 chars/bytes in English)
    estimated_tokens = total_bytes / 4

    print("📊 --- BENCHMARK RESULTS ---")
    print(f"⏱️  Time Elapsed   : {duration:.4f} seconds")
    print(f"📁 Files Scanned  : {total_files:,}")
    print(f"📝 Total Lines    : {total_lines:,}")
    print(f"💾 Total Size     : {total_bytes / 1024:.2f} KB ({total_bytes:,} bytes)")
    print(f"🪙  Est. Tokens    : ~{estimated_tokens:,.0f} tokens")
    print("----------------------------")

    # Calculate burn rate (assuming full context load)
    if duration > 0:
        token_rate = estimated_tokens / duration
        print(f"🔥 Token Burn Rate: ~{token_rate:,.0f} tokens/second")


def main():
    # Parse exactly what's given, allowing the main CLI to pass --target-dir
    parser = argparse.ArgumentParser(description="Autonomous DNA Token Benchmark Utility")
    parser.add_argument("--target-dir", default=".", help="Directory to scan (defaults to current directory)")

    # Because this is called via `autodna benchmark <args>`, we slice off the first two if they exist,
    # OR we just let parse_args handle the generic injection from `cli.py`.
    # `cli.py` already overrides sys.argv correctly now.
    args = parser.parse_args()
    benchmark_directory(args.target_dir)

if __name__ == "__main__":
    main()
