# PEEK × Hermes Evolution 集成评估

> 文档日期：2026-05-23  
> 评估范围：PEEK 论文（arXiv 2605.19932）与 Hermes 全链路进化系统（v3）的集成可行性、优先级及实施路径

---

## 一、PEEK 论文核心结论

**论文**：PEEK: Context Map as an Orientation Cache for Long-Context LLM Agents  
**作者**：Zhuohan Gu, Qizheng Zhang, Omar Khattab, Samuel Madden  
**发布**：2026-05-19

### 方法

维护一个体积恒定的"context map"（方向性缓存），替代无限膨胀的 agent 轨迹。三个模块：

| 模块 | 职责 |
|------|------|
| **Distiller** | 每轮迭代后提炼可复用的方向性知识 |
| **Cartographer** | 将知识结构化为 map 的 diff/edit |
| **Evictor** | 管理 token budget，控制 map 体积恒定 |

### 实验结果

| 指标 | 数值 |
|------|------|
| 比 strong baseline 提升 | 6.3–34.0% |
| 减少迭代次数 | 93–145 次 |
| 比 ACE 框架成本降低 | 1.7–5.8× |
| 上下文学习任务 solving rate 提升 | 6.0–14.0% |
| rubric accuracy 提升 | 7.8–12.1% |

**核心洞察**：agent 不需要记住所有检索内容，只需要知道"去哪找"。

---

## 二、现有系统与 PEEK 的概念对齐

Hermes Evolution 系统中已存在 PEEK 思路的雏形，但粒度粗、缺少自动化闭环：

| PEEK 概念 | Hermes Evolution 现有对应物 | 差距 |
|-----------|----------------------------|------|
| Context Map（恒定体积的方向性缓存） | `data/genes/{profile}/{skill}.json` + `references/field-patterns.md` | 粒度是 session 批次级（周级更新），不是任务内迭代级 |
| Distiller（迭代后提炼知识） | `runner.py extract`（gene-extractor）+ `compile-session` cron | 批量事后运行，不在 GEPA 迭代内实时触发 |
| Cartographer（结构化 diff/update） | 不存在 | 缺失：gene 文件只能整体重写，无 diff 机制 |
| Evictor（token budget 控制） | 不存在 | 缺失：gene 文件会无限增长，无裁剪机制 |

---

## 三、集成点分析

### 集成点 1：GEPA 优化循环内部（最高价值）

**问题**：当前 GEPA 运行 10 次迭代，每次对候选 SKILL.md 打分，但迭代之间无结构化记忆——等于每轮独立探索，重复犯同样的错误。

**PEEK 注入方案**：

```
GEPA Iteration 1 → score Δ+2.1 → Distiller 提取："共情前置语言有效"
                                   Cartographer → 写入 peek_map.json
GEPA Iteration 2 → 注入 peek_map → 已知方向 → 探索更深变体
...
GEPA Iteration N → map 积累 N-1 轮导航知识 → 效率 >> 盲搜
```

**实施位置**：`code/runner.py` 的 GEPA 迭代 hook  
**新增文件**：`code/peek_map.py`（Distiller + Cartographer + Evictor，约 200 行）  
**map 存储**：`data/peek_maps/{profile}/{skill}.json`（每次 evolution run 复用/更新）

**预期收益**：在相同 10 次迭代预算内，搜索路径更优，分数从当前最佳 38.74 有望再提升 3–8 分；同时减少无效 V4 Pro 调用（节省约 20–30% 费用）。

---

### 集成点 2：Route B Deep Research N8n Workflow（次高价值）

**问题**：N8n 12 步 workflow 各节点独立运行，无跨节点的方向性记忆；多次研究同一领域时，重复抓取/分析已知内容。

**PEEK 注入方案**：

```
N8n Node 1（SearXNG 搜索）
    ↓ 查询 topic peek_map → 已知哪些角度?
N8n Node 4（Scrapling 全文抓取）
    ↓ Distiller → 更新 map："URL-A 核心论点 = X"
N8n Node 8（Open Notebook insight 生成）
    ↓ 注入 map → 避免重复生成相同 insight
N8n Node 12（Wiki 写入）
    ↓ Cartographer → 最终 map 持久化
```

**map 存储**：`/vol1/nas-infra/state/deep-research-maps/{topic_slug}.json`  
**实施方式**：N8n 新增"Read/Update PEEK Map"Function 节点（约 30 行 JS），穿插在现有节点之间

**预期收益**：同话题二次研究成本降低 40–60%；insight 质量提升（避免重复，聚焦新增角度）。

---

### 集成点 3：Gene 系统三层分层（架构增强）

