/**
 * 云身份（Auth）接入
 * ============================================================================
 * 提供：会话读取 / 邮箱验证码登录注册 / 邮箱密码登录 / 微信扫码登录 / 退出 / 状态订阅。
 * 会话由 SDK 自行持久化（只存 access token 与不透明刷新句柄 wbrt_…），
 * 应用代码**不要**把 token 写进 URL 或日志。
 *
 * 约定：受保护的数据（Database / Storage）必须先过会话闸门，未登录就渲染登录 UI，
 * 绝不使用匿名登录 / mock 会话 / 纯 localStorage 用户来「让数据看起来能用」。
 */
import type { CloudSession, CloudUser } from '@tencent-ai/workbuddy-cloud-sdk'
import { cloud } from './client'

export type { CloudSession, CloudUser }

/** 统一错误类型：四个模块抛出的错误都归一成它，业务层按 kind 分支即可。 */
export class CloudCallError extends Error {
  readonly kind: string
  readonly code?: string
  constructor(message: string, kind = 'unknown', code?: string) {
    super(message)
    this.name = 'CloudCallError'
    this.kind = kind
    this.code = code
  }
}

/**
 * 把形状不一的原始错误归一成 CloudCallError：
 *   · Auth 的 CloudError 自带 kind；
 *   · Database 的 PostgrestError / Storage 的 CloudStorageError 只有 code / status，
 *     这里按 PostgreSQL 错误码与 HTTP 状态补出 kind，避免业务层去认各家字段名。
 */
export function toCallError(err: unknown, fallback: string): CloudCallError {
  const e = (err || {}) as { message?: string; code?: string; kind?: string; status?: number }
  let kind = e.kind
  if (!kind) {
    if (e.status === 401) kind = 'unauthenticated'
    else if (e.code === '42501') kind = 'permission-denied'
    else if (e.code === '42P01' || e.code === 'PGRST205') kind = 'not-found'
    else kind = 'unknown'
  }
  return new CloudCallError(e.message || fallback, kind, e.code)
}

interface Envelope<T> {
  data: T | null
  error: unknown
}

export function unwrap<T>(res: Envelope<T>, fallback = '云服务调用失败'): T {
  if (res.error) throw toCallError(res.error, fallback)
  return res.data as T
}

/** 当前云端会话（未登录返回 null；其它错误抛出、由 UI 提示重试）。 */
export async function getSession(): Promise<CloudSession | null> {
  const res = await cloud.auth.getSession()
  if (res.error) {
    // 未登录是正常状态，不当作异常抛给页面
    const e = toCallError(res.error, '读取会话失败')
    if (e.kind === 'unauthenticated') return null
    throw e
  }
  return res.data ?? null
}

/** 服务端校验过的当前用户（比本地会话更权威）。 */
export async function fetchUser(): Promise<CloudUser | null> {
  const res = await cloud.auth.getUser()
  if (res.error) {
    const e = toCallError(res.error, '读取用户失败')
    if (e.kind === 'unauthenticated') return null
    throw e
  }
  return res.data ?? null
}

/** 第一步：发送邮箱验证码。返回值必须留在调用方状态里，供第二步校验时使用。 */
export async function sendEmailCode(email: string): Promise<{ verificationId: string; isExistingUser: boolean }> {
  const res = await cloud.auth.sendOtp({ email })
  if (res.error) throw toCallError(res.error, '验证码发送失败')
  const challenge = res.data
  if (!challenge) throw new CloudCallError('验证码发送失败：未返回校验信息')
  return { verificationId: challenge.verificationId, isExistingUser: challenge.isExistingUser }
}

/**
 * 第二步：提交邮箱验证码完成登录/注册。
 * 必须回传第一步的 verificationId 与 isExistingUser（SDK 契约要求）；
 * 新邮箱注册必须带 password，已存在用户会忽略它。
 * ⚠️ 这里**绝不**再调用 sendOtp —— 重输错误验证码时也要复用第一次的 challenge。
 */
export async function verifyEmailCode(params: {
  email: string
  verificationId: string
  isExistingUser: boolean
  token: string
  password?: string
}): Promise<CloudSession> {
  const res = await cloud.auth.verifyOtp({
    email: params.email,
    verificationId: params.verificationId,
    isExistingUser: params.isExistingUser,
    token: params.token,
    password: params.isExistingUser ? undefined : params.password,
  })
  if (res.error) throw toCallError(res.error, '验证码校验失败')
  const session = res.data
  if (!session) throw new CloudCallError('验证码校验失败：未建立会话')
  return session
}

/** 邮箱 + 密码登录。 */
export async function signInWithPassword(email: string, password: string): Promise<CloudSession> {
  const res = await cloud.auth.signInWithPassword({ email, password })
  if (res.error) throw toCallError(res.error, '账号或密码不正确')
  const session = res.data
  if (!session) throw new CloudCallError('登录失败：未建立会话')
  return session
}

/**
 * 微信网页登录（一键 / 扫码是同一个流程）。
 * 注意：`signInWithOAuth` **不跳转**，只返回要去的 URL，由调用方 location.assign。
 * 回调在应用启动阶段由 main.ts 统一处理。
 */
export async function startWechatLogin(): Promise<string> {
  const res = await cloud.auth.signInWithOAuth({
    provider: 'wechat',
    // 必须是站点根：发布产物是静态文件、没有 history 回退，子路径会 404 丢 code
    redirectTo: window.location.origin + import.meta.env.BASE_URL,
  })
  if (res.error) throw toCallError(res.error, '微信登录发起失败')
  const redirect = res.data
  if (!redirect?.url) throw new CloudCallError('微信登录发起失败：未返回跳转地址')
  return redirect.url
}

/**
 * 处理微信回调。返回 null 表示 URL 里没有 code（普通访问），**不是错误**。
 * 成功换取会话后必须清掉地址栏的 code/state —— state 一次性，
 * 留着会让用户刷新时重放已消费的 code，看起来像「登录后又报错」。
 */
export async function completeWechatRedirect(): Promise<CloudSession | null> {
  const res = await cloud.auth.handleWechatWebCallback()
  if (res.error) throw toCallError(res.error, '微信登录回调处理失败')
  const session = res.data ?? null
  if (session) {
    // 清掉地址栏的 code/state。两种模式下它们的位置不同：
    //   history 模式在 search（?code=…），hash 模式在 hash 的 query 段（#/…?code=…）。
    // 这里把 hash 的 query 段一并剥掉，避免刷新时重放已消费的 code。
    const hash = window.location.hash
    const cleanedHash = hash.includes('?') ? hash.slice(0, hash.indexOf('?')) : hash
    window.history.replaceState(null, '', window.location.pathname + cleanedHash)
  }
  return session
}

export async function signOut(): Promise<void> {
  const res = await cloud.auth.signOut()
  if (res.error) {
    const e = toCallError(res.error, '退出失败')
    if (e.kind !== 'unauthenticated') throw e
  }
}

/** 订阅登录态变化；返回取消订阅函数。 */
export function onAuthChange(cb: (session: CloudSession | null) => void): () => void {
  return cloud.auth.onAuthStateChange((_event, session) => cb(session))
}
