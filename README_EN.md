# Mangdehenzhi (芒得很职) — Career-Literacy Adversarial Training Platform on the MARS-408 Multi-Agent Base

> 📖 English README (this page) · [中文 README](README.md)

> Entry for **China International College Students' Innovation Competition (高教主赛道·创意组)** and the **16th "Three Creations" (三创赛) E-Commerce Challenge**.
> A next-generation, multi-agent empowered platform that trains computer-science students' career literacy through adversarial practice:
> in high-pressure scenarios of *being questioned, challenged, and pushed*, students build expression, problem-solving logic, and resilience —
> **and every score is traceable back to the exact words spoken.**
>
> Repository: https://github.com/TrueFurina/MARS-408
>
> Agent roster (MARS-408 base): `triage` → `coordinator` → `diagnostician` → `planner` → `retriever` → `generator_cluster`
> (which fans out to 7 roles: lecturer / quiz / mind-map / slides / code / video / extension)
> → `assessor` → `critic` → `evidence_check` → `quality_gate` → `path_planner`;
> on top of this base, 芒得很职 adds `career_nodes` adversarial loop with six-dimension ECD assessment.

**From "answering questions" to "actually training literacy."**
A career-literacy coaching system driven by an 11-node multi-agent pipeline that closes the full loop:
**diagnose → plan → adversarial practice → evidence assessment → improvement.**

---

## 1. Highlights

### 1. 11-Node Multi-Agent Pipeline (LangGraph, MARS-408 technical base)

Learning-state diagnosis → task planning → knowledge retrieval → resource generation → assessment
→ quality audit → evidence verification → artifact acceptance → path planning. Agents own distinct
responsibilities and cooperate in a closed loop. Unlike a one-shot Q&A chatbot, the system proactively
decomposes study tasks, plans learning paths, asks follow-up questions across turns, and streams
live progress.

### 2. Career-Literacy Adversarial Training (芒得很职 main line, layered on the base)

Built on the same multi-agent base, 芒得很职 runs a closed loop of *profile → scenario-script generation →
multi-turn adversarial dialogue with an AI interviewer → six-dimension ECD assessment after the dialogue →
traceable report*. Each dimension is anchored to verbatim evidence — trainable, measurable, and verifiable.

### 3. GOMARL-Style Weighted Consensus + Conflict Resolution (the anti-hallucination core)