**问题**：当前 gene 文件是单一粒度，缺乏"工作记忆"层。

**PEEK 引入的三层架构**：

```
长期记忆（周级更新）:  data/genes/{profile}/{skill}.json
                       ← gene-extractor 批量提炼 session 模式
                       ← 跨 run 积累，人工策展

中期记忆（run 级）:    data/peek_maps/{profile}/{skill}.json
                       ← PEEK Distiller 实时更新（每次 GEPA 迭代）
                       ← evolution run 结束后，优质 insights 自动 promote 到 genes

短期记忆（迭代内）:    GEPA 运行时 in-context map（消耗完丢弃）
```

**自动 promote 规则**：evolution run 完成后，peek_map 中 `score_delta > 1.5` 的 insight 自动追加到 gene 文件，并标记 `source: peek_promoted`。

---

### 集成点 4：Route B → Gene 自动喂养（长期复利）

```
用户触发 deep-research(topic)
    → N8n 生成 Wiki 内容（含 PEEK map 导航）
    → Wiki 写入完成
    → 自动 POST /evolve?trigger=wiki_ingest&profile=architect&skill=tech-architect
    → gene-extractor 从新 Wiki 内容提炼 gene
    → tech-architect 下次 evolution run 获得新 gene 加持
```

**效果**：研究越多 → wiki 越丰富 → gene 越精准 → skill 进化越快。正向飞轮。

---

## 四、可行性评估

### 技术可行性

| 集成点 | 实施难度 | 依赖 | 可行性 |
|--------|----------|------|--------|
| GEPA 循环内 PEEK map | 中（需 hook GEPA 迭代） | runner.py 重写（已计划） | ✅ 高 |
| Route B N8n 节点 | 低（JS Function 节点） | Route B 已上线 | ✅ 高 |
| Gene 三层分层 | 低（数据结构扩展） | gene-extractor Phase 2 | ✅ 高 |
| Route B → Gene 喂养 | 低（webhook 触发） | /evolve API Phase 1 | ✅ 高 |

### 成本评估

**新增开销**（每次 GEPA evolution run）：
- Distiller 调用：10 次 × DeepSeek V4 Flash ≈ 10 × $0.001 = **$0.01**（可忽略）
- Cartographer：纯 Python JSON 操作，无 LLM 调用
- Evictor：纯 token 计数裁剪，无 LLM 调用

**节省**：减少 GEPA 无效迭代 ≈ 节省 2–3 次 V4 Pro 调用 ≈ **$0.05–0.10/run**（净正收益）

---

## 五、实施优先级与时序

```
Phase 1（当前计划，不变）
  evo-api + runner.py Python CLI + HITL + CI/CD
  ↑ 不引入 PEEK，先把基础设施跑通

Phase 2（Gene 层 + HITL + Grafana）
  ① gene-extractor 实现时，同步建立三层架构（peak_maps/ 目录）
  ② runner.py run 加 --peek flag（默认 on）
  ③ code/peek_map.py 实现（Distiller/Cartographer/Evictor）
  ④ Route B N8n 加 PEEK map 节点（独立，不阻塞 Phase 2 其他工作）

Phase 3（AFlow + 跨 profile）
  ⑤ Route B → Gene 自动喂养 webhook
  ⑥ PEEK map insights 自动 promote 到 gene 文件
```

---

## 六、关键设计约束

1. **PEEK map 体积上限**：500 tokens（约 10 条 insight），Evictor 保留 score_delta 最高的条目
2. **Distiller 模型**：`deepseek-v4-flash`（非 Pro），控制成本
3. **map 持久化**：`data/peek_maps/` 纳入 git（随数据层推送），跨 run 复用同一 skill 的历史 map
4. **N8n map 存储**：用文件系统（`/vol1/nas-infra/state/`），不引入新依赖
5. **降级策略**：PEEK map 读取失败时静默跳过，不影响主流程

---

## 七、结论

PEEK 与 Hermes Evolution 系统在概念上高度契合，且基础设施已基本就绪。  
集成不需要改动核心架构，而是在现有 Phase 2 工作中**自然嵌入**——gene-extractor 加一层实时变体、N8n 加几个 Function 节点、runner.py 加一个 hook。

**建议**：Phase 2 开始时将 PEEK 作为 gene 层设计的组成部分一起实现，而非事后叠加。代码量约 300 行（peek_map.py + runner.py 修改 + N8n 节点），预期为 evolution run 带来 3–8 分的额外提升并降低约 20–30% 的运行成本。

---

*评估依据：PEEK arXiv 2605.19932 + hermes-evolution-plan.md v3 + 实地验证（2026-05-23）*
