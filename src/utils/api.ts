/* ============================================
 * 统一 API 客户端 — 所有请求通过此模块
 * 集中管理：Base URL、Token、错误处理
 * ============================================ */

const API_BASE = ''

function getToken(): string | null {
  try {
    return localStorage.getItem('mars408_token')
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

  /** 流式 POST — 返回 Response 对象用于 SSE 读取 */
  async postStream(path: string, body: unknown): Promise<Response> {
    const token = getToken()
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

    const resp = await fetch(`${API_BASE}/api${path}`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    })
    if (!resp.ok) {
      throw new ApiError(resp.status, '流式请求失败')
    }
    return resp
  },
}

/** TTS 语音合成 — 返回音频 Blob */
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
