import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'
import { useAchievementStore } from '@/stores/achievementStore'

// ── 类型定义 ──

export interface StudentProfile {
  knowledge_base?: string         // 知识基础
  learning_style?: string         // 学习风格
  goal?: string                   // 学习目标
  weak_points?: string            // 薄弱点
  progress?: number               // 学习进度
  interest_area?: string          // 兴趣方向
  study_time?: string             // 每日学习时长
  preferred_difficulty?: string   // 难度偏好
  // 新增5维（对标学境13维画像）
  academic_stage?: string         // 学业阶段（大一/大二/大三/大四/考研）
  subject_confidence?: string     // 各科信心指数（json）
  exam_target?: string            // 目标院校/分数
  study_frequency?: string        // 学习频率（每天/隔天/周末）
  resource_preference?: string    // 资源偏好（视频/图文/代码/交互）
  [key: string]: unknown
}

export interface Segment {
  type: 'reasoning' | 'tool_call' | 'content'
  content?: string
  toolName?: string
  toolArgs?: string
  toolResult?: string
  duration?: number
  isImage?: boolean
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  segments: Segment[]
  timestamp: Date
  reasoningDuration?: number
  imageBase64?: string  // 用户上传的图片（讯飞图片理解）
  svgDiagram?: string   // 导师答疑 SVG 图解（功能④ enhanced-answer）
  videoScript?: string  // 导师答疑短视频脚本（功能④ enhanced-answer）
}

export interface Conversation {
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: Date
  updatedAt: Date
}

export interface StatData {
  studyTime: number
  questionsDone: number
  mastery: number
  streak: number
}

export interface Session {
  id: string
  subject: string
  title: string
  duration: string
  date: string
  score: number
}

export interface Task {
  id: string
  icon: string
  title: string
  desc: string
  time: string
  color: string
}

export interface MasteryItem {
  subject: string
  label: string
  pct: number
}

export interface Question {
  id: string
  text: string
  type: string
  difficulty: string
  subject: string
  chapter: string
  answer: number | string
  options?: string[]
}

export interface SubjectsMap {
  [key: string]: { name: string; chapters: string[] }
}

/** 408 四科 → 章节级科目 key 映射 */
export const COURSE_MAP: Record<string, { name: string; subjects: string[] }> = {
  computer_network: {
    name: '计算机网络',
    subjects: ['overview', 'physical', 'datalink', 'network', 'transport', 'application', 'security'],
  },
  data_structures: {
    name: '数据结构',
    subjects: ['ds_linear', 'ds_stack', 'ds_queue', 'ds_string', 'ds_tree', 'ds_graph', 'ds_search', 'ds_sort'],
  },
  computer_organization: {
    name: '计算机组成原理',
    subjects: ['co_overview', 'co_data', 'co_memory', 'co_isa', 'co_cpu', 'co_bus', 'co_io'],
  },
  operating_system: {
    name: '操作系统',
    subjects: ['os_overview', 'os_process', 'os_memory', 'os_file', 'os_io'],
  },
}

/** 反向映射：章节级 key → 课程 key */
export const SUBJECT_TO_COURSE: Record<string, string> = {}
for (const [courseKey, course] of Object.entries(COURSE_MAP)) {
  for (const sub of course.subjects) {
    SUBJECT_TO_COURSE[sub] = courseKey
  }
}

export interface KnowledgeGraphData {
  nodes: { id: string; label: string; group: number }[]
  edges: { source: string; target: string }[]
}

export interface AssessmentResult {
  mastery: Record<string, number>
  activity: string
  weak_focus: string[]
  trend: string
  adjustment: string
  by_subject: Record<string, { total: number; correct: number; accuracy: number }>
  total_questions: number
  overall_accuracy: number
llm_assessed: boolean
}

// ── 对话管理 ──
const _ns = (k: string) => `mars408_${k}`

function nextId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

