<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { icons } from '@/components/icons'
import { useSkillStore, type SkillTemplate } from '@/stores/skillStore'
import { api } from '@/utils/api'

const route = useRoute()
const router = useRouter()
const store = useSkillStore()

const isEdit = computed(() => !!route.params.id)
const skillId = computed(() => route.params.id as string || '')

// ── 表单数据 ──
const name = ref('')
const description = ref('')
const icon = ref('🤖')
const systemPrompt = ref('')
const llmChannel = ref('auto')
const temperature = ref(0.7)
const maxTokens = ref(2048)
const category = ref('teaching')
const tags = ref('')
const ragEnabled = ref(true)
const selectedTemplate = ref('')

// P2②：记忆权限配置（L1/L2/L3 读写管控）
const useMemory = ref(true)
const memoryAccess = ref('read_write')
const memoryAccessOptions = [
  { value: 'none', label: '❌ 无权限', desc: '技能不访问学情记忆' },
  { value: 'read', label: '📖 只读', desc: '可读取薄弱点/画像，不可写入' },
  { value: 'write', label: '✍️ 只写', desc: '可回写行为事件，不可读取' },
  { value: 'read_write', label: '🔁 读写', desc: '读薄弱学情 + 回写行为记忆' },
]

// 循环13-P0：结构化工具元数据（tools 驱动 LLM 选工具）
const useTools = ref(false)
const toolsMeta = ref<{ name: string; description: string; parameters: string }[]>([])

function addToolMeta() {
  toolsMeta.value.push({ name: '', description: '', parameters: '' })
}

function toolsPayload(): any[] {
  return toolsMeta.value
    .filter(t => t.name.trim())
    .map(t => {
      let parameters: any = { type: 'object', properties: {} }
      try {
        if (t.parameters.trim()) parameters = JSON.parse(t.parameters)
      } catch { /* 参数 JSON 非法时保留默认空 schema */ }
      return {
        type: 'function',
        function: { name: t.name.trim(), description: t.description.trim(), parameters },
      }
    })
}

const saving = ref(false)
const saved = ref(false)
const errorMsg = ref('')
const formTouched = ref(false)

// 离开前提示
function confirmLeave() {
  if (formTouched.value && !saved.value) {
    return '有未保存的修改，确定离开吗？'
  }
  return undefined
}

const categories = [
  { value: 'teaching', label: '教学讲解' },
  { value: 'quiz', label: '出题练习' },
  { value: 'diagnosis', label: '诊断评估' },
  { value: 'guide', label: '学习引导' },
  { value: 'code', label: '代码实践' },
  { value: 'mindmap', label: '思维导图' },
  { value: 'other', label: '其他' },
]

const channelOptions = [
  { value: 'auto', label: '自动选择' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'xfyun', label: '讯飞星火' },
  { value: 'qwen', label: 'Qwen' },
]

const iconOptions = ['🤖', '📝', '🎓', '🔍', '📊', '🧩', '📋', '📖', '🗣️', '💻', '🎯', '💡', '📚', '✏️', '🔬']

function applyTemplate(tmpl: SkillTemplate) {
  name.value = `我的${tmpl.name}`
  description.value = tmpl.description
  icon.value = tmpl.icon
  systemPrompt.value = tmpl.system_prompt_template
  llmChannel.value = tmpl.default_config?.llm_channel || 'auto'
  temperature.value = tmpl.default_config?.temperature ?? 0.7
  maxTokens.value = tmpl.default_config?.max_tokens ?? 2048
  category.value = tmpl.category
  selectedTemplate.value = tmpl.id
}

async function loadForEdit() {
  if (!isEdit.value) return
  try {
    await store.fetchSkill(skillId.value)
    const s = store.currentSkill
    if (!s) return
    name.value = s.name
    description.value = s.description
    icon.value = s.icon
    systemPrompt.value = s.system_prompt
    llmChannel.value = s.llm_channel
    temperature.value = s.temperature
    maxTokens.value = s.max_tokens
    category.value = s.category
    tags.value = s.tags.join(', ')
    ragEnabled.value = s.rag_enabled
    // 循环13-P0：编辑时回填 tools 元数据
    const tools = (s as any).tools || []
    useTools.value = tools.length > 0
    toolsMeta.value = tools.map((t: any) => ({
      name: t?.function?.name || '',
      description: t?.function?.description || '',
      parameters: JSON.stringify(t?.function?.parameters || { type: 'object', properties: {} }),
    }))
  } catch (e) {
    errorMsg.value = '加载技能失败，请检查后端服务'
    console.error('SkillStudio loadForEdit error:', e)
  }
}

