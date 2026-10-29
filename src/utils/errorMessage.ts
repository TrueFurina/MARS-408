/**
 * 从「抛出物」里安全取错误文案。
 *
 * 为什么需要：`catch (e: any)` 曾经让 `e?.message` 一路畅通，但它掩盖了一个真实
 * 缺陷 —— 抛出来的**不一定是 Error**。后端可能抛字符串、SDK 可能抛普通对象、
 * Promise 可能 reject 一个数字。此时 `e?.message` 静默得到 `undefined`，
 * 于是用户看到的是兜底文案，排查时也拿不到真实原因。
 *
 * 把 catch 变量改回 `unknown`（strict 下 `catch (e)` 的默认类型）后，这类访问
 * 会被 tsc 拦住；本函数就是那个"显式收口"的地方：所有形态都尝试取一次，
 * 取不到才用调用方给的兜底。
 *
 * 与 `friendlyError()` 的分工（别混用）：
 *   · `errMessage`  —— 只做取值，**不改写**文案。适合日志、内部错误态、
 *                      以及已经把文案交给上层映射的场景。
 *   · `friendlyError` —— 会把网络/401/404 等技术错误**翻译成用户能看懂的话**，
 *                      适合直接展示给用户。它在内部也走本函数取值。
 */

/** 取错误文案；`fallback` 在取不到时返回 */
export function errMessage(e: unknown, fallback = '操作失败'): string {
  if (e instanceof Error) return e.message || fallback
  // 注意：**不把裸字符串当文案**。`throw 'boom'` 是开发者留给自己的调试串，
  // 直接显示给用户比中文兜底更糟；原始值仍由调用方的 console.error(e) 保留。
  // 这条契约由 src/views/__tests__/masteryMapView.spec.ts 的
  // 「失败对象没有 message 时回退到默认文案」用例锁定，改动前先看那条用例。
  if (e && typeof e === 'object') {
    const m = (e as { message?: unknown }).message
    if (typeof m === 'string' && m.trim()) return m.trim()
  }
  return fallback
}

/** 判断是否「用户主动中断」（AbortController.abort 引起的 AbortError）。 */
export function isAbortError(e: unknown): boolean {
  return !!e && typeof e === 'object' && (e as { name?: unknown }).name === 'AbortError'
}
