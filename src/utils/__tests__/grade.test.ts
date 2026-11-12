import { describe, it, expect } from 'vitest'
import { gradeColor, GRADE_COLORS } from '@/utils/grade'

// 防回归：gradeColor 是 TeacherLiteracyReportView / LiteracyAssessmentView 共用的
// 唯一评级色阶实现。此前两份本地副本各自独立，阈值一旦被单边调整，
// 同一分数在两个页面会显示成不同颜色且无任何报错。
// 这里把「阈值边界」与「色值」同时锁死，任一处漂移立即红。
describe('gradeColor 评级色阶', () => {
  it('空值视为未评级 → 灰', () => {
    expect(gradeColor(null)).toBe(GRADE_COLORS.unrated)
    expect(gradeColor(undefined)).toBe(GRADE_COLORS.unrated)
  })

  it('阈值边界精确：90 / 75 / 60 分别落在更高一档', () => {
    expect(gradeColor(100)).toBe(GRADE_COLORS.excellent)
    expect(gradeColor(90)).toBe(GRADE_COLORS.excellent)
    expect(gradeColor(89.9)).toBe(GRADE_COLORS.good)
    expect(gradeColor(75)).toBe(GRADE_COLORS.good)
    expect(gradeColor(74.9)).toBe(GRADE_COLORS.pass)
    expect(gradeColor(60)).toBe(GRADE_COLORS.pass)
    expect(gradeColor(59.9)).toBe(GRADE_COLORS.fail)
    expect(gradeColor(0)).toBe(GRADE_COLORS.fail)
  })

  it('色值与历史实现逐字一致（改动需同步两端并说明视觉影响）', () => {
    expect(GRADE_COLORS).toEqual({
      unrated: '#94a3b8',
      excellent: '#22c55e',
      good: '#84cc16',
      pass: '#eab308',
      fail: '#ef4444',
    })
  })
})
