import { describe, it, expect } from 'vitest'
import router from './index'

/**
 * 职员路由 requiresRole 在位（F2 + A2 纵深防御守护）。
 *
 * 背景：
 * - F2（2026-10-14 浏览器走查）：/teacher、/career/teacher、/literacy/teacher
 *   三条职员路由只靠 navConfig 的导航可见性隐藏，路由本身无 meta.requiresRole
 *   ⇒ 学生输 URL 即可打开职员 UI（数据仍被后端 require_teacher 拦下，属纵深缺失）。
 * - A2（2026-10-14）：/sandbox 同款漏网，navConfig 早有 roles 而路由裸奔，已补 meta。
 *
 * 本 spec 直接 import 真实路由表做结构断言——导航可见性（navConfig）管「看不见」，
 * 路由 meta 管「进不去」，两层都要有机检。任何人新添职员路由忘了写 meta，
 * 或重构时删掉 meta，对应用例即红。
 */

function metaOf(path: string): Record<string, unknown> | null {
  const route = router.getRoutes().find((r) => r.path === path)
  return (route?.meta as Record<string, unknown>) ?? null
}

function roleSet(meta: Record<string, unknown> | null): Set<string> {
  const raw = meta?.requiresRole
  if (!raw) return new Set()
  return new Set(Array.isArray(raw) ? raw : [raw])
}

describe('职员路由 requiresRole 在位（F2 + A2 回归守护）', () => {
  const cases: Array<{ path: string; roles: string[]; note: string }> = [
    { path: '/teacher', roles: ['teacher', 'admin'], note: 'F2' },
    { path: '/career/teacher', roles: ['teacher', 'admin'], note: 'F2' },
    { path: '/literacy/teacher', roles: ['teacher', 'admin'], note: 'F2' },
    { path: '/audit-log', roles: ['admin', 'teacher'], note: '既有正确写法（对照锚点）' },
    { path: '/sandbox', roles: ['teacher', 'admin'], note: 'A2（2026-10-14 补）' },
    { path: '/admin', roles: ['admin'], note: '管理员专属' },
    { path: '/admin/knowledge', roles: ['admin'], note: '管理员专属' },
  ]

  for (const { path, roles, note } of cases) {
    it(`${path} 要求角色 {${roles.join(', ')}}（${note}）`, () => {
      const meta = metaOf(path)
      expect(meta, `路由 ${path} 应存在于路由表`).not.toBeNull()
      expect(
        roleSet(meta),
        `路由 ${path} 应声明 meta.requiresRole 覆盖 {${roles.join(', ')}}`,
      ).toEqual(new Set(roles))
    })
  }

  it('学生页面不误设 requiresRole（/chat 零角色限制）', () => {
    expect(roleSet(metaOf('/chat'))).toEqual(new Set())
  })
})
