/**
 * 学科 → 设计令牌 的权威映射（单一真值源）
 * ==========================================
 *
 * ## 为什么要有这个文件
 * 历史上项目里出现过**四套学科键**：
 *   1. 短键 `ds/cn/co/os`（旧组件，已废弃）
 *   2. 规范键 `data_structures/computer_network/computer_organization/operating_system`
 *      （后端归一化后的权威键，`subjectNormalizer` 输出）
 *   3. 中文名 `数据结构/计算机网络/…`（仅作展示 label）
 *   4. 混合键（部分组件只用短键配色，导致 `subjectColors[m.subject]` 永远匹配不上）
 *
 * 第 4 种曾导致 `ProfilePanel.vue` 的掌握度条形图**永远走 fallback 配色**
 * （因为 `m.subject` 是规范键，而配色表键是短键）。
 *
 * ## 使用规则（铁律）
 * - **键必须是规范键**（第 2 套），与后端 `subjectNormalizer` 输出一致
 * - 任何组件需要学科配色，**从这里 import**，不得在组件内再定义映射
 * - 短键 `ds/cn/co/os` 仅允许作为 CSS 变量名后缀出现（`--subject-ds`）
 *
 * ## 相关
 * - 展示名 label：`subjectLabel()`（各视图本地或共享）
 * - 归一化逻辑：后端 `subject_normalizer.py` / 前端 `subjectNormalizer.ts`
 */

/** 规范学科键（与后端归一化输出一致） */
export type SubjectKey =
  | 'data_structures'
  | 'computer_network'
  | 'computer_organization'
  | 'operating_system'

/** 规范键 → 设计令牌（CSS 变量） */
export const SUBJECT_COLOR_TOKENS: Record<SubjectKey, string> = {
  data_structures: 'var(--subject-ds)',
  computer_network: 'var(--subject-cn)',
  computer_organization: 'var(--subject-co)',
  operating_system: 'var(--subject-os)',
}

/** 兜底配色（未登记学科或空值） */
export const SUBJECT_COLOR_FALLBACK = 'var(--accent-primary)'

/**
 * 取学科配色令牌；未登记键返回兜底色。
 * 宽进严出：入参可能是任意字符串（含中文名/短键），一律查不到就走兜底，
 * 由调用方决定是否再归一化 —— 本函数不做静默猜测。
 */
export function subjectColor(key: string | null | undefined): string {
  if (!key) return SUBJECT_COLOR_FALLBACK
  return (
    (SUBJECT_COLOR_TOKENS as Record<string, string>)[key] ||
    SUBJECT_COLOR_FALLBACK
  )
}
