"""
tests/test_research_tool.py
Unit tests for autodna/tools/research.py filtering utilities.
"""

from autodna.tools.research import normalize_url, domain_from_url, filter_links, retry, validate_artifact


def test_normalize_url_strips_tracking_and_www():
    url = "HTTPS://WWW.Example.com/Path/?utm_source=foo&id=123#frag"
    assert normalize_url(url) == "https://example.com/Path/?id=123"


def test_domain_from_url_strips_www_and_lowercases():
    url = "https://WWW.Sub.Example.com/thing"
    assert domain_from_url(url) == "sub.example.com"


def test_filter_links_applies_allow_block_and_dedupe():
    links = [
        "https://www.example.com/a?utm_source=foo",
        "https://www.example.com/b?utm_source=bar",
        "https://blog.example.com/c",
        "https://bad.com/a",
        "https://www.other.com/x?utm_medium=email",
    ]

    filtered = filter_links(
        links=links,
        allow_domains=["example.com", "other.com"],
        block_domains=["bad.com"],
        max_sources=3,
        dedupe_host=True,
        dedupe_url=True,
    )

    assert filtered == [
        "https://example.com/a",
        "https://blog.example.com/c",
        "https://other.com/x",
    ]


def test_filter_links_dedupes_by_normalized_url():
    links = [
        "https://example.com/a?utm_source=foo",
        "https://example.com/a?utm_medium=bar",
    ]

    filtered = filter_links(
        links=links,
        allow_domains=[],
        block_domains=[],
        max_sources=5,
        dedupe_host=False,
        dedupe_url=True,
    )

    assert filtered == ["https://example.com/a"]


def test_retry_succeeds_after_failures():
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("fail")
        return "ok"

    assert retry(flaky, attempts=3, delay_seconds=0) == "ok"


def test_retry_raises_after_exhaustion():
    def always_fail():
        raise ValueError("nope")

    try:
        retry(always_fail, attempts=2, delay_seconds=0)
    except ValueError:
        assert True
    else:
        assert False


def test_validate_artifact(tmp_path):
    artifact = tmp_path / "artifact.md"
    assert validate_artifact(artifact) is False
    artifact.write_text("data", encoding="utf-8")
    assert validate_artifact(artifact, min_bytes=3) is True
