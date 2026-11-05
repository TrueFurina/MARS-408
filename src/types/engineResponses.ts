/**
 * 引擎面板响应类型（批5，2026-11-05）
 *
 * 为什么不使用 api.generated.ts 的生成类型：
 * /engine/{frugal-rag-full,gomarl-consensus,conflict-check} 的响应模型对嵌套结构
 * （trajectory / personalized_rerank / dynamic_weights / conflicts）用 `dict`/`list`
 * 兜底——这些是引擎实现细节，模块加一个计数器就会变，硬定型只会让契约随实现抖动。
 * openapi-typescript 会把它们生成为 `unknown` / `unknown[]`，模板里 `step.type`、
 * `adj.reasons`、`c.confidence` 之类的字段访问全部拿不到类型。
 *
 * 故此处按 **前端实际消费的字段** 手写精确接口，逐字段核对来源：
 *   - frugal-rag-full → engines/frugal_rag_stop.py::FrugalRAGFull.retrieve_full + api/engine.py
 *   - gomarl-consensus / conflict-check → engines/gomarl_mixer.py::mix +
 *     engines/gomarl_conflict.py::check_and_resolve + api/engine.py
 * 后端模型带 extra="allow"，未列入本文件的字段仍会原样返回，不影响消费。
 *
 * 注意：/engine/gomarl-consensus 的 `conflicts` 是聚合对象（含 total/details），
 * 而 /engine/conflict-check 的 `conflicts` 是冲突详情数组——两者形状不同，刻意分开定义。
 */

// ── POST /engine/frugal-rag-full ──
/** 检索轨迹单步；不同 type 携带的字段不同，故除 type 外全部可选。 */
export interface FrugalRagTrajectoryStep {
  type: string
  query?: string
  new_chunks?: number
  chunks_found?: number
  should_stop?: boolean
  reason?: string
  thought?: string
  answer_length?: number
  final_coverage?: number
}

/** 个性化重排的单条片段调整。 */
export interface FrugalRagAdjustment {
  chunk_id: string
  adjustment: number
  reasons: string[]
}

/** 画像摘要；无画像时后端返回 null。 */
export interface FrugalRagProfileSummary {
  weak_topics?: string[]
  mastered_topics?: string[]
  review_stage?: string | null
  target_score?: number | null
}

export interface FrugalRagPersonalizedRerank {
  applied: boolean
  affected_chunks: number
  adjustments: FrugalRagAdjustment[]
  profile_summary?: FrugalRagProfileSummary | null
}

export interface FrugalRagFullResp {
  status: string
  answer: string
  trajectory: FrugalRagTrajectoryStep[]
  total_searches: number
  rewrites: number
  coverage: number
  complexity: string
  cleaned_question: string
  chunks_count: number
  personalized_rerank: FrugalRagPersonalizedRerank
}

// ── POST /engine/gomarl-consensus ──
/** 单条冲突（check_and_resolve 的 conflicts 元素）。 */
export interface GomarlConflictDetail {
  agent_a: string
  agent_b: string
  type: string
  description: string
  resolution: string
  confidence: number
  evidence_count?: number
}

/** consensus 端点把冲突统计聚合为对象。 */
export interface GomarlConflictsSummary {
  total: number
  resolved: number
  unresolved: number
  overall_consistency: number
  semantic_checked?: boolean
  details: GomarlConflictDetail[]
}

export interface GomarlConsensusResp {
  status: string
  consensus_score: number
  neural_used: boolean
  /** agent_name → 动态权重（数值，模板里会做乘法 / toFixed）。 */
  dynamic_weights: Record<string, number>
  weighted_scores: Record<string, number>
  /** 分组可能是名字数组，也可能已被降级为标量。 */
  groups: Array<string[] | string>
  sd_loss: number
  conflicts: GomarlConflictsSummary
}

// ── POST /engine/conflict-check ──
/** conflict-check 的 conflicts 是详情数组（不是聚合对象）。 */
export interface ConflictCheckResp {
  status: string
  total_conflicts: number
  resolved: number
  unresolved: number
  overall_consistency: number
  conflicts: GomarlConflictDetail[]
}
