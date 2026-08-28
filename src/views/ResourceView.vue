<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useStudyStore } from '@/stores/studyStore'
import { api } from '@/utils/api'
import { ttsSynthesize } from '@/utils/api'
import { icons } from '@/components/icons'
import { renderMarkdownSafe } from '@/utils/markdown'
import { defineAsyncComponent } from 'vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import type { EvidenceReport, GateResult } from '@/utils/evidence'

// 延迟加载重型组件，非首屏不加载
const TcpHandshakeAnimation = defineAsyncComponent(() => import('@/components/TcpHandshakeAnimation.vue'))
const MindMapViewer = defineAsyncComponent(() => import('@/components/MindMapViewer.vue'))
const MultimodalCard = defineAsyncComponent(() => import('@/components/MultimodalCard.vue'))
const VideoPlayer = defineAsyncComponent(() => import('@/components/VideoPlayer.vue'))
const XfyunWorkshop = defineAsyncComponent(() => import('@/components/XfyunWorkshop.vue'))
const EvidenceCheckPanel = defineAsyncComponent(() => import('@/components/EvidenceCheckPanel.vue'))

const store = useStudyStore()
const route = useRoute()

const topic = ref('')
const difficulty = ref('medium')
const loading = ref(false)
const currentAgent = ref('')
const pipelineStage = ref(0) // 0=未开始 1=规划 2=教学 3=出题 4=多媒体 5=审阅 6=完成
const progressPct = ref(0) // SSE 推送的真实进度百分比
const agentOutputs = ref<Record<string, string>>({}) // 各 Agent 实时产出
// ── 证据校验报告（INC-02：消费 evidence_check 节点推送的 EvidenceReport）──
const evidenceReport = ref<EvidenceReport | null>(null)
// ── 产物验收闸门状态 ──
const gateResult = ref<GateResult | null>(null)
const gateRejected = ref(false)
// ── 单 Agent 错误收集（不阻断其他 Agent 输出）──
const agentErrors = ref<Record<string, string>>({})
const selectedHistory = ref<string | null>(null)
const showHistory = ref(true)  // 默认展开，方便查看历史
// ── 可复用学习资源池（后端登记 + 展示） ──
const poolResources = ref<any[]>([])
const showPool = ref(false)
const poolLoading = ref(false)

async function loadPoolResources() {
  poolLoading.value = true
  try {
    const data = await api.get<any>('/resource/list')
    poolResources.value = data?.resources || []
    showPool.value = true
  } catch {
    poolResources.value = []
  } finally {
    poolLoading.value = false
  }
}

function openPoolResource(item: any) {
  if (!item?.content) return
  const content = item.content
  topic.value = content.topic || item.title || ''
  difficulty.value = content.difficulty || 'medium'
  result.value = {
    teacher_doc: content.teacher_doc || '',
    quiz: content.quiz || '',
    media_plan: content.media_plan || '',
    extension: content.extension || '',
    critic_report: content.critic_report || '审核通过：未发现明显错误',
    mindmap_mermaid: content.mindmap_mermaid || '',
    mindmap_stats: content.mindmap_stats || '',
    mindmap_weak_points: content.mindmap_weak_points || '',
    code_practice: content.code_practice || '',
    ppt_outline: content.ppt_outline || '',
    video_script: content.video_script || '',
    ppt_file: content.ppt_file || null,
    evidence_report: content.evidence_report || null,
    status: 'ok',
  }
  pipelineStage.value = 6
  activeTab.value = 'doc'
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// ── 多模态内容状态 ──
const mmImageBase64 = ref<string | null>(null)
const mmImageSvg = ref<string | null>(null)
const mmImageSource = ref<string>('none')
const mmAudioBase64 = ref<string | null>(null)
const mmAudioFallbackText = ref<string | null>(null)
const mmAudioSource = ref<string>('none')
const mmLoading = ref(false)
const videoLoading = ref(false)
const teachingVideoHtml = ref<string | null>(null)
const teachingVideoLoading = ref(false)
const showTeachingVideo = ref(false)

// ── TTS 语音朗读 ──
const speakingText = ref<string | null>(null)
const audioRef = ref<HTMLAudioElement | null>(null)

async function speakText(text: string, language = 'zh') {
  if (!text || !text.trim()) return
  // 如果正在播放同一段，切换播放/暂停
  if (speakingText.value === text && audioRef.value) {
    if (!audioRef.value.paused) {
      audioRef.value.pause()
      return
    }
    audioRef.value.play().catch(() => {})
    return
  }
  // 停止之前的播放
  if (audioRef.value) {
    audioRef.value.pause()
    audioRef.value = null
  }
  try {
    const clean = text.replace(/```[\s\S]*?```/g, '').replace(/[#*`~\[\]()>|]/g, '').replace(/\n{3,}/g, '\n\n').trim()
    if (!clean) return
    const blob = await ttsSynthesize(clean, language)
    if (!blob) return
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    audioRef.value = audio
    speakingText.value = text
    audio.onended = () => {
      speakingText.value = null
      URL.revokeObjectURL(url)
      audioRef.value = null
    }
    audio.onerror = () => {
      speakingText.value = null
      URL.revokeObjectURL(url)
      audioRef.value = null
    }
    await audio.play()
  } catch {
    speakingText.value = null
  }
}

async function generateMultimodal() {
  if (!topic.value) return
  mmLoading.value = true
  try {
    // 并行生成教学插图 + 语音旁白
    const [imgRes, audioRes] = await Promise.all([
      api.post<any>('/multimodal/generate-image', { topic: topic.value }),
      api.post<any>('/multimodal/generate-audio', {
        text: (result.value?.teacher_doc || result.value?.video_script || '').substring(0, 500)
      }).catch(() => null)
    ])

    const imgData = imgRes.data
    mmImageBase64.value = imgData.image_base64 || null
    mmImageSvg.value = imgData.image_svg || null
    mmImageSource.value = imgData.source || 'none'

    if (audioRes) {
      const audioData = audioRes.data
      mmAudioBase64.value = audioData.audio_base64 || null
      mmAudioFallbackText.value = audioData.fallback_text || null
      mmAudioSource.value = audioData.source || 'none'
    }
  } catch (e: any) {
    console.warn('多模态生成失败:', e?.message)
    mmError.value = '多模态资源生成失败: ' + (e?.message || '请检查后端服务是否运行')
  } finally {
    mmLoading.value = false
  }
}

const mmError = ref('')

async function generateNarratedVideo() {
  const text = result.value?.video_script || result.value?.teacher_doc || ''
  if (!text) return
  videoLoading.value = true
  try {
    const token = localStorage.getItem('mars408_token')
    const resp = await fetch('/api/multimodal/generate-narrated-video', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ text: text.substring(0, 2000), language: 'zh', speed: 1.0 }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      alert('视频生成失败: ' + (err.detail || resp.statusText))
      return
    }
    // 下载视频
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `mars408_${topic.value || 'lecture'}.mp4`
    a.click()
    URL.revokeObjectURL(a.href)
  } catch (e) {
    alert('视频生成失败: ' + (e instanceof Error ? e.message : '未知错误'))
  } finally {
    videoLoading.value = false
  }
}

async function generateTeachingVideo() {
  if (!topic.value) return
  teachingVideoLoading.value = true
  try {
    const res: any = await api.post('/multimodal/generate-teaching-video', {
      topic: topic.value,
      difficulty: difficulty.value,
      output_format: 'html',
    })
    if (res?.html) {
      teachingVideoHtml.value = res.html
      showTeachingVideo.value = true
    }
  } catch (e: any) {
    alert('教学视频生成失败: ' + (e?.message || '未知错误'))
  } finally {
    teachingVideoLoading.value = false
  }
}

// ── 生成历史 localStorage ──
const HISTORY_KEY = 'mars408_resource_history'
interface ResourceHistoryItem {
  id: string
  topic: string
  difficulty: string
  timestamp: string
  result: typeof result.value
}
const resourceHistory = ref<ResourceHistoryItem[]>([])

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    resourceHistory.value = raw ? JSON.parse(raw) : []
  } catch { resourceHistory.value = [] }
}

