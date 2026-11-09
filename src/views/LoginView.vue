<script setup lang="ts">
import { errMessage } from '@/utils/errorMessage'
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'
import { resolveLandingRoute } from '@/router/landing'

const router = useRouter()
const authStore = useAuthStore()

// 本地开发环境（demo 账号仅在此可用；production 不播种）
const isLocalHost = ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname)

const username = ref('')
const password = ref('')
const displayName = ref('')
const error = ref('')
const loading = ref(false)
const showPassword = ref(false)

async function submit() {
  error.value = ''
  if (!username.value.trim() || !password.value) { error.value = '请输入用户名和密码'; return }
  loading.value = true
  try {
    const user = await authStore.login(username.value.trim(), password.value)
    // 登录落点统一由 resolveLandingRoute 决定（纯函数，landing.spec.ts 守护）：
    // 学生落平台首页 /，教师 /teacher，管理员 /admin；入学测评改为首页上的可选项。
    router.push(resolveLandingRoute(user))
  } catch (e) {
    const base = errMessage(e, '登录失败')
    const looksLikeCredential = /密码|账号|用户名|credential/i.test(base)
    error.value =
      !isLocalHost && looksLikeCredential
        ? `${base}；账号由任课教师统一开通，如未收到初始口令请联系任课教师。`
        : base
  } finally { loading.value = false }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <!-- 顶部品牌 -->
      <div class="brand">
        <div class="brand-badge">一个平台 · 两个业务场景</div>
        <div class="brand-logo"><span class="logo-m">芒得</span><span class="logo-a">很职</span></div>
        <div class="brand-title">多智能体赋能职业素养对抗实训平台</div>
        <!-- 原副标题与标题几乎是同一句话的复述（"新一代多智能体赋能的计算机类学生
             职业素养对抗实训平台"），两句并排只是重复占位。改为说明它好在哪。 -->
        <div class="brand-desc">证据链评分 · 每个分数绑定原话 · 教师可复核归档</div>
      </div>

      <!-- 学员账号由课堂统一开通，不提供自助注册入口 -->
      <div class="login-hint">请使用学号或账号登录</div>

      <!-- 表单 -->
      <form class="form" @submit.prevent="submit">
        <div class="fld">
          <label class="fld-lbl">用户名</label>
          <div class="fld-wrap">
            <span class="fld-ico"></span>
            <input v-model="username" class="fld-inp" placeholder="请输入学号或账号" autocomplete="username" />
          </div>
        </div>
        <div class="fld">
          <label class="fld-lbl">密码</label>
          <div class="fld-wrap">
            <span class="fld-ico"></span>
            <input v-model="password" :type="showPassword ? 'text' : 'password'" class="fld-inp" placeholder="请输入密码" autocomplete="current-password" />
            <button type="button" class="pw-eye" @click="showPassword = !showPassword">{{ showPassword ? '' : '' }}</button>
          </div>
        </div>
        <div v-if="error" class="err"> {{ error }}</div>
        <button class="sbtn" :disabled="loading" type="submit">
          <span v-if="loading" class="spin"></span>
          <span v-else>登录</span>
        </button>
      </form>

      <!-- 底部：不开放自助注册，账号由课堂统一开通 -->
      <div class="bot">
        <span>没有账号？请联系任课教师开通</span>
      </div>
      <!-- 演示账号提示：仅本地开发显示 —— demo/demo123456 只在非生产模式播种，
           production（公网部署）下该账号不存在，显示会让访客照着点却登录失败（实测 422）。 -->
      <div v-if="isLocalHost" class="demo"> 演示账号：<code>demo</code> / <code>demo123456</code></div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, var(--color-canvas) 0%, var(--color-surface) 50%, var(--color-canvas) 100%);
  display: flex; align-items: center; justify-content: center;
  padding: var(--space-4);
  z-index: 10;
}
.login-card {
  width: 100%; max-width: 420px;
  padding: var(--space-9) var(--space-8);
  /* 原来是 --color-surface，比画布只亮一档，配 --shadow-4 时仍像贴在地上；
     用独立的卡片 token + 卡片阴影，登录卡才是浮起来的一张面 */
  background: var(--color-card);
  border: 1px solid rgba(var(--accent-rgb),0.15);
  border-radius: 20px;
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  box-shadow: var(--shadow-card);
}

