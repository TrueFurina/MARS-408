<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useStudyStore } from '@/stores/studyStore'
import { useAuthStore } from '@/stores/authStore'
import { api, ApiError } from '@/utils/api'
import { icons } from '@/components/icons'
import type { operations } from '@/types/api.generated'

// 契约类型：取自后端新增的 response_model=ConfigResponse（py-server/api/config_routes.py）
type ConfigResp = operations['config_get_api_config_get']['responses'][200]['content']['application/json']
// /config/test-llm 返回（response_model=TestLLMResponse）
type ConfigTestLLMResp = operations['config_test_llm_api_config_test_llm_post']['responses'][200]['content']['application/json']

const router = useRouter()
const store = useStudyStore()
const authStore = useAuthStore()
// 后端 /api/config 三个端点都是 require_admin；教师能看到表单、填完点保存才 403，
// 等于把无权操作做成一次踩坑。这里按角色直接收口。
const canManageApi = computed(() => authStore.isAdmin)

const config = ref({
  llm_api_key: '',
  llm_base_url: 'https://api.deepseek.com',
  llm_model: 'deepseek-chat',
  embedding_mode: 'local',
})
const loading = ref(true)
const showKey = ref(false)
const saving = ref(false)
const testing = ref(false)
const testResult = ref('')
const statusMsg = ref('')
const hasExistingKey = ref(false)
const isDark = ref(localStorage.getItem('mangdehenzhi-theme') !== 'light')

/* 配色方案：与明暗正交的第二维。真正的 DOM 写入与持久化由 App.vue 的 applyAccent 承担，
   这里只派事件，避免两处各写一份状态导致键名/取值打架。 */
const ACCENTS = [
  { key: 'violet', name: '紫罗兰', color: '#7c6af2' },
  { key: 'teal',   name: '青碧',   color: '#3FB6A8' },
  { key: 'blue',   name: '靛蓝',   color: '#5B9CF0' },
  { key: 'amber',  name: '琥珀',   color: '#E0A84A' },
  { key: 'rose',   name: '玫红',   color: '#EF7FA8' },
] as const
const accent = ref<string>(localStorage.getItem('mangdehenzhi-accent') || 'violet')

/* 账号安全：学生自助改密（2026-11-13）
   登录卡上的初始口令是一次性明文，丢了原本只能找教师重设。
   前端只做长度提示，真正的旧口令校验在后端 /api/auth/change-password。 */
const pwdOld = ref('')
const pwdNew = ref('')
const pwdSaving = ref(false)
const pwdMsg = ref('')
const pwdErr = ref('')

async function changePassword() {
  if (pwdSaving.value) return
  pwdMsg.value = ''
  pwdErr.value = ''
  if (pwdNew.value.length < 8) {
    pwdErr.value = '新口令至少 8 位'
    return
  }
  if (!pwdOld.value) {
    pwdErr.value = '请填写当前口令'
    return
  }
  pwdSaving.value = true
  try {
    const res = await api.post<{ message: string }>('/auth/change-password', {
      old_password: pwdOld.value,
      new_password: pwdNew.value,
    })
    pwdMsg.value = res?.message || '口令已更新'
    pwdOld.value = ''
    pwdNew.value = ''
  } catch (e) {
    pwdErr.value = e instanceof ApiError ? e.message : '修改失败，请稍后重试'
  } finally {
    pwdSaving.value = false
  }
}

function pickAccent(key: string) {
  accent.value = key
  window.dispatchEvent(new CustomEvent('mangdehenzhi:accent', { detail: key }))
}

function toggleTheme() {
  isDark.value = !isDark.value
  window.dispatchEvent(
    new CustomEvent('mangdehenzhi:theme', { detail: isDark.value ? 'dark' : 'light' })
  )
}

async function loadConfig() {
  try {
    const data = await api.get<ConfigResp>('/config')
    config.value = { ...config.value, ...data, llm_api_key: '' }
    hasExistingKey.value = !!data.llm_api_key
  } catch { /* offline */ }
  finally { loading.value = false }
}

// L1/L2/L3 三层学情记忆（低侵入联动：设置页展示记忆薄弱点，失败不影响主流程）
const memoryOverview = ref<any>(null)
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞设置页 */ }
}
onMounted(() => {
  loadConfig()
  loadMemoryOverview()
})

