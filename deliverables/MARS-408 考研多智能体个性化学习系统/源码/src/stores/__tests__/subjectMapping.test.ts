import { describe, it, expect } from 'vitest'
import { COURSE_MAP, SUBJECT_TO_COURSE } from '@/stores/studyStore'

// 防回归：本映射是 /review「四科统计」与学情画像聚合的唯一真相源。
// 曾因后端按章节级 key 聚合导致「科目统计」显示一堆章节名（见 2026-07-20 修复）。
describe('四科映射 COURSE_MAP / SUBJECT_TO_COURSE', () => {
  it('COURSE_MAP 覆盖 4 门 408 科目且中文名正确', () => {
    expect(Object.keys(COURSE_MAP).sort()).toEqual(
      ['computer_network', 'computer_organization', 'data_structures', 'operating_system'].sort(),
    )
    expect(COURSE_MAP.computer_network.name).toBe('计算机网络')
    expect(COURSE_MAP.data_structures.name).toBe('数据结构')
    expect(COURSE_MAP.computer_organization.name).toBe('计算机组成原理')
    expect(COURSE_MAP.operating_system.name).toBe('操作系统')
  })

  it('SUBJECT_TO_COURSE 把章节 key 反向映射到所属课程', () => {
    expect(SUBJECT_TO_COURSE['overview']).toBe('computer_network')
    expect(SUBJECT_TO_COURSE['ds_tree']).toBe('data_structures')
    expect(SUBJECT_TO_COURSE['co_cpu']).toBe('computer_organization')
    expect(SUBJECT_TO_COURSE['os_process']).toBe('operating_system')
  })

  it('每门课的 subjects 都被 SUBJECT_TO_COURSE 完整覆盖', () => {
    for (const [courseKey, course] of Object.entries(COURSE_MAP)) {
      for (const sub of course.subjects) {
        expect(SUBJECT_TO_COURSE[sub]).toBe(courseKey)
      }
    }
  })

  it('所有章节 key 都是合法标识符（防空白/非法 key 导致英文直出）', () => {
    for (const course of Object.values(COURSE_MAP)) {
      for (const sub of course.subjects) {
        // 循环 5-8 修复：薄弱点/科目英文 key 显示问题的数据源校验
        expect(sub).toMatch(/^[a-z][a-z0-9_]*$/)
        expect(sub.trim()).toBe(sub)
        expect(sub).not.toBe('unknown')
        expect(sub).not.toBe('未知')
      }
    }
  })

  it('四科章节 key 总数与知识图谱章节口径一致（防遗漏章节）', () => {
    const all = Object.values(COURSE_MAP).flatMap(c => c.subjects)
    // 四科章节合计：计网7 + 数据结构8 + 计组7 + OS5 = 27
    expect(all.length).toBe(27)
    // 无重复
    expect(new Set(all).size).toBe(all.length)
  })
})
