import { describe, it, expect } from 'vitest'
import { resolveLandingRoute } from './landing'

/**
 * F1 守护：登录落点按角色三分支。
 *
 * 背景：2026-10-14 真实浏览器走查发现教师登录被送进学生入学测评
 * （LoginView.vue 修复前把角色判断放在 diagnostic_required 之后）。
 * 修复后该口径提取为纯函数 resolveLandingRoute，本 spec 防回归——
 * 任何人把逻辑改回「先判 diagnostic_required」都会让teacher/admin 两条用例红。
 */
describe('resolveLandingRoute — 登录落点按角色（F1 回归守护）', () => {
  it('学生且需入学测评 → /diagnostic/start', () => {
    expect(resolveLandingRoute({ role: 'student', diagnostic_required: true }))
      .toBe('/diagnostic/start')
  })

  it('学生且不需测评 → 平台首页 /', () => {
    expect(resolveLandingRoute({ role: 'student', diagnostic_required: false })).toBe('/')
  })

  it('教师 + diagnostic_required=true → /teacher（不被送进学生测评）', () => {
    // F1 核心回归：修复前此输入落 /diagnostic/start
    expect(resolveLandingRoute({ role: 'teacher', diagnostic_required: true }))
      .toBe('/teacher')
  })

  it('教师 + diagnostic_required=false → /teacher', () => {
    expect(resolveLandingRoute({ role: 'teacher', diagnostic_required: false }))
      .toBe('/teacher')
  })

  it('管理员 + diagnostic_required=true → /admin（同款受害路径）', () => {
    expect(resolveLandingRoute({ role: 'admin', diagnostic_required: true }))
      .toBe('/admin')
  })

  it('管理员 + diagnostic_required=false → /admin', () => {
    expect(resolveLandingRoute({ role: 'admin', diagnostic_required: false }))
      .toBe('/admin')
  })

  it('角色缺失 → 按学生处理（与后端 register 只建 student 一致）', () => {
    expect(resolveLandingRoute({})).toBe('/')
    expect(resolveLandingRoute({ diagnostic_required: true })).toBe('/diagnostic/start')
    expect(resolveLandingRoute(null)).toBe('/')
  })
})
