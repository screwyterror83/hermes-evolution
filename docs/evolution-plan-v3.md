# Hermes 全链路进化系统 — 实施计划 v3

## Context

当前 self-evolution 仅覆盖 coach/charm-tactics，手动触发，无结构化管理。  
3 个 profile（coach 346、architect 408、founder 227 sessions），200+ skills 无系统进化机制。  
目标：建立独立 monorepo `hermes-evolution`，包含代码层 + 数据层，MCP/API 触发，HITL 推 Feishu/Telegram，Grafana 全面监控。

**评分说明（hermes-self-evolution）**：
- 评分范围：0–100（LLM judge 对每个 eval session 打分，20 个样本平均）
- 分数含义：LLM 评估 SKILL.md 指导的对话质量占理论最优的百分比
- **当前基线 ~30.76**（原始 charm-tactics），**最佳优化结果 38.74**（第三次 MIPROv2，+26% 相对提升）
- 30–40 属于中低区间，理论上 60+ 才是高质量，进化空间很大
- 每次进化后 Grafana 追踪此分数趋势，目标：通过持续迭代 + Gene 注入推向 50+

---

## 框架选型（4 框架最终决策）

| 框架 | 决策 | 理由 |
|------|------|------|
| hermes-self-evolution (GEPA/MIPROv2) | ✅ **采用，Layer 1** | 直接优化 SKILL.md 文本，已验证（最佳 38.74/100，见评分说明），是核心 |
| Evolver GEP | ✅ **采用，Phase 2** | 见下方说明 |
| EvoAgentX AFlow | ✅ **采用，Phase 3** | 优化 SKILL.md 的模块调用结构（Modules A-N/P 顺序/权重） |
| GenericAgent | ❌ **排除** | 用于从零创建新 agent，会破坏 Hermes 现有 profile/skill 架构，不适用 |

**GEP 是否需要？** 需要，且 Phase 2 实现后会显著提升 GEPA 质量。

**references/ 改进方案**（双格式并行，机器+人类双可读）：

```
references/
├── field-patterns.md        ← 人工策展，SKILL.md/soul.md 可引用（@include 或直接读）
├── anti-patterns.md         ← 同上
├── session-highlights.md    ← 关键对话片段
└── .genes.json              ← 机器可读，gene-extractor 自动维护
```

`references/field-patterns.md` 格式升级（保持 markdown，加机器标注）：
```markdown
## Pattern: 镜像情绪后转移
<!-- gene: g001 | strength: 0.85 | type: effective | updated: 2026-05-22 -->
用户情绪激动时，先镜像情绪再引导，成功率 83%...

## Anti-Pattern: 直接建议跳过共情
<!-- gene: g002 | strength: 0.72 | type: anti | updated: 2026-05-22 -->
```

`references/.genes.json` 是 gene-extractor 的主要产出（机器读取），与 markdown 保持同步。

**与 SKILL.md / soul.md 关联**：
- SKILL.md 的对应 Module（如 Module B：参考案例）显式写入 `@see references/field-patterns.md`
- soul.md 的 character traits 区域加入 `<!-- references: charm-tactics/field-patterns.md -->`
- runner.py 在运行 GEPA 前自动加载 `.genes.json` 作为 few-shot context 注入

gene-extractor（`runner.py extract`）同时产出两种格式，人工可在 markdown 中策展后提升到 JSON。

## 当前进化层覆盖状态

| 进化层 | 框架 | 当前状态 |
|--------|------|---------|
| Layer 1：文本进化（SKILL.md 内容优化） | hermes-self-evolution GEPA | ✅ 存在，仅 coach/charm-tactics，bash 脚本 |
| Layer 2：Gene 提取（sessions → 结构化模式 → 反馈 GEPA） | Evolver GEP | ⚠️ 手动近似（markdown），Phase 2 自动化 |
| Layer 3：结构进化（模块调用图/层级优化） | EvoAgentX AFlow | ❌ 缺失，Phase 3 |
| Layer 4：跨 profile Gene 共享 | GEP 共享 bank | ❌ 缺失，Phase 3 |

---

## 架构决策（最终版）

### 1. 单一 monorepo（代码 + 数据合并）
**理由**：数据层（genes/results/scores）全是文本/JSON，体积小，与代码关联紧密，统一版本管理更清晰。

