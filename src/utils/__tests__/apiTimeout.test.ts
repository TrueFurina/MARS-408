import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { api, ttsSynthesize, ApiError } from '@/utils/api'
import { setupApiTestEnv, hangingFetchImpl, type ApiTestEnv } from './helpers/apiTestEnv'

// 防回归：请求超时是「后端挂起时页面不永久 loading」的唯一保障。
//
// 本文件覆盖两条不同层次的语义：
//   · `request()`（JSON 接口）—— 超时属**可重试**类，与 502/503/504 同等；
//   · 其余四条链路 —— 超时必须按各自既有契约落地，不能一律抛出：
//       postStream → 抛 ApiError（用户主动中断则原样抛 AbortError）
//       upload     → 抛 ApiError
//       getBlob / postBlob → **不抛异常**，按 ok:false + status 0 返回
//       ttsSynthesize      → **不抛异常**，返回 null 让调用方降级到浏览器语音
//
// 公共桩在文件级装配：两个 describe 用同一套 fetch/localStorage/假定时器，
// 各自内联会被 pre-push gate [4] 判为新增克隆块（实测命中过）。
let env: ApiTestEnv
let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  env = setupApiTestEnv()
  fetchMock = env.fetchMock
  fetchMock.mockImplementation(hangingFetchImpl)
})

afterEach(() => {
  env.cleanup()
})

describe('api request 超时保护', () => {
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
    fetchMock
      .mockImplementationOnce(hangingFetchImpl)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ recovered: true }),
      })

    const promise = api.get('/flaky')
    await vi.runAllTimersAsync()
    const result = await promise

    expect(result).toEqual({ recovered: true })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})

describe('api 各链路超时契约', () => {
  it('getBlob 超时不抛异常，返回 ok:false / status 0', async () => {
    const promise = api.getBlob('/export')
    await vi.runAllTimersAsync()
    const result = await promise

    expect(result.ok).toBe(false)
    expect(result.status).toBe(0)
  })

  it('postBlob 超时不抛异常，返回 ok:false / status 0', async () => {
    const promise = api.postBlob('/render', { id: 1 })
    await vi.runAllTimersAsync()
    const result = await promise

    expect(result.ok).toBe(false)
    expect(result.status).toBe(0)
  })

  it('ttsSynthesize 超时返回 null（调用方据此降级到浏览器语音）', async () => {
    const promise = ttsSynthesize('你好')
    await vi.runAllTimersAsync()
    const result = await promise

    expect(result).toBeNull()
  })

  it('upload 超时抛 ApiError 且 status 为 0', async () => {
    let caught: unknown = null
    const promise = api.upload('/upload', new FormData()).catch((e: unknown) => { caught = e })
    await vi.runAllTimersAsync()
    await promise

    expect(caught).toBeInstanceOf(ApiError)
    expect((caught as ApiError).status).toBe(0)
    expect((caught as ApiError).message).toContain('请求超时')
  })

  it('postStream 连接阶段超时抛 ApiError', async () => {
    let caught: unknown = null
    const promise = api.postStream('/stream', { q: 1 }).catch((e: unknown) => { caught = e })
    await vi.runAllTimersAsync()
    await promise

    expect(caught).toBeInstanceOf(ApiError)
    expect((caught as ApiError).message).toContain('请求超时')
  })

  it('postStream 传了调用方 signal 时不接管超时（长对话不被 30s 掐断）', async () => {
    const ac = new AbortController()
    void api.postStream('/stream', { q: 1 }, ac.signal).catch(() => { /* 本用例只验信号透传 */ })

    await vi.advanceTimersByTimeAsync(60_000)

    // 原样透传调用方 signal ⇒ 内部没有另建 AbortController 与计时器
    expect(fetchMock.mock.calls[0][1].signal).toBe(ac.signal)
    expect(vi.getTimerCount()).toBe(0)
  })
})

// 防回归：默认 30s 是按普通接口定的，带 LLM 深度推理的慢接口必须能显式放宽。
// 若这条能力失效，那些接口会从「慢但能成」变成「必然超时」——比不加超时更糟。
describe('单次请求可覆盖超时', () => {
  it('timeoutMs 覆盖默认值：阈值与文案同步变化', async () => {
    let caught: unknown = null
    const promise = api.get('/slow', { timeoutMs: 10_000 }).catch((e: unknown) => { caught = e })

    await vi.runAllTimersAsync()
    await promise

    expect(caught).toBeInstanceOf(ApiError)
    // 文案里的秒数取自实际生效的阈值，不是写死的 30
    expect((caught as ApiError).message).toContain('10 秒')
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('timeoutMs=0 表示不设超时，长任务完全交给调用方 signal', async () => {
    const ac = new AbortController()
    let settled = false
    void api.get('/long', { timeoutMs: 0, signal: ac.signal }).catch(() => { settled = true })

    await vi.advanceTimersByTimeAsync(300_000)

    expect(settled).toBe(false) // 5 分钟也不超时
    expect(fetchMock.mock.calls[0][1].signal).toBe(ac.signal)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('传 signal 时不叠加内部计时器（避免两个 AbortController 抢同一请求）', async () => {
    const ac = new AbortController()
    void api.get('/with-signal', { signal: ac.signal }).catch(() => { /* 只验接线 */ })

    expect(fetchMock.mock.calls[0][1].signal).toBe(ac.signal)
    expect(vi.getTimerCount()).toBe(0)
  })
})
