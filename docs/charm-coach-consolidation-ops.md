# Charm Skill 合并操作文档

**执行日期：** 2026-05-23  
**操作人：** Darren  
**状态：** ✅ 完成

---

## 一、背景与问题

Coach profile 下存在两个功能重叠的 charm 相关 skill，长期并存导致：

- Agent 加载时需要同时引用两个文件，优先级模糊
- 大量内容重复（push-pull、sexual tension、I型策略、attachment theory 等在两个文件各写一遍）
- 两个文件互相引用（charm-tactics 说"加载后立即 skill_view charm-playbook"，charm-playbook 说"Module A-P 已在 charm-tactics 里"），逻辑混乱
- references 文件分散在两个目录，session 日志和提炼文档混放，hermes-evolution 系统无法明确定位

**旧目录：**
```
/vol1/hermes-profiles/coach/skills/
├── coach/                          ← 包含 charm-playbook + negotiation + influence + 僵尸 charm-tactics
│   ├── charm-playbook/SKILL.md     (715 行, v2.1)
│   ├── negotiation-for-dating/SKILL.md
│   ├── influence-for-dating/SKILL.md
│   └── charm-tactics/SKILL.md      (1 行, DISABLED)
└── charm-tactics/                  ← 独立目录
    ├── SKILL.md                    (716 行, v4.0)
    └── references/
        ├── field-patterns.md
        ├── anti-patterns.md
        ├── session-highlights.md
        ├── .genes.json
        ├── xiaodu-mtl-vent-2026-05-11.md
        └── xiaodu-silence-reengagement-2026-05-16.md
```

---

## 二、规划阶段

### 2.1 内容盘点

**charm-playbook 独有内容（不能丢）：**
- Xiaodu 人物画像（I型/恐惧回避/K感知/8种爱语）
- 4条硬规则，带事故历史和 WHY（05-14 上下文遗忘、05-19 三次幻觉、05-19 隐私边界、05-21 用词尊重）
- 对话阶段判断框架（开口/升温/高点/收尾）
- 对话三步推进框架（侧面接住→植入画面→留钩子）
- 关系推进系统（L1-L4 + 当前目标）
- 对话续命五招
- 机会窗口识别
- 发心校验（2问自检）
- 身体触碰时机
- 又怕又爱理论
- 心理烙印机制（Neuro-Imprint）
- 7 场真实 session 记录（5/11–5/21）
- PULSE_FORMAT.md（MemPalace 格式规范）

**charm-tactics 独有内容（不能丢）：**
- 8层分析引擎（更系统的工作流结构）
- 7点发送前风险检查清单
- anti-patterns.md（禁语库，含 Darren 专项失败行为）
- field-patterns.md（已验证正向模式，含锚点链）
- Module N（依恋理论完整框架）
- Module P（外部资源获取）
- xiaodu-silence-reengagement-2026-05-16.md

**重叠可去重：**
Push-pull、sexual tension、I型策略、attachment theory、情绪价值、锚点、tree-hole、禁用短语、三脑模型

### 2.2 关键约束发现

读取 `/vol1/hermes-evolution/docs/evolution-plan-v3.md` 后发现：

1. **skill 名称硬编码**：targets.yaml 写的是 `skill: charm-tactics`，gene 文件是 `charm-tactics.json`
2. **references/ 标准 schema**（evolution 系统期望，不能随意增删）：
   ```
   field-patterns.md / anti-patterns.md / session-highlights.md / .genes.json
   ```
3. **session 日志不在 references/ schema 里**，是 gene-extractor 的输入源，应放 `sessions/` 子目录

### 2.3 决策

| 问题 | 决策 |
|------|------|
| negotiation + influence 怎么办 | 保留为独立引用文件（`references/frameworks/`） |
| 旧目录怎么处理 | rename → `.bak`，不删除，可回滚 |
| 新 skill 目录名 | `charm-coach` |
| session 日志放哪 | `references/sessions/`（gene-extractor Phase 2 读此目录） |
| SKILL.md 结构骨架 | 用 charm-tactics 的 8层引擎，注入 charm-playbook 的 Xiaodu 画像/硬规则/推进系统 |

---

## 三、目标结构

