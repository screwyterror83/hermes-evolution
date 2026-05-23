"""
AFlow Adapter — Phase 3: Module Graph → SKILL.md

Converts an AFlow-optimized module graph back into SKILL.md format,
reordering modules according to optimized priority/weights while
preserving all original content and YAML frontmatter.
"""
import json
from pathlib import Path


def render_graph_to_skill(graph: dict, original_skill_path: Path, output_path: Path) -> Path:
    """
    Render optimized graph back to SKILL.md.
    Phase 3 stub — reorders module sections by priority.
    """
    original = original_skill_path.read_text(encoding="utf-8")

    # Extract frontmatter
    frontmatter = ""
    body = original
    if original.startswith("---"):
        end = original.find("---", 3)
        if end > 0:
            frontmatter = original[:end + 3]
            body = original[end + 3:]

    # Sort nodes by optimized priority (AFlow sets this)
    sorted_nodes = sorted(graph.get("nodes", []), key=lambda n: n.get("priority", 999))

    # For Phase 3: actually re-slice and reorder the SKILL.md sections
    # For now: write a stub that preserves original order (noop)
    # TODO: implement full section reordering once AFlow integration is live

    output_path.write_text(original, encoding="utf-8")
    return output_path


if __name__ == "__main__":
    import sys
    graph = json.loads(Path(sys.argv[1]).read_text())
    original = Path(sys.argv[2])
    output = Path(sys.argv[3]) if len(sys.argv) > 3 else original.parent / "SKILL_optimized.md"
    render_graph_to_skill(graph, original, output)
    print(f"Rendered to {output}")
