import re
from pathlib import Path

def read_memory_sections(path: Path) -> dict[str, list[str]]:
    """Parses Categorized MEMORY.md into a dictionary of sections."""
    if not path.exists():
        return {}
    
    content = path.read_text(encoding="utf-8")
    sections = {}
    current_section = "System Facts"
    sections[current_section] = []
    
    for line in content.splitlines():
        if line.startswith("## "):
            current_section = line.replace("## ", "").strip()
            sections[current_section] = []
        elif line.strip().startswith("- "):
            sections[current_section].append(line.strip())
            
    return sections

def write_memory_sections(sections: dict[str, list[str]], path: Path):
    """Writes categorized memory dictionary back to MEMORY.md."""
    lines = ["# PROJECT MEMORY", "# Hard limit: 150 lines. Facts only - no instructions.", "# Format: - [YYYY-MM-DD] fact", ""]
    
    # Order sections logically
    order = ["Repo Organization", "Known Issues & Fixes", "Research", "Execution History", "System Facts"]
    
    for section in order:
        if section in sections:
            lines.append(f"## {section}")
            lines.extend(sections[section])
            lines.append("")
            
    # Add any extra sections found
    for section, facts in sections.items():
        if section not in order:
            lines.append(f"## {section}")
            lines.extend(facts)
            lines.append("")
            
    path.write_text("\n".join(lines), encoding="utf-8")

def append_to_section(section_name: str, fact: str, path: Path):
    """Adds a fact to a specific section, handling deduplication."""
    sections = read_memory_sections(path)
    if section_name not in sections:
        sections[section_name] = []
        
    # Standardize fact format if it doesn't have a date
    if not re.match(r"- \[\d{4}-\d{2}-\d{2}\]", fact):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        fact = f"- [{now}] {fact.strip('- ')}"
    
    if fact not in sections[section_name]:
        sections[section_name].append(fact)
        write_memory_sections(sections, path)

def migrate_flat_memory(path: Path):
    """One-time migration of flat MEMORY.md to categorized sections."""
    if not path.exists():
        return
    
    content = path.read_text(encoding="utf-8")
    if "## " in content:
        # Already categorized
        return
        
    facts = re.findall(r"^- .*", content, re.MULTILINE)
    sections = {
        "Repo Organization": [],
        "Known Issues & Fixes": [],
        "Research": [],
        "Execution History": [],
        "System Facts": []
    }
    
    for fact in facts:
        l_fact = fact.lower()
        if any(kw in l_fact for kw in ["repo", "worktree", "lab", "source", "target", "path"]):
            sections["Repo Organization"].append(fact)
        elif any(kw in l_fact for kw in ["error", "fail", "permission", "blocked", "issue"]):
            sections["Known Issues & Fixes"].append(fact)
        elif any(kw in l_fact for kw in ["research", "sota", "found", "study"]):
            sections["Research"].append(fact)
        elif "[outcome]" in l_fact:
            sections["Execution History"].append(fact)
        else:
            sections["System Facts"].append(fact)
            
    write_memory_sections(sections, path)