async function doSave() {
  if (!name.value.trim()) {
    errorMsg.value = '请输入技能名称'
    return
  }
  saving.value = true
  errorMsg.value = ''
  saved.value = false

  const tagList = tags.value.split(',').map(t => t.trim()).filter(Boolean)
  const payload = {
    name: name.value.trim(),
    description: description.value.trim(),
    icon: icon.value,
    system_prompt: systemPrompt.value,
    llm_channel: llmChannel.value,
    temperature: temperature.value,
    max_tokens: maxTokens.value,
    category: category.value,
    tags: JSON.stringify(tagList),
    rag_enabled: ragEnabled.value,
    use_memory: useMemory.value,
    memory_access: memoryAccess.value,
    tools: useTools.value ? toolsPayload() : [],
  }

  let ok = false
  try {
    if (isEdit.value) {
      ok = await store.updateSkill(skillId.value, payload)
      if (ok) await store.fetchSkill(skillId.value)
    } else {
      const result = await store.createSkill(payload)
      ok = !!result
      if (result) {
        router.replace(`/studio/${result.id}`)
        await store.fetchSkill(result.id)
      }
    }
  } catch (e) {
    console.error('SkillStudio doSave error:', e)
    ok = false
  } finally {
    saving.value = false
  }
  if (ok) {
    saved.value = true
    formTouched.value = false
    // 刷新列表
    try {
      store.fetchMarket()
      store.fetchMySkills()
    } catch { /* 列表刷新失败不影响保存结果 */ }
    setTimeout(() => { saved.value = false }, 3000)
  } else {
    errorMsg.value = store.error || '保存失败，请检查后端服务'
  }
}

async function doPublish() {
  try {
    await doSave()
    if (isEdit.value && !errorMsg.value) {
      const ok = await store.publishSkill(skillId.value)
      if (ok) router.push(`/skills/${skillId.value}`)
    }
  } catch (e) {
    errorMsg.value = '发布失败，请稍后重试'
    console.error('SkillStudio doPublish error:', e)
  }
}

onMounted(async () => {
  try {
    await store.fetchTemplates()
    if (isEdit.value) {
      await loadForEdit()
    }
  } catch (e) {
    errorMsg.value = '初始化失败，请检查后端服务'
    console.error('SkillStudio onMounted error:', e)
  }
  loadMemoryOverview()
})

// L1/L2/L3 三层学情记忆（低侵入联动：技能工作室页展示记忆薄弱点，失败不影响主流程）
const memoryOverview = ref<any>(null)
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞技能工作室页 */ }
}
</script>

