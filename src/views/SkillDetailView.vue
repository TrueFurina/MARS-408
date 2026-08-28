<script setup lang="ts">
import { ref, onMounted, computed, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { icons } from '@/components/icons'
import Skeleton from '@/components/Skeleton.vue'
import { useSkillStore } from '@/stores/skillStore'
import { api, getAuthHeaders } from '@/utils/api'

const route = useRoute()
const router = useRouter()
const store = useSkillStore()

const skillId = computed(() => route.params.id as string)
const skill = computed(() => store.currentSkill)
const chatBodyRef = ref<HTMLElement | null>(null)
const chatInputRef = ref<HTMLInputElement | null>(null)

// ── 评价 ──
const myRating = ref(5)
const myComment = ref('')
const showRateForm = ref(false)
const ratingSubmitted = ref(false)

// ── 收藏 ──
const isFav = ref(false)
async function checkFav() {
  try {
    const res: any = await api.get(`/skills/favorited/${skillId.value}`)
    isFav.value = res.favorited
  } catch { isFav.value = false }
}
async function toggleFav() {
  if (isFav.value) {
    await api.post(`/skills/unfavorite/${skillId.value}`)
    isFav.value = false
  } else {
    await api.post(`/skills/favorite/${skillId.value}`)
    isFav.value = true
  }
}

// ── 对话弹窗 ──
const showChat = ref(false)
const chatInput = ref('')
const chatMessages = ref<{ role: string; content: string }[]>([])
const useMemory = ref(true)  // 插件执行时注入 L1/L2/L3 三层学情记忆（对标 HKU-DeepTutor 记忆解耦）
const chatLoading = ref(false)
let chatAbort = new AbortController()

function openChat() {
  showChat.value = true
  chatMessages.value = [{ role: 'assistant', content: `你好！我是「${skill.value?.name}」技能助手，有什么可以帮你的？` }]
  nextTick(() => chatInputRef.value?.focus())
}
function closeChat() {
  showChat.value = false
  chatAbort.abort()
  chatMessages.value = []
  chatInput.value = ''
}

async function sendChat() {
  if (!chatInput.value.trim() || chatLoading.value) return
  const msg = chatInput.value
  chatInput.value = ''
  chatMessages.value.push({ role: 'user', content: msg })
  chatLoading.value = true

  const aiMsg = { role: 'assistant', content: '' }
  chatMessages.value.push(aiMsg)
  chatAbort = new AbortController()

  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json', ...getAuthHeaders() }
    const endpoint = useMemory.value ? `/api/skills/run-with-memory/${skillId.value}` : `/api/skills/run-stream/${skillId.value}`
    const resp = await fetch(endpoint, {
      method: 'POST',
      headers,
      body: JSON.stringify({ message: msg, session_id: '' }),
      signal: chatAbort.signal,
    })
    if (!resp.ok) throw new Error('请求失败')
    const reader = resp.body?.getReader()
    const decoder = new TextDecoder()
    if (!reader) return
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const text = decoder.decode(value, { stream: true })
      const lines = text.split('\n').filter(l => l.startsWith('data: '))
      for (const line of lines) {
        const data = line.slice(6)
        if (data === '[DONE]') break
        try {
          const parsed = JSON.parse(data)
          if (parsed.type === 'content') {
            aiMsg.content += parsed.content.replace(/\\n/g, '\n').replace(/\\r/g, '\r')
          } else if (parsed.type === 'error') {
            aiMsg.content = `错误: ${parsed.content}`
          }
        } catch { /* ignore parse errors */ }
      }
    }
  } catch (e: any) {
    if (e.name !== 'AbortError') {
      aiMsg.content = `调用失败: ${e.message}`
    }
  } finally {
    chatLoading.value = false
  }
}

