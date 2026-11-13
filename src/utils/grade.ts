/**
 * 成绩/素养评级色阶 —— 单一真值源。
 *
 * 此前 `TeacherLiteracyReportView.vue` 与 `LiteracyAssessmentView.vue` 各自复制了
 * 一份完全相同的 `scoreColor()`（≥90 绿 / ≥75 黄绿 / ≥60 黄 / 其余红，空值灰）。
 * 两份实现一旦有一处阈值或色值被单独调整，同一分数在两个页面就会显示成不同颜色，
 * 且不会有任何报错。此处收敛为唯一实现。
 *
 * 注意与 `DashboardView.vue` 的 `scoreColor()` **不是同一套口径**：
 * 那个是三级（≥80 / ≥60）且直接返回主题令牌（`var(--text-success)` 等），
 * 属"主题感知"的仪表盘口径；本模块是四级"评级色板"，深浅主题下色值恒定。
 * 两者语义不同，不要强行合并。
 *
 * 色值本身是评级色板数据（非主题令牌），故以常量集中定义在此，
 * 由 `scripts/token_scan_exemptions.json` 以 `category-palette` 登记豁免。
 */

/** 未评级（无分数） */
export const GRADE_UNRATED = '#94a3b8'
/** 优秀：≥ 90 */
export const GRADE_EXCELLENT = '#22c55e'
/** 良好：≥ 75 */
export const GRADE_GOOD = '#84cc16'
/** 及格：≥ 60 */
export const GRADE_PASS = '#eab308'
/** 不及格：< 60 */
export const GRADE_FAIL = '#ef4444'

/** 评级色板（供需要按名取色的场景使用，避免再次散落字面量） */
export const GRADE_COLORS = {
  unrated: GRADE_UNRATED,
  excellent: GRADE_EXCELLENT,
  good: GRADE_GOOD,
  pass: GRADE_PASS,
  fail: GRADE_FAIL,
} as const

/**
 * 分数 → 评级色。
 *
 * 阈值与色值与此前两份本地实现完全一致，属纯提取、零行为变更。
 * @param score 分数（0-100）；`null` / `undefined` 视为未评级，返回灰色。
 */
export function gradeColor(score: number | null | undefined): string {
  if (score == null) return GRADE_UNRATED
  if (score >= 90) return GRADE_EXCELLENT
  if (score >= 75) return GRADE_GOOD
  if (score >= 60) return GRADE_PASS
  return GRADE_FAIL
}
