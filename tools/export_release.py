import argparse
import fnmatch
import json
import os
import shutil
from pathlib import Path

DEFAULT_EXCLUDES = [
    ".git/",
    ".github/",
    ".antigravity/",
    ".claude/",
    ".codex/",
    ".mcp.json",
    "_mcp.json",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "README.md",
    "README.release.md",
    "agent/",
    "skills/",
    "tools/",
    "scripts/",
    "tests/",
    "worker-1/",
    "worker-2/",
    "autodna.egg-info/",
    ".pytest_cache/",
    ".ruff_cache/",
    "bridge.py",
    "docs/",
    "dist/",
    "release_manifest.json",
]

DEFAULT_RENAMES = {
    "README.release.md": "README.md",
}


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {"exclude": list(DEFAULT_EXCLUDES), "rename": dict(DEFAULT_RENAMES)}
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("release manifest must be a JSON object")
    exclude = data.get("exclude", DEFAULT_EXCLUDES)
    rename = data.get("rename", DEFAULT_RENAMES)
    if not isinstance(exclude, list) or not all(isinstance(x, str) for x in exclude):
        raise ValueError("release manifest 'exclude' must be a list of strings")
    if not isinstance(rename, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in rename.items()):
        raise ValueError("release manifest 'rename' must be a string-to-string map")
    return {"exclude": exclude, "rename": rename}


def normalize_patterns(patterns: list[str]) -> list[str]:
    normalized = []
    for pattern in patterns:
        pattern = pattern.replace("\\", "/")
        if pattern.startswith("./"):
            pattern = pattern[2:]
        normalized.append(pattern)
    return normalized


def matches_any(rel_posix: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        pattern = pattern.rstrip("/")
        if not pattern:
            continue
        if rel_posix == pattern:
            return True
        if rel_posix.startswith(pattern + "/"):
            return True
        if fnmatch.fnmatch(rel_posix, pattern):
            return True
    return False


def ensure_empty_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_tree(root: Path, out_dir: Path, exclude: list[str]) -> int:
    files_copied = 0

    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        rel_dir_posix = rel_dir.as_posix() if rel_dir.as_posix() != "." else ""

        if rel_dir_posix and matches_any(rel_dir_posix, exclude):
            dirnames[:] = []
            continue

        pruned = []
        for name in dirnames:
            rel_child = (rel_dir / name).as_posix()
            if matches_any(rel_child, exclude):
                continue
            pruned.append(name)
        dirnames[:] = pruned

        for filename in filenames:
            rel_file = (rel_dir / filename).as_posix()
            if matches_any(rel_file, exclude):
                continue
            src = root / rel_file
            dest = out_dir / rel_file
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            files_copied += 1

    return files_copied


def apply_renames(root: Path, out_dir: Path, rename: dict[str, str]) -> int:
    renamed = 0
    for src_rel, dest_rel in rename.items():
        src_path = root / src_rel
        if not src_path.exists():
            continue
        dest_path = out_dir / dest_rel
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dest_path)
        renamed += 1
    return renamed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a clean release tree from the repo.")
    parser.add_argument("--root", default=".", help="Repository root (default: current directory)")
    parser.add_argument("--out", default="dist/release", help="Output directory (default: dist/release)")
    parser.add_argument("--config", default="release_manifest.json", help="Path to release manifest JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    out_dir = Path(args.out).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (root / config_path).resolve()

    if not root.exists():
        print(f"Root path does not exist: {root}")
        return 2

    config = load_config(config_path)
    exclude = normalize_patterns(config["exclude"])
    rename = config["rename"]

    if out_dir == root:
        print("Refusing to export into repo root.")
        return 2

    if out_dir.is_relative_to(root):
        rel_out = out_dir.relative_to(root).as_posix()
        if rel_out not in exclude:
            exclude.append(rel_out)

    ensure_empty_dir(out_dir)

    files_copied = copy_tree(root, out_dir, exclude)
    renamed = apply_renames(root, out_dir, rename)

    print(f"Export complete: {files_copied} files copied, {renamed} renames applied.")
    print(f"Output: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