async function testLLM() {
  testing.value = true
  testResult.value = ''
  try {
    const data = await api.post<ConfigTestLLMResp>('/config/test-llm', {
      llm_api_key: config.value.llm_api_key,
      llm_base_url: config.value.llm_base_url,
      llm_model: config.value.llm_model,
      embedding_mode: config.value.embedding_mode,
    })
    testResult.value = data.message || (data.status === 'ok' ? '连接成功' : '连接失败')
  } catch {
    testResult.value = '后端不可用'
  } finally {
    testing.value = false
  }
}

async function saveConfig() {
  saving.value = true
  statusMsg.value = ''
  const payload = { ...config.value }
  if (!payload.llm_api_key && hasExistingKey.value) {
    // 保留空串，后端据此判断不更新 key
    payload.llm_api_key = ''
  }
  try {
    await api.post('/config', payload)
    statusMsg.value = '已保存'
    setTimeout(() => { statusMsg.value = '' }, 2000)
  } catch {
    statusMsg.value = '后端不可用'
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  if (canManageApi.value) loadConfig()
  else loading.value = false
})
</script>

<template>
  <div class="page-section">
    <div v-if="loading" class="settings-shell">
      <div class="skel-line-200 skeleton"></div>
      <div class="skel-card skeleton"></div>
      <div class="skel-card skeleton"></div>
      <div class="skel-card-lg skeleton"></div>
    </div>

    <div v-else class="settings-shell">
      <div class="section-header" v-if="canManageApi">
        <div class="section-title">
          <span v-html="icons.shield" class="section-title-icon"></span>API 管理
        </div>
        <div class="section-desc">配置 LLM 和 Embedding 模型参数（仅管理员）</div>
      </div>
      <div class="section-header" v-else>
        <div class="section-title">
          <span v-html="icons.shield" class="section-title-icon"></span>外观与偏好
        </div>
        <div class="section-desc">配色与明暗主题；模型配置由管理员维护</div>
      </div>

      <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
      <div v-if="canManageApi && memoryOverview?.weak_points?.length" class="memory-mini-strip" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:14px;font-size:12px;">
        <span style="padding:3px 10px;border-radius:12px;background:var(--color-accent-subtle);color:var(--accent-primary);font-weight:600;">记忆薄弱点</span>
        <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" style="padding:3px 10px;border-radius:12px;background:var(--color-surface-2);border:1px solid var(--color-border);color:var(--color-text-2);">{{ w }}</span>
      </div>

      <div class="card" v-if="canManageApi">
        <div class="settings-block">
          <div class="settings-subtitle">LLM 配置</div>

          <label class="form-label">
            API Key
            <span v-if="hasExistingKey" class="badge-configured">已配置</span>
          </label>
          <div class="input-with-action">
            <input
              v-model="config.llm_api_key"
              :type="showKey ? 'text' : 'password'"
              :placeholder="hasExistingKey ? '******** 留空则保持原值' : 'sk-...'"
              class="form-input input-secret"
            />
            <button
              class="input-action"
              type="button"
              @click="showKey = !showKey"
              :aria-label="showKey ? '隐藏密钥' : '显示密钥'"
            >
              <svg v-if="showKey" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
            </button>
          </div>

          <div class="form-grid">
            <div class="form-group">
              <label class="form-label">Base URL</label>
              <input v-model="config.llm_base_url" class="form-input" />
            </div>
            <div class="form-group">
              <label class="form-label">Model</label>
              <input v-model="config.llm_model" class="form-input" />
            </div>
          </div>

          <div class="settings-inline">
            <button class="btn btn-secondary" :disabled="testing" @click="testLLM">
              {{ testing ? '测试中…' : '测试连接' }}
            </button>
            <span v-if="testResult" class="test-result" :class="testResult.includes('成功') ? 'is-ok' : 'is-err'">
              {{ testResult }}
            </span>
          </div>
        </div>

        <div class="settings-block">
          <div class="settings-subtitle">Embedding 模型</div>
          <div class="embed-options">
            <label
              class="embed-option"
              :class="{ 'is-active': config.embedding_mode === 'local' }"
              :style="{ borderColor: config.embedding_mode === 'local' ? 'var(--accent-primary)' : 'var(--border-color)', background: config.embedding_mode === 'local' ? 'var(--color-accent-subtle)' : 'transparent' }"
            >
              <input type="radio" value="local" v-model="config.embedding_mode" class="embed-radio" />
              <div>
                <div class="embed-option-title">本地 ONNX</div>
                <div class="embed-option-desc">离线可用</div>
              </div>
            </label>
            <label
              class="embed-option"
              :class="{ 'is-active': config.embedding_mode === 'api' }"
              :style="{ borderColor: config.embedding_mode === 'api' ? 'var(--accent-primary)' : 'var(--border-color)', background: config.embedding_mode === 'api' ? 'var(--color-accent-subtle)' : 'transparent' }"
            >
              <input type="radio" value="api" v-model="config.embedding_mode" class="embed-radio" />
              <div>
                <div class="embed-option-title">远程 API</div>
                <div class="embed-option-desc">需 API Key</div>
              </div>
            </label>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="settings-block">
          <div class="settings-subtitle">外观</div>
          <p class="appearance-hint">配色只换强调色，画布与文字层级不变；与明暗主题自由组合。</p>
          <div class="accent-row" role="radiogroup" aria-label="配色方案">
            <button
              v-for="a in ACCENTS"
              :key="a.key"
              type="button"
              class="accent-chip"
              :class="{ 'is-active': accent === a.key }"
              :aria-checked="accent === a.key"
              role="radio"
              @click="pickAccent(a.key)"
            >
              <span class="accent-dot" :style="{ background: a.color }"></span>
              <span class="accent-name">{{ a.name }}</span>
            </button>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="settings-block">
          <div class="settings-subtitle">账号安全</div>
          <p class="pwd-hint">登录卡上的初始口令是一次性的，可在此改成你自己的口令（至少 8 位）。改完请用新口令登录。</p>
          <div class="form-grid">
            <div class="form-group">
              <label class="form-label" for="pwd-old">当前口令</label>
              <input
                id="pwd-old"
                v-model="pwdOld"
                class="form-input"
                type="password"
                autocomplete="current-password"
              />
            </div>
            <div class="form-group">
              <label class="form-label" for="pwd-new">新口令</label>
              <input
                id="pwd-new"
                v-model="pwdNew"
                class="form-input"
                type="password"
                autocomplete="new-password"
                placeholder="至少 8 位"
              />
            </div>
          </div>
          <div class="settings-inline">
            <button class="btn btn-primary" :disabled="pwdSaving" @click="changePassword">
              {{ pwdSaving ? '提交中…' : '修改口令' }}
            </button>
            <span v-if="pwdMsg" class="pwd-msg" role="status">{{ pwdMsg }}</span>
            <span v-if="pwdErr" class="pwd-err" role="alert">{{ pwdErr }}</span>
          </div>
        </div>
      </div>

      <div class="settings-actions">
        <button class="btn btn-ghost" @click="toggleTheme">
          {{ isDark ? '切换亮色模式' : '切换暗色模式' }}
        </button>
        <router-link to="/" class="settings-backlink">返回对话</router-link>
        <button class="btn btn-primary" v-if="canManageApi" :disabled="saving" @click="saveConfig">
          {{ saving ? '保存中…' : '保存配置' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 本视图 .card 补内边距（全局 .card 不带 padding，避免内容贴边） */
.card { padding: var(--space-6); }

.settings-shell { max-width: 40rem; margin: 0 auto; }

/* 页头：图标与标题同行。全局 .section-title-icon 是块级，会独占一行把标题顶下去。 */
.section-title { display: flex; align-items: center; gap: 8px; }
.section-title-icon { width: 18px; height: 18px; flex: none; display: inline-flex; align-items: center; }

.settings-block { margin-bottom: var(--space-6); }
.settings-block:last-child { margin-bottom: 0; }

/* 三个区块标题统一用中性强色，层级靠字号与间距承担；
   原先主色标题 + 另一块灰标题，会让人误判"Embedding 模型"是次级模块。 */
.settings-subtitle {
  font-size: var(--text-md); font-weight: var(--weight-semibold); margin-bottom: var(--space-4);
  color: var(--color-text);
}
.settings-subtitle--secondary { color: var(--color-text-2); }

.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); margin-top: var(--space-3); }