// ── 通用 ──
function stars(count: number): string {
  const full = Math.round(count)
  return `<span style="color:var(--accent-warm)">${'★'.repeat(full)}</span>${'☆'.repeat(5 - full)}`
}
function statusLabel(s: string): string {
  return { draft: '草稿', published: '已发布', archived: '已归档' }[s] || s
}
function memoryAccessLabel(m: string): string {
  return { none: '禁记忆', read: '只读记忆', write: '只写记忆', read_write: '读写记忆' }[m] || m
}
function memoryAccessTitle(m: string): string {
  const t: Record<string, string> = {
    none: '禁用学情记忆访问（插件不读取/不写入学生记忆）',
    read: '可读取学情记忆（薄弱点/画像/事件流），不可写入',
    write: '可写入行为事件，不可读取学情记忆',
    read_write: '可读写学情记忆（完整闭环）',
  }
  return t[m] || ''
}
async function doPublish() {
  if (!skill.value) return
  const ok = await store.publishSkill(skill.value.id)
  if (ok) await store.fetchSkill(skillId.value)
}
async function doArchive() {
  if (!skill.value) return
  const ok = await store.archiveSkill(skill.value.id)
  if (ok) await store.fetchSkill(skillId.value)
}
async function doDelete() {
  if (!skill.value) return
  if (!confirm('确定删除此技能？此操作不可恢复。')) return
  const ok = await store.deleteSkill(skill.value.id)
  if (ok) router.push('/skills')
}
async function doEdit() {
  if (!skill.value) return
  router.push(`/studio/${skill.value.id}`)
}
async function submitRating() {
  if (!skill.value) return
  const ok = await store.rateSkill(skill.value.id, myRating.value, myComment.value)
  if (ok) {
    ratingSubmitted.value = true
    showRateForm.value = false
    await store.fetchSkill(skillId.value)
    await store.fetchRatings(skillId.value)
  }
}

onMounted(async () => {
  await Promise.all([
    store.fetchSkill(skillId.value),
    store.fetchRatings(skillId.value),
    checkFav(),
  ])
})

// 对话弹窗自动滚动到底部
watch(chatMessages, () => {
  nextTick(() => {
    if (chatBodyRef.value) {
      chatBodyRef.value.scrollTop = chatBodyRef.value.scrollHeight
    }
  })
}, { deep: true })
</script>

