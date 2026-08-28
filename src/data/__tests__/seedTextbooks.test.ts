import { describe, it, expect } from 'vitest'
import { SEED_TEXTBOOK_LIST } from '@/data/seedTextbooks'

// 防回归：/knowledge-base「暂无教材」的根因是 dist 未含兜底逻辑。
// SEED_TEXTBOOK_LIST 是离线/API 异常时的硬兜底，必须稳定存在且结构正确。
describe('种子教材兜底 SEED_TEXTBOOK_LIST', () => {
  it('至少含 4 本 408 教材（计网/数据结构/计组/OS）', () => {
    expect(SEED_TEXTBOOK_LIST.length).toBeGreaterThanOrEqual(4)
  })

  it('每本教材含 id / name / subject 字段', () => {
    const subjects = new Set<string>()
    for (const t of SEED_TEXTBOOK_LIST) {
      expect(typeof t.id).toBe('string')
      expect(t.id.length).toBeGreaterThan(0)
      expect(typeof t.name).toBe('string')
      expect(t.name.length).toBeGreaterThan(0)
      subjects.add(t.subject)
    }
    // 四科覆盖
    expect(subjects).toEqual(
      new Set(['computer_network', 'data_structures', 'computer_organization', 'operating_system']),
    )
  })
})