Multiple agents answer independently, then a weighted-consensus engine inspired by **GOMARL** adjudicates
their disagreement. When agents contradict each other on factual knowledge (e.g. "three-way handshake
vs. four-way wave-off"), a conflict-resolution engine retrieves evidence chains from the knowledge base
and has a **real LLM re-verify the facts before ruling** — hallucination is constrained **mechanically**,
not merely by prompt wording.

### 4. FrugalRAG Adaptive Retrieval Pipeline

E5 768-dimension vector retrieval + BM25 full-text retrieval + personalized re-ranking + adaptive
early stopping. Ships with **1,883 real knowledge chunks + 200 practice questions**, loaded as
**2,122 vector entries**, organized into **26 subject groups**. If any stage of the retrieval
chain fails, the system **degrades to BM25-only** so demos and usage never break.

### 5. Production-Grade Engineering and Graceful Degradation

- Frontend: Vue 3 + TypeScript, **45 pages (45 views)**, multi-role (student / teacher dashboard)
- Backend: FastAPI + LangGraph, **~240 API endpoints** (openapi.json: 223 paths / 240 operations), **917 tests passing** (full regression, 0 failures)
- **Dual-channel LLM failover**: DeepSeek (primary) + iFlytek Spark generalv3.5 (fallback; X2 not authorized)
- Milvus / PostgreSQL / Redis each degrade independently — a single machine runs the system end to end

---

## 2. System Architecture

```
┌─ Frontend: Vue 3 + TypeScript (45 pages / 45 views) ──────────┐
│  Vite :5173  ──proxy──▶  Backend :8002                        │
│  Student: chat / learning path / knowledge graph / practice     │
│  Teacher: class-level learning dashboard                        │
└───────────────────────────────────────────────────────────────┘
                            │
┌─ Backend: FastAPI + LangGraph (11-node agent pipeline) ────────┐
│  coordinator → diagnostician → planner → retriever             │
│    → generator_cluster → assessor → critic                     │
│    → evidence_check → quality_gate → path_planner              │
│  GOMARL consensus + conflict resolution · FrugalRAG retrieval   │
│  + career_nodes adversarial loop (芒得很职 main line)            │
└───────────────────────────────────────────────────────────────┘
                            │
┌─ Data Layer ───────────────────────────────────────────────────┐
│  Milvus (vector store) / InMemoryVectorStore (fallback)        │
│  PostgreSQL / SQLite (fallback) · Redis / in-memory (fallback) │
│  E5 embeddings (768-dim) · 1,883 chunks + 200 questions        │
│  · 26 knowledge groups                                         │
└───────────────────────────────────────────────────────────────┘
```

---

## 3. The 11-Node Agent Pipeline (MARS-408 technical base)

| Node | Responsibility | Output |
|------|----------------|--------|
| `triage` | Triage routing & intent classification; low-cost classifier with short-circuit fast path | Task routing / quick answer |
| `coordinator` | Intent recognition, global orchestration, dispatch | Task routing |
| `diagnostician` | Diagnoses learning state, locates weak knowledge points | Diagnostic report |
| `planner` | Analyzes the learner profile, builds a step-by-step plan | Study plan |
| `retriever` | Hybrid vector + BM25 retrieval over the knowledge base | Relevant evidence chunks |
| `generator_cluster` | Generates multiple learning resources in parallel | Lectures / quizzes / mind maps / slides / video scripts |
| `assessor` | Produces and grades questions by knowledge point and difficulty | Practice questions / scores |
| `critic` | Audits correctness, completeness, readability | Review report |
| `evidence_check` | Cross-validates against the knowledge base, annotates confidence | Evidence-verification report |
| `quality_gate` | Artifact acceptance gate (hard quality block) | Acceptance verdict |
| `path_planner` | Evaluates overall progress, plans the next stage | Recommended path |

**7 resource types** generated in parallel: lecture notes, practice questions, mind maps, extension
readings, slide outlines, hands-on code, and video scripts.

---

## 4. Core Features

| Feature | Description |
|---------|-------------|
| Intelligent chat | 11-node pipeline, auto-detects subject, streams output via SSE progress |
| Personalized learning path | Dynamically plans what to study next from the profile and weak points |
| Knowledge graph | 26 knowledge-group view (v1 rule-based prototype) |
| Question generation & grading | Generates and auto-scores practice by knowledge point / chapter / difficulty |
| Learning-effect assessment | Multi-dimensional report (mastery / accuracy / weak-point trajectory) |
| Teacher dashboard | Class-level aggregation (progress / mastery / weak points) |
| Career-literacy adversarial training | Multi-turn adversarial dialogue + six-dimension ECD assessment + evidence replay (芒得很职 main line, v1 rule-based prototype) |
| Interactive training visualizers | Scenario-simulation / protocol-demonstration visual components (v1 rule-based prototype) |
| Code sandbox | In-browser Python execution |
| Text-to-speech | Dual-engine TTS (local offline + iFlytek API) |

---

## 5. Knowledge Base and Retrieval

| Data | Count | Notes |
|------|-------|-------|
| Knowledge chunks | 1,883 | 739 `knowledge_point` + 1,144 `knowledge_variant` |
| Practice questions | 200 | Multiple-choice / fill-in / short-answer, core subjects |
| Vector entries | 2,122 | All real E5 embeddings (768-dim), **zero all-zero vectors** |
| Knowledge groups | 26 | Topic-level groups enabling cross-group conflict detection |

Retrieval chain: user query → E5 vector search → BM25 full-text search → fusion ranking →
personalized re-ranking → augmented generation. On failure it degrades to BM25-only (flagged
`_degraded`) — **it never silently returns an empty result**.

---

## 6. Measured Results (fully reproducible)

| Metric | Result | Notes |
|--------|--------|-------|
| Retrieval augmentation | **Recall@5 +10.7% / MRR +9.6%** | vs. no-reranking baseline, real CPU run (measured 2026-08-17) |
| Retrieval-layer answerability baseline | `answerable_rate` = 0.533 | 30-question gold set (`eval_gold`), used for regression |

Evaluation scripts ship with the source (`py-server/experiments/`); every metric can be reproduced with
one command. All reported numbers come from **real runs** — no fabricated user-study data.

> Note: career-literacy adversarial-training metrics (MAPPO / P3 catfish) are **synthetic-environment**
> results — they prove "analytically optimal under the *effective* criterion" only, and are **not** cited
> as real teaching gains. See `deliverables/国创赛对外材料诚信口径检查清单.md`.

---

## 7. Quick Start (2 minutes)

### Docker (recommended)

```bash
docker-compose up -d
# Open http://localhost:8002 — register an account first (/api/auth/register)
```

### Local development

```bash
# Terminal A — backend
cd py-server && python -m venv .venv && .venv/Scripts/activate
pip install -e . && python main.py          # :8002

# Terminal B — frontend
npm install && npm run dev                   # :5173, proxies /api -> 8002
```

If Milvus / PostgreSQL / Redis / LLM credentials are missing, the system degrades automatically and
core features still run.

---

## 8. Engineering Metrics at a Glance

| Dimension | Metric |
|-----------|--------|
| Frontend | Vue 3 + TypeScript · 45 pages (45 views) · Vite build |
| Backend | FastAPI + LangGraph · ~240 API endpoints (openapi.json: 223 paths / 240 ops) · 11 agent nodes |
| Tests | 917 tests passing (full regression, 0 failures) |
| LLM | DeepSeek (primary) + iFlytek Spark generalv3.5 (fallback; X2 not authorized), dual-channel failover |
| Retrieval | Real E5 768-dim embeddings · 2,122 vectors · BM25 degradation guard |
| Resilience | Milvus / PG / Redis degrade independently · runs fully on one machine |
| Data | 1,883 knowledge chunks + 200 questions · 26 knowledge groups |

---

## 9. Demos and Evidence

- Demo videos: `submission/03_演示视频/`
- Evaluation and regression scripts: `py-server/experiments/` (`eval_gold.py`, benchmarks)
- Core architecture diagram (MARS-408 multi-agent base): `documents/MARS-408核心架构图.svg`
- Career-literacy transformation plan: `docs/职业素养对抗实训改造方案.md`

---

## 10. Development-Tool Compliance Statement

This is a real, runnable engineering project (Vue 3 + TypeScript frontend / FastAPI + LangGraph backend).
Core modules were developed and iterated with **Trae** (ByteDance's AI IDE, with built-in Doubao /
DeepSeek model capabilities). The repository opens, builds, and runs directly inside Trae, satisfying the
"built with an AI IDE" tooling requirement of the competition.

Key module map: `py-server/agents/graph.py` (multi-agent pipeline),
`py-server/engines/frugal_rag.py` (retrieval engine), `py-server/engines/gomarl.py` (consensus engine),
`py-server/agents/career_nodes.py` (career-literacy adversarial nodes), `src/` (frontend pages).

---

*This English README mirrors the Chinese README's data; every quantitative metric is reproducible via
the scripts shipped with the source. On the `career-literacy` branch, **芒得很职 (Mangdehenzhi)** is the
external product name and MARS-408 is its multi-agent technical base.*
