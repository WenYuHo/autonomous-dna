import sys
import argparse
import urllib.parse
from pathlib import Path
from playwright.sync_api import sync_playwright

def run_research(topic: str) -> str:
    """Uses Playwright to search DuckDuckGo Lite, click top 3 results, and extract text."""
    report_lines = [f"# Research Report: {topic}", ""]
    
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
            page.goto(search_url, timeout=15000)
            page.wait_for_load_state("domcontentloaded")
            
            # Wait for search results container to appear
            try:
                page.wait_for_selector("#web", timeout=10000)
            except Exception:
                pass # Continue anyway and try to extract links
            
            # Extract top 3 result links (generic extraction)
            links = []
            link_elements = page.locator("a").all()
            for el in link_elements:
                href = el.get_attribute("href")
                # Filter out internal links and ads
                if href and href.startswith("http") and "yahoo.com" not in href and "bing.com" not in href:
                    if href not in links:
                        links.append(href)
                if len(links) >= 3:
                     break
                    
            if not links:
                print("  [playwright] ❌ No search results found.")
                return ""
                    
            print(f"  [playwright] Found {len(links)} sources. Reading...")
            
            for url in links:
                print(f"    -> {url}")
                report_lines.append(f"## Source: {url}")
                try:
                    # Create a new page per tab to keep state separated and enforce timeouts
                    tab = context.new_page()
                    # 10s max wait to prevent hanging on bad sites
                    tab.goto(url, timeout=10000, wait_until="domcontentloaded")
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
    
    args_to_parse = sys.argv[1:]
    if sys.argv and sys.argv[0].endswith("cli.py"):
         args_to_parse = sys.argv[2:]
         
    args, _ = parser.parse_known_args(args_to_parse)
    topic_str = " ".join(args.topic)
    
    print(f"--- 🔭 Autonomous DNA: Web Researcher ---")
    print(f"Topic: {topic_str}")
    print("Searching the web via Playwright...")
    
    report_content = run_research(topic_str)
    
    if not report_content:
        sys.exit(1)
    
    filename = "".join(x if x.isalnum() else "_" for x in topic_str[:30]).strip("_").lower()
    save_path = Path(f"agent/skills/auto_generated/{filename}.md")
    save_path.parent.mkdir(parents=True, exist_ok=True)
    
    save_path.write_text(report_content, encoding="utf-8")
    print(f"✅ Research complete. Artifact saved to: {save_path}")
    
    memory_file = Path("agent/MEMORY.md")
    if memory_file.exists():
        mem_content = memory_file.read_text(encoding="utf-8")
        new_fact = f"- [RESEARCH_AUTO] Scraped via Playwright for '{topic_str}'. See `{save_path}`."
        memory_file.write_text(mem_content + f"\n{new_fact}\n", encoding="utf-8")
        
if __name__ == "__main__":
    main()
