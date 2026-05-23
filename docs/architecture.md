# Hermes 全链路进化系统 — 架构文档

> 本文件同步自 `/vol1/nas-infra/docs/hermes-evolution-plan.md`（计划审批版）

## 四层进化架构

### Layer 1：文本进化（GEPA/MIPROv2）

**框架**：hermes-agent-self-evolution (NousResearch)  
**机制**：DSPy 优化器重写 SKILL.md 内容，以 eval sessions 为基准，迭代提升 LLM judge 评分  
**状态**：✅ Phase 1 实现，coach/charm-tactics 基线 30.76 → 最佳 38.74

关键实现细节：
- GEPA 构造函数参数 `max_full_evals`（不是 `max_steps`）
- runner.py 通过 `inspect.signature` 动态检测，无需 sed patch
- 进化完成后自动补全 YAML frontmatter（DSPy 会剥离它）
- 字符计数用 `len(str)` 而非 `wc -m`（UTF-8 安全）

### Layer 2：Gene 提取（Evolver GEP）

**框架**：Evolver GEP 思路（自实现 gene-extractor）  
**机制**：扫描 sessions JSONL → 提取有效/无效模式 → JSON Gene 文件 → 注入 GEPA 作为 few-shot context  
**状态**：🔲 Phase 2，当前为手动 markdown 近似

Gene 文件格式：`data/genes/{profile}/{skill}.json`
```json
{
  "genes": [
    {"id":"g001","type":"effective_pattern","content":"...","strength":0.85,"evidence_sessions":["..."]}
  ],
  "kg_triples": [{"subject":"...","predicate":"...","object":"..."}]
}
```

references/ 目录双格式：
- `field-patterns.md`：人工策展，SKILL.md/soul.md 引用
- `.genes.json`：机器可读，gene-extractor 自动维护，runner.py 在 GEPA 前加载

### Layer 3：结构进化（EvoAgentX AFlow）

**框架**：EvoAgentX AFlow  
**机制**：SKILL.md Module 结构 → JSON graph → AFlow experience-based sampling 优化模块顺序/权重 → 还原为 SKILL.md  
**状态**：🔲 Phase 3，aflow_adapter/ 目录已建立占位

AFlow 作为流水线必要步骤（非选项）：
```
GEPA (内容优化) → AFlow (结构优化) → validate → HITL
```

### Layer 4：跨 profile 共享

**机制**：`data/genes/shared/{topic}.json`，多 profile 的同类 skill 共用 Gene bank  
**状态**：🔲 Phase 3 后续

---

## 触发机制

```
MCP call: evolve_skill(profile, skill)
        ↓
  POST /evolve (evo-api:8621)
        ↓
  runner.py run (subprocess, same image)
        ↓
  hermes-agent-self-evolution (GEPA)
        ↓
  validate + frontmatter fix
        ↓
  write data/results/ + scores.json
        ↓
  HITL push (Feishu + Telegram)
        ↓
  user: approve → POST /hitl/approve
        ↓
  runner.py approve → deploy SKILL.md
```

## 评分体系

- 范围：0–100，LLM judge 对 20 个 eval session 打分平均
- 30–40 = 中低区间（当前），60+ = 高质量目标
- 每次进化写入 `data/registry/scores.json`
- evo-api `/scores` 端点暴露给 Grafana Prometheus scraper

## CI/CD

```
git push gitea main && git push github main
        ↓
Gitea Actions: validate → build → push image → deploy evo-api
```

唯一 Dockerfile，2个 service 通过 `command:` 区分：
- `evo-api`：常驻 FastAPI（port 8621）
- `evo-runner`：按需 CLI（evo-api subprocess 调用）
