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
 *
 * 2026-11-07 视觉走查修订：学生登录后不再强跳入学测评。
 * 原行为把 408 诊断题当作着陆页，学生第一屏看到"TCP 三次握手"，与本平台
 * 职业素养实训的定位冲突，也让人不知道自己在哪。现改为统一落平台首页 `/`，
 * 测评作为首页上的一个可选项，由学生自己决定何时开始。
 */

export type LandingUser = {
  role?: string | null
  diagnostic_required?: boolean | null
}

/** 解析登录后的首跳路由。角色缺失按学生处理（后端 register 只建 student）。 */
export function resolveLandingRoute(user: LandingUser | null | undefined): string {
  const role = user?.role || 'student'
  return role === 'admin' ? '/admin' : (role === 'teacher' ? '/teacher' : '/')
}
