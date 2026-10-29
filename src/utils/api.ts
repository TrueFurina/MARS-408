/* ============================================
 * 统一 API 客户端 — 所有请求通过此模块
 * 集中管理：Base URL、Token、错误处理
 * ============================================ */

const API_BASE = ''

/** storage key 与 authStore.loadAuth/saveAuth 使用的保持完全一致（单一真值源） */
const TOKEN_KEY = 'mangdehenzhi_token'
const USER_KEY = 'mangdehenzhi_user'

function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

/**
 * 当前是否已登录（本地存在 token）。
 * 供「登录后才预取」等场景判断 —— 避免未登录时打鉴权接口产生 401 噪音。
 */
export function hasAuthToken(): boolean {
  return !!getToken()
}

/**
 * 获取带 Auth Token 的请求头（供裸 fetch 调用使用）
 * ⚠️ 用 X-App-Token 而非 Authorization：发布沙箱（CloudStudio）网关会把
 * Authorization 替换成平台身份 token（2026-10-15 实测），自定义头才原样透传。
 * 两个都设：本地/dev 无网关时 Authorization 正常，沙箱下后端优先读 X-App-Token。
 */
export function getAuthHeaders(): Record<string, string> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) {
    headers['X-App-Token'] = token
    headers['Authorization'] = `Bearer ${token}`
  }
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
    // 兼容两种路由模式：history 模式看 pathname（/login），
    // hash 模式（静态托管、无 SPA 回退）路由在 hash 里（#/login），pathname 永远是 base 路径
    const p = window.location.pathname.replace(/\/$/, '')
    const h = window.location.hash.replace(/^#/, '').split('?')[0]
    return p === '/login' || h === '/login'
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

/**
 * 分级超时（ms）—— 不同链路的时长语义不同，共用一个阈值必然误杀其中一类。
 *
 * 为什么必须有：`fetch` 在**服务端已建立连接但不返回**（后端卡在慢查询、
 * 网关半开连接、容器被挂起）时既不 resolve 也不 reject。没有超时的表现是
 * 页面永久停在 loading、重试逻辑（只在下游抛错时触发）永远不生效。
 *
 * 取值依据（宁可偏松，因为超时误杀比慢更糟）：
 *   · JSON 接口 30s：本仓库最慢的正常接口是带 LLM 生成的报告类调用，实测 P99
 *     在 10s 量级，留 3 倍余量；
 *   · SSE 连接 30s：**只约束「拿到响应头」这一段**，不是整个流。fetch 一 resolve
 *     计时器即清除，后续逐 token 推送不受影响 —— 长对话不会被 30s 掐断；
 *   · 上传 120s：多模态图片/文档，含服务端解析时间；
 *   · 二进制下载 120s：报告导出与音视频，体积不可控。
 */
const TIMEOUT_JSON_MS = 30_000
const TIMEOUT_STREAM_CONNECT_MS = 30_000
const TIMEOUT_UPLOAD_MS = 120_000
const TIMEOUT_BLOB_MS = 120_000

/**
 * 超时专用错误类型。
 * 单独成类（而不是直接抛 ApiError）是为了让 `request()` 能区分「超时（可重试）」
 * 与「4xx/5xx（按状态码决定是否重试）」，避免超时被误判成不可重试的 ApiError。
 */
class RequestTimeoutError extends Error {
  constructor(public timeoutMs: number) {
    super(`请求超时：${timeoutMs / 1000} 秒内无响应，请稍后重试`)
    this.name = 'RequestTimeoutError'
  }
}

/**
 * 带超时的 fetch。返回 Response 即视为「已拿到响应头」，计时器随之清除。
 *
 * 调用方自带 signal（组件卸载取消、用户主动中断）时**不接管超时** ——
 * 两个 AbortController 抢同一个请求会让「谁中止的」变得不可判定。
 */
async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  if (init.signal || typeof AbortController === 'undefined' || timeoutMs <= 0) {
    return fetch(url, init)
  }
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  try {
    return await fetch(url, { ...init, signal: controller.signal })
  } catch (e) {
    // 只有「自己掐的」才转成超时错误；外部原因导致的 AbortError 原样抛出
    if (timedOut) throw new RequestTimeoutError(timeoutMs)
    throw e
  } finally {
    clearTimeout(timer)
  }
}

