"""
AFlow Adapter — SKILL.md -> Section Graph

Parses a SKILL.md into a list of sections (nodes) with their content.
Supports multiple header styles used across Hermes skills:
  - ## Part N: Title
  - ### Module X: Title
  - ## SectionName
  - ## Layer N: Title

Graph format:
{
  "skill_path": "...",
  "frontmatter": "---\n...\n---",
  "preamble": "text before first section",
  "node_count": N,
  "nodes": [
    {
      "id": "s0",
      "level": 2,
      "header": "## Part 0: Theory",
      "title": "Part 0: Theory",
      "content": "full section text including header",
      "priority": 0,
      "score": 0.0
    }
  ],
  "edges": []
}
"""
import re
from pathlib import Path


# Match level-2 or level-3 headers (##, ###)
_HEADER_RE = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)


def parse_skill_to_graph(skill_path: Path) -> dict:
    """Parse SKILL.md into a section graph."""
    content = skill_path.read_text(encoding="utf-8")

    # Extract YAML frontmatter
    frontmatter = ""
    body = content
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end > 0:
            frontmatter = content[: end + 4]
            body = content[end + 4:]

    # Find all level-2 and level-3 headers
    headers = list(_HEADER_RE.finditer(body))

    nodes = []
    preamble = body[: headers[0].start()].strip() if headers else body.strip()

    for i, m in enumerate(headers):
        level = len(m.group(1))
        title = m.group(2).strip()

        # Section body = text until next same-or-higher-level header
        start = m.start()
        end = len(body)
        for j in range(i + 1, len(headers)):
            next_level = len(headers[j].group(1))
            if next_level <= level:
                end = headers[j].start()
                break

        section_text = body[start:end].rstrip()

        nodes.append({
            "id": f"s{i}",
            "level": level,
            "header": m.group(0),
            "title": title,
            "content": section_text,
            "priority": i,      # initial order = priority; AFlow updates this
            "score": 0.0,       # AFlow scoring
        })

    # Linear edges (default sequence)
    edges = []
    top_level = [n for n in nodes if n["level"] == 2]
    for k in range(len(top_level) - 1):
        edges.append({
            "from": top_level[k]["id"],
            "to": top_level[k + 1]["id"],
            "weight": 1.0,
            "relation": "sequence",
        })

    return {
        "skill_path": str(skill_path),
        "frontmatter": frontmatter,
        "preamble": preamble,
        "node_count": len(nodes),
        "nodes": nodes,
        "edges": edges,
    }


if __name__ == "__main__":
    import json
    import sys
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("SKILL.md")
    graph = parse_skill_to_graph(path)
    # Print summary
    print(f"Sections: {graph['node_count']}")
    for n in graph["nodes"]:
        indent = "  " if n["level"] == 3 else ""
        print(f"  {indent}[{n['id']}] lv{n['level']} — {n['title'][:60]}")
