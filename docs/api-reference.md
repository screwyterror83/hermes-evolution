# evo-api 端点文档

Base URL: `http://localhost:8621` (内网) / `http://hermes-evo-api:8621` (Docker 网络内)

## POST /evolve

触发进化任务（异步，立即返回 task_id）

**Request:**
```json
{
  "profile": "coach",
  "skill": "charm-tactics",
  "optimizer": "gepa",
  "iterations": 10,
  "model": "openai/deepseek-v4-pro",
  "eval_model": "openai/deepseek-v4-pro",
  "dry_run": false
}
```

**Response:**
```json
{
  "task_id": "a1b2c3d4",
  "status": "queued",
  "message": "Evolution queued for coach/charm-tactics"
}
```

## GET /status/{task_id}

查询任务状态

**Response:**
```json
{
  "task_id": "a1b2c3d4",
  "profile": "coach",
  "skill": "charm-tactics",
  "status": "ok",
  "started_at": "2026-05-22T02:00:00Z",
  "finished_at": "2026-05-22T02:36:00Z",
  "returncode": 0,
  "stdout": "..."
}
```

Status values: `queued` → `running` → `ok` | `error`

## GET /targets

列出 targets.yaml 内容

## GET /results/{profile}/{skill}/latest

最新进化结果

**Response:**
```json
{
  "run_id": "2026-05-22_0200_coach_charm-tactics",
  "metrics": {
    "baseline": 30.76,
    "best": 38.74,
    "improvement_pct": 25.94,
    "duration_seconds": 2174,
    "gene_hits": 0,
    "approved": false
  },
  "has_evolved": true
}
```

## POST /hitl/approve

部署已审批的进化版本

**Request:**
```json
{
  "run_id": "2026-05-22_0200_coach_charm-tactics",
  "profile": "coach",
  "skill": "charm-tactics"
}
```

## POST /hitl/reject

拒绝进化结果

**Request:**
```json
{
  "run_id": "...",
  "profile": "coach",
  "skill": "charm-tactics",
  "reason": "quality not sufficient"
}
```

## GET /scores

历史分数列表（供 Grafana 消费）

**Response:** Array of metrics objects from `data/registry/scores.json`

## GET /health

健康检查，返回 `{"status": "ok"}`
