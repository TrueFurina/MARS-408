import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { debounce, throttle } from '@/utils/perf'

describe('debounce', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('只在等待期结束后执行最后一次调用', () => {
    const fn = vi.fn()
    const d = debounce(fn, 100)
    d()
    d()
    d()
    expect(fn).not.toHaveBeenCalled()
    vi.advanceTimersByTime(99)
    expect(fn).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('把末次调用的参数透传给回调', () => {
    const fn = vi.fn()
    const d = debounce(fn, 100)
    d('a')
    d('b')
    d('c')
    vi.advanceTimersByTime(100)
    expect(fn).toHaveBeenCalledTimes(1)
    expect(fn).toHaveBeenCalledWith('c')
  })

  it('cancel 阻止待执行调用', () => {
    const fn = vi.fn()
    const d = debounce(fn, 100)
    d()
    d.cancel()
    vi.advanceTimersByTime(100)
    expect(fn).not.toHaveBeenCalled()
  })

  it('flush 立即补一次末次调用', () => {
    const fn = vi.fn()
    const d = debounce(fn, 100)
    d('x')
    d.flush()
    expect(fn).toHaveBeenCalledTimes(1)
    expect(fn).toHaveBeenCalledWith('x')
    vi.advanceTimersByTime(100)
    expect(fn).toHaveBeenCalledTimes(1) // 已执行，定时器不再重复
  })
})

describe('throttle', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('首次调用立即执行，等待期内后续调用被收敛', () => {
    const fn = vi.fn()
    const t = throttle(fn, 100)
    t() // 立即
    t() // 收敛
    t() // 收敛
    expect(fn).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(100)
    expect(fn).toHaveBeenCalledTimes(2) // 尾沿补齐一次
  })

  it('超过等待期后可再次立即执行', () => {
    const fn = vi.fn()
    const t = throttle(fn, 100)
    t()
    vi.advanceTimersByTime(100)
    t()
    expect(fn).toHaveBeenCalledTimes(2)
  })

  it('cancel 阻止尾沿补齐', () => {
    const fn = vi.fn()
    const t = throttle(fn, 100)
    t()
    t.cancel()
    vi.advanceTimersByTime(100)
    expect(fn).toHaveBeenCalledTimes(1)
  })
})