export const useStudyStore = defineStore('study', () => {
  // ── 认证 (委派 authStore) ──
  const authStore = useAuthStore()
  const currentUser = computed(() => authStore.currentUser)
  const isAdmin = computed(() => authStore.isAdmin)
  const token = computed(() => authStore.token)
  const login = async (username: string, password: string) => {
    const user = await authStore.login(username, password)
    // 新用户登录：清除旧对话记录，避免跨用户可见
    _clearConversations()
    return user
  }
  const register = async (username: string, password: string, displayName: string) => {
    const user = await authStore.register(username, password, displayName)
    // 新用户注册：清除旧对话记录
    _clearConversations()
    return user
  }
  const logout = () => {
    authStore.logout()
    _clearConversations()
  }

  // ── 学生画像 ──
  const studentProfile = ref<StudentProfile | null>(null)
  const profileCompleted = ref(false)

  // ── 科目列表（延迟加载，多处视图依赖）──
  const subjects = ref<SubjectsMap>({})
  /** 按 408 四科分组的课程列表：{ courseKey: { name, chapters: [{ key, name, subSubjects }] } } */
  const courses = computed(() => {
    const s = subjects.value
    const result: Record<string, { name: string; chapters: { key: string; name: string; subSubjects: string[] }[] }> = {}
    for (const [courseKey, course] of Object.entries(COURSE_MAP)) {
      const chapters = course.subjects
        .filter(k => s[k])
        .map(k => ({ key: k, name: s[k]!.name, subSubjects: s[k]!.chapters || [] }))
      if (chapters.length > 0) {
        result[courseKey] = { name: course.name, chapters }
      }
    }
    return result
  })

  // ── 默认数据（给 ProfilePanel/ProfileView 等依赖 store.data 的组件提供兜底）──
  const data = ref({
    masteryData: [] as any[],
    weaknesses: [] as any[],
    profileTraits: [] as any[],
    learningStyle: [] as any[],
  })

// ── 距考研天数（2026 年考研为 12 月 26-27 日，首个考试日前一天为截止）──
  const EXAM_DATE = new Date('2026-12-26')
  function calcDaysToExam(): number {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    return Math.max(0, Math.ceil((EXAM_DATE.getTime() - today.getTime()) / 86400000))
  }
  const daysToExam = ref(calcDaysToExam())

  function loadProfile() {
    try {
      const raw = localStorage.getItem(_ns('profile'))
      if (raw) {
        studentProfile.value = JSON.parse(raw)
        profileCompleted.value = true
      }
    } catch { /* */ }
  }
function saveProfile(profile: StudentProfile) {
    studentProfile.value = profile
    profileCompleted.value = true
    try { localStorage.setItem(_ns('profile'), JSON.stringify(profile)) } catch { /* */ }
    if (token.value) {
      api.put('/user/profile', { profile }).catch(() => {})
    }
    // 成就追踪
    try { useAchievementStore().recordProfileBuilt() } catch { /* */ }
  }
  function clearProfile() {
    studentProfile.value = null
    profileCompleted.value = false
    try { localStorage.removeItem(_ns('profile')) } catch { /* */ }
  }

  loadProfile()
  // 预加载科目列表（多处视图依赖 subjects）
  fetchSubjects().catch(() => {})

  // ── 思考/Agent 模式 ──
  const thinkingMode = ref(false)
  const agentMode = ref(false)

  // ── 对话管理 ──
  const CONV_KEY = _ns('conversations')
  const conversations = ref<Conversation[]>([])
  const currentConversationId = ref<string | null>(null)

  function _convKey(): string {
    // 按用户隔离对话存储，不同用户看不到彼此的对话
    const uid = authStore.currentUser?.id || 'anonymous'
    return CONV_KEY + '_' + uid
  }

  function _clearConversations() {
    conversations.value = []
    currentConversationId.value = null
    try { localStorage.removeItem(_convKey()) } catch { /* */ }
  }

function normalizeMessage(m: any): ChatMessage {
    return {
      id: m.id || nextId(),
      role: m.role || 'assistant',
      content: m.content || '',
      segments: m.segments || [],
      timestamp: m.timestamp ? new Date(m.timestamp) : new Date(),
      reasoningDuration: m.reasoningDuration,
      svgDiagram: m.svgDiagram,
      videoScript: m.videoScript,
      imageBase64: m.imageBase64,
    }
  }

  function loadConversations() {
    try {
      const raw = localStorage.getItem(_convKey())
      if (raw) {
        const parsed = JSON.parse(raw)
        conversations.value = parsed.map((c: any) => ({
          ...c,
          messages: (c.messages || []).map(normalizeMessage),
          createdAt: new Date(c.createdAt),
          updatedAt: new Date(c.updatedAt),
        }))
        if (conversations.value.length > 0) {
          currentConversationId.value = conversations.value[0]?.id ?? null
        }
      }
    } catch { conversations.value = [] }
    // 若本地无对话且有 token，尝试从后端恢复（归档对话的还原路径）
    if (conversations.value.length === 0 && token.value) {
      api.get('/user/conversations').then((data: any) => {
        if (data && Array.isArray(data.conversations) && data.conversations.length > 0) {
          conversations.value = data.conversations.map((c: any) => ({
            ...c,
            messages: (c.messages || []).map(normalizeMessage),
            createdAt: new Date(c.createdAt),
            updatedAt: new Date(c.updatedAt),
          }))
          currentConversationId.value = conversations.value[0]?.id ?? null
          saveConversations()  // 回写到 localStorage
        }
      }).catch(() => {})
    }
  }

  function saveConversations() {
    // 防止 localStorage 超限：仅保留最近 N 条对话，其余归档到后端
    const MAX_LOCAL_CONVS = 20
    const convs = conversations.value.slice(0, MAX_LOCAL_CONVS)
    try {
      const payload = JSON.stringify(convs)
      // localStorage 通常上限 5-10MB；超过 4MB 时仅保留最近 5 条
      if (payload.length > 4 * 1024 * 1024) {
        const slim = convs.slice(0, 5)
        localStorage.setItem(_convKey(), JSON.stringify(slim))
      } else {
        localStorage.setItem(_convKey(), payload)
      }
    } catch { /* localStorage 写入失败时静默降级 */ }
    // 同步到后端
    if (token.value) {
      api.put('/user/conversations', {
        conversations: conversations.value.map(c => ({
          id: c.id,
          title: c.title,
          messages: c.messages.map(m => ({
            id: m.id, role: m.role, content: m.content,
            segments: m.segments, timestamp: m.timestamp,
          })),
          createdAt: c.createdAt,
          updatedAt: c.updatedAt,
        })),
      }).catch(() => {})
    }
  }

  function createConversation() {
    const conv: Conversation = {
      id: nextId(),
      title: '新对话',
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
    }
    conversations.value.unshift(conv)
    currentConversationId.value = conv.id
    saveConversations()
  }

  async function deleteConversation(id: string) {
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (currentConversationId.value === id) {
      currentConversationId.value = conversations.value[0]?.id ?? null
    }
    saveConversations()
  }

  function getCurrentConversation(): Conversation | undefined {
    return conversations.value.find(c => c.id === currentConversationId.value)
  }

  function getConversationById(id: string): Conversation | undefined {
    return conversations.value.find(c => c.id === id)
  }

  function switchToConversation(id: string): boolean {
    const found = conversations.value.find(c => c.id === id)
    if (found) {
      currentConversationId.value = id
      return true
    }
    return false
  }

  function searchConversations(query: string): Conversation[] {
    if (!query.trim()) return conversations.value
    const q = query.toLowerCase()
    return conversations.value.filter(c =>
      c.title.toLowerCase().includes(q) ||
      c.messages.some(m => m.content.toLowerCase().includes(q))
    )
  }

  async function sendMessageStream(text: string, onChunk?: (chunk: string) => void): Promise<string> {
    const conv = getCurrentConversation()
    if (!conv) return ''

    if (conv.messages.length === 0) {
      conv.title = text.length > 20 ? text.slice(0, 20) + '...' : text
    }

const userMsg: ChatMessage = {
      id: nextId(), role: 'user', content: text, segments: [], timestamp: new Date(),
    }
    conv.messages.push(userMsg)
    conv.updatedAt = new Date()
    saveConversations()

    // 成就追踪：首次对话
    try { useAchievementStore().recordFirstChat() } catch { /* */ }

    const history = conv.messages.slice(0, -1).map(m => ({
      role: m.role, content: m.content,
    }))

    const msgIndex = conv.messages.length
    const msgId = nextId()
    conv.messages.push({
      id: msgId, role: 'assistant', content: '', segments: [], timestamp: new Date(),
    })

    let finalContent = ''
    let reasonStart: number | null = null
    let toolCallStart: number | null = null
    // SSE 流式写入 localStorage 节流：每 2s 最多写一次
    let lastSaveTime = 0
    const throttledSave = () => {
      const now = Date.now()
      if (now - lastSaveTime > 2000) {
        lastSaveTime = now
        saveConversations()
      }
    }

    try {
      const resp = await api.postStream('/chat/stream', {
        conv_id: conv.id, message: text, history,
        thinking_mode: thinkingMode.value, agent_mode: agentMode.value,
      })

      const reader = resp.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6).trim()
          if (payload === '[DONE]') continue
          try {
            const parsed = JSON.parse(payload)
            const type = parsed.type || 'content'
            const msg = conv.messages[msgIndex] as ChatMessage
            const segs = msg.segments

            if (type === 'error') {
              msg.content = 'API 错误: ' + (parsed.content || '')
              break
            }

            if (type === 'reasoning') {
              if (!reasonStart) reasonStart = Date.now()
              const text = parsed.content || ''
              if (segs.length > 0 && segs[segs.length - 1]!.type === 'reasoning') {
                segs[segs.length - 1]!.content! += text
              } else {
                segs.push({ type: 'reasoning', content: text })
              }
              continue
            }

            if (type === 'tool_call') {
              if (reasonStart) {
                msg.reasoningDuration = Date.now() - reasonStart
                reasonStart = null
              }
              toolCallStart = Date.now()
              segs.push({ type: 'tool_call', toolName: parsed.name, toolArgs: parsed.arguments || '' })
              continue
            }

            if (type === 'tool_result') {
              for (let i = segs.length - 1; i >= 0; i--) {
                if (segs[i]!.type === 'tool_call') {
                  const result = parsed.result || ''
                  segs[i]!.toolResult = result
                  segs[i]!.isImage = result.startsWith('data:image')
                  if (toolCallStart) {
                    segs[i]!.duration = Date.now() - toolCallStart
                    toolCallStart = null
                  }
                  break
                }
              }
              continue
            }

            if (type === 'content') {
              if (reasonStart) {
                const dur = Date.now() - reasonStart
                msg.reasoningDuration = dur
                for (let i = segs.length - 1; i >= 0; i--) {
                  if (segs[i]!.type === 'reasoning') {
                    segs[i]!.duration = dur
                    break
                  }
                }
                reasonStart = null
              }
              const text = parsed.content || ''
              if (text) {
                if (segs.length > 0 && segs[segs.length - 1]!.type === 'content') {
                  segs[segs.length - 1]!.content! += text
                } else {
                  segs.push({ type: 'content', content: text })
                }
                finalContent += text
                msg.content = finalContent
                onChunk?.(text)
                throttledSave()
              }
            }
          } catch { /* */ }
        }
      }
    } catch (e) {
      if (!conv.messages[msgIndex]?.content) {
        conv.messages[msgIndex]!.content = '连接失败，请检查后端服务是否运行'
      }
      conv.updatedAt = new Date()
      saveConversations()
      throw e
    }

    conv.updatedAt = new Date()
    saveConversations()
    return finalContent
  }

  loadConversations()

  // 监听用户切换：清除旧用户的内存数据并加载新用户的对话
  watch(() => authStore.currentUser?.id, (newId, oldId) => {
    if (newId !== oldId) {
      _clearConversations()
      loadConversations()
    }
  })

  // ── 讯飞图片理解（用户上传图片 + 提问）──
  async function askImage(imageBase64: string, question: string): Promise<void> {
    const conv = getCurrentConversation()
    if (!conv) return
    const userMsg: ChatMessage = {
      id: nextId(), role: 'user',
      content: question || '（图片提问）',
      segments: [], timestamp: new Date(),
      imageBase64,
    }
    conv.messages.push(userMsg)
    const msgId = nextId()
    conv.messages.push({ id: msgId, role: 'assistant', content: '', segments: [], timestamp: new Date() })
    saveConversations()
    try {
      const data = await api.post<any>('/xfyun/image-understand', {
        image_base64: imageBase64,
        question: question || '这张图片讲了什么？',
      })
      const m = conv.messages.find(x => x.id === msgId)
      if (m) {
        m.content = data.text || '（无回答）'
        m.segments = [{ type: 'content', content: m.content }]
      }
    } catch (e: any) {
      const m = conv.messages.find(x => x.id === msgId)
      const err = '图片理解失败：' + (e?.message || '请检查后端')
      if (m) { m.content = err; m.segments = [{ type: 'content', content: err }] }
    }
    saveConversations()
  }

  // ── 多模态导师答疑（功能④：/tutor/enhanced-answer）──
  // 学生提问 → 调 /tutor/enhanced-answer → 返回文字+SVG图解+短视频脚本
  async function askTutor(question: string): Promise<void> {
    const conv = getCurrentConversation()
    if (!conv) return

    if (conv.messages.length === 0) {
      conv.title = question.length > 20 ? question.slice(0, 20) + '...' : question
    }

    const userMsg: ChatMessage = {
      id: nextId(), role: 'user', content: question, segments: [], timestamp: new Date(),
    }
    conv.messages.push(userMsg)
    conv.updatedAt = new Date()

    const msgId = nextId()
    conv.messages.push({ id: msgId, role: 'assistant', content: '', segments: [], timestamp: new Date() })
    saveConversations()

    try {
      const data = await api.post<any>('/tutor/enhanced-answer', {
        question,
        profile: studentProfile.value || {},
        course: 'computer_network',
        generate_svg: true,
        generate_video: true,
      })
      const m = conv.messages.find(x => x.id === msgId)
      if (m) {
        m.content = data.answer || '（无回答）'
        m.segments = [{ type: 'content', content: m.content }]
        m.svgDiagram = data.svg_diagram || ''
        m.videoScript = data.video_script || ''
      }
    } catch (e: any) {
      const m = conv.messages.find(x => x.id === msgId)
      const err = '导师答疑失败：' + (e?.message || '请检查后端 /tutor/enhanced-answer 接口')
      if (m) { m.content = err; m.segments = [{ type: 'content', content: err }] }
    }
    conv.updatedAt = new Date()
    saveConversations()
  }

  // ── 真实 API 调用 (替代 Mock) ──

  /** 从后端获取学习统计 */
  async function fetchStats(): Promise<StatData | null> {
    try {
      return await api.get<StatData>('/user/stats')
    } catch {
      return null
    }
  }

  /** 从后端获取最近学习记录 */
  async function fetchRecentSessions(): Promise<Session[]> {
    try {
      const data = await api.get<Session[]>('/user/recent-sessions')
      if (data && data.length >= 3) return data
      // 后端数据不足时，用种子数据填充
      return getFallbackSessions()
    } catch {
      return getFallbackSessions()
    }
  }

  /** 从后端获取推荐任务 */
  async function fetchRecommendedTasks(): Promise<Task[]> {
    try {
      const data = await api.get<Task[]>('/user/recommended-tasks')
      if (data && data.length >= 3) return data
      return getFallbackTasks()
    } catch {
      return getFallbackTasks()
    }
  }

  /** 最近学习数据（API失败时返回空） */
  function getFallbackSessions(): Session[] {
    return []
  }

  /** 推荐任务数据（API失败时返回空） */
  function getFallbackTasks(): Task[] {
    return []
  }

  /** 后端科目列表（同时写入 subjects ref 供全局使用） */
  async function fetchSubjects(): Promise<SubjectsMap> {
    try {
      const data = await api.get<any>('/subjects')
      // API 返回 { subjects: { overview: { name, chapters }, ... } }
      const map = (data && data.subjects) ? data.subjects : data
      subjects.value = map
      return map
    } catch {
      return {}
    }
  }

  /** 获取掌握度数据 */
  async function fetchMasteryData(): Promise<MasteryItem[]> {
    try {
      return await api.get<MasteryItem[]>('/user/mastery')
    } catch {
      return []
    }
}

  /** 获取知识图谱 */
  async function fetchKnowledgeGraph(subject: string): Promise<KnowledgeGraphData> {
    try {
      const result = await api.post<KnowledgeGraphData>('/knowledge/graph', { subject })
      // 成就追踪
      try { useAchievementStore().recordKnowledgeBrowse() } catch { /* */ }
      return result
    } catch {
      return { nodes: [], edges: [] }
    }
  }

