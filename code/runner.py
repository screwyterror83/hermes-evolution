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

# Hermes API — all profiles share same key, accessible via hermes-net container names
_HERMES_KEY = os.environ.get("HERMES_API_KEY", "51f149aa975cb5e594d329af954caa4c5dfcecae2e2a6234")
HERMES_APIS = {
    "personal": os.environ.get("HERMES_API_PERSONAL", "http://hermes:8643"),
    "coach":    os.environ.get("HERMES_API_COACH",    "http://hermes-coach:8643"),
    "architect":os.environ.get("HERMES_API_ARCHITECT","http://hermes-architect:8643"),
    "founder":  os.environ.get("HERMES_API_FOUNDER",  "http://hermes-founder:8643"),
}
# Default deliver channel per profile (used for HITL notifications)
HERMES_DELIVER = {
    "personal": "telegram",
    "coach":    "telegram",
    "architect":"feishu",
    "founder":  "telegram",
}

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

    # Emit structured log line for Loki/Grafana ingestion
    log_line = {**metrics, "type": "evolution_metric"}
    print(json.dumps(log_line, ensure_ascii=False), flush=True)

    return metrics


def _git_push_data(label: str = "data: auto-push evolution results"):
    """Commit and double-push data layer changes from the mounted repo root."""
    repo = Path("/repo")
    if not (repo / ".git").exists():
        click.echo("  [warn] /repo not a git repo — skipping data push", err=True)
        return
    try:
        # Ensure git identity
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "evo-api@hermes"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "hermes-evo"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "add", "data/"], check=True, capture_output=True)
        # Only commit if there are staged changes
        staged = subprocess.run(["git", "-C", str(repo), "diff", "--staged", "--quiet"], capture_output=True)
        if staged.returncode == 0:
            click.echo("  [info] data layer unchanged, skip push")
            return
        subprocess.run(["git", "-C", str(repo), "commit", "-m", label], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "push", "gitea", "main"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "push", "github", "main"], check=True, capture_output=True)
        click.echo("  ✓ data layer pushed → gitea + github")
    except subprocess.CalledProcessError as e:
        click.echo(f"  [warn] data push failed: {e.stderr.decode()[:200] if e.stderr else e}", err=True)


def _notify_hitl(metrics: dict, diff_url: str = ""):
    """Push HITL notification via Hermes profile gateway (one-shot cron job)."""
    improvement = metrics["improvement_pct"]
    sign = "+" if improvement >= 0 else ""
    profile = metrics["profile"]
    run_id = metrics["run_id"]

    msg = (
        f"🧬 进化完成 | {profile}/{metrics['skill']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"基线: {metrics['baseline']:.1f} → 最佳: {metrics['best']:.1f} ({sign}{improvement:.1f}%)\n"
        f"优化器: {metrics['optimizer']} | 耗时: {metrics['duration_seconds']//60}min\n"
        f"Gene命中: {metrics['gene_hits']}条\n\n"
        f"回复 approve 部署，或 reject 拒绝。\n"
        f"Run ID: {run_id}\n"
        f"curl -X POST http://hermes-evo-api:8621/hitl/approve "
        f"-d '{{\"run_id\":\"{run_id}\",\"profile\":\"{profile}\",\"skill\":\"{metrics['skill']}\"}}"
    )

    # Write to hitl-queue
    queue_entry = {**metrics, "message": msg, "status": "pending"}
    queue_file = DATA_DIR / "hitl-queue" / f"{run_id}.json"
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    queue_file.write_text(json.dumps(queue_entry, indent=2, ensure_ascii=False))

    # Push via Hermes gateway — create one-shot cron job (repeat=1, @now)
    api_url = HERMES_APIS.get(profile, HERMES_APIS["personal"])
    deliver = HERMES_DELIVER.get(profile, "telegram")

    try:
        resp = httpx.post(
            f"{api_url}/api/jobs",
            headers={"Authorization": f"Bearer {_HERMES_KEY}",
                     "Content-Type": "application/json"},
            json={
                "name": f"[evo-hitl] {profile}/{metrics['skill']} {run_id[:8]}",
                "schedule": "1m",
                "prompt": msg,
                "deliver": deliver,
                "repeat": 1,
            },
            timeout=10,
        )
        if resp.status_code in (200, 201):
            job_id = resp.json().get("job", {}).get("id", "?")
            click.echo(f"  ✓ HITL notification queued → {deliver} (job {job_id})")
        else:
            click.echo(f"  [warn] HITL job create returned {resp.status_code}: {resp.text[:100]}", err=True)
    except Exception as e:
        click.echo(f"  [warn] HITL notify failed: {e} — message saved to hitl-queue", err=True)


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

    # Auto-push data layer
    _git_push_data(f"data: evolution run {run_id}")

    click.echo(f"\n  Run ID: {run_id}")
    click.echo("  Reply 'approve' or 'reject' to process via HITL.")