**Dockerfile 策略**：**1 个 Dockerfile，2 个 docker-compose service，通过 `command:` 覆盖区分角色**：
- 同一镜像同时包含：dspy + hermes-self-evolution + click + FastAPI + uvicorn
- `evo-runner` service：`command: python -m runner run ...`（按需运行，退出）
- `evo-api` service：`command: uvicorn evo_api.main:app --host 0.0.0.0 --port 8621`（常驻）
- evo-api 接到 POST /evolve 时，直接 `subprocess.run(["python", "-m", "runner", "run", ...])` — 同镜像内调用
- aflow-adapter 作为 `runner.py` 的 `--optimizer aflow` 选项集成，不加新 Dockerfile
- 启动顺序：仅 evo-api 需常驻，evo-runner 无需 depends_on，docker-compose 只 deploy evo-api

```
hermes-evolution/                    ← 新 monorepo，双推 Gitea + GitHub
├── code/
│   ├── Dockerfile                   ← 唯一 Dockerfile，含 dspy + FastAPI + click
│   ├── runner.py                    ← click CLI：run/extract/approve 3个子命令
│   ├── evo_api/
│   │   ├── main.py                  ← FastAPI：/evolve /status /hitl /scores
│   │   └── mcp_tools.json
│   └── aflow_adapter/              ← Phase 3：parse_skill.py + render_skill.py
│       ├── parse_skill.py           ← SKILL.md Modules → graph
│       └── render_skill.py          ← graph → SKILL.md
├── data/                           ← 整体 mount 到 /vol2/hermes-evolution/data/
│   ├── genes/                      ← GEP Gene 文件，按 profile/skill 组织
│   │   ├── coach/
│   │   │   └── charm-tactics.json  ← Gene 文件（见下方格式说明）
│   │   ├── architect/
│   │   │   └── tech-architect.json
│   │   └── founder/                ← 后续扩展
│   ├── results/                    ← 每次进化产出，永久保留
│   │   └── 2026-05-22_coach_charm-tactics/
│   │       ├── evolved.md          ← 最终版（含 frontmatter）
│   │       └── metrics.json        ← baseline/best/duration/gene_hits
│   ├── registry/
│   │   ├── targets.yaml            ← 进化目标声明（哪些 skill 需要定期进化）
│   │   └── scores.json             ← 历史分数，evo-api /scores 端点消费
│   └── hitl-queue/                 ← 待审条目（approve/reject 前暂存）
├── grafana/
│   └── evolution-dashboard.json    ← Grafana dashboard 定义
├── .gitea/workflows/
│   └── ci.yaml                     ← Gitea Actions CI/CD
├── docs/
│   ├── README.md                   ← 部署/使用/调用完整说明
│   ├── architecture.md             ← 四层进化架构说明
│   └── api-reference.md            ← evo-api 端点文档
└── docker-compose.yml              ← 统一 compose
```

**Gene 文件格式**（`data/genes/{profile}/{skill}.json`）：
任何 profile 下的任何 skill 都可以有自己的 Gene 文件，结构如下：
```json
{
  "profile": "coach",
  "skill": "charm-tactics",
  "updated_at": "2026-05-22",
  "genes": [
    {
      "id": "g001",
      "type": "effective_pattern",
      "content": "用户情绪激动时，先镜像情绪再引导，触发率-83%",
      "evidence_sessions": ["abc123", "def456"],
      "strength": 0.85
    },
    {
      "id": "g002",
      "type": "anti_pattern",
      "content": "直接给建议跳过共情 → 触发防御机制",
      "evidence_sessions": ["ghi789"],
      "strength": 0.72
    }
  ],
  "kg_triples": [
    {"subject": "用户情绪激动", "predicate": "有效响应", "object": "镜像后转移"}
  ]
}
```
Gene 文件 Phase 1 为空（或不存在，runner.py 静默跳过），Phase 2 gene-extractor 自动填充。

**自动 vs 手动触发（用户决策权）**：  
`data/registry/targets.yaml` 是控制中心，用户直接编辑决定每个 skill 的进化策略：

