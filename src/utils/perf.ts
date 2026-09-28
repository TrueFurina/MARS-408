/**
 * 交互性能工具：防抖 / 节流。
 *
 * 用途：把"高频触发但代价高昂"的回调（输入框逐字重绘、窗口 resize、滚动计算）
 * 收敛成低频执行，直接改善 INP（Interaction to Next Paint）。
 *
 * 设计约束：
 * - 返回函数带 `cancel()`（避免组件卸载后还执行）与 `flush()`（立即补一次末次调用）。
 * - 纯函数、无 Vue 依赖，可在任意 TS 上下文单测。
 */

export interface Cancelable {
  cancel(): void
  flush(): void
}

export type CancelableFn<A extends unknown[]> = ((...args: A) => void) & Cancelable

/** 防抖：最后一次调用后等待 wait 毫秒才真正执行；期间的新调用重置计时。 */
export function debounce<A extends unknown[]>(
  fn: (...args: A) => void,
  wait: number,
): CancelableFn<A> {
  let timer: ReturnType<typeof setTimeout> | null = null
  let lastArgs: A | null = null

  const debounced = (...args: A): void => {
    lastArgs = args
    if (timer !== null) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      if (lastArgs) fn(...lastArgs)
    }, wait)
  }

  debounced.cancel = (): void => {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  debounced.flush = (): void => {
    if (timer !== null && lastArgs) {
      clearTimeout(timer)
      timer = null
      fn(...lastArgs)
    }
  }

  return debounced
}

/** 节流：每 wait 毫秒最多执行一次；尾沿调用通过定时器补齐，避免丢末次。 */
export function throttle<A extends unknown[]>(
  fn: (...args: A) => void,
  wait: number,
): CancelableFn<A> {
  let last = 0
  let timer: ReturnType<typeof setTimeout> | null = null
  let lastArgs: A | null = null

  const throttled = (...args: A): void => {
    const now = Date.now()
    const remaining = wait - (now - last)
    lastArgs = args
    if (remaining <= 0) {
      if (timer !== null) {
        clearTimeout(timer)
        timer = null
      }
      last = now
      fn(...lastArgs)
    } else if (timer === null) {
      timer = setTimeout(() => {
        last = Date.now()
        timer = null
        if (lastArgs) fn(...lastArgs)
      }, remaining)
    }
  }

  throttled.cancel = (): void => {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  throttled.flush = (): void => {
    if (timer !== null && lastArgs) {
      clearTimeout(timer)
      timer = null
      last = Date.now()
      fn(...lastArgs)
    }
  }

  return throttled
}