<template>
  <div class="page-section">
    <div class="back-row">
      <button class="btn btn-ghost" @click="router.push('/skills')">← 返回市场</button>
    </div>

    <div v-if="store.loading" class="skeleton-list">
      <div class="skeleton-header">
        <Skeleton variant="avatar" />
        <div class="skeleton-header-body">
          <Skeleton variant="title" width="12rem" />
          <Skeleton variant="text" width="18rem" />
        </div>
      </div>
      <Skeleton variant="block" height="4rem" radius="var(--radius-md)" />
      <Skeleton variant="text" :count="4" />
    </div>
    <div v-else-if="store.error" class="engine-error">{{ store.error }}</div>
    <div v-else-if="skill" class="skill-detail">
      <!-- 头部 -->
      <div class="detail-header">
        <span class="detail-icon">{{ skill.icon }}</span>
        <div class="detail-title-group">
          <div class="detail-title-row">
            <h1 class="detail-title">{{ skill.name }}</h1>
            <span class="detail-status" :class="`badge-${skill.status}`">{{ statusLabel(skill.status) }}</span>
            <span v-if="skill.is_official" class="badge-official"><span class="badge-ic" v-html="icons.checkCircle"></span>官方</span>
            <span v-if="skill.memory_access" class="badge-memory" :class="`mem-${skill.memory_access}`" :title="memoryAccessTitle(skill.memory_access)">🧠 {{ memoryAccessLabel(skill.memory_access) }}</span>
          </div>
          <div class="detail-meta">
            <span>创作者: {{ skill.creator_name }}</span>
            <span>· 版本 {{ skill.version }}</span>
            <span>· 分类: {{ skill.category_label }}</span>
            <span>· {{ skill.usage_count }} 次使用</span>
          </div>
        </div>
        <button class="fav-btn" :class="{ active: isFav }" @click="toggleFav" :title="isFav ? '取消收藏' : '收藏'">
          <span class="fav-ic" v-html="isFav ? icons.starFilled : icons.star"></span>
        </button>
      </div>

      <!-- 评分 -->
      <div class="detail-rating-bar">
        <span class="big-stars">{{ stars(skill.avg_rating) }}</span>
        <span class="big-rating">{{ skill.avg_rating.toFixed(1) }}</span>
        <span class="rating-count">({{ store.ratings.length }} 评价)</span>
        <button class="btn btn-sm btn-ghost" @click="showRateForm = !showRateForm">
          {{ ratingSubmitted ? '已评价' : '写评价' }}
        </button>
      </div>

      <!-- 评价表单 -->
      <div v-if="showRateForm" class="rate-form">
        <div class="star-picker">
          <span v-for="i in 5" :key="i" class="star-option" :class="{ filled: i <= myRating }" role="button" tabindex="0" :aria-label="'评分 ' + i + ' 星'" @click="myRating = i" @keydown.enter="myRating = i" @keydown.space.prevent="myRating = i">★</span>
        </div>
        <input v-model="myComment" class="rate-input" placeholder="写点评价（可选）" maxlength="200" />
        <div class="rate-actions">
          <button class="btn btn-sm btn-primary" @click="submitRating">提交评价</button>
          <button class="btn btn-sm btn-ghost" @click="showRateForm = false">取消</button>
        </div>
      </div>

      <!-- 描述 -->
      <div class="detail-section">
        <h3 class="detail-section-title"><span class="section-ic" v-html="icons.document"></span>描述</h3>
        <p class="detail-desc">{{ skill.description || '暂无描述' }}</p>
      </div>

      <!-- AI 配置 -->
      <div class="detail-section">
        <h3 class="detail-section-title"><span class="section-ic" v-html="icons.setting"></span>AI 配置</h3>
        <div class="config-grid">
          <div class="config-item">
            <span class="config-label">LLM 通道</span>
            <span class="config-value">{{ skill.llm_channel }}</span>
          </div>
          <div class="config-item">
            <span class="config-label">温度</span>
            <span class="config-value">{{ skill.temperature }}</span>
          </div>
          <div class="config-item">
            <span class="config-label">最大 Token</span>
            <span class="config-value">{{ skill.max_tokens }}</span>
          </div>
          <div class="config-item">
            <span class="config-label">RAG 检索</span>
            <span class="config-value">{{ skill.rag_enabled ? '开启' : '关闭' }}</span>
          </div>
        </div>
      </div>

      <!-- System Prompt -->
      <div class="detail-section">
        <h3 class="detail-section-title"><span class="section-ic" v-html="icons.terminal"></span>System Prompt</h3>
        <pre class="prompt-preview">{{ skill.system_prompt || '无' }}</pre>
      </div>

      <!-- 标签 -->
      <div class="detail-section" v-if="skill.tags.length">
        <h3 class="detail-section-title"><span class="section-ic" v-html="icons.palette"></span>标签</h3>
        <div class="tag-list">
          <span v-for="tag in skill.tags" :key="tag" class="tag-item">{{ tag }}</span>
        </div>
      </div>

      <!-- 评价列表 -->
      <div class="detail-section" v-if="store.ratings.length">
        <h3 class="detail-section-title"><span class="section-ic" v-html="icons.star"></span>评价 ({{ store.ratings.length }})</h3>
        <div class="ratings-list">
          <div v-for="r in store.ratings" :key="r.id" class="rating-item">
            <div class="rating-header">
              <span class="rating-user">{{ r.user_name }}</span>
              <span class="rating-stars">{{ stars(r.rating) }}</span>
              <span class="rating-date">{{ r.created_at?.slice(0, 10) }}</span>
            </div>
            <p v-if="r.comment" class="rating-comment">{{ r.comment }}</p>
          </div>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="detail-actions">
        <button class="btn btn-primary" @click="openChat">
          <span v-html="icons.play"></span> 使用此技能
        </button>
        <button v-if="skill.status === 'draft'" class="btn btn-success" @click="doPublish">发布</button>
        <button v-if="skill.status === 'published'" class="btn" @click="doArchive">归档</button>
        <button class="btn btn-ghost" @click="doEdit"><span v-html="icons.edit"></span> 编辑</button>
        <button class="btn btn-ghost btn-danger" @click="doDelete"><span v-html="icons.trash"></span> 删除</button>
      </div>
    </div>

    <!-- 对话弹窗 -->
    <Teleport to="body">
      <div v-if="showChat" class="chat-overlay" @click.self="closeChat">
        <div class="chat-dialog">
          <div class="chat-dialog-header">
            <span class="chat-dialog-title">{{ skill?.icon }} {{ skill?.name }}</span>
            <button class="chat-dialog-close" @click="closeChat" v-html="icons.close"></button>
          </div>
          <div class="chat-dialog-body" ref="chatBodyRef">
            <div v-for="(msg, i) in chatMessages" :key="i" class="chat-msg" :class="msg.role">
              <div class="chat-msg-role">{{ msg.role === 'user' ? '你' : 'AI' }}</div>
              <div class="chat-msg-content" :class="{ 'markdown-body': msg.role === 'assistant' }">{{ msg.content }}</div>
            </div>
            <div v-if="chatLoading && chatMessages[chatMessages.length-1]?.content === ''" class="chat-msg assistant">
              <div class="chat-msg-role">AI</div>
              <div class="chat-msg-content">
                <div class="typing-indicator"><span></span><span></span><span></span></div>
              </div>
            </div>
          </div>
          <div class="chat-dialog-input">
            <input
              v-model="chatInput"
              ref="chatInputRef"
              class="chat-input-field"
              placeholder="输入消息..."
              :disabled="chatLoading"
              @keydown.enter.prevent="sendChat"
            />
            <button class="btn btn-primary chat-send-btn" :disabled="chatLoading || !chatInput.trim()" @click="sendChat">发送</button>
          </div>
          <div class="chat-dialog-memory">
            <label class="memory-toggle">
              <input type="checkbox" v-model="useMemory" :disabled="chatLoading" />
              <span>🧠 使用学情记忆（注入 L1/L2/L3）</span>
            </label>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.back-row { margin-bottom:1rem; }

