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

/** 维度分字典：缺失 key 表示该场次没有取得这一维度的证据（不是 0 分） */
export type CareerDimScores = Record<string, number | undefined> | null | undefined

/**
 * 固定按 canonical 六维展开，缺失维度显式标注「本场景未覆盖」。
 *
 * 为什么必须显式：一次对抗只考察部分维度时，其余维度没有分数；如果按数据键渲染，
 * 缺失维度会整列消失，教师会以为「这维满分/没采集」；如果写「无数据」，又会被读成 0 分。
 * 口径统一为「本场景未覆盖」，把「没考」和「考了但没分」区分开。
 */
export function careerDimRows(scores: CareerDimScores) {
  const s = scores || {}
  return CAREER_DIM_ORDER.map(d => ({
    key: d, label: CAREER_DIM_LABEL[d] || d, value: s[d], covered: s[d] !== undefined,
  }))
}

/** 缺失维度的合并说明；六维全有分时返回空串（调用方据此决定是否渲染灰字） */
export function careerMissingDimText(scores: CareerDimScores): string {
  const s = scores || {}
  const miss = CAREER_DIM_ORDER.filter(d => s[d] === undefined)
  return miss.length ? `本场景未覆盖：${miss.map(d => CAREER_DIM_LABEL[d] || d).join('、')}` : ''
}

/**
 * 逐人/逐场用的缺失说明：只在「已经有部分维度分数」时列出未覆盖维度。
 * 完全没有任何分数时返回空串——那种情况该显示「—（未评估）」，否则会把
 * 「一个维度都没考」误写成「六维全未覆盖」，与「—」重复渲染。
 */
export function careerPartialMissingDimText(scores: CareerDimScores): string {
  const s = scores || {}
  return Object.keys(s).length ? careerMissingDimText(s) : ''
}

/**
 * 演示样例班识别标记。
 *
 * 该班是 61 人虚构数据 + 61 条模拟前测，与真实班同处一个班级列表：选错一次，
 * 发布的任务与看板数据就落进虚构班（2026-11-12 真实班试点前实测到的误选风险）。
 * 只认名称标记（库里没有 is_demo 列），改名前必须同步改这里。
 */
export const DEMO_CLASS_MARK = '演示'

export function isDemoClassName(name: string | null | undefined): boolean {
  return !!name && name.includes(DEMO_CLASS_MARK)
}