/* 表单原子：全局样式区没有 .form-group / .form-label / .form-input，
   缺了它们 label 与 input 会按 inline 排在同一行、输入框只剩默认宽度。 */
.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-label {
  display: block;
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-2);
  margin-bottom: 2px;
}
.form-input {
  width: 100%;
  padding: 9px 12px;
  border-radius: 9px;
  border: 1px solid var(--color-border);
  background: var(--color-surface-2);
  color: var(--color-text);
  font-family: inherit;
  font-size: var(--text-sm);
  line-height: 1.4;
  transition: var(--transition);
  box-sizing: border-box;
}
.form-input::placeholder { color: var(--color-text-3); }
.form-input:focus {
  outline: none;
  border-color: var(--color-border-focus);
  box-shadow: 0 0 0 3px var(--color-accent-subtle);
}

.input-with-action { position: relative; margin-bottom: var(--space-3); }
.input-secret { padding-right: var(--space-10); }
.input-action {
  position: absolute; right: 0.5rem; top: 50%; transform: translateY(-50%);
  border: none; background: none; cursor: pointer; color: var(--text-muted);
  padding: var(--space-1); display: inline-flex; border-radius: var(--radius-sm);
  transition: color var(--duration-fast);
}
.input-action:hover { color: var(--text-primary); }

