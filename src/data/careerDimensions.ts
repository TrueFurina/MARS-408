/**
 * 职业素养对抗实训 · 六维定义（前端单一真值源）
 *
 * 后端真值在 `py-server/agents/career_state.py` 的 `DIMENSIONS` / `DIMENSION_LABELS`。
 * 此前该映射内联在 `CareerTrainingView.vue` 里；教师端看板需要同一份，
 * 为避免出现第三份副本（口径漂移的经典来源），提取到此处。
 *
 * 顺序即雷达图/进度条的绘制顺序，勿随意调整。
 */
export const CAREER_DIM_ORDER = [
  'expression', 'stress', 'decompose', 'collab', 'presentation', 'problem_solving',
] as const

export const CAREER_DIM_LABEL: Record<string, string> = {
  expression: '表达逻辑',
  stress: '抗压应变',
  decompose: '方案拆解',
  collab: '协作沟通',
  presentation: '技术汇报',
  problem_solving: '问题解决',
}