```yaml
targets:
  - profile: coach
    skill: charm-tactics
    auto: true                   # ← 常用 skill，自动进化
    schedule: "0 2 * * 1"       # 每周一凌晨 2 点
    optimizer: gepa+aflow        # GEPA 内容优化 → AFlow 结构优化，全流水线
    min_improvement_pct: 2.0     # 低于此阈值不部署
    hitl_required: true          # 仍需人工确认
  - profile: architect
    skill: tech-architect
    auto: true
    schedule: "0 3 * * 1"
    optimizer: gepa+aflow
  - profile: founder
    skill: business-strategy
    auto: false                  # ← 不常用，手动触发（MCP 调用）
    optimizer: gepa              # 可单独选轻量优化
```

**使用频率自动升级**：compile-session job 统计 30 天内每个 skill 的对话次数，超过阈值（初期 **20 次**）时向 Telegram 推送建议，让用户一键将该 skill 改为 `auto: true`。

**数据路径**：挂载到 `/vol2/hermes-evolution/data/`（大存储），代码 clone 到 `/vol1/hermes-evolution/`

### 2. entrypoint.sh → Python CLI 重写

**现状问题**：bash 做 JSON 操作很痛苦，frontmatter 提取嵌了 python3 heredoc，字符计数嵌了 python3 `-c`，已经是 bash+Python 混合体，维护难。

**决策：全 Python（click CLI）**
```python
# code/evo-runner/runner.py
@click.command()
@click.option("--profile", required=True, type=click.Choice(["coach","architect","founder"]))
@click.option("--skill", required=True)
@click.option("--optimizer", default="gepa", type=click.Choice(["gepa","mipro"]))
@click.option("--iterations", default=10)
@click.option("--model", default="openai/deepseek-v4-pro")
@click.option("--eval-model", default="openai/deepseek-v4-pro")
@click.option("--dry-run", is_flag=True)
def run(profile, skill, optimizer, iterations, model, eval_model, dry_run):
    # 1. 加载 Gene 文件，注入进化 context
    # 2. 调用 hermes-agent-self-evolution
    # 3. 修复 frontmatter（Python，无 heredoc）
    # 4. 字符计数（Python len()）
    # 5. 写入 data/results/ + 更新 data/registry/scores.json
    # 6. 触发 HITL 推送（Feishu/Telegram）
```

**Docker ENTRYPOINT**：保留薄 bash wrapper（3 行），只负责 `git pull` + `exec python -m runner "$@"`。

**GEPA patch 集成**：Python 直接 import dspy，inspect GEPA signature，动态传正确参数，不依赖 sed patch。

### 3. 触发机制：evo-api（FastAPI）+ MCP 工具
```
POST /evolve        → 触发进化任务（异步）
GET  /status/{id}   → 查询任务状态
GET  /targets       → 列出 targets.yaml
GET  /results/{profile}/{skill}/latest → 最新产出
POST /hitl/approve  → 部署已批准的进化版本
POST /hitl/reject   → 拒绝并记录原因
GET  /scores        → 历史分数（供 Grafana 消费）
```

MCP 工具注册到 hermes-compose，所有 profile 可直接调用：
```json
{"name": "evolve_skill", "description": "触发指定 profile/skill 的进化",
 "inputSchema": {"profile": {"enum":["coach","architect","founder"]}, "skill": {"type":"string"}, "optimizer": {"default":"gepa"}}}
```

### 4. HITL → Feishu + Telegram 双推

进化完成后，runner.py 调用 Hermes platform API（已有 `deliver: feishu/telegram`），推送：

```
🧬 进化完成 | architect/tech-architect
━━━━━━━━━━━━━━━━━━━━
基线: 30.2 → 最佳: 32.8 (+8.6%)
优化器: GEPA | 耗时: 22min
Gene命中: 3条 | 新 Gene: 1条

[查看 diff] [✅ 部署] [❌ 拒绝]
回复对应按钮或文字确认
```

Hermes bot 接收回复 → 调用 `POST /hitl/approve?job_id=xxx` → 自动部署 + git push 数据层。

### 5. CI/CD（Gitea Actions）