/**
 * 单次请求的可选项。
 *
 * `timeoutMs` 的存在理由：默认 30s 是按「普通接口」定的，但仓库里确实有
 * 明确更慢的调用（画像构建这类带 LLM 深度推理的接口，原作者按 60s 设计）。
 * 一刀切会让这类接口从「慢但能成」变成「必然超时」——那是比不加超时更糟的回归。
 * 所以给调用方一个显式放宽的出口：默认收紧，例外必须写明理由。
 */
export interface RequestOptions {
  /** 覆盖默认超时（ms）；传 0 表示不设超时，完全交给调用方 signal 控制 */
  timeoutMs?: number
  /** 调用方中断信号（组件卸载 / 用户主动取消） */
  signal?: AbortSignal
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  _retries = 2,
  timeoutMs: number = TIMEOUT_JSON_MS,
): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  if (token) {
    headers['X-App-Token'] = token
    headers['Authorization'] = `Bearer ${token}`
  }

  let lastError: unknown
  for (let attempt = 0; attempt <= _retries; attempt++) {
    try {
      // 每次尝试独立计时：超时归入「可重试的网络类失败」，与 502/503/504 同等对待。
      const resp = await fetchWithTimeout(
        `${API_BASE}/api${path}`,
        { ...options, headers },
        timeoutMs,
      )

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
    } catch (e) {
      if (e instanceof ApiError) throw e
      // 超时（RequestTimeoutError）与网络错误同属可重试类。对调用方仍统一抛 ApiError，
      // 保持「api.* 只会抛 ApiError」的既有契约，friendlyError 的映射链路不受影响。
      const err = e instanceof RequestTimeoutError ? new ApiError(0, e.message) : e
      // 网络错误：TypeError "Failed to fetch" 等
      if (attempt < _retries) {
        lastError = err
        await new Promise(r => setTimeout(r, 500 * (attempt + 1)))
        continue
      }
      throw err
    }
  }
  throw lastError
}

/**
 * 四个动词的公共派发：拼 RequestInit、透传 signal、套用超时。
 *
 * 抽出来的原因不是「少写几行」，而是四个方法各自展开 10 行后会被 pre-push 的
 * 克隆检测判为新增重复块（实测命中）。这类样板一旦复制，后续给 request()
 * 加参数就得改四处、漏一处就是行为不一致。
 *
 * body 判空沿用既有语义（`body ? JSON.stringify(body) : undefined`）：
 * 改成 `!== undefined` 会让 `0` / `''` / `false` 从「不发 body」变成「发字面量」，
 * 那是没经过验证的行为变更。
 */
function send<T>(
  path: string,
  method: string,
  body: unknown,
  opts?: RequestOptions,
): Promise<T> {
  const init: RequestInit = { method }
  if (body) init.body = JSON.stringify(body)
  if (opts?.signal) init.signal = opts.signal
  return request<T>(path, init, 2, opts?.timeoutMs ?? TIMEOUT_JSON_MS)
}

