import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/utils/api'

// ── 类型 ──
type AuthState = { token: string; user: { id: string; user_id: string; username: string; role: string; display_name?: string } } | null

/** 登录/注册统一返回类型（LoginView 据此判断是否跳转诊断测试） */
type AuthResult = { id: string; user_id: string; username: string; role: string; display_name?: string; diagnostic_required?: boolean }

function normalizeUser(raw: Record<string, any>) {
  return {
    id: raw.id || raw.user_id || '',
    user_id: raw.user_id || raw.id || '',
    username: raw.username || '',
    role: raw.role || 'student',
    display_name: raw.display_name,
  }
}

function loadAuth(): AuthState {
  try {
    const t = localStorage.getItem('mars408_token')
    const u = localStorage.getItem('mars408_user')
    if (t && u) return { token: t, user: normalizeUser(JSON.parse(u)) }
  } catch { /* */ }
  return null
}

function saveAuth(auth: AuthState) {
  if (auth) {
    try {
      localStorage.setItem('mars408_token', auth.token)
      localStorage.setItem('mars408_user', JSON.stringify(auth.user))
    } catch { /* */ }
  } else {
    try {
      localStorage.removeItem('mars408_token')
      localStorage.removeItem('mars408_user')
    } catch { /* */ }
  }
}

export const useAuthStore = defineStore('auth', () => {
  const auth = ref<AuthState>(loadAuth())
  const currentUser = computed(() => auth.value?.user ?? null)
  const isAdmin = computed(() => auth.value?.user?.role === 'admin')
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

  return { auth, currentUser, isAdmin, token, login, register, logout }
})