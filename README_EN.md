# MARS-408 — Personalized 408 Postgraduate-Exam Study Multi-Agent System

> 📖 English README (this page) · [中文 README](README.md)

> Entry for the **2026 Fujian "Volcano Cup" (火山杯) Agent Innovation Contest** · Future Learning Center track
> Covers all four subjects of China's 408 Computer Science postgraduate entrance exam:
> **Data Structures / Computer Organization / Operating Systems / Computer Networks**
>
> Repository: https://github.com/TrueFurina/MARS-408
>
> Agent roster: `coordinator` → `diagnostician` → `planner` → `retriever` → `generator_cluster`
> (which fans out to 7 roles: lecturer / quiz / mind-map / slides / code / video / extension)
> → `assessor` → `critic` → `evidence_check` → `quality_gate` → `path_planner`

**From "answering questions" to "actually understanding you."**
A personalized exam-prep coach driven by a 10-node multi-agent pipeline that closes the full loop:
**diagnose → plan → explain → practice → review.**

---

## 1. Highlights

### 1. 10-Node Multi-Agent Pipeline (LangGraph)

Learning-state diagnosis → task planning → knowledge retrieval → resource generation → assessment
→ quality audit → evidence verification → artifact acceptance → path planning. Agents own distinct
responsibilities and cooperate in a closed loop. Unlike a one-shot Q&A chatbot, the system proactively
decomposes study tasks, plans learning paths, asks follow-up questions across turns, and streams
live progress.

### 2. GOMARL-Style Weighted Consensus + Conflict Resolution (the anti-hallucination core)

