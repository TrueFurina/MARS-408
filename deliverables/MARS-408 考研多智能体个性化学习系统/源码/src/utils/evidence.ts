// ============================================================
// 证据校验报告类型定义与映射工具（INC-02）
//
// 与后端 agents/evidence_check.py 产出的 EvidenceReport 结构保持一致。
// 后端已映射好 severity / disposition，前端仅做展示，不做业务判断（设计 §7.1）。
// ============================================================

export interface EvidenceDTO {
  text: string
  score: number
  source: string
}

export interface ConflictDTO {
  id: string
  type: 'semantic' | 'factual' | 'keyword' | string
  agent_a: string
  agent_b: string
  description: string
  severity: 'low' | 'medium' | 'high' | string
  evidence: EvidenceDTO[]
  resolution: string
  confidence: number
  disposition: 'adopt' | 'reject' | 'human_review' | string
}

// 防幻觉可演示：修正回写 diff（修正前→修正后）
export interface CorrectionDTO {
  field: string
  conflict_id: string
  description: string
  before: string
  after: string
  applied: boolean
}

// 防幻觉可演示：引用章节（知识库来源）
export interface CitationDTO {
  text: string
  source: string
  score: number
}

export interface EvidenceReport {
  status: 'ok' | 'degraded' | 'error' | string
  overall_consistency: number
  consistency_score: number
  confidence_score: number
  total_conflicts: number
  resolved: number
  unresolved: number
  conflicts: ConflictDTO[]
  citations: CitationDTO[]
  corrections: CorrectionDTO[]
  grounding_score: number | null
  grounding_flagged: boolean
  checked_agents: string[]
  course: string
  elapsed_ms: number
  error?: string
}

// 冲突类型 → 中文标签
export const TYPE_LABEL: Record<string, string> = {
  semantic: '语义',
  factual: '事实',
  keyword: '关键词',
}

// 严重度 → 配色（复用设计令牌语义色：紫/橙/红）
export const SEVERITY_COLOR: Record<string, string> = {
  high: 'var(--accent-danger)', // 危险红
  medium: 'var(--accent-warm)', // 警示橙
  low: 'var(--accent-primary)', // 紫
}

export const SEVERITY_LABEL: Record<string, string> = {
  high: '高危',
  medium: '中危',
  low: '低危',
}

// 处置类型 → 标签 + 配色
export const DISPOSITION_LABEL: Record<string, string> = {
  adopt: '采纳',
  reject: '否决',
  human_review: '人工复核',
}

export const DISPOSITION_COLOR: Record<string, string> = {
  adopt: 'var(--accent-success)', // 成功绿
  reject: 'var(--accent-danger)', // 危险红
  human_review: 'var(--accent-warm)', // 警示橙
}

// Agent 名 → 中文展示名
export const AGENT_LABEL: Record<string, string> = {
  teacher: '讲解文档',
  quiz: '题库',
  code_practice: '代码实操',
  ppt: 'PPT大纲',
  extension: '拓展阅读',
  mindmap: '思维导图',
  video: '视频脚本',
  media: '多媒体方案',
}

// ── 产物验收闸门结果类型 ──

export interface GateResult {
  verdict: 'pass' | 'fix' | 'reject'
  reasons: string[]
  hard_failures?: string[]
  consistency_score?: number
  retry_count?: number
}
