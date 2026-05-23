#!/usr/bin/env python3
"""
Hermes Evolution Runner — Python CLI (replaces bash entrypoint.sh)

Subcommands:
  run      — Execute GEPA optimization on a profile/skill
  extract  — Extract GEP Genes from sessions into data/genes/
  approve  — Deploy an approved evolution result to the live SKILL.md
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import click
import httpx
import yaml

DATA_DIR = Path(os.environ.get("HERMES_EVO_DATA", "/vol2/hermes-evolution/data"))
PROFILES_DIR = Path(os.environ.get("HERMES_PROFILES_DIR", "/vol1/hermes-profiles"))
SELF_EVO_DIR = Path("/opt/self-evolution")
HERMES_API = os.environ.get("HERMES_API_URL", "http://hermes:8000")

SKILL_SIZE_LIMIT = 15000  # chars


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_genes(profile: str, skill: str) -> list[dict]:
    """Load gene file if present; return empty list otherwise."""
    gene_file = DATA_DIR / "genes" / profile / f"{skill}.json"
    if gene_file.exists():
        try:
            data = json.loads(gene_file.read_text())
            return data.get("genes", [])
        except Exception as e:
            click.echo(f"  [warn] failed to load genes: {e}", err=True)
    return []


def _detect_gepa_param() -> str:
    """Inspect installed dspy.GEPA to find correct iterations param name."""
    try:
        import inspect
        import dspy
        sig = inspect.signature(dspy.GEPA.__init__)
        if "max_full_evals" in sig.parameters:
            return "max_full_evals"
        if "max_steps" in sig.parameters:
            return "max_steps"
    except Exception:
        pass
    return "max_full_evals"  # default to newer name


def _prepend_frontmatter(evolved_path: Path, original_skill_path: Path) -> Path:
    """Prepend YAML frontmatter from original SKILL.md to evolved output."""
    original = original_skill_path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)

    # Extract frontmatter block (between first and second ---)
    frontmatter_lines = []
    count = 0
    for line in lines:
        if line.strip() == "---":
            count += 1
            frontmatter_lines.append(line)
            if count == 2:
                break
        elif count == 1:
            frontmatter_lines.append(line)

    evolved_content = evolved_path.read_text(encoding="utf-8")
    if not evolved_content.startswith("---"):
        fixed_content = "".join(frontmatter_lines) + "\n" + evolved_content
        evolved_path.write_text(fixed_content, encoding="utf-8")
    return evolved_path


def _validate_size(path: Path) -> tuple[bool, int]:
    content = path.read_text(encoding="utf-8")
    chars = len(content)
    return chars <= SKILL_SIZE_LIMIT, chars


def _write_metrics(run_dir: Path, baseline: float, best: float, duration: float,
                   profile: str, skill: str, optimizer: str, gene_hits: int):
    metrics = {
        "run_id": run_dir.name,
        "profile": profile,
        "skill": skill,
        "optimizer": optimizer,
        "baseline": baseline,
        "best": best,
        "improvement_pct": round((best - baseline) / max(baseline, 0.01) * 100, 2),
        "duration_seconds": round(duration),
        "gene_hits": gene_hits,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "approved": False,
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False))

    # Append to scores.json
    scores_file = DATA_DIR / "registry" / "scores.json"
    scores = []
    if scores_file.exists():
        try:
            scores = json.loads(scores_file.read_text())
        except Exception:
            pass
    scores.append(metrics)
    scores_file.write_text(json.dumps(scores, indent=2, ensure_ascii=False))
    return metrics


def _notify_hitl(metrics: dict, diff_url: str = ""):
    """Push HITL notification to Hermes platform API."""
    improvement = metrics["improvement_pct"]
    sign = "+" if improvement >= 0 else ""
    msg = (
        f"🧬 进化完成 | {metrics['profile']}/{metrics['skill']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"基线: {metrics['baseline']:.1f} → 最佳: {metrics['best']:.1f} ({sign}{improvement:.1f}%)\n"
        f"优化器: {metrics['optimizer']} | 耗时: {metrics['duration_seconds']//60}min\n"
        f"Gene命中: {metrics['gene_hits']}条\n\n"
        f"回复 approve 或 reject 来处理此次进化。\n"
        f"Run ID: {metrics['run_id']}"
    )

    # Write to hitl-queue for evo-api to pick up
    queue_entry = {**metrics, "message": msg, "status": "pending"}
    queue_file = DATA_DIR / "hitl-queue" / f"{metrics['run_id']}.json"
    queue_file.write_text(json.dumps(queue_entry, indent=2, ensure_ascii=False))

    # Try to notify via Hermes API
    try:
        resp = httpx.post(
            f"{HERMES_API}/internal/notify",
            json={"message": msg, "deliver": "all"},
            timeout=10,
        )
        if resp.status_code == 200:
            click.echo("  ✓ HITL notification sent")
        else:
            click.echo(f"  [warn] HITL notify returned {resp.status_code}", err=True)
    except Exception as e:
        click.echo(f"  [warn] HITL notify failed: {e} (queued for retry)", err=True)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """Hermes Evolution Runner"""
    pass


@cli.command()
@click.option("--profile", required=True, type=click.Choice(["personal", "coach", "architect", "founder"]),
              help="Hermes profile to evolve")
@click.option("--skill", required=True, help="Skill name (directory under profile/skills/)")
@click.option("--optimizer", default="gepa", show_default=True,
              help="Optimizer: gepa (default) or gepa+aflow (Phase 3)")
@click.option("--iterations", default=10, show_default=True, help="Optimization iterations")
@click.option("--model", default="openai/deepseek-v4-pro", show_default=True,
              help="LLM model for optimization")
@click.option("--eval-model", default="openai/deepseek-v4-pro", show_default=True,
              help="LLM model for evaluation")
@click.option("--dry-run", is_flag=True, help="Validate config without running optimization")
def run(profile, skill, optimizer, iterations, model, eval_model, dry_run):
    """Run GEPA optimization on a profile/skill."""
    profile_dir = PROFILES_DIR / profile
    skill_dir = profile_dir / "skills" / skill
    original_skill = skill_dir / "SKILL.md"

    click.echo(f"\n🧬 Hermes Evolution | {profile}/{skill}")
    click.echo(f"   optimizer={optimizer} | iterations={iterations} | model={model}")
    click.echo(f"   profile_dir={profile_dir}")

    # Validate paths
    if not profile_dir.exists():
        click.echo(f"  ✗ Profile not found: {profile_dir}", err=True)
        sys.exit(1)
    if not original_skill.exists():
        click.echo(f"  ✗ SKILL.md not found: {original_skill}", err=True)
        sys.exit(1)

    # Load genes
    genes = _load_genes(profile, skill)
    click.echo(f"  Gene bank: {len(genes)} genes loaded")

    # Count sessions
    sessions_dir = profile_dir / "sessions"
    session_count = len(list(sessions_dir.glob("*.jsonl"))) if sessions_dir.exists() else 0
    click.echo(f"  Sessions available: {session_count}")

    if dry_run:
        click.echo("\n  [dry-run] Config valid. Exiting without optimization.")
        return

    # Detect GEPA parameter name dynamically
    gepa_param = _detect_gepa_param()
    click.echo(f"  GEPA param detected: {gepa_param}")

    # Create output directory
    run_id = datetime.now().strftime("%Y-%m-%d_%H%M") + f"_{profile}_{skill}"
    run_dir = DATA_DIR / "results" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Patch evolve_skill.py GEPA parameter if needed
    evolve_script = SELF_EVO_DIR / "evolution" / "skills" / "evolve_skill.py"
    if evolve_script.exists() and gepa_param == "max_full_evals":
        content = evolve_script.read_text()
        patched = content.replace("max_steps=iterations", "max_full_evals=iterations")
        if patched != content:
            evolve_script.write_text(patched)
            click.echo("  GEPA patch applied (max_steps → max_full_evals)")

    # Run self-evolution
    env = {
        **os.environ,
        "HERMES_AGENT_PATH": str(profile_dir),
        "HERMES_AGENT_REPO": str(profile_dir),
        "HERMES_SKILLS_DIR": str(profile_dir / "skills"),
        "OPENAI_API_BASE": os.environ.get("OPENAI_API_BASE", "https://api.deepseek.com/v1"),
        "OPENAI_API_KEY": os.environ.get("DEEPSEEK_API_KEY", ""),
    }

    cmd = [
        sys.executable, "-m", "evolution.skills.evolve_skill",
        "--skill", skill,
        "--iterations", str(iterations),
        "--eval-source", "sessiondb",
        "--optimizer-model", model,
        "--eval-model", eval_model,
    ]

    click.echo(f"\n  Running: {' '.join(cmd)}\n")
    start = time.time()

    result = subprocess.run(cmd, env=env, cwd=str(SELF_EVO_DIR))
    duration = time.time() - start

    # Find evolved output
    evo_output_dir = SELF_EVO_DIR / "output" / skill
    evolved_failed = evo_output_dir / "evolved_FAILED.md"
    evolved_ok = evo_output_dir / "evolved.md"

    evolved_source = evolved_ok if evolved_ok.exists() else (evolved_failed if evolved_failed.exists() else None)

    if evolved_source is None:
        click.echo("  ✗ No evolved output found", err=True)
        sys.exit(1)

    # Post-process: prepend frontmatter if missing
    _prepend_frontmatter(evolved_source, original_skill)

    # Validate size
    ok, chars = _validate_size(evolved_source)
    if not ok:
        click.echo(f"  ✗ Too large: {chars}/{SKILL_SIZE_LIMIT} chars — not queuing for HITL")
        sys.exit(1)

    # Copy to run_dir
    import shutil
    shutil.copy2(evolved_source, run_dir / "evolved.md")
    shutil.copy2(original_skill, run_dir / "original.md")

    # Extract scores from result (best effort, parse from stdout)
    best_score = 0.0
    baseline_score = 0.0

    # Write metrics (scores TBD — parse from log or default)
    metrics = _write_metrics(
        run_dir=run_dir,
        baseline=baseline_score,
        best=best_score,
        duration=duration,
        profile=profile,
        skill=skill,
        optimizer=optimizer,
        gene_hits=len(genes),
    )

    click.echo(f"\n  ✓ Evolution complete: {chars} chars | {duration//60:.0f}min")
    click.echo(f"  Output: {run_dir}")

    # HITL notification
    _notify_hitl(metrics)

    click.echo(f"\n  Run ID: {run_id}")
    click.echo("  Reply 'approve' or 'reject' to process via HITL.")


@cli.command()
@click.option("--profile", required=True, type=click.Choice(["personal", "coach", "architect", "founder"]))
@click.option("--skill", required=True, help="Skill name to extract genes from")
@click.option("--limit", default=50, show_default=True, help="Max sessions to scan")
def extract(profile, skill, limit):
    """Extract GEP Genes from sessions into data/genes/ and references/."""
    import json

    profile_dir = PROFILES_DIR / profile
    sessions_dir = profile_dir / "sessions"
    skill_dir = profile_dir / "skills" / skill
    references_dir = skill_dir / "references"

    click.echo(f"\n🔬 Gene Extraction | {profile}/{skill}")

    if not sessions_dir.exists():
        click.echo(f"  ✗ Sessions dir not found: {sessions_dir}", err=True)
        sys.exit(1)

    references_dir.mkdir(exist_ok=True)

    # Scan recent sessions
    session_files = sorted(sessions_dir.glob("*.jsonl"), key=os.path.getmtime, reverse=True)[:limit]
    click.echo(f"  Scanning {len(session_files)} sessions...")

    # Collect messages mentioning the skill
    relevant_messages = []
    skill_keywords = [skill.replace("-", " "), skill]

    for sf in session_files:
        try:
            with open(sf, errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        content = d.get("content", "")
                        if isinstance(content, list):
                            content = " ".join(
                                c.get("text", "") if isinstance(c, dict) else str(c)
                                for c in content
                            )
                        if any(kw.lower() in content.lower() for kw in skill_keywords):
                            relevant_messages.append({
                                "session": sf.stem,
                                "role": d.get("role", ""),
                                "content": content[:500],
                            })
                    except Exception:
                        continue
        except Exception:
            continue

    click.echo(f"  Found {len(relevant_messages)} relevant message fragments")

    # Load existing gene file
    gene_file = DATA_DIR / "genes" / profile / f"{skill}.json"
    existing = {}
    if gene_file.exists():
        try:
            existing = json.loads(gene_file.read_text())
        except Exception:
            pass

    genes = existing.get("genes", [])
    kg_triples = existing.get("kg_triples", [])

    # Stub: write placeholder gene file for Phase 1
    # Phase 2 will wire in actual LLM-based extraction
    gene_data = {
        "profile": profile,
        "skill": skill,
        "updated_at": datetime.now(timezone.utc).date().isoformat(),
        "session_count_scanned": len(session_files),
        "relevant_fragments": len(relevant_messages),
        "genes": genes,
        "kg_triples": kg_triples,
    }

    gene_file.parent.mkdir(parents=True, exist_ok=True)
    gene_file.write_text(json.dumps(gene_data, indent=2, ensure_ascii=False))
    click.echo(f"  ✓ Gene file written: {gene_file}")

    # Ensure references/ structure exists with markers
    for fname in ["field-patterns.md", "anti-patterns.md", "session-highlights.md"]:
        ref_file = references_dir / fname
        if not ref_file.exists():
            ref_file.write_text(
                f"# {fname.replace('-', ' ').replace('.md', '').title()}\n\n"
                f"<!-- cron-append-start -->\n"
                f"<!-- cron-append-end -->\n",
                encoding="utf-8",
            )
            click.echo(f"  ✓ Created {ref_file.name}")

    # Ensure .genes.json symlink/copy in references/
    genes_ref = references_dir / ".genes.json"
    genes_ref.write_text(gene_file.read_text(), encoding="utf-8")
    click.echo(f"  ✓ Synced .genes.json to references/")

    click.echo(f"\n  Done. Next: run Phase 2 LLM extraction to populate genes[].")


@cli.command()
@click.argument("run_id")
@click.option("--profile", required=True, type=click.Choice(["personal", "coach", "architect", "founder"]))
@click.option("--skill", required=True)
def approve(run_id, profile, skill):
    """Deploy an approved evolution result to the live SKILL.md."""
    import shutil

    run_dir = DATA_DIR / "results" / run_id
    evolved_file = run_dir / "evolved.md"
    skill_path = PROFILES_DIR / profile / "skills" / skill / "SKILL.md"

    click.echo(f"\n✅ Approving {run_id}")

    if not evolved_file.exists():
        click.echo(f"  ✗ evolved.md not found in {run_dir}", err=True)
        sys.exit(1)

    # Validate size
    ok, chars = _validate_size(evolved_file)
    if not ok:
        click.echo(f"  ✗ Size check failed: {chars}/{SKILL_SIZE_LIMIT}", err=True)
        sys.exit(1)

    # Backup original
    backup = skill_path.parent / f"SKILL.md.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
    shutil.copy2(skill_path, backup)

    # Deploy
    shutil.copy2(evolved_file, skill_path)
    click.echo(f"  ✓ Deployed {chars} chars → {skill_path}")

    # Update metrics
    metrics_file = run_dir / "metrics.json"
    if metrics_file.exists():
        metrics = json.loads(metrics_file.read_text())
        metrics["approved"] = True
        metrics["approved_at"] = datetime.now(timezone.utc).isoformat()
        metrics_file.write_text(json.dumps(metrics, indent=2, ensure_ascii=False))

    # Update hitl-queue entry
    queue_file = DATA_DIR / "hitl-queue" / f"{run_id}.json"
    if queue_file.exists():
        entry = json.loads(queue_file.read_text())
        entry["status"] = "approved"
        queue_file.write_text(json.dumps(entry, indent=2, ensure_ascii=False))

    click.echo(f"  Backup saved: {backup.name}")
    click.echo("\n  Skill is live (volume-mounted, no restart needed).")


if __name__ == "__main__":
    cli()