```
/vol1/hermes-profiles/coach/skills/charm-coach/
├── SKILL.md                              ← 合并主文件 v5.0-unified
└── references/
    # === Evolution-standard（gene-extractor 读写，勿删）===
    ├── field-patterns.md
    ├── anti-patterns.md
    ├── session-highlights.md
    ├── .genes.json
    # === Human-facing context ===
    ├── PULSE_FORMAT.md
    ├── sessions/
    │   ├── TEMPLATE.md
    │   ├── 2026-05-11.md
    │   ├── 2026-05-12.md
    │   ├── 2026-05-14.md
    │   ├── 2026-05-18.md
    │   ├── 2026-05-19.md
    │   ├── 2026-05-19-evening.md
    │   ├── 2026-05-21.md
    │   ├── xiaodu-mtl-vent-2026-05-11.md
    │   └── xiaodu-silence-reengagement-2026-05-16.md
    ├── psychology/
    │   ├── hu-ping-dual-thought.md
    │   ├── hu-ping-taming.md
    │   ├── li-zhongying.md
    │   └── jian-de-haoren-tactics.md
    └── frameworks/
        ├── negotiation.md
        └── influence.md
```

---

## 四、执行步骤

### Step 1：创建目录结构

```bash
mkdir -p /vol1/hermes-profiles/coach/skills/charm-coach/references/sessions \
  /vol1/hermes-profiles/coach/skills/charm-coach/references/psychology \
  /vol1/hermes-profiles/coach/skills/charm-coach/references/frameworks
```

### Step 2：写合并版 SKILL.md

结构设计（v5.0-unified）：

```
Part 0: 理论基础（神经科学 + 心理烙印 + 吸引力公式）
Part 1: 小度画像（必读，含依恋类型、爱语、防御信号）
Part 2: 硬规则（4条，带事故历史和 WHY，最高优先级）
Part 3: 8层分析引擎（charm-tactics 骨架 + charm-playbook 对话阶段判断注入）
Part 4: 战术模块库（Module A–P，去重合并）
Part 5: 推进系统（当前目标 + 续命五招 + 机会窗口）
Part 6: 场景速查（A–D）
Part 7: 输出规范（Anti-AI + Anti-template）
Part 8: 发心校验（2问自检）
附：关系时间线 + Session References
```

关键合并决策：
- **Layer 3** 注入对话阶段判断（开口/升温/高点/收尾）+ 三步推进框架（charm-playbook Ch.3 独家）
- **Layer 6** 注入 Darren 的 5 个最容易犯的错 + 独立决策模式（带应对方式）
- **Layer 7** 注入"Darren 给出自己措辞时优化而非替换"规则
- **Module A** 注入 L1-L4 Escalation 梯（来自 charm-playbook Ch.2.2）
- **Module G** 注入身体触碰时机（Ch.2.4）+ 又怕又爱（Ch.2.6）
- **Module N** 保留 charm-tactics 的完整依恋框架，补充小度 fearful avoidant 标注
- **Part 4 风险过滤** 加入 Privacy check（触发 Part 2 规则二）

### Step 3：迁移 references 文件

```bash
# Evolution-standard files（来自 charm-tactics）
cp charm-tactics/references/field-patterns.md     charm-coach/references/
cp charm-tactics/references/anti-patterns.md      charm-coach/references/
cp charm-tactics/references/session-highlights.md charm-coach/references/
cp charm-tactics/references/.genes.json           charm-coach/references/

# Psychology refs（来自 charm-playbook）
cp charm-playbook/references/hu-ping-dual-thought.md  charm-coach/references/psychology/
cp charm-playbook/references/hu-ping-taming.md        charm-coach/references/psychology/
  # 注：hu-ping-taming.md 实际在 negotiation-for-dating/references/ 下
cp charm-playbook/references/li-zhongying.md          charm-coach/references/psychology/
cp charm-playbook/references/jian-de-haoren-tactics.md charm-coach/references/psychology/

# PULSE_FORMAT（来自 charm-playbook）
cp charm-playbook/references/PULSE_FORMAT.md  charm-coach/references/

# Session 日志（来自 charm-playbook，重命名去掉 session- 前缀）
cp charm-playbook/references/session-TEMPLATE.md      charm-coach/references/sessions/TEMPLATE.md
cp charm-playbook/references/session-2026-05-11.md    charm-coach/references/sessions/2026-05-11.md
# ... (11, 12, 14, 18, 19, 19-evening, 21)

# 专项复盘文档（来自 charm-tactics，按日期归档到 sessions/）
cp charm-tactics/references/xiaodu-mtl-vent-2026-05-11.md          charm-coach/references/sessions/
cp charm-tactics/references/xiaodu-silence-reengagement-2026-05-16.md charm-coach/references/sessions/

# Frameworks（来自两个独立 skill）
cp negotiation-for-dating/SKILL.md  charm-coach/references/frameworks/negotiation.md
cp influence-for-dating/SKILL.md    charm-coach/references/frameworks/influence.md
```

