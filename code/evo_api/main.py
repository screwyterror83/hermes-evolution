"""
Hermes Evolution API — FastAPI service (port 8621)

Endpoints:
  POST /evolve                              → trigger async evolution
  GET  /status/{run_id}                     → query task status
  GET  /targets                             → list targets.yaml
  GET  /results/{profile}/{skill}/latest    → latest evolution result
  POST /hitl/approve                        → deploy approved version
  POST /hitl/reject                         → reject with reason
  GET  /scores                              → history for Grafana
"""
import asyncio
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

DATA_DIR = Path(os.environ.get("HERMES_EVO_DATA", "/vol2/hermes-evolution/data"))
PROFILES_DIR = Path(os.environ.get("HERMES_PROFILES_DIR", "/vol1/hermes-profiles"))
RUNNER = "/app/runner.py"

app = FastAPI(
    title="Hermes Evolution API",
    description="Trigger and manage Hermes skill evolution runs",
    version="1.0.0",
)

# In-memory task registry (survives container restart via hitl-queue files)
_tasks: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class EvolveRequest(BaseModel):
    profile: str
    skill: str
    optimizer: str = "gepa"
    iterations: int = 10
    model: str = "openai/deepseek-v4-pro"
    eval_model: str = "openai/deepseek-v4-pro"
    dry_run: bool = False


class HitlDecision(BaseModel):
    run_id: str
    profile: str
    skill: str
    reason: Optional[str] = None


class ExtractRequest(BaseModel):
    profile: str
    skill: str
    limit: int = 50
    no_llm: bool = False


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------

def _run_extract(task_id: str, req: ExtractRequest):
    _tasks[task_id]["status"] = "running"
    _tasks[task_id]["started_at"] = datetime.now(timezone.utc).isoformat()

    cmd = [sys.executable, RUNNER, "extract",
           "--profile", req.profile,
           "--skill", req.skill,
           "--limit", str(req.limit)]
    if req.no_llm:
        cmd.append("--no-llm")

    env = {**os.environ}
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    _tasks[task_id]["returncode"] = result.returncode
    _tasks[task_id]["stdout"] = result.stdout[-4000:] if result.stdout else ""
    _tasks[task_id]["stderr"] = result.stderr[-2000:] if result.stderr else ""
    _tasks[task_id]["finished_at"] = datetime.now(timezone.utc).isoformat()
    _tasks[task_id]["status"] = "ok" if result.returncode == 0 else "error"


def _run_evolution(task_id: str, req: EvolveRequest):
    _tasks[task_id]["status"] = "running"
    _tasks[task_id]["started_at"] = datetime.now(timezone.utc).isoformat()

    cmd = [
        sys.executable, RUNNER, "run",
        "--profile", req.profile,
        "--skill", req.skill,
        "--optimizer", req.optimizer,
        "--iterations", str(req.iterations),
        "--model", req.model,
        "--eval-model", req.eval_model,
    ]
    if req.dry_run:
        cmd.append("--dry-run")

    env = {**os.environ}
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)

    _tasks[task_id]["returncode"] = result.returncode
    _tasks[task_id]["stdout"] = result.stdout[-4000:] if result.stdout else ""
    _tasks[task_id]["stderr"] = result.stderr[-2000:] if result.stderr else ""
    _tasks[task_id]["finished_at"] = datetime.now(timezone.utc).isoformat()
    _tasks[task_id]["status"] = "ok" if result.returncode == 0 else "error"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/evolve", summary="Trigger skill evolution")
async def evolve(req: EvolveRequest, background_tasks: BackgroundTasks):
    if req.profile not in ("personal", "coach", "architect", "founder"):
        raise HTTPException(400, f"Unknown profile: {req.profile}")

    skill_path = PROFILES_DIR / req.profile / "skills" / req.skill / "SKILL.md"
    if not skill_path.exists():
        raise HTTPException(404, f"SKILL.md not found: {skill_path}")

    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {
        "task_id": task_id,
        "profile": req.profile,
        "skill": req.skill,
        "optimizer": req.optimizer,
        "status": "queued",
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }

    background_tasks.add_task(_run_evolution, task_id, req)
    return {"task_id": task_id, "status": "queued", "message": f"Evolution queued for {req.profile}/{req.skill}"}


