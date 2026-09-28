import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { prefetchRoute, schedulePrefetch, cancelPrefetch, __resetPrefetchCache } from '@/utils/routePrefetch'

/**
 * 构造一个最小可用的 Router 替身：只需要 resolve() 返回 matched 记录。
 * 这里刻意不使用真实 router —— 本单元只验证「预取调度」行为，
 * 与路由表具体内容解耦，避免路由变更导致测试脆断。
 */
function makeRouter(records: Array<{ components: Record<string, unknown> }>) {
  return {
    resolve: vi.fn(() => ({ matched: records })),
  } as never
}

/** lazy 组件工厂，记录被调用次数 */
function lazy() {
  const fn = vi.fn(() => Promise.resolve({ default: {} }))
  return fn
}

describe('routePrefetch', () => {
  beforeEach(() => {
    __resetPrefetchCache()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    __resetPrefetchCache()
  })

  it('预取会调用惰性路由组件工厂（触发 chunk 下载）', () => {
    const comp = lazy()
    const router = makeRouter([{ components: { default: comp } }])
    prefetchRoute(router, '/knowledge')
    expect(comp).toHaveBeenCalledTimes(1)
  })

  it('同一路径只预取一次（重复悬停不再发请求）', () => {
    const comp = lazy()
    const router = makeRouter([{ components: { default: comp } }])
    prefetchRoute(router, '/knowledge')
    prefetchRoute(router, '/knowledge')
    prefetchRoute(router, '/knowledge')
    expect(comp).toHaveBeenCalledTimes(1)
  })

  it('嵌套路由会一并预取父级与子级组件', () => {
    const parent = lazy()
    const child = lazy()
    const router = makeRouter([
      { components: { default: parent } },
      { components: { default: child } },
    ])
    prefetchRoute(router, '/knowledge/detail')
    expect(parent).toHaveBeenCalledTimes(1)
    expect(child).toHaveBeenCalledTimes(1)
  })

  it('静态（非函数）组件不会被误当作工厂调用', () => {
    const staticComp = { template: '<div/>' }
    const router = makeRouter([{ components: { default: staticComp } }])
    expect(() => prefetchRoute(router, '/x')).not.toThrow()
  })

  it('预取失败静默：工厂抛错不得冒泡影响交互', () => {
    const bad = vi.fn(() => Promise.reject(new Error('chunk load failed')))
    const router = makeRouter([{ components: { default: bad } }])
    expect(() => prefetchRoute(router, '/broken')).not.toThrow()
    expect(bad).toHaveBeenCalled()
  })

  it('schedulePrefetch 精确延迟 120ms：119ms 未触发，第 120ms 才触发', () => {
    // ⚠️ 这个断言是刻意的边界写法。若只写「advanceTimersByTime(120) 后已调用」，
    // 那么把 PREFETCH_DELAY_MS 改成 0 也能通过（fake timers 下 0ms 同样要手动推进），
    // 测试就变成了假绿 —— 无法真正锁住"防抖延迟"这个行为。
    const comp = lazy()
    const router = makeRouter([{ components: { default: comp } }])
    schedulePrefetch(router, '/practice')
    vi.advanceTimersByTime(119)
    expect(comp).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(comp).toHaveBeenCalledTimes(1)
  })

  it('鼠标快速划过（提前离开）会取消预取，不产生请求', () => {
    const comp = lazy()
    const router = makeRouter([{ components: { default: comp } }])
    schedulePrefetch(router, '/practice')
    cancelPrefetch()
    vi.advanceTimersByTime(500)
    expect(comp).not.toHaveBeenCalled()
  })

  it('Save-Data 开启时完全不预取', () => {
    const original = Object.getOwnPropertyDescriptor(navigator, 'connection')
    Object.defineProperty(navigator, 'connection', {
      configurable: true,
      value: { saveData: true, effectiveType: '4g' },
    })
    try {
      const comp = lazy()
      const router = makeRouter([{ components: { default: comp } }])
      prefetchRoute(router, '/knowledge')
      vi.advanceTimersByTime(500)
      expect(comp).not.toHaveBeenCalled()
    } finally {
      if (original) Object.defineProperty(navigator, 'connection', original)
      else delete (navigator as unknown as Record<string, unknown>).connection
    }
  })

  it('2G 弱网下不预取', () => {
    const original = Object.getOwnPropertyDescriptor(navigator, 'connection')
    Object.defineProperty(navigator, 'connection', {
      configurable: true,
      value: { saveData: false, effectiveType: 'slow-2g' },
    })
    try {
      const comp = lazy()
      const router = makeRouter([{ components: { default: comp } }])
      prefetchRoute(router, '/knowledge')
      expect(comp).not.toHaveBeenCalled()
    } finally {
      if (original) Object.defineProperty(navigator, 'connection', original)
      else delete (navigator as unknown as Record<string, unknown>).connection
    }
  })

  it('空路径是安全的空操作', () => {
    const router = makeRouter([{ components: { default: lazy() } }])
    expect(() => prefetchRoute(router, '')).not.toThrow()
    expect((router as unknown as { resolve: { mock: { calls: unknown[] } } }).resolve).not.toHaveBeenCalled()
  })
})
