# MARS-408: Multi-Agent Personalized Learning System for the 408 CS Postgraduate Exam

[English](./README.md) | [中文](./README.zh.md)

[![CI](https://img.shields.io/badge/CI-passing-brightgreen)](https://github.com/TrueFurina/MARS-408/actions)
[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Uvicorn-009688)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-11--node%20pipeline-FF6F00)](https://github.com/langchain-ai/langgraph)
[![Vue](https://img.shields.io/badge/Vue-38%20views-42B883)](https://vuejs.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](https://github.com/TrueFurina/MARS-408)

**MARS-408** is a multi-agent personalized learning system for China's Postgraduate CS Entrance Exam ("408"): an 11-node LangGraph pipeline (triage → coordinator → diagnostician → planner → retriever → generator → assessor → critic → evidence_check → quality_gate) delivers a full *diagnose → plan → teach → practice → review* loop, with SSE streaming, three-tier degradation (Redis/PostgreSQL/Milvus), E5 vector retrieval, and a MAPPO-trained teaching policy.

> **2026 Fujian Colleges "Volcano Cup" Agent Innovation Competition · Entry**
>
> Covers all four 408 subjects: Data Structures / Computer Organization / Operating Systems / Computer Networks
>
> Repository: https://github.com/TrueFurina/MARS-408
>
> Multi-agent pipeline: `coordinator` → `diagnostician` → `planner` → `retriever` → `generator_cluster` (7 roles: lecturer / quiz-writer / mind-map / slides / code / video / extension) → `assessor` → `critic` → `evidence_check` → `quality_gate` → `path_planner`

**From "answering questions" to "actually understanding you"** — a personalized study coach driven by a 10-node multi-agent pipeline, closing the full learning loop of *diagnose → plan → teach → practice → review*.

> This project originates from a national-level College Student Innovation & Entrepreneurship Training Program, and competes in the 2026 Fujian "Volcano Cup" Agent Innovation Competition as the MARS-408 system.

---

## 0. Capability Realization Status (read this first)

This project holds itself to one principle: **every capability we claim must point at files and produce runnable results.**
The table below is the verified status as of 2026-09-12, with three tiers — no vague claims.

| Capability | Status | Evidence |
|---|---|---|
| 10-node LangGraph pipeline | ✅ Done | All nodes run for real; SSE event stream complete through `data: [DONE]` |
| Backend service | ✅ Done | Cold start **936 ms**, **2,122** vectors loaded, `/docs` returns 200 |
| Real conversational generation | ✅ Done | `POST /api/chat/stream` → 200 / **5.4 s** / valid LLM content |
| Retrieval-augmentation effect | ✅ Done | **Recall@5 +10.7%** (2026-08-17 benchmark, real run) |
| Three-tier degradation | ✅ Done | Redis off → in-memory / PostgreSQL → SQLite / Milvus → InMemoryVectorStore |
| Frontend pages | ✅ Done | **38 views** (70 .vue files incl. components), student app + teacher dashboard |
| Vector retrieval | ✅ Done | E5 localized (`models/e5-base-v2` 437MB / 768-dim); `frugal_rag` runs real vector retrieval, `_degraded` off (verified 2026-09-13) |
| Consensus & conflict-resolution engine | ✅ Rule prototype + triple-review gate | M2 implemented: critic structured output + consensus evidence gate + confidence (tests/test_m2_review_gate.py, 9 cases); GoMARL weighted consensus still rule-based |
| Triage routing (M1) | ✅ Done | Zero-LLM-cost classifier + short-circuit fast path for `low`; tests/test_triage.py, 18 cases pass |
| LLM channels | ⚠️ differs from docs | Actual: **DeepSeek primary + iFlytek Spark generalv3.5**; Spark X2 unauthorized (`11200`) |
| FrugalRAG SFT + GRPO real training | ⏳ Planned | Target for a later milestone |
| Critic evidence gate (M2) | ✅ Done | Critic structured JSON + valid evidence flags + filtered_issues traceability + low-confidence human review |
| E5 vector retrieval restored | ✅ Done | E5 localized (`models/e5-base-v2`); vector path enabled (verified 2026-09-13) |
| MAPPO teaching policy (M3) | ✅ Trained (synthetic env) | Rule-supervised warmup + PPO; 3-seed dynamic env matches rule accuracy at ≤ rule cost, +1.9% beginner-turn reward (experiments/results/mappo_policy_eval_*.json) |
| MARL algorithm comparison (M4) | ✅ Data produced | IQL / VDN / QMIX / MAPPO teaching-policy 3-seed comparison: MAPPO best & steadiest (accuracy 0.963±0.000, on par with rules), QMIX second, VDN worst; report in docs/MARL算法与Agent架构对比研究.md |
| Triple-review / MAPPO production integration (M5) | ✅ End-to-end | policy_action written by coordinator and flows through the whole graph (mock-LLM 13-node smoke pass); consensus carries confidence_score/filtered_issues; demo panel at docs/demo/三评审MAPPO演示面板.html (for the competition/defense) |

> The ⚠️ and ⏳ items above are **not presented as selling points**; the table is the authoritative framing for external introductions.

---

## 1. Core Capabilities

### 1.1 10-node multi-agent pipeline (LangGraph-orchestrated)

Learner diagnosis → task planning → knowledge retrieval → resource generation → assessment feedback → quality check → evidence verification → deliverable acceptance → path planning — specialized roles in a closed loop. Unlike a single-shot Q&A chatbot, the system proactively decomposes study tasks, plans learning paths, asks follow-up questions across turns, and reports progress in real time.

### 1.2 Consensus engine + conflict resolution (v1 rule prototype)

Multiple agents answer independently; a weighted consensus engine adjudicates disagreements. When agents contradict each other on facts (e.g. "three-way vs four-way handshake"), the conflict-resolution engine retrieves the evidence chain from the knowledge base and re-verifies with a real LLM before ruling — a mechanism-level defense against hallucination, not just prompt discipline.

> **Maturity note**: consensus is a v1 rule prototype (hand-set weights) plus the M2 triple-review gate (critic structured output + evidence gate + confidence threshold). The teaching-policy layer is upgraded to MAPPO (M3: `engines/mappo_policy.py`, rule warmup + PPO, checkpoint at `models/mappo_policy.pt`), gated into the Mixer weight source via the `use_mappo_policy` flag (off by default). Real training for NeuralMixer (GroupMixerNet) weights remains a later milestone.

### 1.3 FrugalRAG adaptive retrieval pipeline

Vector retrieval + BM25 full-text + personalized re-ranking + adaptive stopping. Ships with ~**2,100 knowledge shards and practice questions** organized into 26 knowledge groups across the four subjects; on retrieval-pipeline failure it degrades to BM25 automatically so demos never stall.

> **Current status**: the E5 model is localized (verified 2026-09-13); the vector branch is enabled and recall is at design ceiling; BM25-only is the disaster-recovery path (`_degraded` flag), triggered only when E5 is unavailable.
> **E5 localization**: the model is not committed (`.gitignore` excludes `e5-base-v2/`); after a reset or machine change run `python scripts/fetch_e5_model.py` to restore it from hf-mirror — vector retrieval re-enables automatically.

### 1.4 Engineering rigor and disaster recovery throughout

- Frontend Vue 3 + TypeScript, **38 pages**, multi-role (student / teacher dashboard)
- Backend FastAPI + LangGraph, **196+ API endpoints**, **834 tests passing** (full regression, 0 failures)
- **Dual-channel LLM automatic failover**: DeepSeek (primary) → iFlytek Spark generalv3.5 (backup)
- Milvus / PostgreSQL / Redis degrade tier by tier when missing — fully runnable on a single machine

---

## 2. System Architecture

```
┌─ Frontend Vue 3 + TypeScript (38 pages) ─────────────────────┐
│  Vite :5173 → proxy → backend :8002                            │
│  Student: chat / learning path / knowledge graph / quiz / eval │
│  Teacher: class-level learning dashboard                       │
└────────────────────────────────────────────────────────────────┘
                            │
┌─ Backend FastAPI + LangGraph (10-node pipeline) ──────────────┐
│  coordinator → diagnostician → planner → retriever             │
│    → generator_cluster → assessor → critic                     │
│    → evidence_check → quality_gate → path_planner              │
│  consensus engine (v1 rules) + conflict resolution · FrugalRAG │
│  · three-tier degradation                                      │
└────────────────────────────────────────────────────────────────┘
                            │
┌─ Data layer ──────────────────────────────────────────────────┐
│  Milvus (vectors) / InMemoryVectorStore (fallback)             │
│  PostgreSQL / SQLite (fallback) · Redis / in-memory (fallback) │
│  E5 embedding model (768-dim, localized) · ~2,100 items ·      │
│  26 knowledge groups                                           │
│  Current path: vector retrieval primary (E5 localized;         │
│  degrades to BM25-only on failure)                             │
└────────────────────────────────────────────────────────────────┘
```

---

## 3. The Multi-Agent Pipeline (10 nodes)

| Node | Role | Output |
|------|------|--------|
| coordinator | intent recognition, global coordination, task dispatch | task routing |
| diagnostician | learner diagnosis, locating weak knowledge points | diagnostic report |
| planner | profile analysis, step-by-step study plan | learning plan |
| retriever | hybrid retrieval over the knowledge base | relevant evidence chunks |
| generator_cluster | parallel generation of learning resources | lecture / quiz / mind-map / slides / video script etc. |
| assessor | question generation by topic & difficulty, grading feedback | exercises / scores |
| critic | correctness, completeness, readability review | review report |
| evidence_check | cross-validation against the knowledge base, confidence labels | evidence report |
| quality_gate | deliverable acceptance gate (hard quality blocking) | acceptance verdict |
| path_planner | overall assessment, next-stage content planning | recommended path |

Supports 7 parallel resource types: lecture notes, exercises, mind maps, extension reading, slide outlines, hands-on code, video scripts.

---

## 4. Feature Matrix

| Feature | Description |
|---------|-------------|
| Intelligent chat | 10-node pipeline, auto subject detection, SSE streaming |
| Personalized learning path | dynamic next-step planning from profile & weak points |
| Knowledge graph | 26 knowledge groups across four subjects (v1 rule prototype) |
| Smart quiz & grading | per subject / chapter / difficulty with auto scoring |
| Learning analytics | multi-dimensional reports (mastery / accuracy / weak-point trends) |
| Teacher dashboard | class-level aggregation (progress / mastery / weak points) |
| 408 interactive teaching tools | e.g. TCP handshake animation simulator |
| Code sandbox | online Python execution |
| Text-to-speech | dual-engine TTS (local offline + iFlytek API) |

---

## 5. Knowledge Base & Retrieval

| Data | Count | Notes |
|------|-------|-------|
| Knowledge shards | ~1,900 | knowledge_point + knowledge_variant |
| Practice questions | 200 | multiple-choice / fill-in / short-answer across four subjects |
| Vector entries | **2,122** (loaded, measured 2026-09-13) | binary-cache loading; E5 localized (verified 2026-09-13), re-embedding & cache refresh on demand |
| Knowledge groups | 26 | by subject & chapter; supports cross-group conflict detection |

Retrieval chain: question → vector retrieval (enabled) → BM25 full-text → fusion ranking → personalized re-rank → augmented generation.
When the vector branch fails it degrades to BM25-only (`_degraded` flag) — never silently returns empty results.

---

## 6. Quantified Results (all reproducible)

| Metric | Result | Notes |
|--------|--------|-------|
| Retrieval augmentation | **Recall@5 +10.7%** | vs. no-re-rank baseline, real CPU run (measured 2026-08-17) |
| Retrieval answerability baseline | answerable_rate 0.533 | 30-question four-subject validation set (eval_gold), regression-tracked |
| Backend cold start | 936 ms | measured 2026-09-13, incl. 2,122 vectors |
| End-to-end chat latency | 5.4 s | measured 2026-09-02, real streaming LLM |

Evaluation scripts ship with the source (`py-server/experiments/`) — every number is reproducible in one command. All figures come from real runs; no fabricated user-experiment data.

---

## 7. Quick Start (2 minutes)

### One-click (Windows, recommended)

```bat
start.bat
```

Cleans stale instances on 8002 / 5173, then starts backend and frontend in order.

### Docker

```bash
docker-compose up -d
# Visit http://localhost:8002
```

> Register a login first (`/api/auth/register`); if no admin exists yet, the first registered account can log in.

### Local development

```bash
# Terminal A: backend
cd py-server && python -m venv .venv && .venv/Scripts/activate
pip install -e . && python main.py          # :8002

# Terminal B: frontend
npm install && npm run dev                   # :5173, proxies /api → 8002
```

Without Milvus / PostgreSQL / Redis / LLM credentials the system degrades automatically — core features still demo.

---

## 8. Engineering Metrics

| Dimension | Figure |
|-----------|--------|
| Frontend | Vue 3 + TypeScript · 38 views (70 .vue) · Vite build |
| Backend | FastAPI + LangGraph · 196+ API endpoints · 10 agent nodes |
| Code size | backend 414 Python files / ~102k lines · frontend 93 files / ~28k lines |
| Tests | 834 passing (full regression, 0 failures) |
| LLM | DeepSeek (primary) + iFlytek Spark generalv3.5 (backup), dual-channel failover |
| Retrieval | vector primary · ~2,122 entries · E5 localized & enabled (768-dim) |
| DR | Milvus / PG / Redis tiered degradation · fully runnable single-machine |
| Data | ~2,100 knowledge shards & questions · 26 knowledge groups |

---

## 9. Demos & Evidence

- Demo video: `submission/03_演示视频/`
- Evaluation & regression scripts: `py-server/experiments/` (eval_gold / benchmark)
- Core architecture diagram: `documents/MARS-408核心架构图.svg`
- Project health report: `diagnostics/项目体检报告-2026-09-02.md` (claim-by-claim verification)

---

## 10. Development-Tool Compliance Statement

This is a real, runnable code project (Vue 3 + TypeScript frontend / FastAPI + LangGraph backend) built with **Trae** (ByteDance's AI IDE). The repository opens, builds, and runs in Trae directly, satisfying the competition's "built with Trae" tooling requirement.

Key modules: `py-server/agents/graph.py` (multi-agent pipeline), `py-server/engines/frugal_rag.py` (retrieval engine), `py-server/engines/gomarl.py` (consensus engine), `src/` (frontend pages).

---

*Figures in this README match the source; section 0 "Capability Realization Status" is the authoritative framing, and every quantitative metric is reproducible via the scripts shipped with the source.*