/* 品牌 */
.brand { text-align: center; margin-bottom: var(--space-6); }
.brand-badge { display: inline-block; padding: 3px var(--space-3); border-radius: 20px; background: rgba(var(--accent-rgb),0.15); color: var(--color-accent-text); font-size: var(--text-2xs); border: 1px solid rgba(var(--accent-rgb),0.2); margin-bottom: 14px; }
.brand-logo { margin-bottom: var(--space-2); }
.logo-m { font-size: var(--text-5xl); font-weight: 800; color: var(--color-text); letter-spacing: -1px; }
.logo-a { font-size: var(--text-5xl); font-weight: 800; background: linear-gradient(135deg,var(--color-accent),var(--color-accent-text)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.brand-title { font-size: var(--text-xl); font-weight: var(--weight-bold); color: var(--color-text); margin-bottom: var(--space-1); text-wrap: balance; }
.brand-desc { font-size: var(--text-sm); color: var(--color-text-3); line-height: 1.5; text-wrap: balance; }

/* 公开展示站提示 */

/* 模式切换 */
/* 提示语原来居中，紧跟下面左对齐的表单，形成一条居中的孤行；改为与表单标签同一起点 */
.login-hint { font-size: var(--text-sm); color: var(--color-text-3); margin-bottom: var(--space-4); }
.mode-row { display: flex; gap: var(--space-1); padding: 3px; background: var(--color-surface-2); border-radius: 10px; margin-bottom: var(--space-5); }
.mode-btn { flex: 1; padding: 9px; border: none; border-radius: 8px; background: transparent; color: var(--color-text-3); font-size: var(--text-base); cursor: pointer; transition: var(--transition); }
.mode-btn:hover { color: var(--color-text-2); }
.mode-btn.on { background: rgba(var(--accent-rgb),0.2); color: var(--color-accent-text); }

/* 表单 */
.form { display: flex; flex-direction: column; gap: 14px; }
.fld-lbl { display: block; font-size: var(--text-sm); color: var(--color-text-2); margin-bottom: 5px; }
.fld-wrap { display: flex; align-items: center; gap: 10px; padding: 0 14px; border: 1px solid var(--color-border); border-radius: 10px; background: var(--color-surface-2); transition: var(--transition); }
.fld-wrap:focus-within { border-color: rgba(var(--accent-rgb),0.4); }
.fld-ico { font-size: var(--text-md); }
.fld-inp { flex: 1; padding: var(--space-3) 0; border: none; background: transparent; color: var(--color-text); font-size: var(--text-md); outline: none; }
.fld-inp::placeholder { color: var(--color-text-3); }
.pw-eye { background: none; border: none; color: var(--color-text-3); cursor: pointer; font-size: var(--text-md); padding: var(--space-1); }
.err { padding: 10px 14px; background: rgba(var(--danger-rgb),0.1); border: 1px solid rgba(var(--danger-rgb),0.2); border-radius: 10px; color: var(--color-danger); font-size: var(--text-sm); }
.sbtn { width: 100%; padding: 13px; border: none; border-radius: 10px; background: linear-gradient(135deg,var(--color-accent),var(--color-accent-solid)); color: var(--color-text-on-accent); font-size: var(--text-lg); font-weight: var(--weight-semibold); cursor: pointer; transition: var(--transition); display: flex; align-items: center; justify-content: center; gap: var(--space-2); }
.sbtn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(var(--accent-rgb),0.3); }
.sbtn:disabled { opacity: 0.5; cursor: not-allowed; }
.spin { width: 16px; height: 16px; border-radius: 50%; border: 2px solid color-mix(in srgb, var(--color-text-on-accent) 30%, transparent); border-top-color: var(--color-text-on-accent); animation: spin 0.6s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 底部与表单之间原来只隔 18px，两条信息读成一段；补一条分隔线划出「页脚」层 */
.bot { text-align: center; font-size: var(--text-sm); color: var(--color-text-3); margin-top: var(--space-5); padding-top: var(--space-4); border-top: 1px solid var(--color-border); }
.bot-link { background: none; border: none; color: var(--color-accent-text); font-size: var(--text-base); cursor: pointer; margin-left: var(--space-1); padding: 0; }
.bot-link:hover { color: var(--color-accent-text); text-decoration: underline; }
.demo { margin-top: var(--space-3); padding: 10px; background: var(--color-surface-2); border-radius: 10px; text-align: center; font-size: var(--text-sm); color: var(--color-text-3); }
.demo code { padding: 1px 6px; background: rgba(var(--accent-rgb),0.1); border-radius: 4px; font-size: var(--text-xs); color: var(--color-accent-text); }
</style>