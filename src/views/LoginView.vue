<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'

const router = useRouter()
const authStore = useAuthStore()

const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const displayName = ref('')
const error = ref('')
const loading = ref(false)
const showPassword = ref(false)
const isRegister = computed(() => mode.value === 'register')

async function submit() {
  error.value = ''
  if (!username.value.trim() || !password.value) { error.value = '请输入用户名和密码'; return }
  if (isRegister.value && password.value.length < 8) { error.value = '密码长度至少 8 位'; return }
  loading.value = true
  try {
    const user = isRegister.value
      ? await authStore.register(username.value.trim(), password.value, displayName.value.trim())
      : await authStore.login(username.value.trim(), password.value)
    router.push(user.diagnostic_required ? '/diagnostic/start' : (user.role === 'admin' ? '/admin' : '/'))
  } catch (e: any) {
    error.value = e?.message || (isRegister.value ? '注册失败' : '登录失败')
  } finally { loading.value = false }
}
function toggleMode() { mode.value = isRegister.value ? 'login' : 'register'; error.value = '' }
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <!-- 顶部品牌 -->
      <div class="brand">
        <div class="brand-badge">第十五届中国软件杯 A3 赛道</div>
        <div class="brand-logo"><span class="logo-m">MARS</span><span class="logo-a">-408</span></div>
        <div class="brand-title">多智能体个性化学习系统</div>
        <div class="brand-desc">基于改进 GOMARL 与 FrugalRAG 的计算机 408 考研学习平台</div>
      </div>

      <!-- 登录/注册切换 -->
      <div class="mode-row">
        <button class="mode-btn" :class="{ on: !isRegister }" @click="mode = 'login'">🔑 登录</button>
        <button class="mode-btn" :class="{ on: isRegister }" @click="mode = 'register'">✨ 注册</button>
      </div>

      <!-- 表单 -->
      <form class="form" @submit.prevent="submit">
        <div class="fld">
          <label class="fld-lbl">用户名</label>
          <div class="fld-wrap">
            <span class="fld-ico">👤</span>
            <input v-model="username" class="fld-inp" :placeholder="isRegister ? '设置用户名' : '请输入用户名'" autocomplete="username" />
          </div>
        </div>
        <div v-if="isRegister" class="fld">
          <label class="fld-lbl">昵称</label>
          <div class="fld-wrap">
            <span class="fld-ico">📝</span>
            <input v-model="displayName" class="fld-inp" placeholder="展示名称" autocomplete="nickname" />
          </div>
        </div>
        <div class="fld">
          <label class="fld-lbl">密码</label>
          <div class="fld-wrap">
            <span class="fld-ico">🔒</span>
            <input v-model="password" :type="showPassword ? 'text' : 'password'" class="fld-inp" :placeholder="isRegister ? '至少 8 位' : '请输入密码'" autocomplete="current-password" />
            <button type="button" class="pw-eye" @click="showPassword = !showPassword">{{ showPassword ? '🙈' : '👁️' }}</button>
          </div>
        </div>
        <div v-if="error" class="err">⚠️ {{ error }}</div>
        <button class="sbtn" :disabled="loading" type="submit">
          <span v-if="loading" class="spin"></span>
          <span v-else>{{ isRegister ? '✨ 注册并进入' : '🔑 登录' }}</span>
        </button>
      </form>

      <!-- 底部 -->
      <div class="bot">
        <span>{{ isRegister ? '已有账号？' : '还没有账号？' }}</span>
        <button class="bot-link" @click="toggleMode">{{ isRegister ? '去登录' : '立即注册' }}</button>
      </div>
      <div class="demo">💡 演示账号：<code>demo</code> / <code>demo123456</code></div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, #0a0a1a 0%, #1a1a3e 50%, #0d0d2b 100%);
  display: flex; align-items: center; justify-content: center;
  padding: 16px;
  z-index: 10;
}
.login-card {
  width: 100%; max-width: 420px;
  padding: 40px 36px;
  background: rgba(16,16,36,0.92);
  border: 1px solid rgba(124,106,242,0.15);
  border-radius: 20px;
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  box-shadow: 0 8px 40px rgba(0,0,0,0.4);
}

/* 品牌 */
.brand { text-align: center; margin-bottom: 24px; }
.brand-badge { display: inline-block; padding: 3px 12px; border-radius: 20px; background: rgba(124,106,242,0.15); color: #a78bfa; font-size: 11px; border: 1px solid rgba(124,106,242,0.2); margin-bottom: 14px; }
.brand-logo { margin-bottom: 8px; }
.logo-m { font-size: 36px; font-weight: 800; color: #fff; letter-spacing: -1px; }
.logo-a { font-size: 36px; font-weight: 800; background: linear-gradient(135deg,#7c6af2,#a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.brand-title { font-size: 18px; font-weight: 700; color: rgba(255,255,255,0.9); margin-bottom: 4px; }
.brand-desc { font-size: 13px; color: rgba(255,255,255,0.4); line-height: 1.5; }

/* 模式切换 */
.mode-row { display: flex; gap: 4px; padding: 3px; background: rgba(255,255,255,0.04); border-radius: 10px; margin-bottom: 20px; }
.mode-btn { flex: 1; padding: 9px; border: none; border-radius: 8px; background: transparent; color: rgba(255,255,255,0.4); font-size: 14px; cursor: pointer; transition: all 0.2s; }
.mode-btn:hover { color: rgba(255,255,255,0.7); }
.mode-btn.on { background: rgba(124,106,242,0.2); color: #a78bfa; }

/* 表单 */
.form { display: flex; flex-direction: column; gap: 14px; }
.fld-lbl { display: block; font-size: 13px; color: rgba(255,255,255,0.5); margin-bottom: 5px; }
.fld-wrap { display: flex; align-items: center; gap: 10px; padding: 0 14px; border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; background: rgba(255,255,255,0.02); transition: all 0.2s; }
.fld-wrap:focus-within { border-color: rgba(124,106,242,0.4); }
.fld-ico { font-size: 15px; }
.fld-inp { flex: 1; padding: 12px 0; border: none; background: transparent; color: #fff; font-size: 15px; outline: none; }
.fld-inp::placeholder { color: rgba(255,255,255,0.2); }
.pw-eye { background: none; border: none; color: rgba(255,255,255,0.3); cursor: pointer; font-size: 15px; padding: 4px; }
.err { padding: 10px 14px; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.2); border-radius: 10px; color: #fca5a5; font-size: 13px; }
.sbtn { width: 100%; padding: 13px; border: none; border-radius: 10px; background: linear-gradient(135deg,#7c6af2,#6d5ae6); color: #fff; font-size: 16px; font-weight: 600; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; justify-content: center; gap: 8px; }
.sbtn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(124,106,242,0.3); }
.sbtn:disabled { opacity: 0.5; cursor: not-allowed; }
.spin { width: 16px; height: 16px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff; animation: spin 0.6s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 底部 */
.bot { text-align: center; font-size: 14px; color: rgba(255,255,255,0.35); margin-top: 18px; }
.bot-link { background: none; border: none; color: #a78bfa; font-size: 14px; cursor: pointer; margin-left: 4px; padding: 0; }
.bot-link:hover { color: #c4b5fd; text-decoration: underline; }
.demo { margin-top: 12px; padding: 10px; background: rgba(255,255,255,0.02); border-radius: 10px; text-align: center; font-size: 13px; color: rgba(255,255,255,0.35); }
.demo code { padding: 1px 6px; background: rgba(124,106,242,0.1); border-radius: 4px; font-size: 12px; color: #a78bfa; }
</style>