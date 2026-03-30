from pathlib import Path

from autodna.tools.io_utils import read_text_fallback


def test_read_text_fallback_reads_utf8(tmp_path: Path):
    path = tmp_path / "mem.txt"
    path.write_text("alpha\nbeta", encoding="utf-8")
    assert read_text_fallback(path) == "alpha\nbeta"


def test_read_text_fallback_handles_cp1252(tmp_path: Path):
    path = tmp_path / "mem.txt"
    # 0x97 is an em dash in cp1252 and invalid in UTF-8.
    path.write_bytes(b"alpha\x97beta")
    text = read_text_fallback(path)
    assert "alpha" in text
    assert "beta" in text
    assert "\u2014" in text
