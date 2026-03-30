from pathlib import Path


def read_text_fallback(path: Path, primary: str = "utf-8", fallback: str = "cp1252") -> str:
    try:
        return path.read_text(encoding=primary)
    except UnicodeDecodeError:
        return path.read_text(encoding=fallback, errors="replace")
