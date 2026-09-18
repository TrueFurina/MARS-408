import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { getAuthHeaders, ApiError, friendlyError } from '@/utils/api'

// getAuthHeaders 依赖 localStorage（vitest node 环境默认无），先 mock
function mockLocalStorage(store: Record<string, string>) {
  ;(globalThis as any).localStorage = {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v },
    removeItem: (k: string) => { delete store[k] },
  }
}

describe('getAuthHeaders Token 注入', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    delete (globalThis as any).localStorage
  })

  it('有 token 时注入 Authorization Bearer', () => {
    mockLocalStorage({ mars408_token: 'tok-123' })
    const headers = getAuthHeaders()
    expect(headers['Authorization']).toBe('Bearer tok-123')
  })

  it('无 token 时返回空 headers', () => {
    mockLocalStorage({})
    const headers = getAuthHeaders()
    expect(headers['Authorization']).toBeUndefined()
  })

  it('localStorage 不可用时安全降级（不抛异常）', () => {
    delete (globalThis as any).localStorage
    expect(() => getAuthHeaders()).not.toThrow()
    expect(getAuthHeaders()).toEqual({})
  })
})

describe('ApiError 结构', () => {
  it('携带 status/code/message', () => {
    const err = new ApiError(429, 'too many', 'RATE_LIMITED')
    expect(err.status).toBe(429)
    expect(err.code).toBe('RATE_LIMITED')
    expect(err.message).toBe('too many')
    expect(err.name).toBe('ApiError')
    expect(err).toBeInstanceOf(Error)
  })

  it('code 可选', () => {
    const err = new ApiError(500, 'internal')
    expect(err.code).toBeUndefined()
  })
})

describe('friendlyError 与 ApiError 联动', () => {
  it('ApiError 429 映射频率限制提示', () => {
    expect(friendlyError(new ApiError(429, 'Too Many Requests'), 'fb')).toBe('操作过于频繁，请稍后再试')
  })
  it('ApiError 500 映射服务器错误提示', () => {
    expect(friendlyError(new ApiError(500, 'Internal Server Error'), 'fb')).toBe('服务器内部错误，请稍后重试')
  })
})
