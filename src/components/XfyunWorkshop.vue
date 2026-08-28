<script setup lang="ts">
import { ref } from 'vue'
import { api } from '@/utils/api'
import { useStudyStore } from '@/stores/studyStore'

const store = useStudyStore()

const props = defineProps<{
  topic: string
  result: any
}>()

// ── 讯飞AI工坊：集中调用控制台已开通的全部讯飞能力 ──
const xfLoading = ref<string | null>(null)
const xfError = ref<string | null>(null)
let _xfErrorTimer: ReturnType<typeof setTimeout> | null = null
const xfPpt = ref<{ url: string; title: string } | null>(null)
const xfVideo = ref<{ url: string; audio: string; text: string } | null>(null)
const xfSearch = ref<{ items: { title: string; summary: string; url: string }[]; count: number } | null>(null)
const xfProof = ref<{ corrections: any[]; count: number } | null>(null)
const xfGov = ref<{ corrections: any[]; count: number } | null>(null)
const xfCompliance = ref<{ passed: boolean; suggest: string; hits: any[] } | null>(null)
const xfResume = ref<{ url: string | null; raw: string } | null>(null)

// 角色模拟 mini-chat
const rpPersona = ref('interviewer')
const rpTopic = ref('')
const rpInput = ref('')
const rpMessages = ref<{ role: string; content: string }[]>([])

async function xfCall(key: string, fn: () => Promise<void>) {
  xfLoading.value = key
  try { await fn() }
  catch (e: any) {
    const detail = e?.response?.data?.detail || e?.message || '调用失败'
    xfError.value = `讯飞工坊「${key}」出错：${detail}`
    console.error('讯飞工坊调用失败:', key, e)
    if (_xfErrorTimer) clearTimeout(_xfErrorTimer)
    _xfErrorTimer = setTimeout(() => { xfError.value = null }, 8000)
  }
  finally { xfLoading.value = null }
}

async function pollXfTask(statusUrl: string, timeoutMs = 320000): Promise<any> {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    const s = await api.get<any>(statusUrl)
    if (s.status === 'done') return s
    if (s.status === 'failed') throw new Error(s.error || '生成失败')
    await new Promise(r => setTimeout(r, 4000))
  }
  throw new Error('生成超时（>5分钟），请稍后在讯飞控制台查看结果')
}

function _sourceText(): string {
  return (props.result?.teacher_doc || props.topic || '').slice(0, 2000)
}

async function genXfPpt() {
  if (!props.topic.trim()) return
  await xfCall('ppt', async () => {
    const submit = await api.post<any>('/xfyun/ppt', {
      query: props.topic, is_figure: true, ai_image: 'normal', search: true,
    })
    const s = await pollXfTask('/xfyun/ppt/status/' + submit.task_id)
    xfPpt.value = { url: s.result.ppt_url, title: s.result.title }
  })
}

async function genXfVideo() {
  const prompt = (props.result?.video_script || props.result?.teacher_doc || props.topic).slice(0, 800)
  if (!prompt.trim()) return
  await xfCall('video', async () => {
    const submit = await api.post<any>('/xfyun/video', { prompt, word_count: 120 })
    const s = await pollXfTask('/xfyun/video/status/' + submit.task_id)
    xfVideo.value = { url: s.result.video_url, audio: s.result.audio_url, text: s.result.text }
  })
}

async function doXfSearch() {
  if (!props.topic.trim()) return
  await xfCall('search', async () => {
    const d = await api.post<any>('/xfyun/search', { query: props.topic, limit: 5 })
    xfSearch.value = { items: d.items || [], count: d.count || 0 }
  })
}

async function doXfProofread() {
  const text = _sourceText()
  if (!text.trim()) return
  await xfCall('proof', async () => {
    const d = await api.post<any>('/xfyun/proofread', { text })
    xfProof.value = { corrections: d.corrections || [], count: d.count || 0 }
  })
}

async function doXfGovProof() {
  const text = _sourceText()
  if (!text.trim()) return
  await xfCall('gov', async () => {
    const d = await api.post<any>('/xfyun/proofread-doc', { text })
    xfGov.value = { corrections: d.corrections || [], count: d.count || 0 }
  })
}

async function doXfCompliance() {
  const text = _sourceText()
  if (!text.trim()) return
  await xfCall('compliance', async () => {
    const d = await api.post<any>('/xfyun/compliance', { text })
    xfCompliance.value = { passed: d.passed, suggest: d.suggest, hits: d.hits || [] }
  })
}

