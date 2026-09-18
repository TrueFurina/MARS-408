/* ============================================
 * 统一 API 客户端 — 所有请求通过此模块
 * 集中管理：Base URL、Token、错误处理
 * ============================================ */

const API_BASE = ''

/** storage key 与 authStore.loadAuth/saveAuth 使用的保持完全一致（单一真值源） */
const TOKEN_KEY = 'mars408_token'
const USER_KEY = 'mars408_user'

function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

/** 获取带 Auth Token 的请求头（供裸 fetch 调用使用） */
export function getAuthHeaders(): Record<string, string> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  return headers
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/**
 * 把后端掉线 / 代理返回 HTML 等裸错误转成友好提示
 * 全局统一使用，避免各 store/view 重复实现
 */
export function friendlyError(e: unknown, fallback: string): string {
  const msg = String((e as any)?.message || e || fallback)
  if (/Unexpected token|not valid JSON|Failed to fetch|NetworkError|ECONNREFUSED|ERR_|<!DOCTYPE/i.test(msg)) {
    return '后端服务未连接，请先运行后端服务（端口 8002）'
  }
  if (/401|Unauthorized|Invalid or expired credentials/i.test(msg)) {
    return '登录已过期，请重新登录'
  }
  if (/403|Forbidden/i.test(msg)) {
    return '没有权限执行此操作'
  }
  if (/404|Not Found/i.test(msg)) {
    return '请求的资源不存在'
  }
  if (/429|Too Many Requests|quota|limit|rate/i.test(msg)) {
    return '操作过于频繁，请稍后再试'
  }
  if (/500|Internal Server Error/i.test(msg)) {
    return '服务器内部错误，请稍后重试'
  }
  return msg || fallback
}

/* ============================================
 * 401 统一处理（登录态失效自动登出）
 * ============================================
 * 背景：路由守卫只校验 token「是否存在」，不校验有效性。token 过期后用户
 * 依然处于已登录态、能进任意页面，但每个接口都返回 401，页面只渲染一堆
 * 「加载失败 / Invalid or expired credentials」错误卡片，用户无法判断是
 * 登录过期还是系统整体坏了。
 *
 * 覆盖范围（重要：本模块**并非**所有 HTTP 的唯一出口，下面逐个列明接线状态）：
 *   已接 401 拦截（清态 + 跳登录页，且仍把真实错误抛回调用方）：
 *     · request()      —— 供 api.get/post/put/delete，覆盖绝大多数页面与 store
 *     · postStream()   —— 供对话流式输出
 *     · requestForm()  —— 供 api.upload()
 *     · postBlob()     —— 供二进制下载；只接线拦截，不改其「不抛异常、
 *                         仅返回 ok:false」的既有契约
 *   未接 401 拦截：
 *     · ttsSynthesize()—— 非 2xx 直接 return null，错误被吞（既有契约：
 *                         调用方依赖「失败返回 null → 降级到浏览器
 *                         SpeechSynthesis」，本次不动）。因此登录过期时
 *                         仅 TTS 一条链路不会触发自动登出。
 *   本文件之外的裸 fetch（若有）同样不在拦截范围内。
 *
 * 处理策略：
 *   1. 清除本地失效登录态（storage key 与 authStore 保持同一真值源）；
 *   2. 跳转登录页（已在登录页则不跳，避免重定向死循环）；
 *   3. 只清态/跳转，**不吞错误** —— 调用方仍会拿到带真实 status + detail
 *      的 ApiError，错误提示链路保持完整。
 */

/**
 * 已触发过自动登出的 token：同一 token 只跳转一次（并发请求各跳一次会打架）。
 *
 * 注意：后端 create_token 的 iat/exp 取自 int(time.time())，是**秒级**粒度，
 * 同一用户在同一秒内重新登录会得到**完全相同**的 token 字符串。因此这个
 * latch 必须在每次写入新 token 时重置，否则「自动登出 → 同秒重登」后
 * loggedOutToken === token 会命中早退，该 token 再遇 401 将永远不再跳转。
 * 重置入口见 authStore.saveAuth() 调用的 resetUnauthorizedLatch()。
 */
let loggedOutToken: string | null = null

/** 重置 401 latch —— 每次登录/注册写入新 token 时由 authStore 调用 */
export function resetUnauthorizedLatch(): void {
  loggedOutToken = null
}

function clearAuthStorage(): void {
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  } catch { /* localStorage 不可用（隐私模式等）时静默降级 */ }
}

function isLoginRoute(): boolean {
  try {
    return window.location.pathname === '/login'
  } catch {
    return false
  }
}