<template>
  <div class="page-section">
    <div class="back-row">
      <button class="btn btn-ghost" @click="router.push('/skills')">← 返回市场</button>
    </div>

    <div class="studio-layout">
      <!-- 左侧：编辑器 -->
      <div class="studio-editor">
        <div class="section-title">{{ isEdit ? '编辑技能' : '创建新技能' }}</div>
        <div class="section-desc">{{ isEdit ? '修改技能配置后保存' : '从模板开始或从零创建' }}</div>

        <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
        <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">
          <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);">🧠 记忆薄弱点:</span>
          <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" style="padding:3px 10px;border-radius:12px;background:rgba(239,68,68,0.12);color:var(--accent-danger);">{{ w }}</span>
        </div>

        <!-- 模板选择（仅创建时） -->
        <div v-if="!isEdit && store.templates.length" class="template-picker">
          <div class="form-label">从模板创建（可选）</div>
          <div class="template-grid">
            <button
              v-for="t in store.templates"
              :key="t.id"
              class="template-btn"
              :class="{ active: selectedTemplate === t.id }"
              @click="applyTemplate(t)"
            >
              <span class="tpl-icon">{{ t.icon }}</span>
              <span class="tpl-name">{{ t.name }}</span>
            </button>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">技能名称 *</label>
          <input v-model="name" class="form-input" placeholder="给技能起个名字" maxlength="100" />
        </div>

        <div class="form-group">
          <label class="form-label">描述</label>
          <textarea v-model="description" class="form-textarea" placeholder="简要描述这个技能的功能" rows="2" maxlength="500"></textarea>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label class="form-label">图标</label>
            <div class="icon-picker">
              <button
                v-for="opt in iconOptions"
                :key="opt"
                class="icon-opt"
                :class="{ active: icon === opt }"
                @click="icon = opt"
              >{{ opt }}</button>
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">分类</label>
            <select v-model="category" class="form-select">
              <option v-for="c in categories" :key="c.value" :value="c.value">{{ c.label }}</option>
            </select>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">标签（逗号分隔）</label>
          <input v-model="tags" class="form-input" placeholder="如: 数据结构, 出题, 冲刺" />
        </div>

        <div class="form-section-divider">⚙️ AI 配置</div>

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
          <div class="form-group">
            <label class="form-label">最大 Token</label>
            <input v-model.number="maxTokens" type="number" min="64" max="8192" step="64" class="form-input" />
          </div>
        </div>

        <div class="form-group">
          <label class="checkbox-label">
            <input v-model="ragEnabled" type="checkbox" class="form-checkbox" />
            启用 RAG 知识库检索
          </label>
        </div>

        <!-- P2②：记忆权限配置面板（L1/L2/L3 读写管控） -->
        <div class="form-section-divider">🧠 学情记忆权限</div>
        <div class="form-group">
          <label class="checkbox-label">
            <input v-model="useMemory" type="checkbox" class="form-checkbox" />
            启用 L1/L2/L3 学情记忆联动
          </label>
        </div>
        <div v-if="useMemory" class="memory-access-panel">
          <div
            v-for="opt in memoryAccessOptions"
            :key="opt.value"
            class="memory-access-opt"
            :class="{ active: memoryAccess === opt.value }"
            @click="memoryAccess = opt.value"
          >
            <div class="ma-label">{{ opt.label }}</div>
            <div class="ma-desc">{{ opt.desc }}</div>
          </div>
        </div>

        <!-- 循环13-P0：结构化工具元数据（tools 驱动 LLM 选工具） -->
        <div class="form-section-divider">🔧 工具元数据（可选）</div>
        <div class="form-group">
          <label class="checkbox-label">
            <input v-model="useTools" type="checkbox" class="form-checkbox" />
            启用结构化工具（LLM 按元数据准确选择工具）
          </label>
        </div>
        <div v-if="useTools" class="tools-editor">
          <div v-for="(t, ti) in toolsMeta" :key="ti" class="tool-editor-item">
            <div class="tool-editor-header">
              <span class="tool-index">#{{ ti + 1 }}</span>
              <input v-model="t.name" class="form-input tool-name-input" placeholder="工具名（如 calculate_subnet）" />
              <button class="tool-del-btn" title="删除工具" @click="toolsMeta.splice(ti, 1)">🗑️</button>
            </div>
            <input v-model="t.description" class="form-input" placeholder="工具描述（LLM 选择依据，如「用户要求计算子网时应调用」）" />
            <textarea
              v-model="t.parameters"
              class="form-textarea code-textarea tool-params"
              placeholder='参数 JSON Schema（OpenAI function 格式），如 {"type":"object","properties":{"ip":{"type":"string","description":"IP地址"}},"required":["ip"]}'
              rows="3"
            ></textarea>
          </div>
          <button class="tool-add-btn" @click="addToolMeta">➕ 添加工具</button>
          <div class="tool-hint">tools 为 OpenAI function schema 列表；配置后 LLM 会按 name/description/parameters 元数据准确选工具并生成合规参数</div>
        </div>

        <div class="form-section-divider">💬 System Prompt</div>

        <div class="form-group">
          <label class="form-label">System Prompt — 定义 AI 的行为和角色</label>
          <textarea
            v-model="systemPrompt"
            class="form-textarea code-textarea"
            placeholder="你是一个 408 出题专家。请根据以下要求生成练习题..."
            rows="10"
          ></textarea>
        </div>

        <!-- 错误/成功提示 -->
        <div v-if="errorMsg" class="form-error">{{ errorMsg }}</div>
        <div v-if="saved" class="form-success">✅ 已保存</div>

        <!-- 操作按钮 -->
        <div class="form-actions">
          <button class="btn btn-primary" :disabled="saving" @click="doSave">
            {{ saving ? '保存中...' : '💾 保存草稿' }}
          </button>
          <button class="btn btn-success" :disabled="saving" @click="doPublish">
            {{ saving ? '保存中...' : '🚀 保存并发布' }}
          </button>
          <button class="btn btn-ghost" @click="router.push('/skills')">取消</button>
        </div>
      </div>

      <!-- 右侧：预览 -->
      <div class="studio-preview">
        <div class="section-title">预览</div>
        <div class="preview-card">
          <div class="preview-icon">{{ icon }}</div>
          <div class="preview-name">{{ name || '技能名称' }}</div>
          <div class="preview-desc">{{ description || '技能描述' }}</div>
          <div class="preview-config">
            <span>LLM: {{ llmChannel }}</span>
            <span>· T: {{ temperature }}</span>
            <span>· Max: {{ maxTokens }}</span>
          </div>
          <div class="preview-category">{{ categories.find(c => c.value === category)?.label || category }}</div>
          <div v-if="systemPrompt" class="preview-prompt">
            <div class="preview-prompt-title">System Prompt:</div>
            <pre>{{ systemPrompt.slice(0, 200) }}{{ systemPrompt.length > 200 ? '...' : '' }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.back-row { margin-bottom:1rem; }

.studio-layout { display: grid; grid-template-columns: 1fr 320px; gap: 24px; }
@media (max-width: 900px) { .studio-layout { grid-template-columns: 1fr; } }

.studio-editor { min-width:0; }
.studio-preview { position: sticky; top:1rem; align-self: start; }

.template-picker { margin:0.75rem 0; }
.template-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 6px; margin-top: 6px; }
.template-btn { display: flex; flex-direction: column; align-items: center; gap:0.25rem; padding:0.625rem 0.5rem; border: 1px solid var(--color-border); border-radius:0.625rem; background: var(--color-surface); cursor: pointer; transition: all 0.15s; }
.template-btn:hover { border-color: var(--color-border-focus); background: var(--color-surface-hover); }
.template-btn.active { border-color: var(--accent); background: rgba(124,106,242,0.08); }
.tpl-icon { font-size:1.5rem; }
.tpl-name { font-size:0.6875rem; color: var(--color-text-2); text-align: center; }