@app.get("/status/{task_id}", summary="Query task status")
async def status(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(404, f"Task not found: {task_id}")
    return _tasks[task_id]


@app.post("/extract", summary="Trigger gene extraction (async)")
async def extract(req: ExtractRequest, background_tasks: BackgroundTasks):
    if req.profile not in ("personal", "coach", "architect", "founder"):
        raise HTTPException(400, f"Unknown profile: {req.profile}")

    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {
        "task_id": task_id,
        "profile": req.profile,
        "skill": req.skill,
        "action": "extract",
        "status": "queued",
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }
    background_tasks.add_task(_run_extract, task_id, req)
    return {"task_id": task_id, "status": "queued",
            "message": f"Gene extraction queued for {req.profile}/{req.skill}"}


@app.get("/genes/{profile}/{skill}", summary="Get gene file for a profile/skill")
async def get_genes(profile: str, skill: str):
    gene_file = DATA_DIR / "genes" / profile / f"{skill}.json"
    if not gene_file.exists():
        raise HTTPException(404, f"No gene file for {profile}/{skill}")
    return json.loads(gene_file.read_text())


@app.get("/genes/shared", summary="List all shared (cross-profile) gene files")
async def get_shared_genes():
    shared_dir = DATA_DIR / "genes" / "shared"
    if not shared_dir.exists():
        return {"shared": []}
    result = []
    for f in sorted(shared_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            result.append({
                "topic": data.get("topic", f.stem),
                "gene_count": len(data.get("genes", [])),
                "source_profiles": data.get("source_profiles", []),
                "updated_at": data.get("updated_at"),
            })
        except Exception:
            pass
    return {"shared": result}


@app.get("/targets", summary="List evolution targets")
async def targets():
    targets_file = DATA_DIR / "registry" / "targets.yaml"
    if not targets_file.exists():
        return {"targets": []}
    data = yaml.safe_load(targets_file.read_text())
    return data or {"targets": []}


@app.get("/results/{profile}/{skill}/latest", summary="Latest evolution result")
async def latest_result(profile: str, skill: str):
    results_dir = DATA_DIR / "results"
    if not results_dir.exists():
        raise HTTPException(404, "No results yet")

    pattern = f"*_{profile}_{skill}"
    matches = sorted(results_dir.glob(pattern), reverse=True)
    if not matches:
        raise HTTPException(404, f"No results for {profile}/{skill}")

    run_dir = matches[0]
    metrics_file = run_dir / "metrics.json"
    metrics = json.loads(metrics_file.read_text()) if metrics_file.exists() else {}

    return {
        "run_id": run_dir.name,
        "metrics": metrics,
        "has_evolved": (run_dir / "evolved.md").exists(),
    }


def _do_approve(run_id: str, profile: str, skill: str) -> dict:
    """Shared approve logic used by both POST and GET endpoints."""
    cmd = [
        sys.executable, RUNNER, "approve",
        run_id, "--profile", profile, "--skill", skill,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(500, result.stderr)
    return {"status": "approved", "run_id": run_id, "output": result.stdout}


@app.post("/hitl/approve", summary="Deploy approved evolution")
async def hitl_approve(decision: HitlDecision):
    return _do_approve(decision.run_id, decision.profile, decision.skill)


@app.get("/hitl/approve", summary="Deploy approved evolution (browser-clickable link)")
async def hitl_approve_get(run_id: str, profile: str, skill: str):
    """Same as POST but via GET so Telegram/Feishu message links work directly."""
    from fastapi.responses import HTMLResponse
    try:
        result = _do_approve(run_id, profile, skill)
        return HTMLResponse(
            f"<h2>✅ Approved</h2><p>run_id: {run_id}</p>"
            f"<p>Skill <b>{profile}/{skill}</b> has been deployed.</p>"
            f"<pre>{result.get('output','')[:2000]}</pre>"
        )
    except HTTPException as e:
        return HTMLResponse(f"<h2>❌ Error</h2><pre>{e.detail}</pre>", status_code=e.status_code)


@app.post("/hitl/reject", summary="Reject evolution result")
async def hitl_reject(decision: HitlDecision):
    return _do_reject(decision.run_id, decision.reason)


def _do_reject(run_id: str, reason: str = "") -> dict:
    queue_file = DATA_DIR / "hitl-queue" / f"{run_id}.json"
    if queue_file.exists():
        entry = json.loads(queue_file.read_text())
        entry["status"] = "rejected"
        entry["reject_reason"] = reason or ""
        entry["rejected_at"] = datetime.now(timezone.utc).isoformat()
        queue_file.write_text(json.dumps(entry, indent=2, ensure_ascii=False))
    return {"status": "rejected", "run_id": run_id}


@app.get("/hitl/reject", summary="Reject evolution result (browser-clickable link)")
async def hitl_reject_get(run_id: str, profile: str, skill: str, reason: str = ""):
    """GET version for clickable links in Telegram/Feishu messages."""
    from fastapi.responses import HTMLResponse
    _do_reject(run_id, reason)
    return HTMLResponse(
        f"<h2>❌ Rejected</h2><p>run_id: {run_id}</p>"
        f"<p>Evolution of <b>{profile}/{skill}</b> has been rejected.</p>"
    )


@app.get("/scores", summary="Evolution score history (Grafana / Prometheus)")
async def scores():
    scores_file = DATA_DIR / "registry" / "scores.json"
    if not scores_file.exists():
        return []
    return json.loads(scores_file.read_text())


@app.get("/health")
async def health():
    return {"status": "ok", "data_dir": str(DATA_DIR)}
