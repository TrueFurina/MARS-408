import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  describeError,
  shouldNotify,
  resetNotifyThrottle,
  installGlobalErrorHandlers,
} from '@/utils/globalErrorHandler'

// 防回归：全局错误兜底是「异常可恢复」的最后一道网。
// 三条语义必须锁死：① 错误文案可读；② 同文案节流（并发失败不轰炸）；
// ③ 装/卸成对（HMR 与重复 mount 不叠加监听器）。
describe('describeError 文案归一', () => {
  it('Error 取 message', () => {
    expect(describeError(new Error('boom'))).toBe('boom')
  })

  it('字符串原样返回（去掉首尾空白）', () => {
    expect(describeError('  网络异常  ')).toBe('网络异常')
  })

  it('空字符串 / null / undefined 回落到 fallback', () => {
    expect(describeError('', '兜底')).toBe('兜底')
    expect(describeError(null, '兜底')).toBe('兜底')
    expect(describeError(undefined, '兜底')).toBe('兜底')
  })

  it('类 Error 对象（带 message 字段）也能取到文案', () => {
    expect(describeError({ message: '伪错误' })).toBe('伪错误')
  })
})

describe('shouldNotify 节流', () => {
  beforeEach(() => resetNotifyThrottle())

  it('首次放行，窗口内重复拦截', () => {
    expect(shouldNotify('同一条错误', 1000)).toBe(true)
    expect(shouldNotify('同一条错误', 1000 + 100)).toBe(false)
    expect(shouldNotify('同一条错误', 1000 + 4999)).toBe(false)
  })

  it('超过 5s 窗口后重新放行', () => {
    expect(shouldNotify('同一条错误', 1000)).toBe(true)
    expect(shouldNotify('同一条错误', 1000 + 5000)).toBe(true)
  })

  it('不同文案互不影响', () => {
    expect(shouldNotify('A', 1000)).toBe(true)
    expect(shouldNotify('B', 1001)).toBe(true)
  })
})

describe('installGlobalErrorHandlers 接线', () => {
  let errorSpy: ReturnType<typeof vi.spyOn>
  let toastError: ReturnType<typeof vi.fn>
  let uninstall: (() => void) | null = null

  beforeEach(() => {
    resetNotifyThrottle()
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    toastError = vi.fn()
    ;(window as any).__toast = { error: toastError, success: vi.fn(), info: vi.fn(), warning: vi.fn() }
  })

  afterEach(() => {
    uninstall?.()
    uninstall = null
    delete (window as any).__toast
    vi.restoreAllMocks()
  })

  it('未捕获的 promise rejection 会留痕并提示用户', () => {
    const app = { config: {} } as any
    uninstall = installGlobalErrorHandlers(app)

    const ev = new Event('unhandledrejection') as Event & { reason?: unknown }
    ev.reason = new Error('异步炸了')
    window.dispatchEvent(ev)

    expect(errorSpy).toHaveBeenCalled()
    expect(toastError).toHaveBeenCalledWith('异步炸了')
  })

  it('app.config.errorHandler 接住组件内错误', () => {
    const app = { config: {} } as any
    uninstall = installGlobalErrorHandlers(app)

    expect(typeof app.config.errorHandler).toBe('function')
    app.config.errorHandler(new Error('组件内错误'), null, 'render function')

    expect(toastError).toHaveBeenCalledWith('组件内错误')
  })

  it('同一文案在节流窗口内只提示一次（并发失败不轰炸）', () => {
    const app = { config: {} } as any
    uninstall = installGlobalErrorHandlers(app)

    const boom = () => {
      const ev = new Event('unhandledrejection') as Event & { reason?: unknown }
      ev.reason = new Error('并发失败')
      window.dispatchEvent(ev)
    }
    boom()
    boom()
    boom()

    expect(toastError).toHaveBeenCalledTimes(1)
  })

  it('卸载后不再响应（避免 HMR / 重复 mount 叠加监听器）', () => {
    const app = { config: {} } as any
    uninstall = installGlobalErrorHandlers(app)
    uninstall()
    uninstall = null

    const ev = new Event('unhandledrejection') as Event & { reason?: unknown }
    ev.reason = new Error('卸载后的错误')
    window.dispatchEvent(ev)

    expect(toastError).not.toHaveBeenCalled()
  })
})
