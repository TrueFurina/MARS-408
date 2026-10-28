import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { api, ApiError } from '@/utils/api'

// 防回归：请求超时是「后端挂起时页面不永久 loading」的唯一保障。
// 语义要求：① 超时按可重试处理（与 502/503/504 同等），不是一次性失败；
// ② 最终抛出的文案可读（不能把 AbortError 原样甩给用户）；
// ③ 成功路径必须清掉计时器，否则 30s 后会对已完成请求补一次 abort。
describe('api request 超时保护', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  /** 永不返回、只在 abort 时 reject 的 fetch —— 模拟「连上了但服务端不响应」 */
  function hangingFetch() {
    return vi.fn(
      (_url: string, init?: RequestInit) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            const err = new Error('The operation was aborted.')
            err.name = 'AbortError'
            reject(err)
          })
        }),
    )
  }

  beforeEach(() => {
    fetchMock = hangingFetch()
    ;(globalThis as any).fetch = fetchMock
    ;(globalThis as any).localStorage = { getItem: () => null }
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    delete (globalThis as any).fetch
    delete (globalThis as any).localStorage
  })

  it('挂起请求超时后重试，3 次尝试后抛可读超时文案', async () => {
    let caught: unknown = null
    const promise = api.get('/hang').catch((e: unknown) => { caught = e })

    await vi.runAllTimersAsync()
    await promise

    expect(caught).toBeInstanceOf(ApiError)
    expect((caught as ApiError).message).toContain('请求超时')
    // 初始 1 次 + 2 次重试
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('超时错误不是 AbortError 原文（用户看不懂 DOMException）', async () => {
    let caught: unknown = null
    const promise = api.get('/hang').catch((e: unknown) => { caught = e })

    await vi.runAllTimersAsync()
    await promise

    expect((caught as Error).name).toBe('ApiError')
    expect((caught as Error).message).not.toContain('aborted')
  })

  it('成功路径会清掉超时计时器（不对已完成请求补发 abort）', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: 1 }),
    })

    const result = await api.get('/fast')

    expect(result).toEqual({ ok: 1 })
    expect(vi.getTimerCount()).toBe(0)
  })

  it('超时后若下一次尝试成功则正常返回（超时属可重试类）', async () => {
    fetchMock = vi
      .fn()
      .mockImplementationOnce((_url: string, init?: RequestInit) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            const err = new Error('The operation was aborted.')
            err.name = 'AbortError'
            reject(err)
          })
        }),
      )
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ recovered: true }),
      })
    ;(globalThis as any).fetch = fetchMock

    const promise = api.get('/flaky')
    await vi.runAllTimersAsync()
    const result = await promise

    expect(result).toEqual({ recovered: true })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
