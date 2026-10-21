import { describe, it, expect, beforeEach, vi } from 'vitest'
import { api, getAuthHeaders, ttsSynthesize } from './api'

// ============================================================
// 契约测试：**所有**认证请求必须同时携带 X-App-Token 与 Authorization。
//
// 为什么是双头而不是一个：
//   CloudStudio 发布网关会把 Authorization 替换成平台身份 token（2026-10-15 实测），
//   只有自定义头 X-App-Token 原样透传 ⇒ 后端 get_current_user 双头都读、任一有效即认。
//   漏掉 X-App-Token 的请求在**本地**完全正常（本地无网关，Authorization 直达后端），
//   一上线就稳定 401 —— 这类缺陷本地永远绿、线上功能死。
//
// 真实案例（2026-10-21 线上只读巡检抓到的）：
//   getBlob（导出一页纸报告）只带了 Authorization ⇒ 线上 401，
//   且 handleUnauthorized 会把用户**踢到登录页**（比"功能坏"更严重的 UX 事故）；
//   ttsSynthesize 同款漏头，只是它吞错降级、不登出，所以一直没人发现。
// ============================================================

const TOKEN = 'tok_e2e_dual_header'

interface Call { url: string; headers: Record<string, string> }

function mockFetchOk(): Call[] {
  const calls: Call[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url: String(url), headers: (init.headers || {}) as Record<string, string> })
    return {
      ok: true,
      status: 200,
      json: async () => ({}),
      blob: async () => new Blob(['x']),
      text: async () => '',
    } as unknown as Response
  }))
  return calls
}

/** 双头断言：任一头缺失都必须是失败，且失败信息要点名是哪个方法漏的 */
function expectDualAuthHeaders(calls: Call[], label: string) {
  expect(calls.length, `${label} 应发出一次请求`).toBe(1)
  const call = calls[0]
  if (!call) throw new Error(`${label}: 未捕获到 fetch 调用`)
  const h = call.headers
  expect(h['X-App-Token'], `${label} 必须带 X-App-Token（发布网关只透传自定义头，漏了线上必 401）`).toBe(TOKEN)
  expect(h['Authorization'], `${label} 必须同时保留 Authorization（本地/无网关环境靠它）`).toBe(`Bearer ${TOKEN}`)
}

describe('api 客户端认证头契约（X-App-Token + Authorization 双头）', () => {
  beforeEach(() => {
    localStorage.setItem('mangdehenzhi_token', TOKEN)
  })

  it('getAuthHeaders 本身产出双头（本契约的单一真值源）', () => {
    const h = getAuthHeaders()
    expect(h['X-App-Token']).toBe(TOKEN)
    expect(h['Authorization']).toBe(`Bearer ${TOKEN}`)
  })

  it('api.get / post / put / delete 全部走双头', async () => {
    let calls = mockFetchOk()
    await api.get('/career/classes')
    expectDualAuthHeaders(calls, 'api.get')

    calls = mockFetchOk()
    await api.post('/career/task/join', { join_code: 'ABC123' })
    expectDualAuthHeaders(calls, 'api.post')

    calls = mockFetchOk()
    await api.put('/x', { a: 1 })
    expectDualAuthHeaders(calls, 'api.put')

    calls = mockFetchOk()
    await api.delete('/x')
    expectDualAuthHeaders(calls, 'api.delete')
  })

  it('api.upload（FormData）走双头', async () => {
    const calls = mockFetchOk()
    await api.upload('/admin/import', new FormData())
    expectDualAuthHeaders(calls, 'api.upload')
  })

  it('api.postBlob / api.getBlob 走双头', async () => {
    let calls = mockFetchOk()
    await api.postBlob('/career/export', { a: 1 })
    expectDualAuthHeaders(calls, 'api.postBlob')

    calls = mockFetchOk()
    await api.getBlob('/career/classes/cls_x/export-report')
    expectDualAuthHeaders(calls, 'api.getBlob')
  })

  it('ttsSynthesize 走双头（含 Content-Type）', async () => {
    const calls = mockFetchOk()
    await ttsSynthesize('你好', 'zh', 'auto')
    expectDualAuthHeaders(calls, 'ttsSynthesize')
    const call = calls[0]
    if (!call) throw new Error('ttsSynthesize: 未捕获到 fetch 调用')
    expect(call.headers['Content-Type']).toBe('application/json')
  })
})
