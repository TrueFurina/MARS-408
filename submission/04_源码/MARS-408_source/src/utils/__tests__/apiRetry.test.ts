import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { api } from '@/utils/api'

// 防回归：request 重试逻辑是前端容错核心。
// 502/503/504 重试（指数退避）、4xx 不重试（立即抛错）、网络错误重试。
describe('api request 重试逻辑', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
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

  function jsonResponse(status: number, body: unknown) {
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
    }
  }

  it('200 成功直接返回数据', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { data: 1 }))
    const result = await api.get('/test')
    expect(result).toEqual({ data: 1 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('502/503/504 自动重试后成功（最多 retries 次）', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(503, { detail: 'temp' }))
      .mockResolvedValueOnce(jsonResponse(503, { detail: 'temp' }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }))

    const promise = api.get('/retry')
    await vi.runAllTimersAsync()
    const result = await promise
    expect(result).toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledTimes(3) // 初始 + 2 次重试
  })

  it('持续 503 超出重试次数后抛 ApiError', async () => {
    fetchMock.mockResolvedValue(jsonResponse(503, { detail: 'still down' }))
    // 先挂 catch 捕获 rejection，避免 Vitest unhandled rejection 警告（promise 创建与 handler 挂载的时序窗口）
    let caught: unknown = null
    const promise = api.get('/down').catch((e: unknown) => { caught = e })
    await vi.runAllTimersAsync()
    await promise
    expect(caught).toBeInstanceOf(Error)
    expect((caught as Error)?.message).toContain('still down')
    expect(fetchMock).toHaveBeenCalledTimes(3) // 初始 + 2 次重试
  })

  it('4xx 不重试（立即抛错，仅 1 次请求）', async () => {
    fetchMock.mockResolvedValue(jsonResponse(404, { detail: 'not found' }))
    await expect(api.get('/missing')).rejects.toThrow('not found')
    expect(fetchMock).toHaveBeenCalledTimes(1) // 4xx 不重试
  })

  it('网络错误（Failed to fetch）重试后成功', async () => {
    fetchMock
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }))

    const promise = api.get('/network')
    await vi.runAllTimersAsync()
    const result = await promise
    expect(result).toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
