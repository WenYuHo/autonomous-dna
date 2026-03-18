import sys
import argparse
import urllib.parse
import time
import os
from datetime import datetime, timezone
from pathlib import Path

from autodna.tools.io_utils import read_text_fallback
from playwright.sync_api import sync_playwright

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_name",
    "utm_reader",
    "utm_viz_id",
    "utm_pubreferrer",
    "utm_swu",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
    "spm",
}

DEFAULT_ARTIFACT_DIR = Path("agent/skills/auto_generated")



def normalize_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception:
        return url

    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    filtered_pairs = [(k, v) for k, v in query_pairs if k.lower() not in TRACKING_PARAMS]
    query = urllib.parse.urlencode(filtered_pairs, doseq=True)

    return urllib.parse.urlunsplit((scheme, netloc, parsed.path, query, ""))


def domain_from_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
        host = parsed.netloc.lower()
    except Exception:
        return ""

    if host.startswith("www."):
        host = host[4:]
    return host


def domain_matches(host: str, domain: str) -> bool:
    host = host.lower()
    domain = domain.lower()
    return host == domain or host.endswith(f".{domain}")


def filter_links(
    links: list[str],
    allow_domains: list[str],
    block_domains: list[str],
    max_sources: int,
    dedupe_host: bool,
    dedupe_url: bool,
) -> list[str]:
    filtered = []
    seen_hosts = set()
    seen_urls = set()

    for url in links:
        host = domain_from_url(url)
        if not host:
            continue

        if allow_domains and not any(domain_matches(host, domain) for domain in allow_domains):
            continue
        if block_domains and any(domain_matches(host, domain) for domain in block_domains):
            continue

        normalized = normalize_url(url) if dedupe_url else url

        if dedupe_url and normalized in seen_urls:
            continue
        if dedupe_host and host in seen_hosts:
            continue

        filtered.append(normalized)
        seen_urls.add(normalized)
        seen_hosts.add(host)

        if len(filtered) >= max_sources:
            break

    return filtered


def retry(action, attempts: int, delay_seconds: float, backoff: float = 2.0):
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    last_exc = None
    current_delay = delay_seconds
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except Exception as exc:
            last_exc = exc
            if attempt == attempts:
                break
            if current_delay > 0:
                time.sleep(current_delay)
                current_delay *= backoff
    raise last_exc


def validate_artifact(path: Path, min_bytes: int = 1) -> bool:
    if not path.exists():
        return False
    try:
        return path.stat().st_size >= min_bytes
    except Exception:
        return False



def slugify_topic(topic: str, max_len: int = 30) -> str:
    slug = "".join(ch if ch.isalnum() else "_" for ch in topic[:max_len]).strip("_").lower()
    return slug or "research"


def build_artifact_path(
    topic_str: str,
    out_dir: Path,
    timestamped: bool,
    now: datetime | None = None,
) -> Path:
    slug = slugify_topic(topic_str)
    if timestamped:
        current = now or datetime.now(timezone.utc)
        ts = current.strftime("%Y%m%dT%H%M%S") + f"{int(current.microsecond / 1000):03d}Z"
        filename = f"{slug}_{ts}.md"
    else:
        filename = f"{slug}.md"
    return out_dir / filename




