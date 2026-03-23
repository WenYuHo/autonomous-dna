import sys
import argparse
import urllib.parse
import time
import os
import subprocess
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from autodna.tools.io_utils import read_text_fallback

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "utm_reader", "utm_viz_id", "utm_pubreferrer",
    "utm_swu", "gclid", "fbclid", "mc_cid", "mc_eid", "ref", "source", "spm",
}

DEFAULT_ARTIFACT_DIR = Path("agent/skills/auto_generated")

class AgentBrowserSession:
    def __init__(self, session_name="autodna-research", timeout=30):
        self.session_name = session_name
        self.timeout = timeout

    def run(self, command: list[str], json_output=True) -> str | dict:
        cmd = ["agent-browser", "--session", self.session_name]
        if json_output:
            cmd.append("--json")
        cmd.extend(command)
        
        # Use Popen with process group for reliable timeout on Windows
        kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        
        proc = subprocess.Popen(cmd, **kwargs)
        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            # Kill the entire process tree on Windows
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
            else:
                proc.kill()
            proc.wait()
            raise RuntimeError(f"agent-browser timed out after {self.timeout}s on: {' '.join(command)}")
        
        stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
        
        if proc.returncode != 0:
            if "not recognized" in stderr or "not found" in stderr:
                 raise RuntimeError("agent-browser CLI not found.")
            raise RuntimeError(f"agent-browser failed: {stderr or stdout}")
        if json_output:
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                return stdout
        return stdout



def normalize_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception:
        return url
    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."): netloc = netloc[4:]
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
    if host.startswith("www."): host = host[4:]
    return host

def domain_matches(host: str, domain: str) -> bool:
    return host == domain.lower() or host.endswith(f".{domain.lower()}")

def filter_links(links: list[str], allow_domains: list[str], block_domains: list[str], max_sources: int, dedupe_host: bool, dedupe_url: bool) -> list[str]:
    filtered = []
    seen_hosts = set()
    seen_urls = set()
    for url in links:
        if not isinstance(url, str): continue
        host = domain_from_url(url)
        if not host: continue
        if allow_domains and not any(domain_matches(host, d) for d in allow_domains): continue
        if block_domains and any(domain_matches(host, d) for d in block_domains): continue
        normalized = normalize_url(url) if dedupe_url else url
        if dedupe_url and normalized in seen_urls: continue
        if dedupe_host and host in seen_hosts: continue
        filtered.append(normalized)
        seen_urls.add(normalized)
        seen_hosts.add(host)
        if len(filtered) >= max_sources: break
    return filtered

def validate_artifact(path: Path, min_bytes: int = 1) -> bool:
    return path.exists() and path.stat().st_size >= min_bytes

def slugify_topic(topic: str, max_len: int = 40) -> str:
    stop_words = {"how", "to", "what", "is", "a", "an", "the", "research", "patterns", "vs", "versus"}
    words = [w for w in topic.lower().split() if w not in stop_words]
    if not words: words = topic.lower().split()
    slug = "_".join(words)[:max_len].strip("_")
    slug = "".join(ch if ch.isalnum() or ch == "_" else "" for ch in slug)
    return re.sub(r"_+", "_", slug) or "research"

def build_artifact_path(topic_str: str, out_dir: Path, timestamped: bool, now: datetime | None = None) -> Path:
    slug = slugify_topic(topic_str)
    current_time = now or datetime.now(timezone.utc)
    if timestamped:
        ts = current_time.strftime("%Y%m%dT%H%M%S%f")[:-3] + "Z"
        filename = f"{slug}_{ts}.md"
    else:
        filename = f"{slug}.md"
    return out_dir / filename

def ensure_unique_path(path: Path, max_tries: int = 1000) -> Path:
    if not path.exists(): return path
    for idx in range(1, max_tries + 1):
        c = path.with_name(f"{path.stem}_{idx}{path.suffix}")
        if not c.exists(): return c
    return path

def extract_links_from_page(session, exclude_patterns=None):
    if exclude_patterns is None: exclude_patterns = []
    try:
        links_data = session.run(["find", "role", "link", "get", "attr", "href"])
        links = []
        if isinstance(links_data, list):
            for href in links_data:
                if isinstance(href, str) and href.startswith("http") and not any(x in href for x in exclude_patterns):
                    links.append(href)
        return links
    except Exception:
        return []

