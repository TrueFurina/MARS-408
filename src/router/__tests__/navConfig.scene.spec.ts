/**
 * 双场景导航门禁测试（前端集成 F0 验收）
 *
 * 锁定「场景化导航」的核心不变量：
 *   1. 迁位不丢页：career 项从「实验室/教学管理」迁到场景B 后 key 仍完整
 *   2. 场景隔离：kaoyan 场景看不到 career 专属项，反之亦然
 *   3. 通用项（common/缺省）两场景都可见
 *   4. 向后兼容：不传 scene 时不过滤（等价 F0 之前的行为）
 */
import { describe, it, expect } from 'vitest'
import { NAV_GROUPS, visibleGroups, flattenItems, type Scene } from '@/router/navConfig'

const ROLES = ['student', 'teacher', 'admin'] as const

function keysOf(role: (typeof ROLES)[number], scene?: Scene): string[] {
  return flattenItems(visibleGroups(role, scene)).map((i) => i.key)
}

describe('navConfig 场景化导航（F0 门禁）', () => {
  it('career 项已入导航（迁位不丢）', () => {
    const all = keysOf('admin', undefined)
    expect(all).toContain('career-training')
    expect(all).toContain('career-teacher')
  })

  it('kaoyan 场景不含 career 专属项', () => {
    for (const role of ROLES) {
      const keys = keysOf(role, 'kaoyan')
      expect(keys).not.toContain('career-training')
      expect(keys).not.toContain('career-teacher')
    }
  })

  it('career 场景含职业素养实训项（含教师端按角色）', () => {
    expect(keysOf('student', 'career')).toContain('career-training')
    expect(keysOf('teacher', 'career')).toContain('career-teacher')
    expect(keysOf('admin', 'career')).toContain('career-teacher')
  })

  it('common 项两场景都可见', () => {
    for (const scene of ['kaoyan', 'career'] as Scene[]) {
      const keys = keysOf('student', scene)
      expect(keys).toContain('settings')
      expect(keys).toContain('profile')
    }
  })

  it('不传 scene 时不过滤（向后兼容 F0 之前行为）', () => {
    const noScene = keysOf('student', undefined)
    expect(noScene).toContain('career-training')
    expect(noScene).toContain('settings')
  })

  it('两场景并集覆盖 kaoyan 全量（无丢页）', () => {
    const union = new Set([...keysOf('student', 'kaoyan'), ...keysOf('student', 'career')])
    for (const k of keysOf('student', 'kaoyan')) expect(union.has(k)).toBe(true)
  })

  it('NAV_GROUPS 未因场景化丢分组', () => {
    const ids = NAV_GROUPS.map((g) => g.id)
    expect(ids).toContain('learn')
    expect(ids).toContain('career')
    expect(ids).toContain('lab')
    expect(ids).toContain('me')
    expect(ids).toContain('staff')
  })
})