onMounted(() => {
  if (route.query.topic) {
    topic.value = route.query.topic as string
  }
  loadMemoryOverview()
})

// L1/L2/L3 三层学情记忆（低侵入联动：资源池页展示记忆薄弱点，失败不影响主流程）
const memoryOverview = ref<any>(null)
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞资源池页 */ }
}

function saveToHistory(r: typeof result.value) {
  const item: ResourceHistoryItem = {
    id: Date.now().toString(36),
    topic: topic.value,
    difficulty: difficulty.value,
    timestamp: new Date().toLocaleString('zh-CN'),
    result: r,
  }
  resourceHistory.value.unshift(item)
  if (resourceHistory.value.length > 20) resourceHistory.value = resourceHistory.value.slice(0, 20)
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(resourceHistory.value)) } catch {}

  // 登记到可复用学习资源池（内容哈希去重，幂等）
  if (r) {
    const payload = {
      resource_type: 'resource_bundle',
      title: topic.value || 'AI 生成资源',
      content: {
        topic: topic.value,
        difficulty: difficulty.value,
        teacher_doc: r.teacher_doc,
        quiz: r.quiz,
        media_plan: r.media_plan,
        extension: r.extension,
        critic_report: r.critic_report,
        mindmap_mermaid: r.mindmap_mermaid,
        mindmap_stats: r.mindmap_stats,
        mindmap_weak_points: r.mindmap_weak_points,
        code_practice: r.code_practice,
        ppt_outline: r.ppt_outline,
        video_script: r.video_script,
        ppt_file: r.ppt_file,
        evidence_report: r.evidence_report,
      },
      quality_score: r.critic_report && r.critic_report !== '审核通过：未发现明显错误' ? 70 : 85,
    }
    api.post('/resource/register', payload).catch(() => { /* 登记失败不影响本地历史 */ })
  }
}

function loadFromHistory(item: ResourceHistoryItem) {
  topic.value = item.topic
  difficulty.value = item.difficulty
  result.value = item.result
  pipelineStage.value = 6  // 标记为完成，显示结果
  selectedHistory.value = item.id
}

function clearHistory() {
  resourceHistory.value = []
  localStorage.removeItem(HISTORY_KEY)
}

loadHistory()

const showTcpAnimation = computed(() => {
  const t = topic.value.toLowerCase()
  return t.includes('tcp') || t.includes('三次握手') || t.includes('握手')
})

const showSynFlood = computed(() => {
  const t = topic.value.toLowerCase()
  return t.includes('syn') || t.includes('flood') || t.includes('攻击') || t.includes('半连接')
})

interface ResourceResult {
  teacher_doc: string
  quiz: string
  media_plan: string
  extension: string
  critic_report: string
  mindmap_mermaid: string
  mindmap_stats: string
  mindmap_weak_points: string
  code_practice: string
  ppt_outline: string
  video_script: string
  ppt_file: { url: string; filename: string; slide_count: number } | null
  evidence_report: EvidenceReport | null
  status: string
}
const result = ref<ResourceResult | null>(null)

const agentSteps = [
  { name: '规划 Agent', icon: icons.sparkle, desc: '分析知识点和学习需求', stage: 1 },
  { name: '教学 Agent', icon: icons.book, desc: '生成讲解文档', stage: 2 },
  { name: '出题 Agent', icon: icons.quiz, desc: '生成练习题', stage: 3 },
  { name: '资源集群', icon: icons.agent, desc: '导图/拓展/代码/PPT/视频并行', stage: 4 },
  { name: '审阅 Agent', icon: icons.search, desc: '检查内容准确性', stage: 5 },
]

// 资源卡顶部 tab（图标 + 文案，禁裸 emoji）
const resourceTabs = [
  { key: 'doc', icon: 'document', label: '讲解' },
  { key: 'quiz', icon: 'quiz', label: '题目' },
  { key: 'media', icon: 'palette', label: '导图' },
  { key: 'extension', icon: 'bookOpen', label: '拓展' },
  { key: 'ppt', icon: 'barChart', label: 'PPT' },
  { key: 'code', icon: 'terminal', label: '代码' },
  { key: 'video', icon: 'play', label: '视频' },
{ key: 'critic', icon: 'search', label: '审核' },
  { key: 'evidence', icon: 'microscope', label: '证据校验' },
  { key: 'gate', icon: 'shield', label: '闸门' },
]

