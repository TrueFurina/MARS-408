import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api, resetUnauthorizedLatch } from '@/utils/api'

// ── 类型 ──
type AuthState = { token: string; user: { id: string; user_id: string; username: string; role: string; display_name?: string; readonly?: boolean } } | null

/** 登录/注册统一返回类型（LoginView 据此判断是否跳转诊断测试） */
type AuthResult = { id: string; user_id: string; username: string; role: string; display_name?: string; readonly?: boolean; diagnostic_required?: boolean }

function normalizeUser(raw: Record<string, any>) {
  return {
    id: raw.id || raw.user_id || '',
    user_id: raw.user_id || raw.id || '',
    username: raw.username || '',
    role: raw.role || 'student',
    display_name: raw.display_name,
    // 只读演示账号标志（后端 shared/auth.is_readonly_user 判定，登录与 /auth/me 均下发）
    readonly: raw.readonly === true,
  }
}

function loadAuth(): AuthState {
  try {
    const t = localStorage.getItem('mangdehenzhi_token')
    const u = localStorage.getItem('mangdehenzhi_user')
    if (t && u) return { token: t, user: normalizeUser(JSON.parse(u)) }
  } catch { /* */ }
  return null
}

function saveAuth(auth: AuthState) {
  // 写入新 token 前必须重置 401 自动登出 latch：后端 create_token 的 iat/exp
  // 是秒级粒度，同一秒内重新登录会拿到与上次**完全相同**的 token，若不重置，
  // 该 token 再遇 401 会被 loggedOutToken 早退拦住，永久不再跳转登录页。
  // （这里是全仓库唯一写入 mangdehenzhi_token 的地方，见 router/index.ts 只读）
  resetUnauthorizedLatch()
  if (auth) {
    try {
      localStorage.setItem('mangdehenzhi_token', auth.token)
      localStorage.setItem('mangdehenzhi_user', JSON.stringify(auth.user))
    } catch { /* */ }
  } else {
    try {
      localStorage.removeItem('mangdehenzhi_token')
      localStorage.removeItem('mangdehenzhi_user')
    } catch { /* */ }
  }
}

export const useAuthStore = defineStore('auth', () => {
  const auth = ref<AuthState>(loadAuth())
  const currentUser = computed(() => auth.value?.user ?? null)
  const isAdmin = computed(() => auth.value?.user?.role === 'admin')
  const isReadonly = computed(() => auth.value?.user?.readonly === true)
  const token = computed(() => auth.value?.token ?? null)

  async function login(username: string, password: string): Promise<AuthResult> {
    const data = await api.post<{ token: string; user: any; diagnostic_required?: boolean }>('/auth/login', { username, password })
    const user = normalizeUser(data.user)
    auth.value = { token: data.token, user }
    saveAuth(auth.value)
    // 返回用户信息 + 后端可能下发的诊断测试标志（LoginView 据此跳转 /diagnostic/start）
    return { ...user, diagnostic_required: data.diagnostic_required }
  }

  async function register(username: string, password: string, displayName: string): Promise<AuthResult> {
    const data = await api.post<{ token: string; user: any }>('/auth/register', {
      username, password, display_name: displayName,
    })
    const user = normalizeUser(data.user)
    auth.value = { token: data.token, user }
    saveAuth(auth.value)
    return { ...user, diagnostic_required: undefined }
  }

  function logout() {
    auth.value = null
    saveAuth(null)
  }

  /**
   * 用 /auth/me 刷新本地用户信息（尤其是 readonly 标志）。
   * 老用户 localStorage 里的 user 是加这个标志之前写下的，不刷新就一直是 false；
   * 刷新失败（离线/登录失效）静默保留原值，不打断页面。
   */
  async function refreshProfile(): Promise<void> {
    if (!auth.value?.token) return
    try {
      const me = await api.get<Record<string, any>>('/auth/me')
      // 以 /auth/me 为准（账号从只读名单里移除时这里能跟着摘掉标志）；老部署不带该字段时才沿用本地值。
      const readonly = typeof me.readonly === 'boolean' ? me.readonly : auth.value.user.readonly === true
      const user = { ...normalizeUser(me), readonly }
      auth.value = { token: auth.value.token, user }
      saveAuth(auth.value)
    } catch { /* 保留既有登录态，401 已由 api 层统一处理 */ }
  }

  return { auth, currentUser, isAdmin, isReadonly, token, login, register, logout, refreshProfile }
})