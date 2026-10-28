/**
 * API 测试公共桩（测试专用，不进生产包）。
 *
 * 为什么抽出来：`apiRetry.test.ts` 与 `apiTimeout.test.ts` 都需要同一套
 * 「可控 fetch + 无 token 的 localStorage + 假定时器」环境，各自内联一份会被
 * pre-push 的克隆检测判为新增重复区域（gate [4] 实测命中）。
 * 与其在基线里加豁免，不如把这段样板收成一处 —— 豁免会掩盖后续真正的重复。
 */
import { vi } from 'vitest'

export interface ApiTestEnv {
  /** 可随时 mockResolvedValue / mockImplementation 的 fetch 桩 */
  fetchMock: ReturnType<typeof vi.fn>
  /** 复原全局桩与定时器（务必在 afterEach 调用，否则会污染同文件其它用例） */
  cleanup: () => void
}

/**
 * 永不返回、只在 abort 时 reject 的 fetch 实现 —— 模拟「连上了但服务端不响应」。
 *
 * 单列在公共桩里而不是各测试内联：两个超时测试文件都需要它，内联会构成
 * 逐字重复（pre-push gate [4] 会判为新增克隆块）。
 */
export function hangingFetchImpl(_url: string, init?: RequestInit): Promise<Response> {
  return new Promise((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => {
      const err = new Error('The operation was aborted.')
      err.name = 'AbortError'
      reject(err)
    })
  })
}

/**
 * @param useFakeTimers 是否需要假定时器。重试退避与超时都依赖 setTimeout，
 *   不装假定时器会让用例真的等 30s。
 */
export function setupApiTestEnv(useFakeTimers = true): ApiTestEnv {
  const fetchMock = vi.fn()
  ;(globalThis as any).fetch = fetchMock
  // 恒无 token：避免用例意外走到鉴权分支（getAuthHeaders 会读 localStorage）
  ;(globalThis as any).localStorage = { getItem: () => null }
  if (useFakeTimers) vi.useFakeTimers()

  return {
    fetchMock,
    cleanup() {
      if (useFakeTimers) vi.useRealTimers()
      vi.restoreAllMocks()
      delete (globalThis as any).fetch
      delete (globalThis as any).localStorage
    },
  }
}