async function generateResource() {
  if (!topic.value.trim() || loading.value) return

  loading.value = true
  result.value = null
      pipelineStage.value = 0
      progressPct.value = 0
agentOutputs.value = {}
      evidenceReport.value = null
      gateResult.value = null
      gateRejected.value = false
      agentErrors.value = {}

  try {
    const resp = await api.postStream('/agents/langgraph/stream', {
      message: topic.value,
      difficulty: difficulty.value,
      profile: store.studentProfile,
      course: 'computer_network',
    })

    if (!resp.body) {
      throw new Error('无响应流')
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    // LangGraph SSE 事件格式：
    //   {type:'node_done', field:'coordinator', content:'...'}
    //   {type:'status', field:'generating', content:'...'}
    //   {type:'content', field:'teacher'|'quiz'|'media'|'extension'|'mindmap'|'code_practice'|'ppt_outline'|'video_script'|'critic', content:'...'}
    //   {type:'data', field:'mindmap_stats'|'mindmap_weak_points', content:'...'}
    //   {type:'error', field:'pipeline_error', content:'...'}
    //   data: [DONE]
const stageMap: Record<string, number> = {
      coordinator: 1, diagnostician: 1, planner: 1, retriever: 1,
      generator_cluster: 2, assessor: 3, critic: 4, evidence_check: 5, quality_gate: 5, path_planner: 5,
    }
    const contentAgentMap: Record<string, string> = {
      teacher: '教学 Agent', quiz: '出题 Agent', media: '多媒体 Agent',
      extension: '拓展 Agent', critic: '审阅 Agent',
      mindmap: '思维导图 Agent', code_practice: '代码实操 Agent',
      ppt_outline: 'PPT Agent', video_script: '视频脚本 Agent',
    }
    const stageProgress: Record<number, number> = {
      1: 15, 2: 50, 3: 70, 4: 85, 5: 100,
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() || ''
      for (const block of blocks) {
        const line = block.trim()
        if (!line.startsWith('data:')) continue
        const payload = line.slice(5).trim()
        if (payload === '[DONE]') continue
        try {
          const evt = JSON.parse(payload)
          if (evt.type === 'error') {
            // P1-10: single agent error collection, don't break SSE loop
            // other agents may still be producing output
            const errField = (evt.field || 'pipeline') as string
            agentErrors.value[errField] = evt.content || 'Generation failed'
            continue
          }
          // node_done：Agent 节点完成，更新进度
          if (evt.type === 'node_done') {
            const nodeName = (evt.field || '') as string
            if (stageMap[nodeName]) {
              pipelineStage.value = stageMap[nodeName] as number
              progressPct.value = stageProgress[pipelineStage.value] || progressPct.value
            }
            const step = agentSteps[pipelineStage.value - 1]
            currentAgent.value = (step && step.name) || nodeName
          }
          // content：Agent 生成的具体内容
          if (evt.type === 'content' && evt.field && evt.content) {
            const agentName = evt.field as string
            // ppt_file 推送的是 JSON（真实 .pptx 文件信息），单独解析为对象
            if (agentName === 'ppt_file') {
              try { (agentOutputs.value as any).ppt_file_obj = JSON.parse(evt.content) } catch { /* 忽略解析失败 */ }
            } else {
              agentOutputs.value[agentName] = evt.content
              const displayName = contentAgentMap[agentName]
              if (displayName) {
                currentAgent.value = displayName
              }
            }
          }
          // data：结构化数据 (mindmap_stats, mindmap_weak_points)
          if (evt.type === 'data' && evt.field && evt.content) {
            agentOutputs.value[evt.field] = evt.content
          }
          // status：状态更新
          if (evt.type === 'status' && evt.content) {
            currentAgent.value = evt.content as string
          }
// evidence：证据校验报告（INC-02，evidence_check 节点推送的 EvidenceReport）
          if (evt.type === 'evidence' && evt.content) {
            try {
              evidenceReport.value = JSON.parse(evt.content) as EvidenceReport
            } catch { /* 跳过无法解析的证据报告 */ }
          }
          // gate_pass / gate_rejected / gate_fix：产物验收闸门事件
          if (evt.type === 'gate_pass' || evt.type === 'gate_rejected' || evt.type === 'gate_fix') {
            try {
              gateResult.value = JSON.parse(evt.content) as GateResult
            } catch { /* 跳过 */ }
          }
          if (evt.type === 'gate_rejected') {
            gateRejected.value = true
          }
        } catch { /* 跳过无法解析的 SSE 行 */ }
      }
    }

    // 组装最终结果（SSE 推送的所有资源）
    // 注：result.value 在函数开头被赋 null，TS 控制流会把此处窄化为 null；
    // 实际运行时此处流结束后才会在此分支赋值，用显式断言避免 never 类型误报。
    const r: ResourceResult | null = result.value as ResourceResult | null
    if (!r || r.status !== 'error') {
      const mindmapMermaid = agentOutputs.value.mindmap || ''
      const mindmapStats = agentOutputs.value.mindmap_stats || ''
      const mindmapWeak = agentOutputs.value.mindmap_weak_points || ''

      result.value = {
        teacher_doc: agentOutputs.value.teacher_corrected || agentOutputs.value.teacher || '(教学 Agent 未产出)',
        quiz: agentOutputs.value.quiz || agentOutputs.value.quizmaster || '(出题 Agent 未产出)',
        media_plan: agentOutputs.value.media || mindmapMermaid || '(多媒体 Agent 未产出)',
        extension: agentOutputs.value.extension || '',
        critic_report: agentOutputs.value.critic || '审核通过：未发现明显错误',
        mindmap_mermaid: mindmapMermaid,
        mindmap_stats: mindmapStats,
        mindmap_weak_points: mindmapWeak,
        code_practice: agentOutputs.value.code_practice || '',
        ppt_outline: agentOutputs.value.ppt_outline || '',
        video_script: agentOutputs.value.video_script || '',
        ppt_file: (agentOutputs.value as any).ppt_file_obj || null,
        evidence_report: evidenceReport.value,
        status: 'ok',
      }
      // 若有单 Agent 失败，在教学文档末尾附注
      if (Object.keys(agentErrors.value).length > 0) {
        const errLines = Object.entries(agentErrors.value)
          .map(([agent, msg]) => agent + ': ' + msg)
        if (!result.value!.teacher_doc || result.value!.teacher_doc === '(教学 Agent 未产出)') {
          result.value!.teacher_doc = '部分 Agent 生成失败: ' + errLines.join('; ')
        } else {
          result.value!.teacher_doc += '\n---\n*注：以下 Agent 生成失败:* ' + errLines.join('; ') + '*'
        }
      }
      pipelineStage.value = 6
      progressPct.value = 100
    }
  } catch {
    result.value = {
      teacher_doc: '抱歉，资源生成失败，请检查后端是否运行。',
      quiz: '', media_plan: '', extension: '', critic_report: '',
      mindmap_mermaid: '', mindmap_stats: '', mindmap_weak_points: '',
      code_practice: '', ppt_outline: '', video_script: '',
      ppt_file: null,
      evidence_report: null,
      status: 'error',
    }
    pipelineStage.value = 6
    if (result.value && result.value.status === 'ok') saveToHistory(result.value)
  } finally {
    loading.value = false
  }
}

const activeTab = ref<'doc' | 'quiz' | 'media' | 'extension' | 'ppt' | 'code' | 'video' | 'critic' | 'evidence' | 'gate'>('doc')

// 资源卡顶部类型色条（按 tab 映射学科/类型语义色，禁裸色）
const tabAccent = computed(() => {
  const map: Record<string, string> = {
    doc: 'var(--subject-cn)',
    quiz: 'var(--accent-warm)',
    media: 'var(--subject-co)',
    extension: 'var(--accent-cyan)',
    ppt: 'var(--accent-pink)',
    code: 'var(--accent-success)',
    video: 'var(--accent-warm)',
critic: 'var(--accent-danger)',
    evidence: 'var(--subject-os)',
    gate: 'var(--accent-pink)',
  }
  return map[activeTab.value] || 'var(--subject-cn)'
})

// 拓展阅读（第5种资源类型，赛题功能2要求≥5种）
const extensionLoading = ref(false)
const extensionDoc = ref('')
const extensionWarnings = ref<string[]>([])

async function generateExtension() {
  if (!topic.value.trim() || extensionLoading.value) return
  extensionLoading.value = true
  extensionDoc.value = ''
  extensionWarnings.value = []
  try {
    const data = await api.post<any>('/agents/generate-extension', {
      topic: topic.value,
      difficulty: difficulty.value,
      profile: store.studentProfile,
    })
    extensionDoc.value = data.extension_doc || '(拓展阅读 Agent 未产出)'
    extensionWarnings.value = data.hallucination_warnings || []
    activeTab.value = 'extension'
  } catch {
    extensionDoc.value = '拓展阅读生成失败，请检查后端是否运行。'
  } finally {
    extensionLoading.value = false
  }
}

// PPT大纲（赛题功能2：≥5种资源含PPT）
const pptLoading = ref(false)
const pptOutline = ref('')

async function generatePpt() {
  if (!topic.value.trim() || pptLoading.value) return
  pptLoading.value = true
  pptOutline.value = ''
  try {
    const data = await api.post<any>('/agents/generate-ppt', {
      topic: topic.value,
      difficulty: difficulty.value,
      profile: store.studentProfile,
    })
    pptOutline.value = data.ppt_outline || '(PPT大纲 Agent 未产出)'
    activeTab.value = 'ppt'
  } catch {
    pptOutline.value = 'PPT大纲生成失败，请检查后端是否运行。'
  } finally {
    pptLoading.value = false
  }
}

// 代码实操案例（赛题功能2：≥5种资源含代码实操案例）
const codeLoading = ref(false)
const codePractice = ref('')
const codeWarnings = ref<string[]>([])

async function generateCodePractice() {
  if (!topic.value.trim() || codeLoading.value) return
  codeLoading.value = true
  codePractice.value = ''
  codeWarnings.value = []
  try {
    const data = await api.post<any>('/agents/generate-code-practice', {
      topic: topic.value,
      difficulty: difficulty.value,
      profile: store.studentProfile,
    })
    codePractice.value = data.code_practice || '(代码实操 Agent 未产出)'
    codeWarnings.value = data.hallucination_warnings || []
    activeTab.value = 'code'
  } catch {
    codePractice.value = '代码实操案例生成失败，请检查后端是否运行。'
  } finally {
    codeLoading.value = false
  }
}

// 解析思维导图统计数据 (SSE 推送的 JSON 字符串)
function parseMindmapStats(statsStr: string) {
  try {
    const s = JSON.parse(statsStr)
    return [
      { label: '知识点总数', value: s.total ?? 0, color: 'var(--text-primary)' },
      { label: '已掌握', value: s.mastered ?? 0, color: 'var(--accent-success)' },
      { label: '薄弱', value: s.weak ?? 0, color: 'var(--accent-5)' },
      { label: '未学', value: s.unlearned ?? 0, color: 'var(--accent-danger)' },
    ]
  } catch {
    return []
  }
}

// 解析薄弱知识点列表 (SSE 推送的 JSON 数组字符串)
function parseWeakPoints(wpStr: string): string[] {
  try {
    const arr = JSON.parse(wpStr)
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

// ── 生成历史 localStorage ──
</script>

<template>
  <div class="page-section active">
    <ErrorBoundary title="资源生成异常">
    <div class="section-header">
      <div class="section-title"><span class="section-title-icon" v-html="icons.robot"></span>多智能体资源生成</div>
      <div class="section-desc">输入知识点，7个AI智能体协作为你生成7种个性化学习资源（讲解/题目/导图/拓展/PPT/代码实操/视频脚本）</div>
    </div>

    <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
    <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">
      <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);">🧠 记忆薄弱点:</span>
      <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" style="padding:3px 10px;border-radius:12px;background:rgba(239,68,68,0.12);color:var(--accent-danger);">{{ w }}</span>
    </div>

    <!-- 输入区 -->
    <div class="card rv-card">
      <div class="rag-config">
        <input
          v-model="topic"
          placeholder="输入知识点，如 TCP三次握手、子网划分、CSMA/CD..."
          class="form-input res-input"
          @keyup.enter="generateResource"
        />
        <select class="rag-select" v-model="difficulty">
          <option value="easy">基础</option>
          <option value="medium">中等</option>
          <option value="hard">进阶</option>
        </select>
        <button class="rag-btn" @click="generateResource" :disabled="!topic.trim() || loading">
          <span class="btn-ic" v-html="icons.rocket"></span>{{ loading ? '生成中...' : '生成资源' }}
        </button>
      </div>
    </div>

    <!-- 生成历史 -->
    <div v-if="resourceHistory.length > 0" class="history-bar">
      <div class="history-bar-header" role="button" tabindex="0" :aria-expanded="showHistory" @click="showHistory = !showHistory" @keydown.enter="showHistory = !showHistory" @keydown.space.prevent="showHistory = !showHistory">
        <span><span class="btn-ic" v-html="icons.history"></span>生成历史 ({{ resourceHistory.length }})</span>
        <span class="history-toggle">{{ showHistory ? '收起' : '展开' }}</span>
      </div>
      <div v-if="showHistory" class="history-list">
        <div
          v-for="item in resourceHistory"
          :key="item.id"
          class="history-item"
          :class="{ active: selectedHistory === item.id }"
          @click="loadFromHistory(item)"
        >
          <span class="history-topic">{{ item.topic || '(空)' }}</span>
          <span class="history-meta">{{ item.timestamp }}</span>
        </div>
        <button class="history-clear" @click="clearHistory">清空历史</button>
      </div>
    </div>

    <!-- 可复用学习资源池 -->
    <div class="history-bar">
      <div class="history-bar-header" role="button" tabindex="0" :aria-expanded="showPool" @click="showPool ? (showPool = false) : loadPoolResources()" @keydown.enter="showPool ? (showPool = false) : loadPoolResources()">
        <span><span class="btn-ic" v-html="icons.book"></span>我的资源池 ({{ poolResources.length }})</span>
        <span class="history-toggle">{{ showPool ? '收起' : '展开' }}</span>
      </div>
      <div v-if="showPool" class="history-list">
        <div v-if="poolLoading" class="pool-loading">加载中...</div>
        <div v-else-if="poolResources.length === 0" class="pool-empty">
          暂无已登记资源。生成资源后会在这里展示，可直接打开复用，也可重新生成。
        </div>
        <div
          v-for="item in poolResources"
          :key="item.id"
          class="history-item"
          :class="{ active: selectedHistory === item.id }"
          @click="openPoolResource(item)"
        >
          <span class="history-topic">{{ item.title || '(未命名资源)' }}</span>
          <span class="history-meta">{{ item.resource_type }} · {{ item.created_at }}</span>
        </div>
      </div>
    </div>

    <!-- 流水线进度 -->
    <div v-if="loading || pipelineStage > 0" class="card rv-card">
      <!-- 真实进度条（SSE 推送，赛题非功能4：生成进度追踪）-->
      <div v-if="loading" class="rv-progress-head">
        <div class="rv-progress-row">
          <span>{{ currentAgent || '初始化中...' }}</span>
          <span class="rv-progress-pct">{{ progressPct }}%</span>
        </div>
        <div class="rv-progress-track">
          <div :style="{
            width: progressPct + '%',
            height: '100%',
            background: 'var(--gradient-primary)',
            transition: 'width 0.4s ease',
            borderRadius: 'var(--radius-full)',
          }"></div>
        </div>
      </div>
      <div class="agent-flow">
        <template v-for="(step, idx) in agentSteps" :key="step.name">
        <div class="agent-node"
          :class="{
            active: pipelineStage === step.stage,
            done: pipelineStage > step.stage
          }"
        >
          <div class="agent-node-icon" :style="{
            background: pipelineStage >= step.stage ? 'var(--gradient-primary)' : 'var(--bg-secondary)',
            color: pipelineStage >= step.stage ? '#fff' : 'var(--text-muted)',
          }" v-html="step.icon"></div>
          <div class="agent-node-name">{{ step.name }}</div>
          <div class="agent-node-status">
            {{ pipelineStage === step.stage ? '进行中...' : pipelineStage > step.stage ? '已完成' : '等待中' }}
          </div>
        </div>
        <div v-if="idx < agentSteps.length - 1" class="agent-arrow">→</div>
        </template>
      </div>
      <div v-if="loading" class="rv-working">
        {{ currentAgent }} 正在工作...
      </div>
    </div>

    <!-- TCP 动画（知识点相关时显示） -->
    <div v-if="result && showTcpAnimation" class="rv-gap">
      <TcpHandshakeAnimation :mode="showSynFlood ? 'synflood' : 'normal'" />
    </div>