.detail-header { display: flex; gap:1rem; align-items: flex-start; margin-bottom:1rem; }
.detail-icon {
  font-size:1.75rem; line-height:1;
  width:3.25rem; height:3.25rem; flex-shrink:0;
  display: flex; align-items: center; justify-content: center;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-card);
}
.detail-title-group { flex: 1; min-width: 0; }
.detail-title-row { display: flex; align-items: center; gap:0.625rem; flex-wrap: wrap; }
.detail-title { font-size:1.5rem; font-weight: 700; margin:0; color: var(--text-primary); }
.detail-status { font-size:0.6875rem; padding:0.125rem 0.625rem; border-radius:var(--radius-full); font-weight: 600; }
.badge-draft { background: var(--accent-primary-10); color: var(--accent-primary); }
.badge-published { background: var(--accent-success-10); color: var(--accent-success); }
.badge-archived { background: var(--bg-secondary); color: var(--text-muted); }
.badge-official {
  font-size:0.6875rem; padding:0.125rem 0.625rem; border-radius:var(--radius-full);
  background: var(--accent-primary-10); color: var(--accent-primary); font-weight: 600;
  display: inline-flex; align-items: center; gap: 0.25rem;
}
.badge-ic { width:0.875rem; height:0.875rem; display:inline-flex; }
.badge-ic :deep(svg) { width:100%; height:100%; }
.detail-meta { font-size:0.8125rem; color: var(--text-muted); margin-top:0.25rem; }

.fav-btn {
  width:2.5rem; height:2.5rem; flex-shrink:0; padding:0;
  display:inline-flex; align-items:center; justify-content:center;
  background: none; border: none; cursor: pointer;
  color: var(--text-muted); transition: var(--transition);
}
.fav-ic { width:1.5rem; height:1.5rem; display:inline-flex; }
.fav-ic :deep(svg) { width:100%; height:100%; }
.fav-btn:hover { color: var(--accent-warm); }
.fav-btn.active { color: var(--accent-warm); }

.detail-rating-bar {
  display: flex; align-items: center; gap:0.5rem; padding:0.75rem 1rem;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur)); -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border); border-radius: var(--radius-md); margin-bottom:1rem;
}
.big-stars { font-size:1.25rem; color: var(--accent-warm); letter-spacing:0.125rem; }
.big-rating { font-size:1.25rem; font-weight: 700; color: var(--accent-warm); }
.rating-count { font-size:0.8125rem; color: var(--text-muted); margin-right:auto; }

.rate-form {
  padding:1rem; background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur)); -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border); border-radius: var(--radius-md);
  margin-bottom:1rem; display: flex; flex-direction: column; gap:0.625rem;
}
.star-picker { display: flex; gap:0.25rem; }
.star-option { font-size:1.5rem; cursor: pointer; color: var(--text-muted); transition: color 0.15s; }
.star-option.filled { color: var(--accent-warm); }
.star-option:hover { color: var(--accent-warm); }
.rate-input {
  padding:0.5rem 0.75rem; border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
  background: var(--bg-elevated); color: var(--text-primary); font-size:0.875rem;
}
.rate-input:focus { outline: none; border-color: var(--border-focus); }
.rate-actions { display: flex; gap:0.5rem; }

.detail-section { margin-bottom:1.25rem; }
.detail-section-title {
  font-size:1rem; font-weight: 600; margin:0 0 0.5rem; color: var(--text-primary);
  display: flex; align-items: center;
}
.section-ic { width:1.125rem; height:1.125rem; display:inline-flex; margin-right:0.4rem; color: var(--accent-primary); }
.section-ic :deep(svg) { width:100%; height:100%; }
.detail-desc { font-size:0.875rem; color: var(--text-secondary); line-height:1.6; margin:0; }