.badge-configured {
  margin-left: var(--space-2); font-size: var(--text-2xs); font-weight: var(--weight-semibold);
  color: var(--accent-success); padding: 0.125rem var(--space-2); border-radius: var(--radius-xs);
  background: var(--accent-success-10);
}

.settings-inline { display: flex; align-items: center; gap: var(--space-3); margin-top: var(--space-3); }

.embed-options { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); }
.embed-option {
  display: flex; align-items: center; gap: 0.625rem; padding: 0.875rem;
  border-radius: var(--radius-sm); border: 2px solid var(--border-color);
  cursor: pointer; transition: var(--transition); background: transparent;
}
.embed-option.is-active {
  border-color: var(--accent-primary);
  background: var(--color-accent-subtle);   /* 原 --accent-primary-10 未定义，背景实际是透明的 */
}
.embed-radio { accent-color: var(--accent-primary); width: auto; }
.embed-option-title { font-size: var(--text-sm); font-weight: var(--weight-semibold); color: var(--text-primary); }
.embed-option-desc { font-size: var(--text-2xs); color: var(--text-muted); }

.test-result { font-size: var(--text-xs); }
.test-result.is-ok { color: var(--accent-success); }
.test-result.is-err { color: var(--accent-danger); }

/* ── 外观：配色方案 ── */
.appearance-hint {
  margin: 0 0 var(--space-3);
  font-size: var(--text-2xs);
  color: var(--text-muted);
  line-height: 1.5;
}

/* ── 账号安全：改密 ── */
.pwd-hint {
  margin: 0 0 var(--space-3);
  font-size: var(--text-2xs);
  color: var(--text-muted);
  line-height: 1.5;
}
.pwd-msg { font-size: var(--text-2xs); color: var(--accent-success); }
.pwd-err { font-size: var(--text-2xs); color: var(--accent-danger); }
.accent-row { display: flex; flex-wrap: wrap; gap: 8px; }
.accent-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  border-radius: 9px;
  border: 1px solid var(--color-border);
  background: var(--color-card);
  color: var(--color-text-2);
  font-family: inherit;
  font-size: var(--text-xs);
  cursor: pointer;
  transition: var(--transition);
}
.accent-chip:hover { border-color: var(--color-border-strong); color: var(--color-text); }
.accent-chip.is-active {
  border-color: var(--accent-primary);
  color: var(--color-text);
  box-shadow: 0 0 0 3px var(--color-accent-subtle);
}
.accent-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.18);
}
.accent-name { white-space: nowrap; }

.settings-actions {
  display: flex; gap: var(--space-3); justify-content: flex-end; align-items: center;
  margin-top: var(--space-6);
}
.settings-backlink { font-size: var(--text-sm); color: var(--text-muted); text-decoration: underline; }
.settings-backlink:hover { color: var(--text-secondary); }

/* 骨架屏尺寸（复用全局 .skeleton 微光动画） */
.skel-line-200 { width: 12.5rem; height: 1.75rem; margin: 0 auto var(--space-5); border-radius: var(--radius-sm); }
.skel-card { width: 100%; height: 3.75rem; margin-bottom: var(--space-3); border-radius: var(--radius-md); }
.skel-card-lg { width: 100%; height: 7.5rem; border-radius: var(--radius-md); }

@media (max-width: 640px) {
  .settings-actions { flex-wrap: wrap; }
  .form-grid, .embed-options { grid-template-columns: 1fr; }
}
</style>
