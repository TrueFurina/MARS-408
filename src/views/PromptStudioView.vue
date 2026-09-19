<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { icons } from '@/components/icons'
import { useSkillStore, type SkillTemplate } from '@/stores/skillStore'
import { api } from '@/utils/api'

const router = useRouter()
const store = useSkillStore()

// ── 编辑区 ──
const promptText = ref('')
const promptTitle = ref('')
const selectedTemplate = ref('')
const temperature = ref(0.7)
const llmChannel = ref('auto')

// ── 测试对话区 ──
const testInput = ref('')
const testOutput = ref('')
const testLoading = ref(false)
const testError = ref('')

const channelOptions = [
  { value: 'auto', label: '自动选择' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'xfyun', label: '讯飞星火' },
  { value: 'qwen', label: 'Qwen' },
]

function applyTemplate(tmpl: SkillTemplate) {
  promptText.value = tmpl.system_prompt_template
  promptTitle.value = `我的${tmpl.name}`
  selectedTemplate.value = tmpl.id
  temperature.value = tmpl.default_config?.temperature ?? 0.7
  llmChannel.value = tmpl.default_config?.llm_channel || 'auto'
}

function insertVariable(name: string) {
  promptText.value += `{{${name}}}`
}

async function runTest() {
  if (!testInput.value.trim()) return
  if (!promptText.value.trim()) {
    testError.value = '请先输入 System Prompt'
    return
  }
  testLoading.value = true
  testError.value = ''
  testOutput.value = ''

  try {
    const res: any = await api.post('/skills/prompt-test', {
      system_prompt: promptText.value,
      message: testInput.value,
      llm_channel: llmChannel.value,
      temperature: temperature.value,
    })
    testOutput.value = res?.response || '(无响应)'
  } catch (e: any) {
    const msg = String(e?.message || e || '调用失败')
    if (/Failed to fetch|NetworkError|ECONNREFUSED|ERR_/i.test(msg)) {
      testError.value = '后端服务未连接，请先运行后端服务'
    } else if (/LLM .* 通道.*不可用|quota|limit|rate/i.test(msg)) {
      testError.value = 'LLM 服务暂不可用，请检查 API Key 配置或稍后重试'
    } else {
      testError.value = msg
    }
  } finally {
    testLoading.value = false
  }
}

async function saveAsSkill() {
  if (!promptText.value.trim()) return
  const name = promptTitle.value.trim() || '未命名技能'
  const result = await store.createSkill({
    name,
    system_prompt: promptText.value,
    llm_channel: llmChannel.value,
    temperature: temperature.value,
    category: 'teaching',
  })
  if (result) {
    router.push(`/studio/${result.id}`)
  }
}

onMounted(() => {
  store.fetchTemplates()
  loadMemoryOverview()
})

// L1/L2/L3 三层学情记忆（低侵入联动：提示词工作室页展示记忆薄弱点，失败不影响主流程）
const memoryOverview = ref<any>(null)
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞提示词工作室页 */ }
}
</script>

<template>
  <div class="page-section">
    <div class="section-header">
      <div class="section-title-group">
        <div class="section-title" v-html="icons.skill"></div>
        <div>
          <div class="section-title"> Prompt Studio</div>
          <div class="section-desc">可视化编辑 System Prompt，实时测试效果</div>
        </div>
      </div>
      <div class="section-actions">
        <button class="btn btn-primary" @click="saveAsSkill">
          <span v-html="icons.plus"></span> 保存为技能
        </button>
        <button class="btn btn-ghost" @click="router.push('/skills')">← 返回市场</button>
      </div>
    </div>

    <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
    <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">
      <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);"> 记忆薄弱点:</span>
      <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" style="padding:3px 10px;border-radius:12px;background:rgba(239,68,68,0.12);color:var(--accent-danger);">{{ w }}</span>
    </div>

    <div class="studio-layout">
      <!-- 左侧：编辑器 -->
      <div class="editor-panel">
        <!-- 模板选择 -->
        <div v-if="store.templates.length" class="template-strip">
          <span class="strip-label">从模板：</span>
          <button
            v-for="t in store.templates"
            :key="t.id"
            class="strip-btn"
            :class="{ active: selectedTemplate === t.id }"
            @click="applyTemplate(t)"
          >{{ t.icon }} {{ t.name }}</button>
        </div>

        <div class="form-group">
          <label class="form-label">技能名称</label>
          <input v-model="promptTitle" class="form-input" placeholder="给这个 Prompt 起个名字" />
        </div>

        <div class="form-row">
          <div class="form-group">
            <label class="form-label">LLM 通道</label>
            <select v-model="llmChannel" class="form-select">
              <option v-for="opt in channelOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">温度 ({{ temperature }})</label>
            <input v-model.number="temperature" type="range" min="0" max="1" step="0.1" class="form-range" />
          </div>
        </div>

        <div class="form-group">
          <div class="form-label-row">
            <label class="form-label">System Prompt</label>
            <div class="var-hint">
              插入变量：
              <button class="var-btn" @click="insertVariable('subject')">subject</button>
              <button class="var-btn" @click="insertVariable('difficulty')">difficulty</button>
              <button class="var-btn" @click="insertVariable('knowledge_point')">knowledge_point</button>
              <button class="var-btn" @click="insertVariable('style')">style</button>
              <button class="var-btn" @click="insertVariable('concept')">concept</button>
            </div>
          </div>
          <textarea
            v-model="promptText"
            class="form-textarea code-textarea prompt-editor"
            placeholder="你是一个 408 出题专家。请根据以下要求生成练习题..."
            rows="14"
          ></textarea>
        </div>
      </div>

      <!-- 右侧：测试区 -->
      <div class="test-panel">
        <div class="panel-title"> 实时测试</div>

        <div class="test-input-area">
          <textarea
            v-model="testInput"
            class="test-input"
            placeholder="输入测试消息..."
            rows="3"
            @keydown.enter.ctrl="runTest"
          ></textarea>
          <button class="btn btn-primary test-btn" :disabled="testLoading || !testInput.trim()" @click="runTest">
            <span v-if="testLoading" class="typing-indicator" aria-label="思考中"><span></span><span></span><span></span></span>
            <span v-else>发送</span>
          </button>
        </div>

        <div v-if="testError" class="test-error">{{ testError }}</div>

        <div v-if="testOutput" class="test-output">
          <div class="output-label">响应：</div>
          <div class="output-content">{{ testOutput }}</div>
        </div>

        <div v-else-if="!testLoading" class="test-placeholder">
          <div class="placeholder-icon"></div>
          <div class="placeholder-text">输入测试消息后点击"发送"，查看 Prompt 效果</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.section-header { display: flex; justify-content: space-between; align-items: flex-start; gap:var(--space-4); flex-wrap: wrap; }
