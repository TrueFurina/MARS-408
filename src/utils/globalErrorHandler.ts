/**
 * 全局错误兜底（WS5-3.1 前端健壮性）
 *
 * 为什么需要：`components/ErrorBoundary.vue` 通过 `onErrorCaptured` 只能捕获
 * **同步**渲染 / setup 阶段抛出的错误。以下三类错误完全绕过它：
 *   1. 事件处理器里未被 catch 的 rejected promise（`onClick` 里的 `await`）；
 *   2. `setTimeout` / `queueMicrotask` 回调里抛出的错误；
 *   3. 组件树之外的模块级代码抛错。
 * 这类错误在界面上表现为「点了没反应」「某块区域一直空着」，控制台有报错但
 * 用户与验收者都无从定位 —— 正是「异常不可恢复」的典型形态。
 *
 * 本模块把三类全局钩子收敛到一处，统一 console 记录 + 用户可见提示：
 *   · `app.config.errorHandler`   —— 组件渲染 / 生命周期 / watcher 内抛错
 *   · `window.unhandledrejection` —— 未 catch 的 promise
 *   · `window.error`              —— 脚本运行时错误（**排除**资源加载失败）
 *
 * 设计约束（勿随意改动）：
 *   · **不吞错**：仍然 `console.error` 输出原始对象，方便排查；不调用
 *     `preventDefault()` 掩盖浏览器原生报错。
 *   · **不重复轰炸**：同一文案 5s 内只提示一次。并发请求同时失败时，若不节流
 *     会叠出十几条一模一样的 toast，反而盖住真正有用的信息。
 *   · **资源加载错误不提示**：`<img>`/`<script>` 等资源 404 属降级而非崩溃，
 *     提示给用户没有可操作价值。这类事件规范上不冒泡，当前冒泡阶段监听本就
 *     收不到；处理函数里仍保留 target 判断，作为将来改 capture 监听时的护栏。
 */

import type { App } from 'vue'
import { toast } from './toast'
import { errMessage } from './errorMessage'

/** 同一文案的提示节流窗口（ms） */
const DEDUPE_WINDOW_MS = 5000
/** 节流表容量上限：异常风暴时不无限增长（超限直接清空，宁可多提示一次） */
const DEDUPE_MAX_ENTRIES = 50

const lastShownAt = new Map<string, number>()

/**
 * 把任意抛出物转成一句可展示的文案。
 *
 * 与 `errMessage` 的**刻意差异**：这里保留「裸字符串直接当文案」的行为。
 * 全局错误提示是最后一道兜底，此时 `throw '后端 502'` 里的字符串往往就是
 * 唯一线索，显示它比显示「页面出现异常」有用；
 * 而页面内嵌的错误态（走 `errMessage`）面对的是普通用户，裸调试串不如中文兜底。
 * 两处语义不同是**有意为之**，各自有用例锁定，改动前先看对应用例。
 */
export function describeError(err: unknown, fallback = '页面出现异常，请重试'): string {
  if (typeof err === 'string' && err.trim()) return err.trim()
  return errMessage(err, fallback)
}

/**
 * 是否应当向用户提示（节流判断，命中则登记时间戳）。
 * 导出仅为单测可验证节流语义，业务代码不应直接调用。
 */
export function shouldNotify(message: string, now = Date.now()): boolean {
  const last = lastShownAt.get(message)
  if (last !== undefined && now - last < DEDUPE_WINDOW_MS) return false
  if (lastShownAt.size >= DEDUPE_MAX_ENTRIES) lastShownAt.clear()
  lastShownAt.set(message, now)
  return true
}

/** 仅测试使用：清空节流表 */
export function resetNotifyThrottle(): void {
  lastShownAt.clear()
}

function report(scope: string, err: unknown): void {
  console.error(`[global-error:${scope}]`, err)
  const message = describeError(err)
  if (shouldNotify(message)) toast('error', message)
}

/**
 * 安装全局错误钩子。返回卸载函数（单测 / HMR 场景可复原，
 * 避免重复 mount 时叠加多份监听器）。
 */
export function installGlobalErrorHandlers(app: App): () => void {
  app.config.errorHandler = (err, _instance, info) => {
    report('vue', err)
    // info 含组件名 / 生命周期钩子名，单独打一条便于定位（不进入用户文案）
    console.error('[global-error:vue-info]', info)
  }

  const onUnhandledRejection = (event: PromiseRejectionEvent) => {
    report('promise', event.reason)
  }

  const onWindowError = (event: ErrorEvent) => {
    // 防御性判断：资源加载失败（img/script/link 404）在规范里**不冒泡**，
    // 当前以冒泡阶段注册的监听器收不到它们，所以正常情况下走不到这个分支。
    // 保留判断是为了「将来若改成 capture 监听」时也不会把资源 404 弹给用户 ——
    // 那属于降级不属崩溃，只在控制台留痕。
    if (event.target && event.target !== window) {
      console.warn('[global-error:resource]', (event.target as EventTarget & { src?: string }).src || event.target)
      return
    }
    report('window', event.error ?? event.message)
  }

  window.addEventListener('unhandledrejection', onUnhandledRejection)
  window.addEventListener('error', onWindowError)

  return () => {
    window.removeEventListener('unhandledrejection', onUnhandledRejection)
    window.removeEventListener('error', onWindowError)
  }
}