async function sendRp() {
  const msg = rpInput.value.trim()
  if (!msg || xfLoading.value === 'roleplay') return
  rpMessages.value.push({ role: 'user', content: msg })
  rpInput.value = ''
  await xfCall('roleplay', async () => {
    const d = await api.post<any>('/xfyun/roleplay', {
      persona: rpPersona.value, message: msg, topic: rpTopic.value,
    })
    rpMessages.value.push({ role: 'assistant', content: d.reply || '（无回答）' })
  })
}

async function genXfResume() {
  const p: any = store.studentProfile || {}
  const info = [
    `姓名：${p.name || '张敏杰'}`,
    `求职意向：计算机408考研复试 / 技术岗位`,
    `教育背景：${p.knowledge_base || '计算机相关专业本科'}`,
    `掌握科目：计算机网络、数据结构、操作系统、计算机组成原理`,
    `学习风格：${p.learning_style || '理论+实践结合'}`,
    `薄弱点：${p.weak_points || '待评估'}`,
    `目标方向：${p.goal || '985/211 计算机'}`,
    `请生成1份专业考研复试简历。`,
  ].join('\n')
  await xfCall('resume', async () => {
    const d = await api.post<any>('/xfyun/resume', { info })
    xfResume.value = { url: d.word_url, raw: d.raw }
  })
}
</script>