```yaml
# .gitea/workflows/ci.yaml
on: [push]
jobs:
  validate:
    steps:
      - name: Validate targets.yaml
        run: python -c "import yaml; yaml.safe_load(open('data/registry/targets.yaml'))"
      - name: Lint runner.py
        run: ruff check code/evo-runner/
      - name: Build evo-runner image
        run: docker build -t hermes-evolution/evo-runner:${{ github.sha }} code/evo-runner/
      - name: Push to Gitea registry
        run: docker push gitea.nas/admin/evo-runner:${{ github.sha }}
  deploy:
    needs: validate
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Update hermes-compose service
        run: |
          ssh nas "cd /vol1/hermes-compose && docker compose pull evo-runner && docker compose up -d evo-runner"
```

---

## Grafana Dashboard 设计（全面）

**Dashboard 名**：`Hermes Evolution Intelligence`  
**数据源**：evo-api `GET /scores` → Prometheus exporter（JSON → metrics）+ Loki（日志）

**Panel 布局（12 行 × 2 列）**：

| Row | Left Panel | Right Panel |
|-----|-----------|-------------|
| 1 | **进化总览** — Score 历史折线（每 profile/skill 一条线） | **本周进化** — 运行次数、成功/失败率、平均提升幅度 |
| 2 | **Profile 进化热力图** — coach/architect/founder × skill × 时间 | **HITL 审批率** — 批准 vs 拒绝比例，趋势 |
| 3 | **迭代效率** — 每次进化的 iterations 数 vs 分数提升幅度（散点图） | **Gene 命中率** — 每次进化 Gene 命中数量趋势 |
| 4 | **进化耗时分布** — histogram（按 profile） | **API 调用费用估算** — 按 run 累计，按 model 分组 |
| 5 | **Session 积累速率** — 每 profile 的 session 数量趋势 | **进化覆盖率** — 已进化 skill 数 / 总 skill 数（gauge） |
| 6 | **Baseline vs Best 散点图** — 每个 skill 的起点和终点 | **最近 10 次进化日志** — Loki 查询，错误高亮 |

**核心 metrics**（runner.py 写入 `data/registry/scores.json`，evo-api 暴露为 Prometheus metrics）：
```
evolution_score{profile, skill, optimizer, run_id}
evolution_baseline{profile, skill}
evolution_improvement_pct{profile, skill}
evolution_duration_seconds{profile, skill}
evolution_gene_hits{profile, skill}
evolution_approved_total{profile}
evolution_rejected_total{profile}
evolution_sessions_used{profile, skill}
```

Dashboard JSON 文件放入 `grafana/evolution-dashboard.json`，通过 nas-infra 的 grafana-provisioning 自动加载。

---

## 关键文件变更

### 新建（hermes-evolution monorepo）
| 文件 | 说明 |
|------|------|
| `code/Dockerfile` | **唯一** Dockerfile，含 dspy + FastAPI + click |
| `code/runner.py` | Python CLI（click），`run`/`extract`/`approve` 3个子命令，含 GEPA 动态参数检测 |
| `code/evo_api/main.py` | FastAPI：/evolve /status /hitl /scores |
| `code/evo_api/mcp_tools.json` | MCP 工具定义（注册到 hermes-compose） |
| `code/aflow_adapter/parse_skill.py` | SKILL.md Modules → JSON graph（Phase 3） |
| `code/aflow_adapter/render_skill.py` | JSON graph → SKILL.md（Phase 3） |
| `data/registry/targets.yaml` | 进化目标声明（初始：coach/charm-tactics、architect/tech-architect、founder/待定） |
| `grafana/evolution-dashboard.json` | 完整 Grafana dashboard JSON（12 panels） |
| `docs/README.md` | 部署、使用、API 调用完整文档 |
| `.gitea/workflows/ci.yaml` | Gitea Actions CI/CD（validate + build 1镜像 + deploy） |

### 修改现有
| 文件 | 变更 |
|------|------|
| `/vol1/hermes-compose/docker-compose.yml` | 新增 evo-api 服务（8621 端口）；更新 evo-runner 指向新镜像 |
| `/vol1/nas-infra/compose/observability-compose/grafana-provisioning/dashboards/` | 加载 evolution-dashboard.json |
| `/vol1/hermes-profiles/architect/cron/jobs.json` | 加 evolve-skills job（调 MCP evolve_skill） |
| `/vol1/hermes-profiles/founder/cron/jobs.json` | 同上 |
| `/vol1/hermes-profiles/coach/cron/jobs.json` | charm-tactics 进化迁移到新系统 |
| `/vol1/nas-infra/compose/self-evolution/` | 保留不动直到新系统验证 |