/** 获取学习评估 */
  async function fetchAssessment(quizHistory: { subject: string; correct: boolean }[]): Promise<AssessmentResult | null> {
    return await api.post<AssessmentResult>('/assessment', {
      quiz_history: quizHistory,
      profile: studentProfile.value,
    })
  }

/** 生成题目 */
  async function generateQuestions(subject: string, chapter: string, type: string, difficulty: string) {
    const result = await api.post<any>('/rag/generate', {
      subject, chapter, question_type: type, difficulty, count: 10,
    })
    // 如果选定科目无题目，自动轮询所有可用科目合并结果
    if ((!result || !result.questions || result.questions.length === 0) && subject) {
      const allResults: any[] = []
      for (const [key] of Object.entries(subjects.value)) {
        if (key === subject) continue
        try {
          const r = await api.post<any>('/rag/generate', {
            subject: key, chapter: '', question_type: type, difficulty, count: 3,
          })
          if (r && r.questions && r.questions.length > 0) {
            allResults.push(...r.questions)
          }
        } catch { /* skip */ }
        if (allResults.length >= 5) break
      }
      if (allResults.length > 0) {
        return { questions: allResults.slice(0, 5), message: '已自动匹配其他章节的题目' }
      }
    }
    return result
  }

/** 提交答题 */
  async function submitQuiz(records: any) {
    try {
      const result = await api.post<any>('/quiz/submit', {
        profile: studentProfile.value || {},
        records,
      })
      // 成就追踪：记录答题
      try {
        const achStore = useAchievementStore()
        if (Array.isArray(records)) {
          for (const r of records) {
            achStore.recordQuiz(r.correct ?? false, r.subject)
          }
        } else if (records && typeof records === 'object') {
          achStore.recordQuiz(records.correct ?? false, records.subject)
        }
        achStore.recordStreak()
      } catch { /* 成就追踪不影响主流程 */ }
      return result
    } catch {
      return null
    }
  }

  return {
// auth
    currentUser, isAdmin, token,
    login, register, logout,
    // profile
    studentProfile, profileCompleted,
    loadProfile, saveProfile, clearProfile,
    // subjects
    subjects, courses,
    // data (兜底默认值)
    data,
    daysToExam,
    // modes
    thinkingMode, agentMode,
    // conversations
    conversations, currentConversationId,
    createConversation, deleteConversation,
    getCurrentConversation, getConversationById,
    switchToConversation, searchConversations,
    sendMessageStream, saveConversations, askImage, askTutor,
    // api
    fetchStats, fetchRecentSessions, fetchRecommendedTasks,
    fetchSubjects, fetchMasteryData, fetchKnowledgeGraph,
    fetchAssessment, generateQuestions, submitQuiz,
  }
})