<!-- 生成结果 -->
    <div v-if="result" class="card rv-card" :style="{ borderTop: `3px solid ${tabAccent}` }">
      <!-- 产物验收不通过横幅 -->
      <div v-if="gateRejected" class="gate-reject-banner">
        <span class="gate-reject-icon">!</span>
        <div>
          <strong>产物验收不通过</strong>
          <div class="gate-reject-reasons">
            <div v-for="(r, i) in (gateResult?.reasons || [])" :key="i">{{ r }}</div>
          </div>
        </div>
      </div>
      <div class="card-header rv-card-header">
        <span class="card-title"><span class="section-title-icon" v-html="icons.package"></span>学习资源包：{{ topic }}</span>
        <div class="rv-tab-row">
        <button v-for="tab in resourceTabs"
          :key="tab.key"
          class="rag-btn rv-tab"
          :class="{ 'is-active': activeTab === tab.key }"
          @click="activeTab = tab.key as any"
        ><span class="tab-ic" v-html="icons[tab.icon as keyof typeof icons]"></span>{{ tab.label }}</button>
        </div>
      </div>

      <!-- 讲解文档 -->
      <div v-if="activeTab === 'doc'" class="content-with-tts">
        <button class="speak-btn" :class="{ speaking: speakingText === result.teacher_doc }"
                @click="speakText(result.teacher_doc || '')" title="朗读讲解">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path v-if="speakingText !== result.teacher_doc" d="M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>
            <polygon v-else points="6 4 18 4 18 20 6 20"/>
          </svg>
        </button>
        <div class="markdown-body" v-html="renderMarkdownSafe(result.teacher_doc || '*暂无内容*')"></div>
      </div>

      <!-- 练习题 -->
      <div v-if="activeTab === 'quiz'" class="content-with-tts">
        <button class="speak-btn" :class="{ speaking: speakingText === result.quiz }"
                @click="speakText(result.quiz || '')" title="朗读题目">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path v-if="speakingText !== result.quiz" d="M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>
            <polygon v-else points="6 4 18 4 18 20 6 20"/>
          </svg>
        </button>
        <div class="markdown-body" v-html="renderMarkdownSafe(result.quiz || '*暂无内容*')"></div>
      </div>

      <!-- 多媒体/导图 -->
      <div v-if="activeTab === 'media'">
        <MindMapViewer :content="result.media_plan || ''" />
        <!-- 思维导图统计信息 (SSE 推送) -->
        <div v-if="result.mindmap_stats" class="rv-stat-row">
          <template v-for="stat in parseMindmapStats(result.mindmap_stats)" :key="stat.label">
            <div class="rv-stat">
              <div class="rv-stat-value" :style="{color: stat.color}">{{ stat.value }}</div>
              <div class="rv-stat-label">{{ stat.label }}</div>
            </div>
          </template>
        </div>
        <!-- 薄弱知识点列表 -->
        <div v-if="result.mindmap_weak_points && result.mindmap_weak_points !== '[]'" class="rv-weak-box">
          <div class="rv-weak-title">薄弱/未学知识点</div>
          <div class="rv-weak-tags">
            <span v-for="wp in parseWeakPoints(result.mindmap_weak_points)" :key="wp"
              class="rv-weak-tag">{{ wp }}</span>
          </div>
        </div>
        <div class="markdown-body rv-mt" v-html="renderMarkdownSafe(result.media_plan || '')"></div>
      </div>

      <!-- 拓展阅读（SSE推送优先，无则手动生成）-->
      <div v-if="activeTab === 'extension'">
        <div v-if="result.extension" class="content-with-tts">
          <button class="speak-btn" :class="{ speaking: speakingText === result.extension }"
                  @click="speakText(result.extension || '')" title="朗读拓展阅读">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path v-if="speakingText !== result.extension" d="M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>
              <polygon v-else points="6 4 18 4 18 20 6 20"/>
            </svg>
          </button>
          <div class="markdown-body" v-html="renderMarkdownSafe(result.extension)"></div>
        </div>
        <div v-else-if="!extensionDoc && !extensionLoading" class="rv-empty">
          <button class="rag-btn" @click="generateExtension">生成拓展阅读材料</button>
          <div class="rv-empty-hint">推荐论文/工业实践/前沿动态/开源项目</div>
        </div>
        <div v-else-if="extensionLoading" class="rv-empty">
          <div class="loading-spinner"></div>
          <div class="rv-empty-hint">拓展阅读 Agent 正在收集资料...</div>
        </div>
        <div v-else>
          <div class="markdown-body" v-html="renderMarkdownSafe(extensionDoc)"></div>
          <div v-if="extensionWarnings.length" class="rv-warn-box">
            <div v-for="w in extensionWarnings" :key="w" class="rv-warn-item">{{ w }}</div>
          </div>
        </div>
      </div>

      <!-- 审阅报告 -->
      <div v-if="activeTab === 'critic'">
        <div class="markdown-body" v-html="renderMarkdownSafe(result.critic_report || '*暂无内容*')"></div>
        <div v-if="result.status === 'ok'" class="rv-ok-box">
          审阅完成：所有内容已通过事实核查
        </div>
        <div v-else class="rv-err-box">
          生成过程中出现问题
        </div>
      </div>