### 存储路径
```
/vol1/hermes-evolution/          ← 代码 clone（git）
/vol2/hermes-evolution/data/     ← 数据层挂载点（volume mount from monorepo data/）
```

---

## 实施顺序

### Phase 1：基础设施 + Layer 1 泛化（2-3天）
1. 初始化 `hermes-evolution` monorepo，配置 Gitea + GitHub 双推
2. 重写 evo-runner 为 Python CLI（runner.py），含 GEPA 动态 patch（无需 sed）
3. 实现 evo-api FastAPI（/evolve /status /hitl /scores）
4. 注册 MCP 工具，部署 evo-api 到 hermes-compose
5. 配置 Gitea Actions CI/CD（validate + build + deploy）
6. **验证**：`evolve_skill(profile="architect", skill="tech-architect")` 跑通一次

### Phase 2：references 整理 + Gene 层 + HITL + Grafana（1-2天）
7. **SKILL.md references 结构化整理**（Gene 层的前置）：
    - 为 architect 和 founder 的 top skills 建立 `references/` 目录（对齐 coach/charm-tactics 的结构）
    - 标准 schema：`field-patterns.md`（有效模式）、`anti-patterns.md`（失败模式）、`session-highlights.md`（关键片段）
    - 为所有已配置 targets.yaml 的 skill 建立 references，并补充 `<!-- cron-append-start/end -->` 标记
    - 收录方案：gene-extractor 运行时自动追加到 references/，人工策展后提升为 Gene JSON
8. gene-extractor（`runner.py extract`）：sessions JSONL → 结构化 Gene JSON，写入 `data/genes/{profile}/{skill}.json`；同步更新对应 references/ 文件
9. Feishu/Telegram HITL 推送（runner.py 调用 Hermes platform API）
10. Grafana dashboard（12 panels，全部 metrics）
11. 数据层 auto git push（每次进化完成）

### Phase 3：结构进化 + 跨 profile 共享（后续）
11. **AFlow adapter** 完整实现：
    - `aflow_adapter/parse_skill.py`：解析 SKILL.md 的 Modules A-N/P → JSON graph（节点=模块，边=调用关系，权重=优先级）
    - 集成 EvoAgentX AFlow：以 graph 为优化目标，通过 experience-based sampling 调整模块顺序/权重/依赖
    - `aflow_adapter/render_skill.py`：优化后 graph → 重新排版 SKILL.md，保持原有格式约定
    - AFlow 是**流水线的必要步骤**，不是选项：`runner.py run` 默认执行 GEPA（内容优化）→ AFlow（结构优化）→ validate → HITL
    - targets.yaml 的 `optimizer: gepa+aflow` 触发完整流水线；`optimizer: gepa` 仅做内容优化（Phase 1/2 临时）
    - AFlow 不修改模块内文本，只调整 Modules A-N/P 的顺序/权重/调用关系
    - Phase 3 完成后，`gepa+aflow` 成为所有 auto skill 的默认 optimizer
12. 跨 profile Gene 共享：`data/genes/shared/{topic}.json`，多个 profile 的 skill 可引用同一 Gene bank

---

## 计划文档存放

- **立即**：将本计划推送到 `/vol1/nas-infra/docs/hermes-evolution-plan.md`，双推 Gitea + GitHub
- **Phase 1 完成后**：同步一份到 `hermes-evolution/docs/architecture.md`（作为 monorepo 内文档的一部分）

## 验证方法
1. `curl -X POST localhost:8621/evolve -d '{"profile":"architect","skill":"tech-architect","dry_run":true}'` → 返回 session 数量和 profile 路径
2. 完整进化一次 → `data/results/` 有产出，自动推送 Gitea + GitHub
3. Feishu 或 Telegram 收到 HITL 通知，回复 ✅ → SKILL.md 自动更新
4. Grafana `grafana.nas` → Evolution Intelligence dashboard 有数据
5. `GET /targets` 列出 3 个初始进化目标
6. Gitea Actions CI 推送后自动 build + deploy evo-runner 镜像