.config-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 8px; }
.config-item { padding:0.75rem; background: var(--bg-secondary); border-radius: var(--radius-sm); border:1px solid var(--glass-border); }
.config-label { display: block; font-size: 11px; color: var(--text-muted); margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
.config-value { font-size:0.875rem; font-weight: 600; color: var(--text-primary); }

.prompt-preview {
  padding:0.75rem; background: var(--bg-secondary); border:1px solid var(--glass-border);
  border-radius: var(--radius-sm); font-size:0.8125rem; line-height:1.6; color: var(--text-secondary);
  white-space: pre-wrap; font-family: var(--font-mono); max-height:12.5rem; overflow-y: auto; margin:0;
}

.tag-list { display: flex; gap:0.375rem; flex-wrap: wrap; }
.tag-item { padding:0.25rem 0.625rem; border-radius:var(--radius-sm); background: var(--bg-secondary); color: var(--text-secondary); font-size:0.8125rem; border:1px solid var(--glass-border); }

.ratings-list { display: flex; flex-direction: column; gap:0.625rem; }
.rating-item { padding:0.75rem; background: var(--bg-secondary); border-radius: var(--radius-sm); border:1px solid var(--glass-border); }
.rating-header { display: flex; align-items: center; gap:0.5rem; margin-bottom:0.25rem; }
.rating-user { font-size:0.8125rem; font-weight: 600; color: var(--text-primary); }
.rating-stars { font-size:0.875rem; color: var(--accent-warm); }
.rating-date { font-size:0.6875rem; color: var(--text-muted); margin-left:auto; }
.rating-comment { font-size:0.8125rem; color: var(--text-secondary); margin:0; }

.detail-actions {
  display: flex; gap:0.5rem; flex-wrap: wrap; margin-top:1.5rem; padding-top:1rem;
  border-top: 1px solid var(--glass-border);
}

/* 对话弹窗 */
.chat-overlay { position: fixed; inset: 0; background: var(--color-overlay); z-index: 1000; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(2px); }
.chat-dialog {
  width: 90%; max-width: 560px; height: 70vh; max-height: 600px;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur)); -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border); border-radius: var(--radius-lg);
  display: flex; flex-direction: column; overflow: hidden;
  box-shadow: var(--shadow-xl), var(--glow-primary);
}
.chat-dialog-header {
  display: flex; align-items: center; justify-content: space-between;
  padding:0.875rem 1.125rem; border-bottom: 1px solid var(--glass-border);
  background: linear-gradient(180deg, var(--accent-primary-10), transparent);
}
.chat-dialog-title { font-size:1rem; font-weight: 600; color: var(--text-primary); }
.chat-dialog-close {
  width:2rem; height:2rem; padding:0; display:inline-flex; align-items:center; justify-content:center;
  background: none; border: none; border-radius: var(--radius-sm); color: var(--text-muted); cursor: pointer; transition: var(--transition);
}
.chat-dialog-close :deep(svg) { width:1.125rem; height:1.125rem; }
.chat-dialog-close:hover { background: var(--bg-card-hover); color: var(--text-primary); }
.chat-dialog-body { flex: 1; overflow-y: auto; padding:1rem; display: flex; flex-direction: column; gap:0.75rem; }
.chat-msg { display: flex; flex-direction: column; gap:0.25rem; }
.chat-msg.user { align-items: flex-end; }
.chat-msg.assistant { align-items: flex-start; }
.chat-msg-role { font-size:0.6875rem; font-weight: 600; color: var(--text-muted); }
.chat-msg-content { padding:0.625rem 0.875rem; border-radius:var(--radius-sm); font-size:0.875rem; line-height:1.6; max-width:85%; white-space: pre-wrap; }
.chat-msg.user .chat-msg-content { background: var(--accent-primary); color: #fff; border-bottom-right-radius:0.25rem; }
.chat-msg.assistant .chat-msg-content { background: var(--bg-secondary); color: var(--text-primary); border-bottom-left-radius:0.25rem; border:1px solid var(--glass-border); }
.chat-dialog-input { display: flex; gap:0.5rem; padding:0.75rem 1rem; border-top: 1px solid var(--glass-border); }
.chat-input-field {
  flex: 1; padding:0.625rem 0.875rem; border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
  background: var(--bg-secondary); color: var(--text-primary); font-size:0.875rem;
}
.chat-input-field:focus { outline: none; border-color: var(--border-focus); }
.chat-send-btn { white-space: nowrap; }

/* 移动端适配 */
@media (max-width: 480px) {
  .chat-dialog { width: 100%; height: 100vh; max-height: 100vh; border-radius: 0; }
  .chat-dialog-body { padding: 0.75rem; }
  .chat-msg-content { max-width: 92%; font-size: 0.8125rem; }
  .chat-dialog-input { padding: 0.5rem 0.75rem; }
}
</style>