<template>
  <div class="card xfyun-workshop">
    <div class="card-header xfyun-card-header">
      <span class="card-title">🔥 讯飞AI工坊</span>
      <span class="xfyun-subtitle">深度集成科大讯飞：TTI/PPT/数字人视频/聚合搜索/图片理解/纠错/校对/合规/角色模拟/智能简历</span>
    </div>

    <div v-if="xfError" class="xfyun-error" role="alert" tabindex="0" aria-label="错误信息，点击或按回车关闭" @click="xfError = null" @keydown.enter="xfError = null">
      ⚠️ {{ xfError }} <span class="xfyun-error-close" aria-hidden="true">✕</span>
    </div>
    <div class="xfyun-grid">
      <!-- 1. 智能PPT -->
      <div class="xfyun-card">
        <div class="xfyun-card-title">📊 智能PPT生成</div>
        <div class="xfyun-card-desc">基于知识点一键生成带AI配图的演示PPT（讯飞智能PPT）</div>
        <button class="rag-btn" :disabled="!topic.trim() || !!xfLoading" @click="genXfPpt">
          {{ xfLoading==='ppt' ? '生成中...' : '生成PPT课件' }}
        </button>
        <div v-if="xfPpt" class="xfyun-result">
          <a :href="xfPpt.url" target="_blank" rel="noopener" class="xfyun-link">⬇️ 下载PPT：{{ xfPpt.title || '课件' }}</a>
        </div>
      </div>

      <!-- 2. 数字人视频 -->
      <div class="xfyun-card">
        <div class="xfyun-card-title">🎬 数字人视频</div>
        <div class="xfyun-card-desc">将讲解内容渲染为数字人播报视频（讯飞数字人视频大模型）</div>
        <button class="rag-btn" :disabled="!topic.trim() || !!xfLoading" @click="genXfVideo">
          {{ xfLoading==='video' ? '生成中...' : '生成讲解视频' }}
        </button>
        <div v-if="xfVideo" class="xfyun-result">
          <video v-if="xfVideo.url" :src="xfVideo.url" controls aria-label="数字人讲解视频" class="xfyun-video"></video>
          <div v-if="xfVideo.text" class="xfyun-video-text">{{ xfVideo.text }}</div>
        </div>
      </div>

      <!-- 3. 聚合搜索 -->
      <div class="xfyun-card">
        <div class="xfyun-card-title">🔍 联网检索（万搜）</div>
        <div class="xfyun-card-desc">联网补充检索，增强RAG知识库（讯飞聚合搜索）</div>
        <button class="rag-btn" :disabled="!topic.trim() || !!xfLoading" @click="doXfSearch">
          {{ xfLoading==='search' ? '检索中...' : '联网检索' }}
        </button>
        <div v-if="xfSearch" class="xfyun-result">
          <div v-if="xfSearch.count===0" class="xfyun-muted">未检索到结果</div>
          <div v-for="(it,i) in xfSearch.items" :key="i" class="xfyun-search-item">
            <a :href="it.url" target="_blank" rel="noopener" class="xfyun-link">{{ it.title }}</a>
            <div class="xfyun-muted">{{ it.summary }}</div>
          </div>
        </div>
      </div>

      <!-- 4. 文本纠错 -->
      <div class="xfyun-card">
        <div class="xfyun-card-title">✅ 文本纠错</div>
        <div class="xfyun-card-desc">对讲解内容做拼写/语法/搭配纠错（讯飞文本纠错）</div>
        <button class="rag-btn" :disabled="!topic.trim() || !!xfLoading" @click="doXfProofread">
          {{ xfLoading==='proof' ? '纠错中...' : '纠错讲解内容' }}
        </button>
        <div v-if="xfProof" class="xfyun-result">
          <div v-if="xfProof.count===0" class="xfyun-ok">✅ 未发现错误</div>
          <div v-for="(c,i) in xfProof.corrections" :key="i" class="xfyun-correction">
            「{{ c[1] }}」→ <b>{{ c[2] }}</b> <span class="xfyun-muted">({{ c[3] }})</span>
          </div>
        </div>
      </div>

      <!-- 5. 公文校对 -->
      <div class="xfyun-card">
        <div class="xfyun-card-title">📝 公文校对</div>
        <div class="xfyun-card-desc">政务/公文风格校对（讯飞公文校对引擎）</div>
        <button class="rag-btn" :disabled="!topic.trim() || !!xfLoading" @click="doXfGovProof">
          {{ xfLoading==='gov' ? '校对中...' : '公文校对' }}
        </button>
        <div v-if="xfGov" class="xfyun-result">
          <div v-if="xfGov.count===0" class="xfyun-ok">✅ 未发现错误</div>
          <div v-for="(c,i) in xfGov.corrections" :key="i" class="xfyun-correction">
            「{{ c[1] }}」→ <b>{{ c[2] }}</b> <span class="xfyun-muted">({{ c[3] }})</span>
          </div>
        </div>
      </div>

      <!-- 6. 内容合规 -->
      <div class="xfyun-card">
        <div class="xfyun-card-title">🛡️ 内容合规审核</div>
        <div class="xfyun-card-desc">内容安全审核，防违规/防幻觉输出（讯飞文本合规）</div>
        <button class="rag-btn" :disabled="!topic.trim() || !!xfLoading" @click="doXfCompliance">
          {{ xfLoading==='compliance' ? '审核中...' : '合规审核' }}
        </button>
        <div v-if="xfCompliance" class="xfyun-result">
          <div v-if="xfCompliance.passed" class="xfyun-ok">✅ 内容合规，通过审核</div>
          <div v-else class="xfyun-warn">⚠️ 命中风险：{{ xfCompliance.hits.map(h=>h.word).join('、') }}</div>
        </div>
      </div>

      <!-- 7. 角色模拟 -->
      <div class="xfyun-card xfyun-card-wide">
        <div class="xfyun-card-title">🎭 角色模拟·模拟面试官</div>
        <div class="xfyun-card-desc">星火角色模拟：模拟考研面试官/导师与你多轮对话</div>
        <div class="xfyun-rp-controls">
          <select class="rag-select" v-model="rpPersona">
            <option value="interviewer">通用考研模拟面试官</option>
            <option value="interviewer_network">计网面试官</option>
            <option value="interviewer_os">操作系统面试官</option>
            <option value="tutor">408一对一导师</option>
          </select>
          <input v-model="rpTopic" placeholder="面试主题（可选）" class="xfyun-rp-topic" />
        </div>
        <div class="xfyun-rp-messages">
          <div v-for="(m,i) in rpMessages" :key="i" class="xfyun-rp-msg" :class="m.role">
            <div class="xfyun-rp-role">{{ m.role==='user' ? '我' : '面试官' }}</div>
            <div class="xfyun-rp-content">{{ m.content }}</div>
          </div>
          <div v-if="rpMessages.length===0" class="xfyun-muted">选择角色后，在下方输入你的回答开始模拟</div>
        </div>
        <div class="xfyun-rp-input">
          <input v-model="rpInput" placeholder="输入你的回答..." @keyup.enter="sendRp" :disabled="xfLoading==='roleplay'" />
          <button class="rag-btn" :disabled="xfLoading==='roleplay' || !rpInput.trim()" @click="sendRp">
            <span v-if="xfLoading==='roleplay'" class="typing-indicator" aria-label="思考中"><span></span><span></span><span></span></span>
            <span v-else>发送</span>
          </button>
        </div>
      </div>

      <!-- 8. 智能简历 -->
      <div class="xfyun-card">
        <div class="xfyun-card-title">📄 智能简历</div>
        <div class="xfyun-card-desc">生成可下载的考研复试简历（讯飞智能简历）</div>
        <button class="rag-btn" :disabled="!!xfLoading" @click="genXfResume">
          {{ xfLoading==='resume' ? '生成中...' : '生成我的简历' }}
        </button>
        <div v-if="xfResume" class="xfyun-result">
          <a v-if="xfResume.url" :href="xfResume.url" target="_blank" rel="noopener" class="xfyun-link">⬇️ 下载简历(word)</a>
          <div v-else class="xfyun-muted">简历已生成，但未返回下载链接</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.xfyun-workshop { padding:1.125rem 1.25rem 1.375rem; margin-top:1.25rem; }