export const api = {
  get<T>(path: string, opts?: RequestOptions): Promise<T> {
    return send<T>(path, 'GET', undefined, opts)
  },

  post<T>(path: string, body?: unknown, opts?: RequestOptions): Promise<T> {
    return send<T>(path, 'POST', body, opts)
  },

  put<T>(path: string, body?: unknown, opts?: RequestOptions): Promise<T> {
    return send<T>(path, 'PUT', body, opts)
  },

  delete<T>(path: string, opts?: RequestOptions): Promise<T> {
    return send<T>(path, 'DELETE', undefined, opts)
  },

  /** 流式 POST — 返回 Response 对象用于 SSE 读取；signal 用于中断（AbortController） */
  async postStream(path: string, body: unknown, signal?: AbortSignal): Promise<Response> {
    const token = getToken()
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) {
      headers['X-App-Token'] = token
      headers['Authorization'] = `Bearer ${token}`
    }

    // 超时只约束「拿到响应头」这一段：fetch 一 resolve 计时器即清除，
    // 后续逐 token 的流式推送不受影响（长对话不会被 30s 掐断）。
    // 调用方传了 signal（用户主动中断）时不接管超时。
    let resp: Response
    try {
      resp = await fetchWithTimeout(
        `${API_BASE}/api${path}`,
        {
          method: 'POST',
          headers,
          body: JSON.stringify(body),
          ...(signal ? { signal } : {}),
        },
        TIMEOUT_STREAM_CONNECT_MS,
      )
    } catch (e) {
      // 统一成 ApiError（超时 status 记 0），与其它 api.* 的异常契约一致；
      // 用户主动中断（AbortError）原样抛出，调用方据此区分「取消」与「失败」。
      if (e instanceof RequestTimeoutError) throw new ApiError(0, e.message)
      throw e
    }
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
    // 双头必须走 getAuthHeaders()：发布网关只透传自定义头 X-App-Token
    // （Authorization 会被换成平台身份 token），漏一个头本地全绿、线上 401。
    // Content-Type 不设置，由浏览器自动补全 boundary（见下方注释）。
    return requestForm<T>(path, formData, getAuthHeaders())
  },

  /** 返回二进制 Blob（视频 / 音频 / 文件下载） */
  async postBlob(path: string, body: unknown): Promise<{ blob: Blob; ok: boolean; status: number }> {
    const token = getToken()
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) {
      headers['X-App-Token'] = token
      headers['Authorization'] = `Bearer ${token}`
    }

    // 契约不变：本方法不抛异常，超时按「失败」返回 ok:false（status 0），
    // 由调用方走既有的降级分支，不新增异常路径。
    let resp: Response
    try {
      resp = await fetchWithTimeout(
        `${API_BASE}/api${path}`,
        { method: 'POST', headers, body: JSON.stringify(body) },
        TIMEOUT_BLOB_MS,
      )
    } catch {
      return { blob: new Blob(), ok: false, status: 0 }
    }
    // 401 → 统一自动登出；契约不变：仍然不抛异常，照旧返回 { blob, ok, status }
    handleUnauthorized(resp.status)
    return { blob: await resp.blob(), ok: resp.ok, status: resp.status }
  },

  /** GET 二进制下载（如导出报告 HTML）；接 401 统一登出，契约同 postBlob：不抛异常、返回 ok/status */
  async getBlob(path: string): Promise<{ blob: Blob; ok: boolean; status: number }> {
    // 双头必须走 getAuthHeaders()：CloudStudio 网关只透传自定义头 X-App-Token，
    // 只带 Authorization 的请求在线上稳定 401（2026-10-21 线上巡检实测：
    // 教师点「导出一页纸报告」→ 401 → handleUnauthorized 把用户踢回登录页）。
    // 契约同 postBlob：超时/网络异常不抛出，按 ok:false + status 0 返回
    let resp: Response
    try {
      resp = await fetchWithTimeout(
        `${API_BASE}/api${path}`,
        { method: 'GET', headers: getAuthHeaders() },
        TIMEOUT_BLOB_MS,
      )
    } catch {
      return { blob: new Blob(), ok: false, status: 0 }
    }
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
  let resp: Response
  try {
    resp = await fetchWithTimeout(
      `${API_BASE}/api${path}`,
      {
        method: 'POST',
        headers: authHeaders,
        body: formData,
      },
      TIMEOUT_UPLOAD_MS,
    )
  } catch (e) {
    // 统一成 ApiError，保持「api.* 只抛 ApiError」的契约（超时 status 记 0）
    if (e instanceof RequestTimeoutError) throw new ApiError(0, e.message)
    throw e
  }
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
  // 双头（X-App-Token + Authorization）缺一不可：发布网关只透传自定义头，
  // 只带 Authorization 在线上 401 —— 而本函数吞错降级、不登出，错了也没人发现。
  // getAuthHeaders() 在无 token 时返回 {}，未登录的匿名 TTS 调用不受影响。
  const headers: Record<string, string> = { ...getAuthHeaders(), 'Content-Type': 'application/json' }

  // 既有契约是「失败返回 null → 调用方降级到浏览器 SpeechSynthesis」，
  // 因此超时/网络异常一律并入 null，不新增异常路径（否则降级逻辑会失效）。
  let resp: Response
  try {
    resp = await fetchWithTimeout(
      `${API_BASE}/api/tts/synthesize`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify({ text, language, engine }),
      },
      TIMEOUT_BLOB_MS,
    )
  } catch {
    return null
  }
  if (!resp.ok) return null
  return resp.blob()
}
