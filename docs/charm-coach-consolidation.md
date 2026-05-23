# Charm Skill Consolidation Plan

## Context

Coach profile currently has two overlapping charm/dating coach skills that need to be merged into one authoritative skill:

- `/vol1/hermes-profiles/coach/skills/coach/charm-playbook/` — master playbook v2.1, 715 lines
- `/vol1/hermes-profiles/coach/skills/charm-tactics/` — unified framework v4.0, 716 lines

Plus two sub-skills inside `coach/skills/coach/` that will be folded into references:
- `negotiation-for-dating/` (Voss-based negotiation)
- `influence-for-dating/` (Cialdini-based influence)
- `charm-tactics/` (DISABLED — circular redirect, will be deleted in bak)

**Target**: single skill at `/vol1/hermes-profiles/coach/skills/charm-coach/`

---

## What Each Skill Contains

### charm-playbook strengths (unique content to preserve)
- Xiaodu portrait (必读 profile: I-type, avoidant attachment, K-sensory)
- Hard-enforced rules with incident history and WHY:
  - Privacy boundary (05-19: never imply relationship is known to others)
  - Context validation (05-14: always check session history before answering)
  - Phrasing respect (05-21: optimize Darren's wording, don't replace it)
- Session logs 5/11–5/21 — ground truth for pattern validation
- PULSE_FORMAT.md — MemPalace machine-readable snapshot format
- Relationship progression system (L1-L4, current stage tracker)
- Heart verification (2-question pre-send self-check)
- Psychology theory refs: Li Zhongying, Hu Ping, 《奸的好人》

### charm-tactics strengths (unique content to preserve)
- 8-layer analysis engine (better structured workflow than charm-playbook)
- 15-module toolkit (Modules A–P, comprehensive)
- 3-option A/B/C framework with risk stratification
- 7-point pre-send risk checklist
- Neuroscience foundation (dopamine/oxytocin, intermittent reinforcement)
- Anti-AI / anti-template output standards
- `anti-patterns.md` — 79 lines banned phrases + Darren-specific failure behaviors
- `field-patterns.md` — 97 lines verified positive patterns with anchor chains
- `xiaodu-silence-reengagement-2026-05-16.md` — cold restart protocol

### Overlap (deduplicated in merge)
Push-pull, sexual tension, I-type strategy, attachment theory, emotional value architecture, anchor points, tree-hole/venting, forbidden phrases, three-brain model — all present in both, merged into single canonical Module.

---

## Target Directory Structure

```
/vol1/hermes-profiles/coach/skills/charm-coach/
├── SKILL.md                         ← merged master
└── references/
    # === Evolution-standard files (gene-extractor reads/writes — do not delete) ===
    ├── field-patterns.md             ← migrated from charm-tactics + gene annotation format
    ├── anti-patterns.md              ← migrated from charm-tactics
    ├── session-highlights.md         ← migrated from charm-tactics (currently empty, gene-extractor fills)
    ├── .genes.json                   ← migrated from charm-tactics (currently empty)
    # === Human-facing context ===
    ├── xiaodu-portrait.md            ← extracted from charm-playbook Ch.1
    ├── hard-rules.md                 ← enforced rules + incident history (with WHY)
    ├── PULSE_FORMAT.md               ← MemPalace snapshot format spec
    ├── sessions/                     ← all session records (gene-extractor input source)
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
        ├── negotiation.md            ← content from negotiation-for-dating/SKILL.md
        └── influence.md              ← content from influence-for-dating/SKILL.md
```

Old directories renamed to `.bak` (NOT deleted — rollback available):
- `/vol1/hermes-profiles/coach/skills/coach.bak/`
- `/vol1/hermes-profiles/coach/skills/charm-tactics.bak/`

---

## Merged SKILL.md Structure

```
Part 0: Foundations (neuroscience, attraction formula, meta-principles)
Part 1: Xiaodu Profile (必读 — portrait + current stage + L1-L4 progression)
Part 2: Hard Rules (enforced, with incident history and WHY)
Part 3: 8-Layer Analysis Engine (from charm-tactics — better structure)
Part 4: Tactical Module Library (A–P, merged and deduplicated)
Part 5: Output Standards (anti-AI, 7-point checklist, 3-option A/B/C framework)
Part 6: Scene Speed-Check (from charm-playbook Ch.4)
Part 7: Heart Verification (2-question pre-send self-check)
```

---

## ⚠️ Evolution System Dependencies — Must Update After Merge

This rename affects the hermes-evolution pipeline. The following must be updated when the new skill goes live:

| File | Change Required |
|------|----------------|
| `data/registry/targets.yaml` | `skill: charm-tactics` → `skill: charm-coach` |
| `data/genes/coach/charm-tactics.json` | rename → `data/genes/coach/charm-coach.json` |
| `code/runner.py` | check for any hardcoded path to `charm-tactics` |

The standard `references/` schema (field-patterns.md, anti-patterns.md, session-highlights.md, .genes.json) is preserved in the new location — gene-extractor will continue to work without changes to its logic, only the skill name in targets.yaml needs updating.

**Session logs location**: `references/sessions/` — gene-extractor should be pointed at this subdirectory when `runner.py extract` is implemented in Phase 2.

---

## Status

- [ ] Write merged SKILL.md
- [ ] Migrate and reorganize references/
- [ ] Rename old directories to .bak
- [ ] Update targets.yaml: charm-tactics → charm-coach
- [ ] Rename gene file
- [ ] Verify coach session loads correctly with new skill