### Step 4：旧目录 rename 到 .bak

```bash
mv /vol1/hermes-profiles/coach/skills/coach         \
   /vol1/hermes-profiles/coach/skills/coach.bak

mv /vol1/hermes-profiles/coach/skills/charm-tactics \
   /vol1/hermes-profiles/coach/skills/charm-tactics.bak
```

### Step 5：更新 hermes-evolution 依赖

**targets.yaml：**
```yaml
# 修改前
- profile: coach
  skill: charm-tactics

# 修改后
- profile: coach
  skill: charm-coach
  notes: "Renamed from charm-tactics 2026-05-23. Merged charm-playbook v2.1 + charm-tactics v4.0 → v5.0-unified."
```

**Gene 文件重命名：**
```bash
mv data/genes/coach/charm-tactics.json \
   data/genes/coach/charm-coach.json

# 同时更新文件内 "skill" 字段：charm-tactics → charm-coach
```

**hermes-evolution 双推：**
```bash
cd /vol1/hermes-evolution
git add data/registry/targets.yaml data/genes/coach/charm-coach.json
git commit -m "feat: rename charm-tactics → charm-coach, update targets + gene file"
git push gitea main && git push github main
```

---

## 五、产出验证

```bash
# 确认新目录结构完整
find /vol1/hermes-profiles/coach/skills/charm-coach -type f | sort
# 预期：22 个文件（SKILL.md + 21 个 references）

# 确认旧目录已归档
ls /vol1/hermes-profiles/coach/skills/
# 预期：charm-coach/  coach.bak/  charm-tactics.bak/

# 确认 evolution 系统 targets 已更新
grep "skill:" /vol1/hermes-evolution/data/registry/targets.yaml | grep coach
# 预期：skill: charm-coach

# 确认 gene 文件已更新
cat /vol1/hermes-evolution/data/genes/coach/charm-coach.json | grep '"skill"'
# 预期："skill": "charm-coach"
```

---

## 六、后续待办

| 任务 | 说明 | 优先级 |
|------|------|--------|
| runner.py 路径检查 | 确认 code/runner.py 中是否有硬编码 `charm-tactics` 路径 | 中 |
| gene-extractor Phase 2 路径配置 | `runner.py extract` 实现后，session 输入路径指向 `references/sessions/` | 低（Phase 2 才需要）|
| session-highlights.md 填充 | 当前为空模板，从 session 日志中提炼关键对话片段 | 低 |
| 下次 coach session 验证 | 用真实 Xiaodu 消息测试新 SKILL.md 是否正常加载和响应 | 高 |
| .bak 目录清理 | 验证稳定后可删除（建议保留 30 天）| 低 |

---

## 七、文件版本对比

| 文件 | 旧版本 | 新版本 |
|------|--------|--------|
| charm-playbook/SKILL.md | v2.1，715 行，章节叙事式 | 归档（.bak） |
| charm-tactics/SKILL.md | v4.0，716 行，模块引擎式 | 归档（.bak） |
| charm-coach/SKILL.md | — | **v5.0-unified，~700 行，8 Part 结构** |
| targets.yaml | `skill: charm-tactics` | `skill: charm-coach` |
| genes/coach/charm-tactics.json | skill: charm-tactics，2 genes | 重命名 + skill 字段更新 |
| genes/coach/charm-coach.json | — | 4 genes（evolution 系统自动追加 g003/g004）|

---

*文档生成：2026-05-23 | 操作完成确认：Darren ✅*