def run_research(topic: str, max_sources: int, allow_domains: list[str], block_domains: list[str], dedupe_host: bool, dedupe_url: bool, timeout_ms: int, retries: int, session_name: str = "autodna-research", engine: str = "google", depth: int = 1, benchmark: bool = False) -> str:
    report_lines = [f"# Research Report: {topic}", ""]
    session = AgentBrowserSession(session_name)
    exclude = ["google.com/search", "google.com/preferences", "bing.com/search", "perplexity.ai/search", "google.com/url"]

    try:
        print(f"  [agent-browser] Level 0: Searching {engine} for '{topic}'...")
        if engine == "perplexity":
            url = f"https://www.perplexity.ai/search?q={urllib.parse.quote(topic)}"
        else:
            url = f"https://www.google.com/search?q={urllib.parse.quote(topic)}"
        
        session.run(["open", url])
        session.run(["wait", "--load", "networkidle"])
        
        # Bot-detection heuristic: check page snapshot for CAPTCHA indicators
        try:
            snapshot = session.run(["snapshot", "-i"], json_output=False)
            snapshot_str = str(snapshot).lower() if snapshot else ""
            bot_indicators = ["captcha", "unusual traffic", "not a robot", "security challenge", "cloudflare", "verify you are human"]
            if any(indicator in snapshot_str for indicator in bot_indicators):
                print(f"  [agent-browser] ⚠️ Bot detection triggered on {engine}. Signaling fallback.")
                return "FALLBACK_REQUIRED"
        except Exception:
            pass  # Snapshot failed, continue with link extraction
        
        links = extract_links_from_page(session, exclude)
        filtered = filter_links(links, allow_domains, block_domains, max_sources, dedupe_host, dedupe_url)
        
        if not filtered:
            print(f"  [agent-browser] No results on {engine}. Signaling fallback.")
            return "FALLBACK_REQUIRED"

        all_sources = list(filtered)
        visited = set()
        current_depth = 1
        
        while current_depth <= depth and all_sources:
            next_level = []
            for url in list(all_sources):
                if url in visited: continue
                visited.add(url)
                print(f"    -> {url}")
                report_lines.append(f"## Source: {url}")
                try:
                    session.run(["open", url])
                    session.run(["wait", "--load", "networkidle"])
                    text = session.run(["get", "text"], json_output=False)
                    if text: report_lines.append(str(text).strip()[:8000])
                    if current_depth < depth:
                        next_level.extend(extract_links_from_page(session, exclude)[:3])
                except Exception as e:
                    report_lines.append(f"_Failed: {e}_")
                report_lines.append("\n---\n")
                if len(visited) >= max_sources: break
            all_sources = next_level
            current_depth += 1
            if len(visited) >= max_sources: break

    except Exception as exc:
        print(f"  [agent-browser] ðŸ˜« Research failed: {exc}")
        print("  [Fallback] Attempting high-reliability search via google_web_search...")
        return "FALLBACK_REQUIRED"
    finally:
        try: session.run(["close"]) 
        except: pass

    return "\n".join(report_lines)

def main():
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument("topic", nargs="+")
    parser.add_argument("--max-sources", type=int, default=3)
    parser.add_argument("--depth", type=int, default=1)
    parser.add_argument("--allow-domain", action="append", default=[])
    parser.add_argument("--block-domain", action="append", default=[])
    parser.add_argument("--no-dedupe-host", action="store_true")
    parser.add_argument("--no-dedupe-url", action="store_true")
    parser.add_argument("--timeout-ms", type=int, default=15000)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--timestamped", action="store_true")
    parser.add_argument("--out-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--session", default="autodna-research")
    parser.add_argument("--engine", choices=["google", "perplexity"], default="google")

    args, _ = parser.parse_known_args()
    topic = " ".join(args.topic)
    
    print(f"--- ðŸ”­ Autonomous DNA: Web Researcher ---")
    res = run_research(topic, args.max_sources, args.allow_domain, args.block_domain, not args.no_dedupe_host, not args.no_dedupe_url, args.timeout_ms, max(1, args.retries), args.session, args.engine, args.depth, args.benchmark)
    
    if res == "FALLBACK_REQUIRED":
        print("SIGNAL: FALLBACK_REQUIRED") # Signal to epoch.py or caller
        sys.exit(1)
    
    if not res: sys.exit(1)
    
    # Save logic...
    out_dir = Path(args.out_dir)
    save_path = build_artifact_path(topic, out_dir, args.timestamped)
    save_path = ensure_unique_path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_text(res, encoding="utf-8")
    print(f"âœ… Saved to: {save_path}")

if __name__ == "__main__":
    main()