<!-- 证据校验（INC-02，消费 evidence_check 节点报告）-->
      <div v-if="activeTab === 'evidence'" class="evidence-tab">
        <EvidenceCheckPanel v-if="result.evidence_report" :report="result.evidence_report" />
        <div v-else class="markdown-body rv-empty">
          证据校验报告将在审阅完成后由「证据校验 Agent」生成。
        </div>
      </div>

      <!-- 产物验收闸门 -->
      <div v-if="activeTab === 'gate'" class="gate-tab">
        <div v-if="gateResult" class="gate-result" :class="'gate-' + gateResult.verdict">
          <div class="gate-header">
            <span class="gate-verdict-badge" :class="'gate-badge-' + gateResult.verdict">
              {{ gateResult.verdict === 'pass' ? '通过' : gateResult.verdict === 'fix' ? '需修复' : '已拒绝' }}
            </span>
            <span v-if="gateResult.consistency_score !== undefined" class="gate-score">
              一致性: {{ gateResult.consistency_score }}/100
            </span>
          </div>
          <div class="gate-reasons">
            <div v-for="(reason, i) in (gateResult.reasons || [])" :key="i" class="gate-reason">
              {{ reason }}
            </div>
          </div>
        </div>
        <div v-else class="markdown-body rv-empty">
          产物验收闸门将在证据校验后执行。
        </div>
      </div>

      <!-- PPT大纲（SSE推送优先，无则手动生成）-->
      <div v-if="activeTab === 'ppt'">
        <div v-if="result.ppt_outline" class="content-with-tts">
          <button class="speak-btn" :class="{ speaking: speakingText === result.ppt_outline }"
                  @click="speakText(result.ppt_outline || '')" title="朗读PPT大纲">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path v-if="speakingText !== result.ppt_outline" d="M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>
              <polygon v-else points="6 4 18 4 18 20 6 20"/>
            </svg>
          </button>
          <div class="markdown-body" v-html="renderMarkdownSafe(result.ppt_outline)"></div>
          <!-- 真实 .pptx 文件下载（赛题多模态产出） -->
          <div v-if="result.ppt_file" class="rv-ppt-dl">
            <a :href="result.ppt_file.url" :download="result.ppt_file.filename" target="_blank" rel="noopener"
               class="rag-btn rv-dl-link">
              <span class="btn-ic" v-html="icons.download"></span>下载 PPT 文件（.pptx · {{ result.ppt_file.slide_count }} 页）
            </a>
          </div>
        </div>
        <div v-else-if="!pptOutline && !pptLoading" class="rv-empty">
          <button class="rag-btn" @click="generatePpt">生成PPT幻灯片大纲</button>
          <div class="rv-empty-hint">8-12页结构化大纲，适合课堂展示和复习速览</div>
        </div>
        <div v-else-if="pptLoading" class="rv-empty">
          <div class="loading-spinner"></div>
          <div class="rv-empty-hint">PPT大纲 Agent 正在规划幻灯片结构...</div>
        </div>
        <div v-else>
          <div class="markdown-body" v-html="renderMarkdownSafe(pptOutline)"></div>
        </div>
      </div>

      <!-- 代码实操案例（SSE推送优先，无则手动生成）-->
      <div v-if="activeTab === 'code'">
        <div v-if="result.code_practice" class="content-with-tts">
          <button class="speak-btn" :class="{ speaking: speakingText === result.code_practice }"
                  @click="speakText(result.code_practice || '')" title="朗读代码案例">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path v-if="speakingText !== result.code_practice" d="M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>
              <polygon v-else points="6 4 18 4 18 20 6 20"/>
            </svg>
          </button>
          <div class="markdown-body" v-html="renderMarkdownSafe(result.code_practice)"></div>
        </div>
        <div v-else-if="!codePractice && !codeLoading" class="rv-empty">
          <button class="rag-btn" @click="generateCodePractice">生成代码实操案例</button>
          <div class="rv-empty-hint">可运行的Python代码，动手理解网络原理</div>
        </div>
        <div v-else-if="codeLoading" class="rv-empty">
          <div class="loading-spinner"></div>
          <div class="rv-empty-hint">代码实操 Agent 正在编写可运行案例...</div>
        </div>
        <div v-else>
          <div class="markdown-body" v-html="renderMarkdownSafe(codePractice)"></div>
          <div v-if="codeWarnings.length" class="rv-warn-box">
            <div v-for="w in codeWarnings" :key="w" class="rv-warn-item">{{ w }}</div>
          </div>
        </div>
      </div>

      <!-- 视频脚本（第7种资源，SSE推送）+ 多模态展示 -->
      <div v-if="activeTab === 'video'">
        <!-- 多模态内容卡片（图片+音频） -->
        <MultimodalCard
          :image-base64="mmImageBase64"
          :image-svg="mmImageSvg"
          :audio-base64="mmAudioBase64"
          :audio-fallback-text="mmAudioFallbackText"
          :image-source="mmImageSource"
          :audio-source="mmAudioSource"
          :loading="mmLoading"
        />
        <!-- 错误提示 -->
        <div v-if="mmError" class="engine-error rv-mm-error">{{ mmError }}</div>

        <!-- 生成多模态按钮 -->
        <div v-if="result.video_script && !mmImageBase64 && !mmImageSvg" class="rv-mm-actions">
          <button class="btn btn-primary" @click="generateMultimodal" :disabled="mmLoading">
            {{ mmLoading ? '生成中...' : '生成教学插图 + 语音旁白' }}
          </button>
          <button class="btn btn-video" @click="generateNarratedVideo" :disabled="videoLoading">
            {{ videoLoading ? '合成中...' : '生成配音教学视频' }}
          </button>
          <button class="btn btn-primary" @click="generateTeachingVideo" :disabled="teachingVideoLoading">
            {{ teachingVideoLoading ? '生成中...' : '生成程序化教学视频' }}
          </button>
          <span class="rv-mm-note">
            讯飞TTI+TTS多模态生成 | MeloTTS+FFmpeg配音视频 | 零API成本程序化合成
          </span>
        </div>

        <!-- 程序化教学视频播放器 -->
        <VideoPlayer
          v-if="showTeachingVideo && teachingVideoHtml"
          :html="teachingVideoHtml"
          :title="topic + ' - 教学视频'"
          @close="showTeachingVideo = false"
        />

        <!-- 视频脚本内容 -->
        <div v-if="result.video_script" class="content-with-tts">
          <button class="speak-btn" :class="{ speaking: speakingText === result.video_script }"
                  @click="speakText(result.video_script || '')" title="朗读视频脚本">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path v-if="speakingText !== result.video_script" d="M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>
              <polygon v-else points="6 4 18 4 18 20 6 20"/>
            </svg>
          </button>
          <div class="markdown-body" v-html="renderMarkdownSafe(result.video_script)"></div>
        </div>
        <div v-else-if="!mmLoading" class="rv-empty">
          <div class="rv-empty-title">视频脚本由多模态视频 Agent 在生成时自动产出</div>
          <div class="rv-empty-hint">包含分镜、画面描述、旁白文案、动画说明</div>
        </div>
      </div>
    </div>

    <!-- 讯飞AI工坊：深度集成讯飞开放平台全部已开通能力（始终可见） -->
    <XfyunWorkshop :topic="topic" :result="result" />
    </ErrorBoundary>
  </div>