.form-group { margin-bottom:0.75rem; }
.form-label { display: block; font-size:0.8125rem; font-weight: 500; color: var(--color-text-2); margin-bottom:0.25rem; }
.form-input, .form-select, .form-textarea { width:100%; padding:0.625rem 0.75rem; border: 1px solid var(--color-border); border-radius:0.5rem; background: var(--color-surface-2); color: var(--color-text); font-size:0.875rem; }
.form-input:focus, .form-select:focus, .form-textarea:focus { outline: none; border-color: var(--color-border-focus); }
.form-textarea { resize: vertical; min-height:3.75rem; }
.code-textarea { font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace; font-size:0.8125rem; line-height:1.5; }
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 600px) { .form-row { grid-template-columns: 1fr; } }
.form-range { width:100%; accent-color: var(--accent); }
.form-checkbox { margin-right:0.375rem; accent-color: var(--accent); }
.checkbox-label { font-size:0.875rem; color: var(--color-text-2); cursor: pointer; display: flex; align-items: center; }
/* P2②：记忆权限配置面板 */
.memory-access-panel { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-top: 4px; }
@media (max-width: 640px) { .memory-access-panel { grid-template-columns: 1fr; } }
.memory-access-opt { padding: 10px 12px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); cursor: pointer; transition: var(--transition); background: var(--glass-bg); }
.memory-access-opt:hover { border-color: var(--accent); }
.memory-access-opt.active { border-color: var(--accent); background: var(--accent-primary-10); box-shadow: 0 0 0 2px var(--accent-primary-10); }
.ma-label { font-size: 0.8125rem; font-weight: 600; color: var(--color-text); margin-bottom: 2px; }
.ma-desc { font-size: 0.75rem; color: var(--color-text-2); line-height: 1.4; }
/* 循环13-P0：工具元数据编辑面板 */
.tools-editor { display: flex; flex-direction: column; gap: 8px; }
.tool-editor-item { border: 1px solid var(--color-border); border-radius: var(--radius-sm); padding: 10px; background: var(--glass-bg); }
.tool-editor-header { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.tool-index { font-size: 0.75rem; color: var(--color-text-2); flex-shrink: 0; }
.tool-name-input { flex: 1; }
.tool-del-btn { background: transparent; border: none; cursor: pointer; font-size: 0.875rem; opacity: 0.7; }
.tool-del-btn:hover { opacity: 1; }
.tool-params { font-family: var(--font-mono); font-size: 0.75rem; margin-top: 6px; }
.tool-add-btn { align-self: flex-start; padding: 6px 14px; border-radius: var(--radius-sm); border: 1px dashed var(--color-border); background: transparent; color: var(--color-text-2); cursor: pointer; font-size: 0.8125rem; transition: var(--transition); }
.tool-add-btn:hover { border-color: var(--accent); color: var(--accent); }
.tool-hint { font-size: 0.75rem; color: var(--color-text-2); line-height: 1.5; }

.form-section-divider { font-size:1rem; font-weight: 600; color: var(--color-text); padding:1rem 0 0.5rem; border-top: 1px solid var(--color-border); margin:1rem 0 0.5rem; }

.icon-picker { display: flex; flex-wrap: wrap; gap:0.25rem; }
.icon-opt { width:2.25rem; height:2.25rem; display: flex; align-items: center; justify-content: center; border: 1px solid var(--color-border); border-radius:0.5rem; background: var(--color-surface); font-size:1.125rem; cursor: pointer; transition: all 0.15s; }
.icon-opt:hover { border-color: var(--color-border-focus); }
.icon-opt.active { border-color: var(--accent); background: rgba(124,106,242,0.12); }

.form-error { padding:0.625rem 0.75rem; background: rgba(239,68,68,0.1); color: var(--accent-danger); border-radius:0.5rem; font-size:0.8125rem; margin:0.5rem 0; }
.form-success { padding:0.625rem 0.75rem; background: rgba(34,197,94,0.1); color: var(--accent-success); border-radius:0.5rem; font-size:0.8125rem; margin:0.5rem 0; }
.form-actions { display: flex; gap:0.5rem; flex-wrap: wrap; margin-top:1rem; }

/* 预览卡片 */
.preview-card { padding:1.25rem; background: var(--color-surface); border: 1px solid var(--color-border); border-radius:0.75rem; display: flex; flex-direction: column; align-items: center; gap:0.5rem; text-align: center; }
.preview-icon { font-size:3rem; line-height:1; }
.preview-name { font-size:1.125rem; font-weight: 700; color: var(--color-text); }
.preview-desc { font-size:0.8125rem; color: var(--color-text-2); }
.preview-config { font-size:0.75rem; color: var(--color-text-3); }
.preview-category { font-size:0.6875rem; padding:0.125rem 0.5rem; border-radius:1.25rem; background: var(--color-surface-2); color: var(--color-text-2); }
.preview-prompt { width:100%; text-align: left; margin-top:0.5rem; }
.preview-prompt-title { font-size: 11px; font-weight: 600; color: var(--color-text-3); margin-bottom: 4px; text-transform: uppercase; }
.preview-prompt pre { font-size:0.6875rem; line-height:1.5; color: var(--color-text-2); white-space: pre-wrap; margin:0; font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace; }

/* 移动端适配 */
@media (max-width: 480px) {
  .page-section { padding: 1rem 0.75rem; }
  .studio-layout { gap: 16px; }
  .form-row { gap: 8px; }
  .icon-picker { gap: 2px; }
  .icon-opt { width: 32px; height: 32px; font-size: 16px; }
  .form-actions { flex-direction: column; }
  .form-actions .btn { width: 100%; }
  .template-grid { grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); }
}
</style>