.section-title-group { display: flex; align-items: center; gap:var(--space-3); }
.section-title-group :deep(svg) { width:2rem; height:2rem; color: var(--accent); }
.section-actions { display: flex; gap:var(--space-2); }

.studio-layout { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-5); margin-top: var(--space-4); }
@media (max-width: 1000px) { .studio-layout { grid-template-columns: 1fr; } }

.editor-panel { min-width:0; }

.template-strip { display: flex; align-items: center; gap:0.375rem; flex-wrap: wrap; margin-bottom:var(--space-4); padding:0.625rem var(--space-3); background: var(--color-surface-2); border-radius:0.625rem; }
.strip-label { font-size:var(--text-xs); color: var(--color-text-3); font-weight: var(--weight-medium); white-space: nowrap; }
.strip-btn { padding:var(--space-1) 0.625rem; border: 1px solid var(--color-border); border-radius:0.375rem; background: var(--color-surface); color: var(--color-text-2); font-size:var(--text-xs); cursor: pointer; transition: var(--transition); white-space: nowrap; }
.strip-btn:hover { border-color: var(--color-border-focus); }
.strip-btn.active { border-color: var(--accent); background: var(--accent-primary-10); color: var(--accent); }

.form-group { margin-bottom:var(--space-3); }
.form-label { display: block; font-size:var(--text-sm); font-weight: var(--weight-medium); color: var(--color-text-2); margin-bottom:var(--space-1); }
.form-label-row { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap:var(--space-2); }
.form-input, .form-select { width:100%; padding:0.625rem var(--space-3); border: 1px solid var(--color-border); border-radius:0.5rem; background: var(--color-surface-2); color: var(--color-text); font-size:var(--text-base); }
.form-input:focus, .form-select:focus { outline: none; border-color: var(--color-border-focus); }
.form-textarea { width:100%; padding:0.625rem var(--space-3); border: 1px solid var(--color-border); border-radius:0.5rem; background: var(--color-surface-2); color: var(--color-text); font-size:var(--text-base); resize: vertical; }
.form-textarea:focus { outline: none; border-color: var(--color-border-focus); }
.code-textarea { font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace; font-size:var(--text-sm); line-height:1.5; }
.prompt-editor { min-height:17.5rem; }
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); }
.form-range { width:100%; accent-color: var(--accent); }

.var-hint { font-size:var(--text-2xs); color: var(--color-text-3); display: flex; align-items: center; gap:var(--space-1); flex-wrap: wrap; }
.var-btn { padding:0.125rem 0.375rem; border: 1px dashed var(--color-border); border-radius:0.25rem; background: transparent; color: var(--accent); font-size:var(--text-2xs); cursor: pointer; font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace; }
.var-btn:hover { background: color-mix(in srgb, var(--accent-primary) 8%, transparent); }

/* 测试面板 */
.test-panel { position: sticky; top:1rem; align-self: start; }
.panel-title { font-size:var(--text-lg); font-weight: var(--weight-semibold); margin-bottom:var(--space-3); color: var(--color-text); }

.test-input-area { display: flex; flex-direction: column; gap:var(--space-2); }
.test-input { width:100%; padding:0.625rem var(--space-3); border: 1px solid var(--color-border); border-radius:0.5rem; background: var(--color-surface-2); color: var(--color-text); font-size:var(--text-base); resize: vertical; }
.test-input:focus { outline: none; border-color: var(--color-border-focus); }
.test-btn { align-self: flex-end; }

.test-error { padding:0.625rem var(--space-3); background: var(--accent-danger-10); color: var(--accent-danger); border-radius:0.5rem; font-size:var(--text-sm); margin-top:var(--space-2); }

.test-output { margin-top:var(--space-3); padding:var(--space-3); background: var(--color-surface-2); border-radius:0.5rem; }
.output-label { font-size: var(--text-2xs); font-weight: var(--weight-semibold); color: var(--color-text-3); margin-bottom: 6px; text-transform: uppercase; }
.output-content { font-size:var(--text-base); line-height:1.6; color: var(--color-text); white-space: pre-wrap; }

.test-placeholder { margin-top:var(--space-6); text-align: center; padding:var(--space-10) var(--space-5); }
.placeholder-icon { font-size:2.5rem; margin-bottom:var(--space-2); }
.placeholder-text { font-size:var(--text-base); color: var(--color-text-3); }

/* 移动端适配 */
@media (max-width: 480px) {
  .page-section { padding: var(--space-4) var(--space-3); }
  .studio-layout { gap: var(--space-3); }
  .section-header { flex-direction: column; }
  .section-actions { width: 100%; }
  .section-actions .btn { flex: 1; }
  .test-btn { width: 100%; }
}
</style>