function handleUnauthorized(status: number): void {
  if (status !== 401) return
  const token = getToken()
  // 无 token：本来就是匿名请求（未登录/已登出），不该触发自动登出；
  // 同一 token 已处理过：说明并发请求同时 401，不再重复跳转。
  if (!token || loggedOutToken === token) return

  loggedOutToken = token
  clearAuthStorage()

  // 已在登录页（守卫把用户挡回来 / 登录页自身触发 401）→ 只清态，不再跳转
  if (isLoginRoute()) return

  // 动态引入：避免 utils 层与 router 层形成静态循环依赖
  // （stores/authStore 静态依赖本模块，静态反向依赖会成环）
  void import('@/router')
    .then((m) => m.default.replace('/login'))
    .catch(() => { /* 路由不可用时留在当前页，错误已抛给调用方展示 */ })
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  _retries = 2,
): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  let lastError: unknown
  for (let attempt = 0; attempt <= _retries; attempt++) {
    try {
      const resp = await fetch(`${API_BASE}/api${path}`, {
        ...options,
        headers,
      })

      if (!resp.ok) {
        let detail = `请求失败 (${resp.status})`
        try {
          const body = await resp.json()
          detail = body?.detail || body?.error?.message || detail
        } catch { /* ignore */ }
        // 401 → 统一清除失效登录态并跳登录页（幂等，不吞错误）
        handleUnauthorized(resp.status)
        const err = new ApiError(resp.status, detail)
        // 仅对可重试的状态码（502/503/504）和网络错误重试，4xx 不重试
        if (attempt < _retries && [502, 503, 504].includes(resp.status)) {
          lastError = err
          await new Promise(r => setTimeout(r, 500 * (attempt + 1)))
          continue
        }
        throw err
      }

      return resp.json() as Promise<T>
    } catch (e: any) {
      if (e instanceof ApiError) throw e
      // 网络错误：TypeError "Failed to fetch" 等
      if (attempt < _retries) {
        lastError = e
        await new Promise(r => setTimeout(r, 500 * (attempt + 1)))
        continue
      }
      throw e
    }
  }
  throw lastError
}

export const api = {
  get<T>(path: string): Promise<T> {
    return request<T>(path, { method: 'GET' })
  },

  post<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    })
  },

  put<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    })
  },

  delete<T>(path: string): Promise<T> {
    return request<T>(path, { method: 'DELETE' })
  },

  /** 流式 POST — 返回 Response 对象用于 SSE 读取；signal 用于中断（AbortController） */
  async postStream(path: string, body: unknown, signal?: AbortSignal): Promise<Response> {
    const token = getToken()
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

    const resp = await fetch(`${API_BASE}/api${path}`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      ...(signal ? { signal } : {}),
    })
    if (!resp.ok) {
      // BugFix：原先一律抛 "流式请求失败"，把 401（登录过期）等真实状态码与
      // 后端错误详情全部吞掉，用户只看到无意义的提示。这里与 request() 对齐，
      // 保留真实 status 与 detail，让 friendlyError 能映射出可操作的提示。
      let detail = `流式请求失败 (${resp.status})`
      try {
        const errBody = await resp.json()
        detail = errBody?.detail || errBody?.error?.message || detail
      } catch { /* 非 JSON 错误体（如代理 502 HTML），保留默认文案 */ }
      handleUnauthorized(resp.status)
      throw new ApiError(resp.status, detail)
    }
    return resp
  },

  /**
   * multipart/form-data 上传。
   * 注意：不设置 Content-Type，由浏览器自动补全 boundary，
   * 否则后端无法正确解析分块。
   */
  async upload<T>(path: string, formData: FormData): Promise<T> {
    const token = getToken()
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`
    return requestForm<T>(path, formData, headers)
  },

  /** 返回二进制 Blob（视频 / 音频 / 文件下载） */
  async postBlob(path: string, body: unknown): Promise<{ blob: Blob; ok: boolean; status: number }> {
    const token = getToken()
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

  const resp = await fetch(`${API_BASE}/api${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
  // 401 → 统一自动登出；契约不变：仍然不抛异常，照旧返回 { blob, ok, status }
  handleUnauthorized(resp.status)
  return { blob: await resp.blob(), ok: resp.ok, status: resp.status }
},
}

/** FormData 请求（不经过 JSON 序列化，且不设置 Content-Type） */
async function requestForm<T>(
  path: string,
  formData: FormData,
  authHeaders: Record<string, string>,
): Promise<T> {
  const resp = await fetch(`${API_BASE}/api${path}`, {
    method: 'POST',
    headers: authHeaders,
    body: formData,
  })
  let data: any
  try {
    data = await resp.json()
  } catch {
    data = null
  }
  if (!resp.ok) {
    // 401 → 统一自动登出（与 request() 语义一致）；随后照旧抛 ApiError
    handleUnauthorized(resp.status)
    throw new ApiError(resp.status, data?.detail || `上传失败 (${resp.status})`)
  }
  return data as T
}

/** TTS 语音合成 — 返回音频 Blob
 *
 * 注意：本函数**未**接入 handleUnauthorized —— 非 2xx 时直接 return null，
 * 错误被吞（既有契约，调用方依赖「返回 null → 降级到浏览器 SpeechSynthesis」）。
 * 因此登录过期时走这条链路不会触发自动登出，属于已知且本次刻意保留的行为，
 * 详见本节顶部「401 统一处理」的覆盖范围说明。
 */
export async function ttsSynthesize(
  text: string,
  language = 'zh',
  engine = 'auto',
): Promise<Blob | null> {
  const token = getToken()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const resp = await fetch(`${API_BASE}/api/tts/synthesize`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ text, language, engine }),
  })
  if (!resp.ok) return null
  return resp.blob()
}
