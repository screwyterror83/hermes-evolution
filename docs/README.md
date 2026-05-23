# hermes-evolution

Hermes 全链路进化系统 — 自动优化所有 Hermes agent skill，支持 MCP/API 触发、HITL 审批、Grafana 监控。

## 架构概览

```
sessions (JSONL)
    ↓ runner.py extract
Gene Bank (data/genes/)
    ↓ runner.py run (GEPA + Gene context)
evolved SKILL.md
    ↓ HITL (Feishu / Telegram)
deployed SKILL.md  ←→  data/results/ + scores.json
    ↓ Grafana
Evolution Intelligence Dashboard
```

四层进化：
| Layer | 框架 | 状态 |
|-------|------|------|
| 1 文本优化 | hermes-self-evolution GEPA | ✅ Phase 1 |
| 2 Gene 提取 | Evolver GEP | 🔲 Phase 2 |
| 3 结构优化 | EvoAgentX AFlow | 🔲 Phase 3 |
| 4 跨 profile 共享 | GEP shared bank | 🔲 Phase 3 |

## 快速开始

### 部署 evo-api

```bash
cd /vol1/hermes-evolution
docker compose up -d evo-api
```

### 触发进化（curl）

```bash
# Dry-run 验证配置
curl -X POST http://localhost:8621/evolve \
  -H "Content-Type: application/json" \
  -d '{"profile":"architect","skill":"tech-architect","dry_run":true}'

# 实际进化
curl -X POST http://localhost:8621/evolve \
  -H "Content-Type: application/json" \
  -d '{"profile":"coach","skill":"charm-tactics","iterations":10}'
```

### 触发进化（MCP）

在任意 Hermes profile 中调用：
```
evolve_skill(profile="coach", skill="charm-tactics")
```

### 查看结果

```bash
curl http://localhost:8621/results/coach/charm-tactics/latest
curl http://localhost:8621/scores
```

### 手动审批/拒绝

```bash
# 批准并部署
curl -X POST http://localhost:8621/hitl/approve \
  -H "Content-Type: application/json" \
  -d '{"run_id":"2026-05-22_1544_coach_charm-tactics","profile":"coach","skill":"charm-tactics"}'

# 拒绝
curl -X POST http://localhost:8621/hitl/reject \
  -H "Content-Type: application/json" \
  -d '{"run_id":"...","profile":"coach","skill":"charm-tactics","reason":"score too low"}'
```

## 目录结构

```
hermes-evolution/
├── code/
│   ├── Dockerfile          ← 唯一 Dockerfile（evo-api + runner 共用）
│   ├── runner.py           ← CLI: run / extract / approve
│   ├── evo_api/main.py     ← FastAPI 7个端点（port 8621）
│   └── aflow_adapter/      ← Phase 3 结构进化
├── data/                   ← mount: /vol2/hermes-evolution/data/
│   ├── genes/              ← GEP Gene 文件（profile/skill.json）
│   ├── results/            ← 每次进化产出（永久保留）
│   ├── registry/
│   │   ├── targets.yaml    ← 进化目标配置（编辑此文件控制自动/手动）
│   │   └── scores.json     ← 历史分数
│   └── hitl-queue/         ← 待审批队列
├── grafana/                ← Evolution Intelligence dashboard JSON
├── .gitea/workflows/ci.yaml
└── docs/
    ├── README.md           ← 本文件
    ├── architecture.md     ← 详细架构 + 四层进化说明
    └── api-reference.md    ← API 端点完整文档
```

## 进化目标管理

编辑 `data/registry/targets.yaml`：

```yaml
targets:
  - profile: coach
    skill: charm-tactics
    auto: true              # 自动每周进化
    schedule: "0 2 * * 1"
    optimizer: gepa
    min_improvement_pct: 2.0
    hitl_required: true

  - profile: founder
    skill: business-strategy
    auto: false             # 手动触发
```

当某 skill 30天内对话超过 20 次，会推送 Telegram 建议升级为 `auto: true`。

## 评分说明

- 范围：0–100（LLM judge 对 20 个 eval session 打分取平均）
- 基线 ~30 = 原始 SKILL.md 质量
- 目标：通过持续迭代 + Gene 注入推向 50+
- Grafana `Evolution Intelligence` dashboard 追踪全历史

## 存储路径

| 路径 | 用途 |
|------|------|
| `/vol1/hermes-evolution/` | 代码（git clone） |
| `/vol2/hermes-evolution/data/` | 数据层（volume mount） |
| `/vol1/hermes-profiles/{profile}/skills/{skill}/` | 线上 SKILL.md（approve 后部署） |