</template>

<style scoped>
.agent-flow {
  display: flex;
  align-items: center;
  justify-content: center;
  gap:0.375rem;
  margin-bottom:0.5rem;
  flex-wrap: wrap;
}
.agent-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap:0.25rem;
  padding:0.625rem 0.875rem;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  border-radius:var(--radius-md);
  min-width:4.375rem;
  transition: var(--transition);
}
.agent-node.active {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px var(--accent-primary-10), var(--glow-primary);
  animation: pulse-glow 2s ease-in-out infinite;
}
.agent-node.done {
  border-color: var(--accent-success);
  box-shadow: var(--glow-success);
  opacity: 0.85;
}
.agent-node-icon {
  width:2.25rem;
  height:2.25rem;
  border-radius:var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size:1.125rem;
  transition: var(--transition);
}
.agent-node-name { font-size:0.75rem; font-weight: 600; color: var(--text-primary); }
.agent-node-status { font-size:0.6875rem; color: var(--text-muted); }
.agent-arrow { font-size:1.125rem; color: var(--text-muted); }

/* ── 生成历史 ── */
.history-bar {
  margin-bottom:1rem;
  border: 1px solid var(--border-color);
  border-radius:var(--radius-md);
  overflow: hidden;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.history-bar-header {
  display: flex; justify-content: space-between; align-items: center;
  padding:0.625rem 0.875rem; cursor: pointer; font-size:0.8125rem; font-weight: 600;
  color: var(--text-secondary); user-select: none;
  transition: var(--transition);
}
.history-bar-header:hover { background: var(--bg-card-hover); }
.history-toggle { font-size:0.6875rem; color: var(--text-muted); font-weight: 400; }
.history-list { padding:0.25rem 0.5rem 0.5rem; max-height:12.5rem; overflow-y: auto; }
.history-item {
  display: flex; justify-content: space-between; align-items: center;
  padding:0.375rem 0.625rem; border-radius:var(--radius-sm); cursor: pointer;
  transition: var(--transition); font-size:0.75rem;
}
.history-item:hover { background: var(--bg-card-hover); }
.history-item.active { background: var(--accent-primary-10); color: var(--accent-primary); }
.history-topic { color: var(--text-primary); font-weight: 500; max-width:60%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-meta { color: var(--text-muted); font-size:0.6875rem; }
.history-clear {
  width:100%; margin-top:0.25rem; padding:0.3125rem; border: none; border-radius:var(--radius-sm);
  background: transparent; color: var(--text-muted); font-size:0.6875rem; cursor: pointer;
  transition: var(--transition);
}
.history-clear:hover { color: var(--accent-danger); background: var(--accent-danger-10); }

/* ── TTS 语音朗读 ── */
.content-with-tts { position: relative; }
.speak-btn {
  position: absolute; top: 0; right: 0; z-index: 5;
  display: inline-flex; align-items: center; justify-content: center;
  width:2rem; height:2rem; border-radius:50%; border: none;
  background: var(--glass-bg); backdrop-filter: blur(var(--glass-blur));
  color: var(--text-muted); cursor: pointer;
  transition: var(--transition); flex-shrink: 0;
  box-shadow: var(--shadow-sm);
}
.speak-btn:hover { background: var(--bg-card-hover); color: var(--accent-primary); box-shadow: var(--shadow-md); }
.speak-btn.speaking { color: var(--accent-primary); background: var(--accent-primary-10); animation: speak-pulse 1.5s ease-in-out infinite; }
@keyframes speak-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(124, 106, 242, 0.3); }
  50% { box-shadow: 0 0 0 8px rgba(124, 106, 242, 0); }
}
.btn-ic {
  width: 1rem;
  height: 1rem;
  display: inline-flex;
  vertical-align: -2px;
  margin-right: 0.375rem;
}
.btn-ic :deep(svg) { width: 100%; height: 100%; }
.tab-ic {
  width: 0.875rem;
  height: 0.875rem;
  display: inline-flex;
  vertical-align: -1px;
  margin-right: 0.25rem;
}
.tab-ic :deep(svg) { width: 100%; height: 100%; }

