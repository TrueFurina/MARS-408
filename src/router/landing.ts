/**
 * 登录落点解析（F1 守护 · 2026-10-14 从 LoginView.vue 提取为纯函数）
 *
 * 历史缺陷（浏览器走查实测，2026-10-14）：原逻辑把角色判断放在
 * `diagnostic_required` 之后 —— 教师无画像 ⇒ diagnostic_required=true ⇒
 * 登录后被送进学生入学测评（/diagnostic/start）；admin 同受害。
 *
 * 修复口径：**先按角色定首页，仅 student 才可能走测评**。
 * 提取为纯函数使该口径可被单测守护（见 src/router/landing.spec.ts），
 * 避免下次重构 LoginView 时静默回退。
 */

export type LandingUser = {
  role?: string | null
  diagnostic_required?: boolean | null
}

/** 解析登录后的首跳路由。角色缺失按学生处理（后端 register 只建 student）。 */
export function resolveLandingRoute(user: LandingUser | null | undefined): string {
  const role = user?.role || 'student'
  const home = role === 'admin' ? '/admin' : (role === 'teacher' ? '/teacher' : '/')
  return role === 'student' && user?.diagnostic_required ? '/diagnostic/start' : home
}