.xfyun-card-header { border-bottom: 1px solid var(--border-light); padding-bottom:0.75rem; flex-wrap: wrap; gap:0.5rem; }
.xfyun-video { width:100%; border-radius:var(--radius-sm); margin-top:0.5rem; background: var(--color-canvas); display: block; }
.xfyun-subtitle { font-size:0.75rem; color: var(--text-muted); }
.xfyun-error { margin:0 0 0.875rem; padding:0.625rem 0.875rem; border-radius:var(--radius-sm); cursor: pointer;
  background: var(--accent-danger-10); border: 1px solid var(--accent-danger-20);
  color: var(--text-danger); font-size:0.8125rem; display: flex; justify-content: space-between; align-items: center; }
.xfyun-error-close { opacity: 0.6; font-size:0.875rem; }
.xfyun-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap:0.875rem;
}
.xfyun-card {
  display: flex;
  flex-direction: column;
  gap:0.5rem;
  padding:1rem;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  border-radius:var(--radius-md);
  transition: var(--transition);
}
.xfyun-card:hover { border-color: var(--accent-primary); box-shadow: var(--glow-primary); }
.xfyun-card-wide { grid-column: 1 / -1; }
.xfyun-card-title { font-size:0.9375rem; font-weight: 700; color: var(--text-primary); }
.xfyun-card-desc { font-size:0.75rem; color: var(--text-muted); line-height:1.5; flex: 1; }
.xfyun-card .rag-btn { align-self: flex-start; padding:0.4375rem 1rem; font-size:0.8125rem; }
.xfyun-result { margin-top:0.25rem; font-size:0.8125rem; }
.xfyun-link { color: var(--accent-primary); text-decoration: none; word-break: break-all; }
.xfyun-link:hover { text-decoration: underline; }
.xfyun-muted { color: var(--text-muted); font-size:0.75rem; line-height:1.5; }
.xfyun-ok { color: var(--accent-success); font-size:0.8125rem; font-weight: 600; }
.xfyun-warn { color: var(--accent-danger); font-size:0.8125rem; font-weight: 600; }
.xfyun-correction { font-size:0.75rem; color: var(--text-secondary); padding:0.125rem 0; }
.xfyun-correction b { color: var(--accent-success); }
.xfyun-search-item { padding:0.375rem 0; border-top: 1px solid var(--glass-border); }
.xfyun-video-text { margin-top:0.375rem; font-size:0.75rem; color: var(--text-secondary); white-space: pre-wrap; }
.xfyun-rp-controls { display: flex; gap:0.5rem; flex-wrap: wrap; margin-top:0.25rem; }
.xfyun-rp-topic {
  flex: 1; min-width:7.5rem; padding:0.375rem 0.625rem; border-radius:var(--radius-sm);
  border: 1px solid var(--border-color); background: var(--bg-card); color: var(--text-primary); font-size: 13px; outline: none;
}
.xfyun-rp-messages {
  max-height:13.75rem; overflow-y: auto; display: flex; flex-direction: column; gap:0.5rem;
  padding:0.625rem; background: var(--bg-secondary); border-radius:var(--radius-sm); margin:0.5rem 0;
}
.xfyun-rp-msg { display: flex; flex-direction: column; gap:0.125rem; }
.xfyun-rp-msg.user { align-items: flex-end; }
.xfyun-rp-role { font-size:0.6875rem; color: var(--text-muted); }
.xfyun-rp-content {
  font-size:0.8125rem; color: var(--text-primary); line-height:1.5;
  padding:0.5rem 0.75rem; border-radius:var(--radius-sm); max-width:85%;
}
.xfyun-rp-msg.user .xfyun-rp-content { background: var(--accent-primary-10); color: var(--accent-primary); }
.xfyun-rp-msg.assistant .xfyun-rp-content { background: var(--glass-bg); border: 1px solid var(--glass-border); }
.xfyun-rp-input { display: flex; gap:0.5rem; }
.xfyun-rp-input input {
  flex: 1; padding:0.5rem 0.75rem; border-radius:var(--radius-sm);
  border: 1px solid var(--border-color); background: var(--bg-card); color: var(--text-primary); font-size: 13px; outline: none;
}
.xfyun-rp-input input:focus { border-color: var(--accent-primary); }
</style>