def ensure_unique_path(path: Path, max_tries: int = 1000) -> Path:
    if not path.exists():
        return path
    for idx in range(1, max_tries + 1):
        candidate = path.with_name(f"{path.stem}_{idx}{path.suffix}")
        if not candidate.exists():
            return candidate
    # Placeholder for benchmark logic.
    # In a real implementation, this would involve parsing the artifact, calculating
    # token estimates based on OpenAI's tiktoken or a similar tokenizer,
    # and comparing against the current repository's average token consumption.
    def estimate_tokens(text: str) -> int:
        return len(text) // 4  # Very rough heuristic.

    # ... existing code ...

    def run_research(
        topic: str,
        max_sources: int,
        allow_domains: list[str],
        block_domains: list[str],
        dedupe_host: bool,
        dedupe_url: bool,
        timeout_ms: int,
        retries: int,
        benchmark: bool = False,
    ) -> str:
        # ... inside the loop ...
        # Add token estimation to the artifact
        # ...
        if benchmark:
            report_lines.append("## Benchmarking Analysis")
            token_count = estimate_tokens(text)
            report_lines.append(f"- Estimated tokens for this source: {token_count}")
        # ...

    report_lines = [f"# Research Report: {topic}", ""]
    report_lines.append("## Filters")
    report_lines.append(f"- Max sources: {max_sources}")
    report_lines.append(f"- Allow domains: {', '.join(allow_domains) if allow_domains else 'NONE'}")
    report_lines.append(f"- Block domains: {', '.join(block_domains) if block_domains else 'NONE'}")
    report_lines.append(f"- Dedupe host: {'ON' if dedupe_host else 'OFF'}")
    report_lines.append(f"- Dedupe url: {'ON' if dedupe_url else 'OFF'}")
    report_lines.append("")

    with sync_playwright() as p:
        # Launch browser in headless mode
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print("  [playwright] Navigating to search engine...")
            search_url = f"https://search.yahoo.com/search?p={urllib.parse.quote(topic)}"
            def goto_search():
                page.goto(search_url, timeout=timeout_ms)
                page.wait_for_load_state("domcontentloaded")
            try:
                retry(goto_search, attempts=retries, delay_seconds=1.0)
            except Exception as exc:
                print(f"  [playwright] âŒ Search navigation failed after retries: {exc}")
                return ""

            # Wait for search results container to appear
            try:
                page.wait_for_selector("#web", timeout=10000)
            except Exception:
                pass  # Continue anyway and try to extract links

            # Extract top result links (generic extraction)
            links = []
            link_elements = page.locator("a").all()
            for el in link_elements:
                href = el.get_attribute("href")
                # Filter out internal links and ads
                if href and href.startswith("http") and "yahoo.com" not in href and "bing.com" not in href:
                    if href not in links:
                        links.append(href)
                if len(links) >= max_sources * 5:
                     break

            filtered_links = filter_links(
                links=links,
                allow_domains=allow_domains,
                block_domains=block_domains,
                max_sources=max_sources,
                dedupe_host=dedupe_host,
                dedupe_url=dedupe_url,
            )
            if not filtered_links:
                print("  [playwright] âŒ No search results found after filtering.")
                return ""

            print(f"  [playwright] Found {len(filtered_links)} sources. Reading...")

            for url in filtered_links:
                print(f"    -> {url}")
                report_lines.append(f"## Source: {url}")
                try:
                    # Create a new page per tab to keep state separated and enforce timeouts
                    tab = context.new_page()
                    # 10s max wait to prevent hanging on bad sites
                    def goto_source():
                        tab.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                    retry(goto_source, attempts=retries, delay_seconds=0.5)
                    # Extract raw text from the body, stripping out script tags if possible
                    # A quick evaluate script to get visible text loosely
                    text = tab.evaluate("""() => {
                        const sel = window.getSelection();
                        sel.selectAllChildren(document.body);
                        return sel.toString();
                    }""")

                    if text:
                        # Truncate to save context window (roughly 1500 words / 8000 chars max per site)
                        text = text.strip()[:8000]
                        report_lines.append(text)
                    else:
                        report_lines.append("_No text extracted._")

                    tab.close()
                except Exception as e:
                    print(f"    -> Error loading {url}: {e}")
                    report_lines.append(f"_Failed to fetch: {e}_")

                report_lines.append("\n---\n")

        finally:
            browser.close()

    return "\n".join(report_lines)

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(description="Autonomous DNA Web Researcher")
    parser.add_argument("topic", nargs="+", help="The topic or error message to research")
    parser.add_argument("--max-sources", type=int, default=3, help="Max sources to read after filtering")
    parser.add_argument("--allow-domain", action="append", default=[], help="Allow specific domain (repeatable)")
    parser.add_argument("--block-domain", action="append", default=[], help="Block specific domain (repeatable)")
    parser.add_argument("--no-dedupe-host", action="store_true", help="Disable host-level dedupe")
    parser.add_argument("--no-dedupe-url", action="store_true", help="Disable URL-level dedupe")
    parser.add_argument("--timeout-ms", type=int, default=15000, help="Timeout per page navigation (ms)")
    parser.add_argument("--retries", type=int, default=2, help="Retry count for navigation failures")
    parser.add_argument("--timestamped", action="store_true", help="Append UTC timestamp to artifact filename")
    parser.add_argument("--out-dir", default=str(DEFAULT_ARTIFACT_DIR), help="Output directory for research artifacts")

    args_to_parse = sys.argv[1:]
    if sys.argv and sys.argv[0].endswith("cli.py"):
         args_to_parse = sys.argv[2:]

    args, _ = parser.parse_known_args(args_to_parse)
    topic_str = " ".join(args.topic)

    print("--- ðŸ”­ Autonomous DNA: Web Researcher ---")
    print(f"Topic: {topic_str}")
    print("Searching the web via Playwright...")

    retries = max(1, args.retries)
    report_content = run_research(
        topic=topic_str,
        max_sources=args.max_sources,
        allow_domains=args.allow_domain,
        block_domains=args.block_domain,
        dedupe_host=not args.no_dedupe_host,
        dedupe_url=not args.no_dedupe_url,
        timeout_ms=args.timeout_ms,
        retries=retries,
    )

    if not report_content:
        sys.exit(1)

    timestamped = args.timestamped or os.getenv("AUTODNA_RESEARCH_TIMESTAMPED", "").strip().lower() in {"1", "true", "yes"}
    out_dir = Path(args.out_dir)
    save_path = build_artifact_path(topic_str, out_dir, timestamped)
    save_path = ensure_unique_path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    save_path.write_text(report_content, encoding="utf-8")
    if not validate_artifact(save_path, min_bytes=50):
        print(f"âŒ Research artifact failed integrity check: {save_path}")
        sys.exit(1)
    print(f"âœ… Research complete. Artifact saved to: {save_path}")

    memory_file = Path("agent/MEMORY.md")
    if memory_file.exists():
        mem_content = read_text_fallback(memory_file)
        new_fact = f"- [RESEARCH_AUTO] Scraped via Playwright for '{topic_str}'. See `{save_path}`."
        memory_file.write_text(mem_content + f"\n{new_fact}\n", encoding="utf-8")

if __name__ == "__main__":
    main()
