"""
AFlow Adapter — Section Graph -> SKILL.md

Converts a section graph (with updated priorities) back into SKILL.md.
Reorders top-level sections (## headers) by their `priority` field.
Sub-sections (### headers) move with their parent section.

Usage:
  from aflow_adapter.render_skill import render_graph_to_skill
  output = render_graph_to_skill(graph, output_path)
"""
import json
from pathlib import Path


def render_graph_to_skill(graph: dict, output_path: Path) -> Path:
    """
    Render section graph back to SKILL.md, reordering top-level sections
    by their `priority` field (lowest priority value = first).

    Sub-sections (level==3) are NOT independently reordered — they move
    with their parent level-2 section.
    """
    frontmatter = graph.get("frontmatter", "")
    preamble = graph.get("preamble", "")
    nodes = graph.get("nodes", [])

    if not nodes:
        # Nothing to reorder — reconstruct from parts
        parts = []
        if frontmatter:
            parts.append(frontmatter)
        if preamble:
            parts.append(preamble)
        output_path.write_text("\n\n".join(parts), encoding="utf-8")
        return output_path

    # Separate top-level (##) and sub-level (###) nodes
    top_nodes = [n for n in nodes if n["level"] == 2]
    sub_nodes = {n["id"]: n for n in nodes if n["level"] == 3}

    # Build map: top-level section id -> its sub-sections (in original order)
    # Sub-sections belong to the most-recently-seen top-level node
    top_ids_in_order = [n["id"] for n in nodes if n["level"] == 2]
    children: dict[str, list[dict]] = {tid: [] for tid in top_ids_in_order}

    current_top = None
    for n in nodes:
        if n["level"] == 2:
            current_top = n["id"]
        elif n["level"] == 3 and current_top is not None:
            children[current_top].append(n)

    # Sort top-level sections by priority
    sorted_tops = sorted(top_nodes, key=lambda n: n.get("priority", 999))

    # Reconstruct SKILL.md text
    parts = []

    if frontmatter:
        parts.append(frontmatter.rstrip())

    if preamble:
        parts.append(preamble.rstrip())

    for top in sorted_tops:
        # Add top-level section
        parts.append(top["content"].rstrip())
        # Sub-sections are already embedded in top["content"], so no need
        # to add them separately — they come along for the ride.

    text = "\n\n".join(parts) + "\n"
    output_path.write_text(text, encoding="utf-8")
    return output_path


def reorder_by_scores(graph: dict) -> dict:
    """
    Update node priorities based on their scores (higher score = earlier).
    Returns the graph with updated priorities.
    """
    top_nodes = [n for n in graph["nodes"] if n["level"] == 2]
    # Sort descending by score
    scored = sorted(top_nodes, key=lambda n: n.get("score", 0.0), reverse=True)
    score_to_priority = {n["id"]: i for i, n in enumerate(scored)}

    for n in graph["nodes"]:
        if n["level"] == 2:
            n["priority"] = score_to_priority.get(n["id"], n["priority"])

    return graph


if __name__ == "__main__":
    import sys
    graph = json.loads(Path(sys.argv[1]).read_text())
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("SKILL_optimized.md")
    render_graph_to_skill(graph, output)
    print(f"Rendered to {output}")
