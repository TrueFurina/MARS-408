/**
 * 教师端「班级学情看板」CSV 组装（纯函数，无 DOM 依赖）
 *
 * 从 `TeacherCareerView.vue` 的 `exportDashCsv` 里抽出来，是为了让表头/缺失维度口径
 * 能被单元测试直接覆盖：这部分决定「过程性考核依据」能不能被归档，错一次就是
 * 交上去的材料错一次（缺列、错列、把未评估写成 0 分）。视图只负责下载和回执。
 *
 * 三个既定口径（2026-11-13 落实，均有测试锁）：
 * 1. 维度列固定取 canonical 六维（CAREER_DIM_ORDER），缺失维度**留空**而不消失——
 *    留空是为了让数字列还能被表格工具做统计；按数据键取列会让某维整列消失，跨班/跨场
 *    合并时还会错列。
 * 2. 缺失维度另起末列「未覆盖维度」显式写明缺哪几维；六维全无分数写「未评分」，
 *    与「部分维度缺失」区分开——前者是这道任务没做，后者是这道任务没考这一维。
 * 3. 「是否加入」用「学生本人凭码加入过」的口径，不用「教师已建号」：
 *    全班 48 个号是教师批量建的，写成「全班已加入」就是假数据。
 */
import { CAREER_DIM_LABEL, CAREER_DIM_ORDER, careerMissingDimText } from './careerDimensions'

export interface DashCsvStudent {
  student_no?: string | null
  name?: string | null
  /** 学生本人凭任务码加入过；旧响应无此字段 */
  joined?: boolean
  /** 名册已绑定账号（教师建号即可达成，不代表学生登录过） */
  bound?: boolean
  finished_count?: number | null
  session_count?: number | null
  overall_best?: number | null
  dimension_avg?: Record<string, number | undefined> | null
}

export interface DashCsvSummary {
  student_count: number
  started_count?: number | null
  finished_count?: number | null
  dimension_avg?: Record<string, number | undefined> | null
}

export interface DashCsvSource {
  class_name?: string | null
  students?: DashCsvStudent[] | null
  summary?: DashCsvSummary | null
}

/** CSV 单元格转义：含逗号 / 引号 / 换行时加双引号并转义内部引号（防姓名等破列） */
export function csvCell(v: unknown): string {
  const s = v == null ? '' : String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

/** 末列文案：六维全无分数写「未评分」，部分缺失列出未覆盖维度，六维齐全留空 */
export function dashMissCell(scores: Record<string, number | undefined> | null | undefined): string {
  return Object.keys(scores || {}).length === 0
    ? '未评分（六维均无分数）'
    : careerMissingDimText(scores)
}

/** 表头：六维固定展开 + 末列「未覆盖维度」 */
export function dashCsvHead(): string[] {
  return [
    '学号', '姓名', '是否加入', '完成场次', '总会话', 'best_overall',
    ...CAREER_DIM_ORDER.map(d => CAREER_DIM_LABEL[d] || d),
    '未覆盖维度',
  ]
}

/** 逐人一行 + 末尾班级均分行（有聚合才有） */
export function dashCsvRows(src: DashCsvSource): string[][] {
  const students = src.students || []
  const rows: string[][] = students.map(s => {
    const scores = s.dimension_avg || {}
    return [
      s.student_no || '', s.name || '',
      s.joined ? '已加入' : (s.bound ? '已建号未加入' : '未建号'),
      s.finished_count == null ? '' : String(s.finished_count),
      s.session_count == null ? '' : String(s.session_count),
      s.overall_best == null ? '' : String(s.overall_best),
      ...CAREER_DIM_ORDER.map(d => (scores[d] == null ? '' : String(scores[d]))),
      dashMissCell(scores),
    ]
  })
  const sum = src.summary
  if (sum) {
    const scores = sum.dimension_avg || {}
    rows.push([
      '', `班级均分（${sum.student_count}人）`, '',
      sum.finished_count == null ? '' : String(sum.finished_count),
      sum.started_count == null ? '' : String(sum.started_count),
      '',
      ...CAREER_DIM_ORDER.map(d => (scores[d] == null ? '' : String(scores[d]))),
      dashMissCell(scores),
    ])
  }
  return rows
}

/** 拼成最终 CSV 文本（不含 BOM，BOM 由视图在下载时补） */
export function dashCsvText(src: DashCsvSource): string {
  return [dashCsvHead(), ...dashCsvRows(src)]
    .map(r => r.map(csvCell).join(','))
    .join('\n')
}