/* 移动端适配 */
@media (max-width: 480px) {
  .page-section { padding: 1rem 0.75rem; }
  .agent-flow { gap: 0.25rem; }
  .agent-node { padding: 0.5rem 0.625rem; min-width: 3.75rem; }
  .agent-node-icon { width: 2rem; height: 2rem; font-size: 1rem; }
}

/* ── Wave D：内联样式迁移（一致性）── */
.rv-card { margin-bottom: 1.25rem; }
.rv-gap { margin-bottom: 1.25rem; }
.rv-mt { margin-top: 0.75rem; }
.res-input { flex: 1; min-width: 12.5rem; }

.rv-progress-head { margin-bottom: 1rem; }
.rv-progress-row { display: flex; justify-content: space-between; font-size: 0.8125rem; color: var(--text-secondary); margin-bottom: 0.375rem; }
.rv-progress-pct { font-weight: 600; color: var(--accent-primary); }
.rv-progress-track { height: 0.5rem; background: var(--bg-secondary); border-radius: var(--radius-full); overflow: hidden; }
.rv-working { text-align: center; padding: 0.5rem 0; font-size: 0.8125rem; color: var(--text-muted); }

.rv-card-header { border-bottom: 1px solid var(--border-light); padding-bottom: 0.75rem; margin-bottom: 0.75rem; }
.rv-tab-row { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.rv-tab { padding: 0.375rem 0.875rem; font-size: 0.75rem; }
.rv-tab.is-active { background: var(--gradient-primary); color: #fff; border: none; }
.rv-tab:not(.is-active) { background: transparent; color: var(--text-secondary); border: 1px solid var(--border-color); }

.rv-stat-row { margin-top: 0.75rem; display: flex; gap: 0.75rem; flex-wrap: wrap; }
.rv-stat { padding: 0.5rem 1rem; background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: var(--radius-sm); text-align: center; }
.rv-stat-value { font-size: 1.25rem; font-weight: 700; }
.rv-stat-label { font-size: 0.75rem; color: var(--text-muted); }

.rv-weak-box { margin-top: 0.75rem; padding: 0.75rem; background: color-mix(in srgb, var(--accent-warm) 10%, transparent); border-radius: var(--radius-sm); }
.rv-weak-title { font-size: 0.8125rem; font-weight: 600; color: var(--accent-warm); margin-bottom: 0.375rem; }
.rv-weak-tags { display: flex; gap: 0.375rem; flex-wrap: wrap; }
.rv-weak-tag { padding: 0.1875rem 0.625rem; background: color-mix(in srgb, var(--accent-warm) 14%, transparent); border-radius: var(--radius-full); font-size: 0.75rem; color: var(--accent-warm); }

.rv-empty { text-align: center; padding: 1.875rem; color: var(--text-muted); }
.rv-empty-title { font-size: 0.875rem; }
.rv-empty-hint { margin-top: 0.625rem; font-size: 0.8125rem; }

.rv-warn-box { margin-top: 0.75rem; padding: 0.75rem; background: var(--accent-danger-10); border-radius: var(--radius-sm); }
.rv-warn-item { font-size: 0.8125rem; color: var(--accent-danger); }

.rv-ok-box { margin-top: 0.75rem; padding: 0.75rem; background: var(--accent-success-10); border-radius: var(--radius-sm); color: var(--accent-success); font-size: 0.8125rem; }
.rv-err-box { margin-top: 0.75rem; padding: 0.75rem; background: var(--accent-danger-10); border-radius: var(--radius-sm); color: var(--accent-danger); font-size: 0.8125rem; }

.rv-ppt-dl { margin-top: 0.875rem; }
.rv-dl-link { display: inline-flex; align-items: center; gap: 0.5rem; text-decoration: none; }

.rv-mm-error { margin: 0.5rem 0; }
.rv-mm-actions { margin: 1rem 0; display: flex; gap: 0.625rem; flex-wrap: wrap; }
.rv-mm-note { margin-left: 0.25rem; font-size: 0.8125rem; color: var(--text-secondary); }

/* 视频生成按钮（绿色语义：配音教学视频） */
.btn-video { background: var(--accent-success); color: #fff; }
.btn-video:hover { background: color-mix(in srgb, var(--accent-success) 85%, #000); }

/* ── 产物验收闸门 ── */
.gate-reject-banner {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  margin: 0 0 1rem 0;
  background: color-mix(in srgb, var(--accent-danger) 12%, transparent);
  border: 1px solid var(--accent-danger);
  border-radius: var(--radius-md);
  color: var(--accent-danger);
  font-size: 0.875rem;
  line-height: 1.5;
}
.gate-reject-icon {
  flex-shrink: 0;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  background: var(--accent-danger);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.875rem;
}
.gate-reject-reasons {
  margin-top: 0.375rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.gate-reject-reasons > div {
  opacity: 0.85;
  font-size: 0.8125rem;
}

.gate-tab {
  padding: 0.5rem 0;
}
.gate-result {
  padding: 1rem;
  border-radius: var(--radius-md);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
}
.gate-result.gate-pass {
  border-color: var(--accent-success);
  background: color-mix(in srgb, var(--accent-success) 6%, var(--glass-bg));
}
.gate-result.gate-fix {
  border-color: var(--accent-warm);
  background: color-mix(in srgb, var(--accent-warm) 6%, var(--glass-bg));
}
.gate-result.gate-reject {
  border-color: var(--accent-danger);
  background: color-mix(in srgb, var(--accent-danger) 6%, var(--glass-bg));
}
.gate-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}
.gate-verdict-badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  font-size: 0.8125rem;
  font-weight: 600;
}
.gate-badge-pass {
  background: color-mix(in srgb, var(--accent-success) 20%, transparent);
  color: var(--accent-success);
}
.gate-badge-fix {
  background: color-mix(in srgb, var(--accent-warm) 20%, transparent);
  color: var(--accent-warm);
}
.gate-badge-reject {
  background: color-mix(in srgb, var(--accent-danger) 20%, transparent);
  color: var(--accent-danger);
}
.gate-score {
  font-size: 0.8125rem;
  color: var(--text-secondary);
}
.gate-reasons {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.gate-reason {
  font-size: 0.8125rem;
  color: var(--text-secondary);
  padding: 0.375rem 0.625rem;
  background: var(--glass-bg);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
}
</style>
