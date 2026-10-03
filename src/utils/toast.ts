/**
 * 全局 Toast 调用入口（单一真值源）。
 *
 * `window.__toast` 由 `ToastNotification` 组件在挂载时注入，提供
 * success / error / info / warning 四个方法。组件尚未挂载（极早期）时降级为
 * console 输出，避免提示静默丢失。
 *
 * 背景：此前 AchievementView / DailyPlanView / WrongQuestionsView 各自维护一份
 * 相同的 toast 逻辑（其中两份逐字重复），且当 `__toast` 缺失时会 dispatch 一个
 * **无人监听**的旧自定义事件 —— 该兜底既无效、又残留已废弃的旧品牌名。
 * 此处统一收口为单一工具函数。
 */
export type ToastType = 'success' | 'error' | 'info' | 'warning'

export function toast(type: ToastType | string, message: string): void {
  const t = (window as any).__toast
  if (t?.[type]) {
    t[type](message)
    return
  }
  // 组件未挂载时的兜底：留下可诊断记录（不再 dispatch 无人监听的事件）
  console.warn(`[toast:${type}] ${message}`)
}