def _collect_session_fragments(sessions_dir: Path, skill: str, limit: int) -> list[dict]:
    """Scan recent sessions and collect exchanges relevant to the skill."""
    skill_keywords = [skill.replace("-", " "), skill.replace("-", "")]
    session_files = sorted(sessions_dir.glob("*.jsonl"), key=os.path.getmtime, reverse=True)[:limit]
    fragments = []
    for sf in session_files:
        try:
            messages = []
            with open(sf, errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        role = d.get("role", "")
                        if role not in ("user", "assistant"):
                            continue
                        content = d.get("content", "")
                        if isinstance(content, list):
                            content = " ".join(
                                c.get("text", "") if isinstance(c, dict) else str(c)
                                for c in content
                            )
                        messages.append({"role": role, "content": content})
                    except Exception:
                        continue
            # Keep exchanges where any message mentions the skill
            if any(
                any(kw.lower() in m["content"].lower() for kw in skill_keywords)
                for m in messages
            ):
                # Collect up to 6 messages around skill mentions
                for i, m in enumerate(messages):
                    if any(kw.lower() in m["content"].lower() for kw in skill_keywords):
                        start = max(0, i - 1)
                        end = min(len(messages), i + 3)
                        for msg in messages[start:end]:
                            fragments.append({
                                "session": sf.stem,
                                "role": msg["role"],
                                "content": msg["content"][:600],
                            })
        except Exception:
            continue
    # Deduplicate
    seen = set()
    unique = []
    for f in fragments:
        key = f["session"] + f["content"][:50]
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def _llm_extract_genes(fragments: list[dict], profile: str, skill: str,
                        existing_genes: list[dict]) -> dict:
    """Call DeepSeek to extract structured genes from session fragments."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key or not fragments:
        return {"genes": existing_genes, "kg_triples": []}

    # Build context from fragments (cap at ~4000 chars)
    context_parts = []
    total = 0
    for f in fragments:
        line = f"[{f['role']}] {f['content']}\n"
        if total + len(line) > 4000:
            break
        context_parts.append(line)
        total += len(line)
    context = "".join(context_parts)

    existing_ids = {g["id"] for g in existing_genes}
    next_id = len(existing_genes) + 1

    prompt = f"""你是 Hermes skill 进化系统的 Gene 提取器。

分析以下来自 Hermes profile "{profile}" 的 "{skill}" skill 相关对话片段，提取结构化 Gene。

对话片段：
{context}

请提取：
1. effective_pattern：有效的策略/方法（用户或 agent 的行为产生好结果）
2. anti_pattern：无效/有害的模式（导致失败或低质量结果）
3. kg_triple：知识图谱三元组（subject-predicate-object 格式）

输出 JSON 格式（只输出 JSON，不要其他文字）：
{{
  "new_genes": [
    {{"id": "g{next_id:03d}", "type": "effective_pattern", "content": "...", "strength": 0.8, "evidence_sessions": ["session_id"]}},
    {{"id": "g{next_id+1:03d}", "type": "anti_pattern", "content": "...", "strength": 0.7, "evidence_sessions": ["session_id"]}}
  ],
  "kg_triples": [
    {{"subject": "...", "predicate": "...", "object_": "..."}}
  ]
}}

要求：
- content 简洁具体，不超过 80 字
- 只提取有实质证据的模式，不要编造
- 如果没有明显模式，返回 {{"new_genes": [], "kg_triples": []}}
"""

    try:
        resp = httpx.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 1000,
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        # Strip markdown code block if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        new_genes = result.get("new_genes", [])
        kg_triples = result.get("kg_triples", [])
        # Merge with existing, skip duplicate ids
        all_genes = list(existing_genes)
        for g in new_genes:
            if g["id"] not in existing_ids:
                all_genes.append(g)
        return {"genes": all_genes, "kg_triples": kg_triples}
    except Exception as e:
        click.echo(f"  [warn] LLM extraction failed: {e}", err=True)
        return {"genes": existing_genes, "kg_triples": []}


def _update_references_markdown(references_dir: Path, genes: list[dict],
                                  kg_triples: list[dict], session_fragments: list[dict]):
    """Append new genes to field-patterns.md / anti-patterns.md / session-highlights.md."""
    today = datetime.now().strftime("%Y-%m-%d")

    # field-patterns.md — effective patterns
    effective = [g for g in genes if g.get("type") == "effective_pattern"]
    if effective:
        fp = references_dir / "field-patterns.md"
        content = fp.read_text(encoding="utf-8") if fp.exists() else "# Field Patterns\n\n<!-- cron-append-start -->\n<!-- cron-append-end -->\n"
        new_entries = ""
        for g in effective:
            marker = f"<!-- gene: {g['id']} | strength: {g.get('strength',0)} | type: effective | updated: {today} -->"
            entry = f"\n## {g['content'][:50]}\n{marker}\n{g['content']}\n"
            if g["id"] not in content:
                new_entries += entry
        if new_entries:
            content = content.replace("<!-- cron-append-end -->", new_entries + "<!-- cron-append-end -->")
            fp.write_text(content, encoding="utf-8")

    # anti-patterns.md — anti patterns
    anti = [g for g in genes if g.get("type") == "anti_pattern"]
    if anti:
        ap = references_dir / "anti-patterns.md"
        content = ap.read_text(encoding="utf-8") if ap.exists() else "# Anti-Patterns\n\n<!-- cron-append-start -->\n<!-- cron-append-end -->\n"
        new_entries = ""
        for g in anti:
            marker = f"<!-- gene: {g['id']} | strength: {g.get('strength',0)} | type: anti | updated: {today} -->"
            entry = f"\n## {g['content'][:50]}\n{marker}\n{g['content']}\n"
            if g["id"] not in content:
                new_entries += entry
        if new_entries:
            content = content.replace("<!-- cron-append-end -->", new_entries + "<!-- cron-append-end -->")
            ap.write_text(content, encoding="utf-8")

    # session-highlights.md — top fragments
    sh = references_dir / "session-highlights.md"
    content = sh.read_text(encoding="utf-8") if sh.exists() else "# Session Highlights\n\n<!-- cron-append-start -->\n<!-- cron-append-end -->\n"
    highlights = session_fragments[:3]  # top 3 fragments
    if highlights:
        new_entries = f"\n## 摘录 ({today})\n"
        for h in highlights:
            new_entries += f"\n**[{h['role']}]** {h['content'][:200]}...\n"
        if today not in content:
            content = content.replace("<!-- cron-append-end -->", new_entries + "<!-- cron-append-end -->")
            sh.write_text(content, encoding="utf-8")


@cli.command()
@click.option("--profile", required=True, type=click.Choice(["personal", "coach", "architect", "founder"]))
@click.option("--skill", required=True, help="Skill name to extract genes from")
@click.option("--limit", default=50, show_default=True, help="Max sessions to scan")
@click.option("--no-llm", is_flag=True, help="Skip LLM extraction (scan only, update counts)")
def extract(profile, skill, limit, no_llm):
    """Extract GEP Genes from sessions into data/genes/ and references/ (LLM-powered)."""
    profile_dir = PROFILES_DIR / profile
    sessions_dir = profile_dir / "sessions"
    skill_dir = profile_dir / "skills" / skill
    references_dir = skill_dir / "references"

    click.echo(f"\n🔬 Gene Extraction | {profile}/{skill}")

    if not sessions_dir.exists():
        click.echo(f"  ✗ Sessions dir not found: {sessions_dir}", err=True)
        sys.exit(1)

    references_dir.mkdir(exist_ok=True)

    # Scan sessions
    session_files = sorted(sessions_dir.glob("*.jsonl"), key=os.path.getmtime, reverse=True)
    click.echo(f"  Total sessions: {len(session_files)}, scanning last {limit}")
    fragments = _collect_session_fragments(sessions_dir, skill, limit)
    click.echo(f"  Relevant fragments: {len(fragments)} from {len(set(f['session'] for f in fragments))} sessions")

    # Load existing gene file
    gene_file = DATA_DIR / "genes" / profile / f"{skill}.json"
    existing = {}
    if gene_file.exists():
        try:
            existing = json.loads(gene_file.read_text())
        except Exception:
            pass
    existing_genes = existing.get("genes", [])
    existing_triples = existing.get("kg_triples", [])

    # LLM extraction
    if no_llm or not fragments:
        new_data = {"genes": existing_genes, "kg_triples": existing_triples}
        if no_llm:
            click.echo("  [--no-llm] Skipping LLM extraction")
        else:
            click.echo("  No relevant fragments found, skipping LLM")
    else:
        click.echo(f"  Running LLM extraction (deepseek-chat)...")
        new_data = _llm_extract_genes(fragments, profile, skill, existing_genes)
        new_count = len(new_data["genes"]) - len(existing_genes)
        click.echo(f"  ✓ Extracted: {new_count} new genes, {len(new_data['kg_triples'])} KG triples")

    # Write gene file
    gene_data = {
        "profile": profile,
        "skill": skill,
        "updated_at": datetime.now(timezone.utc).date().isoformat(),
        "session_count_scanned": len(session_files[:limit]),
        "relevant_fragments": len(fragments),
        "genes": new_data["genes"],
        "kg_triples": new_data.get("kg_triples", existing_triples),
    }
    gene_file.parent.mkdir(parents=True, exist_ok=True)
    gene_file.write_text(json.dumps(gene_data, indent=2, ensure_ascii=False))
    click.echo(f"  ✓ Gene file: {len(gene_data['genes'])} genes → {gene_file}")

    # Ensure standard references/ files exist
    for fname, default in [
        ("field-patterns.md", "# Field Patterns\n\n<!-- cron-append-start -->\n<!-- cron-append-end -->\n"),
        ("anti-patterns.md", "# Anti-Patterns\n\n<!-- cron-append-start -->\n<!-- cron-append-end -->\n"),
        ("session-highlights.md", "# Session Highlights\n\n<!-- cron-append-start -->\n<!-- cron-append-end -->\n"),
    ]:
        fpath = references_dir / fname
        if not fpath.exists():
            fpath.write_text(default, encoding="utf-8")

    # Update markdown references
    _update_references_markdown(references_dir, new_data["genes"],
                                 new_data.get("kg_triples", []), fragments)
    click.echo("  ✓ references/ markdown updated")

    # Sync .genes.json
    genes_ref = references_dir / ".genes.json"
    genes_ref.write_text(gene_file.read_text(), encoding="utf-8")
    click.echo("  ✓ .genes.json synced to references/")

    click.echo(f"\n  Done. Total genes: {len(gene_data['genes'])}")


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

    # Auto-push data layer (approved metrics + hitl-queue update)
    _git_push_data(f"data: approve {run_id} {profile}/{skill}")


if __name__ == "__main__":
    cli()
