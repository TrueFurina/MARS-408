<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useStudyStore } from '@/stores/studyStore'
import { api } from '@/utils/api'
import { icons } from '@/components/icons'

const router = useRouter()
const store = useStudyStore()

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
const isDark = ref(localStorage.getItem('mars408_theme') !== 'light')

function toggleTheme() {
  isDark.value = !isDark.value
  document.documentElement.setAttribute('data-theme', isDark.value ? 'dark' : 'light')
  localStorage.setItem('mars408_theme', isDark.value ? 'dark' : 'light')
}

async function loadConfig() {
  try {
    const data = await api.get<any>('/config')
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
    const data = await api.post<any>('/config/test-llm', {
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

onMounted(loadConfig)
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
      <div class="section-header section-header--center">
        <div class="section-title">
          <span v-html="icons.shield" class="section-title-icon"></span>API 管理
        </div>
        <div class="section-desc">配置 LLM 和 Embedding 模型参数</div>
      </div>

      <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
      <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">
        <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);">🧠 记忆薄弱点:</span>
        <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" style="padding:3px 10px;border-radius:12px;background:rgba(239,68,68,0.12);color:var(--accent-danger);">{{ w }}</span>
      </div>

      <div class="card">
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
          <div class="settings-subtitle settings-subtitle--secondary">Embedding 模型</div>
          <div class="embed-options">
            <label
              class="embed-option"
              :class="{ 'is-active': config.embedding_mode === 'local' }"
              :style="{ borderColor: config.embedding_mode === 'local' ? 'var(--accent-primary)' : 'var(--border-color)', background: config.embedding_mode === 'local' ? 'var(--accent-primary-10)' : 'transparent' }"
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
              :style="{ borderColor: config.embedding_mode === 'api' ? 'var(--accent-primary)' : 'var(--border-color)', background: config.embedding_mode === 'api' ? 'var(--accent-primary-10)' : 'transparent' }"
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

      <div class="settings-actions">
        <button class="btn btn-ghost" @click="toggleTheme">
          {{ isDark ? '切换亮色模式' : '切换暗色模式' }}
        </button>
        <router-link to="/" class="settings-backlink">返回对话</router-link>
        <button class="btn btn-primary" :disabled="saving" @click="saveConfig">
          {{ saving ? '保存中…' : '保存配置' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 本视图 .card 补内边距（全局 .card 不带 padding，避免内容贴边） */
.card { padding: 1.5rem; }

.settings-shell { max-width: 35rem; margin: 0 auto; }
.section-header--center { text-align: center; }

.settings-block { margin-bottom: 1.5rem; }
.settings-block:last-child { margin-bottom: 0; }

.settings-subtitle {
  font-size: 0.9375rem; font-weight: 600; margin-bottom: 1rem;
  color: var(--accent-primary);
}
.settings-subtitle--secondary { color: var(--accent-secondary); }

.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }

.input-with-action { position: relative; margin-bottom: 0.75rem; }
.input-secret { padding-right: 2.5rem; }
.input-action {
  position: absolute; right: 0.5rem; top: 50%; transform: translateY(-50%);
  border: none; background: none; cursor: pointer; color: var(--text-muted);
  padding: 0.25rem; display: inline-flex; border-radius: var(--radius-sm);
  transition: color var(--duration-fast);
}
.input-action:hover { color: var(--text-primary); }

.badge-configured {
  margin-left: 0.5rem; font-size: 0.6875rem; font-weight: 600;
  color: var(--accent-success); padding: 0.125rem 0.5rem; border-radius: var(--radius-xs);
  background: var(--accent-success-10);
}

.settings-inline { display: flex; align-items: center; gap: 0.75rem; }

.embed-options { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
.embed-option {
  display: flex; align-items: center; gap: 0.625rem; padding: 0.875rem;
  border-radius: var(--radius-sm); border: 2px solid var(--border-color);
  cursor: pointer; transition: var(--transition); background: transparent;
}
.embed-option.is-active {
  border-color: var(--accent-primary);
  background: var(--accent-primary-10);
}
.embed-radio { accent-color: var(--accent-primary); width: auto; }
.embed-option-title { font-size: 0.8125rem; font-weight: 600; color: var(--text-primary); }
.embed-option-desc { font-size: 0.6875rem; color: var(--text-muted); }

.test-result { font-size: 0.75rem; }
.test-result.is-ok { color: var(--accent-success); }
.test-result.is-err { color: var(--accent-danger); }

.settings-actions {
  display: flex; gap: 0.75rem; justify-content: flex-end; align-items: center;
  margin-top: 1.5rem;
}
.settings-backlink { font-size: 0.8125rem; color: var(--text-muted); text-decoration: underline; }
.settings-backlink:hover { color: var(--text-secondary); }

/* 骨架屏尺寸（复用全局 .skeleton 微光动画） */
.skel-line-200 { width: 12.5rem; height: 1.75rem; margin: 0 auto 1.25rem; border-radius: var(--radius-sm); }
.skel-card { width: 100%; height: 3.75rem; margin-bottom: 0.75rem; border-radius: var(--radius-md); }
.skel-card-lg { width: 100%; height: 7.5rem; border-radius: var(--radius-md); }

@media (max-width: 640px) {
  .settings-actions { flex-wrap: wrap; }
  .form-grid, .embed-options { grid-template-columns: 1fr; }
}
</style>
