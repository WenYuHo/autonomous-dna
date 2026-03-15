import sys
import argparse
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
from pathlib import Path
from ddgs import DDGS

def search_duckduckgo(query: str) -> list[str]:
    """Search DuckDuckGo using ddgs library and return top 3 URLs."""
    urls = []
    try:
        results = DDGS().text(query, max_results=3)
        for r in results:
            if 'href' in r:
                urls.append(r['href'])
    except Exception as e:
        print(f"Search failed: {e}")
    return urls

def fetch_page_text(url: str) -> str:
    """Fetch and extract text from a URL."""
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read()
            soup = BeautifulSoup(html, 'html.parser')
            # Extract basic text
            for script in soup(["script", "style"]):
                script.extract()
            text = soup.get_text(separator=' ', strip=True)
            return text[:2000] # Cap output to save context
    except Exception as e:
        return f"Failed to fetch {url}: {e}"

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        
    parser = argparse.ArgumentParser(description="Autonomous DNA Web Researcher")
    parser.add_argument("topic", nargs="+", help="The topic or error message to research")
    
    args_to_parse = sys.argv[1:]
    if sys.argv and sys.argv[0].endswith("cli.py"):
         args_to_parse = sys.argv[2:]
         
    args, _ = parser.parse_known_args(args_to_parse)
    topic_str = " ".join(args.topic)
    
    print(f"--- 🔭 Autonomous DNA: Web Researcher ---")
    print(f"Topic: {topic_str}")
    print("Searching the web...")
    
    urls = search_duckduckgo(topic_str)
    if not urls:
        print("❌ No results found or search blocked.")
        sys.exit(1)
        
    print(f"Found {len(urls)} sources. Reading...")
    
    report_lines = [f"# Research Report: {topic_str}", ""]
    
    for url in urls:
        print(f"  -> {url}")
        content = fetch_page_text(url)
        report_lines.append(f"## Source: {url}")
        report_lines.append(content)
        report_lines.append("\n---\n")
        
    report_content = "\n".join(report_lines)
    
    filename = "".join(x if x.isalnum() else "_" for x in topic_str[:30]).strip("_").lower()
    save_path = Path(f"agent/skills/auto_generated/{filename}.md")
    save_path.parent.mkdir(parents=True, exist_ok=True)
    
    save_path.write_text(report_content, encoding="utf-8")
    print(f"✅ Research complete. Artifact saved to: {save_path}")
    
    memory_file = Path("agent/MEMORY.md")
    if memory_file.exists():
        mem_content = memory_file.read_text(encoding="utf-8")
        new_fact = f"- [RESEARCH_AUTO] Scraped {len(urls)} sources for '{topic_str}'. See `{save_path}`."
        memory_file.write_text(mem_content + f"\n{new_fact}\n", encoding="utf-8")