Multiple agents answer independently, then a weighted-consensus engine inspired by **GOMARL** adjudicates
their disagreement. When agents contradict each other on factual knowledge (e.g. "three-way handshake
vs. four-way wave-off"), a conflict-resolution engine retrieves evidence chains from the knowledge base
and has a **real LLM re-verify the facts before ruling** — hallucination is constrained **mechanically**,
not merely by prompt wording.

### 3. FrugalRAG Adaptive Retrieval Pipeline

E5 768-dimension vector retrieval + BM25 full-text retrieval + personalized re-ranking + adaptive
early stopping. Ships with **1,883 real knowledge chunks + 200 practice questions (2,083 vector entries
in total)**, organized into **26 subject groups** across the four subjects. If any stage of the retrieval
chain fails, the system **degrades to BM25-only** so demos and usage never break.

### 4. Production-Grade Engineering and Graceful Degradation

- Frontend: Vue 3 + TypeScript, **68 pages**, multi-role (student / teacher dashboard)
- Backend: FastAPI + LangGraph, **196+ API endpoints**, **616 defined tests** (198 passing on Windows CI; the rest blocked by environment-level SIGSEGV, authority on Linux CI)
- **Dual-channel LLM failover**: iFlytek Spark X2 (primary) + DeepSeek (fallback)
- Milvus / PostgreSQL / Redis each degrade independently — a single machine runs the system end to end

---

## 2. System Architecture

```
┌─ Frontend: Vue 3 + TypeScript (68 pages) ─────────────────────┐
│  Vite :5173  ──proxy──▶  Backend :8002                        │
│  Student: chat / learning path / knowledge graph / practice    │
│  Teacher: class-level learning dashboard                       │
└───────────────────────────────────────────────────────────────┘
                            │
┌─ Backend: FastAPI + LangGraph (10-node agent pipeline) ────────┐
│  coordinator → diagnostician → planner → retriever             │
│    → generator_cluster → assessor → critic                     │
│    → evidence_check → quality_gate → path_planner              │
│  GOMARL consensus + conflict resolution · FrugalRAG retrieval   │
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

## 3. The 10-Node Agent Pipeline

| Node | Responsibility | Output |
|------|----------------|--------|
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
| Intelligent chat | 10-node pipeline, auto-detects subject, streams output via SSE progress |
| Personalized learning path | Dynamically plans what to study next from the profile and weak points |
| Knowledge graph | 26 knowledge-group view across four subjects (v1 rule-based prototype) |
| Question generation & grading | Generates and auto-scores practice by subject / chapter / difficulty |
| Learning-effect assessment | Multi-dimensional report (mastery / accuracy / weak-point trajectory) |
| Teacher dashboard | Class-level aggregation (progress / mastery / weak points) |
| Interactive 408 teaching tools | Visual teaching components such as a TCP handshake animation |
| Code sandbox | In-browser Python execution |
| Text-to-speech | Dual-engine TTS (local offline + iFlytek API) |

---

## 5. Knowledge Base and Retrieval

| Data | Count | Notes |
|------|-------|-------|
| Knowledge chunks | 1,883 | 739 `knowledge_point` + 1,144 `knowledge_variant` |
| Practice questions | 200 | Multiple-choice / fill-in / short-answer, all four subjects |
| Vector entries | 2,083 | All real E5 embeddings (768-dim), **zero all-zero vectors** |
| Knowledge groups | 26 | Chapter-level groups enabling cross-group conflict detection |

Retrieval chain: user query → E5 vector search → BM25 full-text search → fusion ranking →
personalized re-ranking → augmented generation. On failure it degrades to BM25-only (flagged
`_degraded`) — **it never silently returns an empty result**.

---

## 6. Measured Results (fully reproducible)

| Metric | Result | Notes |
|--------|--------|-------|
| Retrieval augmentation | **Recall@5 +15.8% / MRR +16.0%** | vs. no-reranking baseline, real CPU run (measured 2026-08) |
| Retrieval-layer answerability baseline | `answerable_rate` = 0.533 | 30-question four-subject gold set (`eval_gold`), used for regression |

Evaluation scripts ship with the source (`py-server/experiments/`); every metric can be reproduced with
one command. All reported numbers come from **real runs** — no fabricated user-study data.

---

## 7. Quick Start (2 minutes)

### Docker (recommended)

```bash
docker-compose up -d
# Open http://localhost:8002 — log in with demo / demo123456
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
| Frontend | Vue 3 + TypeScript · 68 pages · Vite build |
| Backend | FastAPI + LangGraph · 196+ API endpoints · 10 agent nodes |
| Tests | 616 defined tests · 198 passing on Windows CI (rest blocked by env-level SIGSEGV, authority on Linux CI) |
| LLM | iFlytek Spark X2 (primary) + DeepSeek (fallback), dual-channel failover |
| Retrieval | Real E5 768-dim embeddings · 2,083 vectors · BM25 degradation guard |
| Resilience | Milvus / PG / Redis degrade independently · runs fully on one machine |
| Data | 1,883 knowledge chunks + 200 questions · 26 knowledge groups |

---

## 9. Demos and Evidence

- Demo videos: `submission/03_演示视频/`
- Evaluation and regression scripts: `py-server/experiments/` (`eval_gold.py`, benchmarks)
- Core architecture diagram: `documents/MARS-408核心架构图.svg`

---

## 10. Development-Tool Compliance Statement

This is a real, runnable engineering project (Vue 3 + TypeScript frontend / FastAPI + LangGraph backend).
Core modules were developed and iterated with **Trae** (ByteDance's AI IDE, with built-in Doubao /
DeepSeek model capabilities). The repository opens, builds, and runs directly inside Trae, satisfying the
"built with Trae" tooling requirement of the 2026 Fujian "Volcano Cup" Agent Innovation Contest.

Key module map: `py-server/agents/graph.py` (multi-agent pipeline),
`py-server/engines/frugal_rag.py` (retrieval engine), `py-server/engines/gomarl.py` (consensus engine),
`src/` (frontend pages).

---

*This English README mirrors the Chinese README's data; every quantitative metric is reproducible via
the scripts shipped with the source.*
