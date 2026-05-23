"""
AFlow Adapter — Phase 3: SKILL.md → Module Graph

Parses SKILL.md Modules (A-N/P) into a JSON graph suitable for
EvoAgentX AFlow structural optimization.

Graph format:
{
  "nodes": [
    {"id": "A", "label": "Module A: ...", "content": "...", "priority": 1}
  ],
  "edges": [
    {"from": "A", "to": "B", "weight": 1.0, "relation": "calls"}
  ]
}
"""
import re
from pathlib import Path


def parse_skill_to_graph(skill_path: Path) -> dict:
    """Parse SKILL.md into a module graph. Phase 3 stub."""
    content = skill_path.read_text(encoding="utf-8")

    # Extract module sections — pattern: ## Module X: Title or ### Module X
    module_pattern = re.compile(
        r"^#{2,3}\s+(?:Module\s+)?([A-P])[:\s]+(.+?)$",
        re.MULTILINE
    )

    nodes = []
    edges = []
    prev_id = None

    for match in module_pattern.finditer(content):
        mod_id = match.group(1)
        mod_label = match.group(2).strip()

        # Extract module content (text until next module header)
        start = match.end()
        next_match = module_pattern.search(content, start)
        end = next_match.start() if next_match else len(content)
        mod_content = content[start:end].strip()[:500]  # truncate for graph

        nodes.append({
            "id": mod_id,
            "label": f"Module {mod_id}: {mod_label}",
            "content": mod_content,
            "priority": len(nodes) + 1,  # initial order = priority
        })

        # Default linear edge from previous module
        if prev_id is not None:
            edges.append({
                "from": prev_id,
                "to": mod_id,
                "weight": 1.0,
                "relation": "sequence",
            })
        prev_id = mod_id

    return {
        "skill_path": str(skill_path),
        "node_count": len(nodes),
        "nodes": nodes,
        "edges": edges,
    }


if __name__ == "__main__":
    import json
    import sys
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("SKILL.md")
    graph = parse_skill_to_graph(path)
    print(json.dumps(graph, indent=2, ensure_ascii=False))
