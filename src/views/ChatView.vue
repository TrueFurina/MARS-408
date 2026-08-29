<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, shallowReactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useStudyStore } from '@/stores/studyStore'
import ChatInput from '@/components/ChatInput.vue'
import EmptyState from '@/components/EmptyState.vue'
import { icons } from '@/components/icons'
import { api } from '@/utils/api'
import { renderMarkdownSafe, sanitizeSvg } from '@/utils/markdown'
import { ttsSynthesize } from '@/utils/api'
import { useVirtualizer, type Virtualizer } from '@tanstack/vue-virtual'
import VideoPlayer from '@/components/VideoPlayer.vue'

const route = useRoute()
const router = useRouter()
const store = useStudyStore()
const suggestedPrompts = [
  '根据我的薄弱点，帮我定制本周的 408 四科复习计划',
  '用思维导图帮我梳理操作系统「进程调度」的知识脉络',
  '出 5 道数据结构算法题，按我的错题难度逐题讲解',
  '用生活化的比喻讲清楚 TCP 三次握手和四次挥手的区别',
]
const isLoading = ref(false)
// 发送失败提示：避免「发不出却无反馈」的静默失败（BugFix：原 catch {} 吞掉错误）
const sendError = ref<string | null>(null)
const messagesRef = ref<HTMLElement | null>(null)
const chatInputRef = ref<InstanceType<typeof ChatInput> | null>(null)
const showScrollBtn = ref(false)
const collapsedReasons = shallowReactive(new Set<string>())

// 当前用户（store.currentUser 未暴露到类型，从 auth 派生，等价实现）
const currentUser = computed(() => store.currentUser)

// ── 教学视频播放 ──
const showTeachingVideo = ref(false)
const teachingVideoHtml = ref<string | null>(null)
const teachingVideoTopic = ref('')

// ── 画像在对话中可见 ──
const showProfile = ref(false)
const profileLevelLabel = computed(() => {
  const p = store.studentProfile
  if (!p?.knowledge_base) return '未评估'
  const labels: Record<string, string> = { none: '零基础', beginner: '入门', intermediate: '进阶', advanced: '精通' }
  return labels[p.knowledge_base] || p.knowledge_base
})
const profileWeakCount = computed(() => {
  const wp = store.studentProfile?.weak_points
  if (!wp) return 0
  return wp.split(/[,，、]/).filter(Boolean).length
})

// ── 多模态导师答疑模式（功能④）──
const tutorMode = ref(false)

// ── TTS 语音朗读 ──
const speakingId = ref<string | null>(null)
const audioRef = ref<HTMLAudioElement | null>(null)
const ttsSpeed = ref(1.0)
const ttsLanguage = ref('zh')
const speakingLock = ref(false)  // 防连点锁

/** 简单检测文本语言 */
function detectLanguage(text: string): string {
  const cnRatio = (text.match(/[\u4e00-\u9fff]/g) || []).length / text.length
  const enRatio = (text.match(/[a-zA-Z]/g) || []).length / text.length
  const jaRatio = (text.match(/[\u3040-\u309f\u30a0-\u30ff]/g) || []).length / text.length
  const krRatio = (text.match(/[\uac00-\ud7af]/g) || []).length / text.length
  if (jaRatio > 0.1) return 'ja'
  if (krRatio > 0.1) return 'ko'
  if (cnRatio > 0.3) return 'zh'
  if (enRatio > 0.5) return 'en'
  return 'zh'
}

async function speakMessage(msgId: string, text: string, language?: string) {
  // 防连点锁：已有语音在播放或请求中时忽略本次点击
  if (speakingLock.value) return
  speakingLock.value = true
  // 自动检测语言
  const lang = language || detectLanguage(text)
  ttsLanguage.value = lang
  // 如果正在播放同一段，切换播放/暂停
  if (speakingId.value === msgId && audioRef.value) {
    if (!audioRef.value.paused) {
      audioRef.value.pause()
      speakingLock.value = false
      return
    }
    audioRef.value.play().catch(() => {})
    speakingLock.value = false
    return
  }
  // 停止之前的播放
  if (audioRef.value) {
    audioRef.value.pause()
    audioRef.value = null
  }
  try {
    // 用 Promise.race 实现超时控制，防止 TTS 卡死
    const blob = await Promise.race([
      ttsSynthesize(text, lang, 'auto'),
      new Promise<null>((_, reject) =>
        setTimeout(() => reject(new Error('TTS 超时')), 30000)
      ),
    ])
    if (!blob) {
      // 后端 TTS 失败，降级到浏览器 SpeechSynthesis
      fallbackSpeak(text, lang)
      speakingLock.value = false
      return
    }
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    audio.playbackRate = ttsSpeed.value
    audioRef.value = audio
    speakingId.value = msgId
    audio.onended = () => {
      speakingId.value = null
      URL.revokeObjectURL(url)
      audioRef.value = null
      speakingLock.value = false
    }
    audio.onerror = () => {
      speakingId.value = null
      URL.revokeObjectURL(url)
      audioRef.value = null
      speakingLock.value = false
    }
    await audio.play()
    speakingLock.value = false
  } catch {
    // TTS 失败，降级到浏览器 SpeechSynthesis
    fallbackSpeak(text, lang)
    speakingId.value = null
    speakingLock.value = false
  }
}

/** 浏览器 SpeechSynthesis 降级方案 */
function fallbackSpeak(text: string, lang: string = 'zh') {
  if (!window.speechSynthesis) return
  window.speechSynthesis.cancel()
  const utter = new SpeechSynthesisUtterance(text)
  utter.lang = lang === 'zh' ? 'zh-CN' : 'en-US'
  utter.rate = ttsSpeed.value
  utter.onend = () => { speakingId.value = null }
  utter.onerror = () => { speakingId.value = null }
  speakingId.value = 'browser-tts'
  window.speechSynthesis.speak(utter)
}

/** 提取消息中可朗读的文本（去除 markdown 标记、代码块等） */
function getSpeakableText(msg: { role: string; content?: string; segments?: Array<{ type: string; content?: string }> }): string | null {
  if (msg.role !== 'assistant') return null
  // 优先取 segments 中的 content 片段
  if (msg.segments && msg.segments.length > 0) {
    const parts = msg.segments
      .filter(s => s.type === 'content' && s.content)
      .map(s => s.content!.replace(/```[\s\S]*?```/g, '')  // 移除代码块
        .replace(/[#*`~[\]()>|]/g, '')  // 移除 markdown 标记
        .replace(/\n{3,}/g, '\n\n')
        .trim())
      .filter(Boolean)
    if (parts.length > 0) return parts.join('。')
  }
  // 降级使用 content
  if (msg.content) {
    return msg.content.replace(/```[\s\S]*?```/g, '')
      .replace(/[#*`~[\]()>|]/g, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim()
  }
  return null
}

// ── 虚拟滚动 ──
const virtualizer = ref<Virtualizer<HTMLElement, HTMLElement> | null>(null)
onMounted(() => {
  virtualizer.value = useVirtualizer(
    computed(() => ({
      count: currentMessages.value.length,
      getScrollElement: () => messagesRef.value,
      estimateSize: () => 120,
      overscan: 10,
      // 动态测量实际元素高度，避免固定 80px 导致布局抖动
      measureElement: (el: HTMLElement) => {
        const h = el.getBoundingClientRect().height
        return h > 0 ? h : 120
      },
    }))
  ).value
})

// 讯飞图片理解：待发送图片（base64）+ 文件名
const pendingImage = ref<string | null>(null)
const pendingImageName = ref('')

function onImageSelected(file: File) {
  const reader = new FileReader()
  reader.onload = () => {
    pendingImage.value = reader.result as string
    pendingImageName.value = file.name
  }
  reader.readAsDataURL(file)
}

function clearPendingImage() {
  pendingImage.value = null
  pendingImageName.value = ''
}

const currentMessages = computed(() => {
  const conv = store.getCurrentConversation()
  return conv?.messages || []
})

// 对话历史侧栏状态（v8 补充：模板引用但未声明，导致 vue-tsc 报错）
const sidebarOpen = ref(false)
const conversations = computed(() => store.conversations)
const currentConvId = computed(() => store.currentConversationId ?? null)

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

function selectConversation(id: string) {
  if (store.switchToConversation(id)) router.push('/c/' + id)
}

function removeConversation(id: string, e?: Event) {
  e?.stopPropagation?.()
  if (window.confirm('确定删除该对话？')) store.deleteConversation(id)
}

// 路由参数 → store
watch(() => route.params.convId, (convId) => {
  if (convId && typeof convId === 'string') {
    if (!store.switchToConversation(convId)) router.replace('/')
  }
})

// 技能参数 → 初始化对话时使用技能的 system prompt
const skillInfo = ref<{ name: string; icon: string } | null>(null)
const memoryOverview = ref<any>(null)
onMounted(async () => {
  loadMemoryOverview()
  const skillId = route.query.skill as string
  if (skillId) {
    try {
      const res: any = await api.get(`/skills/get/${skillId}`)
      if (res?.skill) {
        skillInfo.value = { name: res.skill.name, icon: res.skill.icon }
        // 在第一条消息中提示用户
        const msg = `🧠 当前使用技能: ${res.skill.icon} ${res.skill.name}\n\n请输入你的问题，此技能将使用自定义配置回答。`
        const conv = store.getCurrentConversation()
        if (conv) {
          conv.messages.push({ role: 'assistant', content: msg, id: Date.now().toString(), segments: [], timestamp: new Date() })
        }
      }
    } catch (e: any) {
      console.warn('加载技能信息失败:', e?.message)
    }
  }
})

// L1/L2/L3 三层学情记忆（低侵入联动：对话页展示记忆上下文提示，失败不影响主流程）
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞对话页 */ }
}

async function sendMessage(text: string) {
  if (isLoading.value) return
  isLoading.value = true
  try {
    // 检测视频生成指令
    const videoCmd = text.match(/^(生成|制作|创建)\s*(教学)?\s*视频[:：]?\s*(.+)?$/i)
    if (videoCmd) {
      const topic = videoCmd[3]?.trim() || text.replace(/^(生成|制作|创建)\s*(教学)?\s*视频[:：]?\s*/i, '').trim() || '计算机408知识点'
      await store.sendMessageStream(`📺 正在生成「${topic}」的教学视频...`, () => { scrollToBottom() })
      try {
        const res: any = await api.post('/multimodal/generate-teaching-video', { topic, difficulty: 'medium', output_format: 'html' })
        if (res?.html) {
          teachingVideoHtml.value = res.html
          teachingVideoTopic.value = topic
          showTeachingVideo.value = true
        }
      } catch (e: any) {
        await store.sendMessageStream(`❌ 视频生成失败: ${e?.message || '未知错误'}`, () => { scrollToBottom() })
      }
      const conv = store.getCurrentConversation()
      if (conv && conv.messages.length > 0 && !route.params.convId) {
        router.replace('/c/' + conv.id)
      }
      return
    }
    // 带图片 → 走讯飞图片理解
    if (pendingImage.value) {
      const img = pendingImage.value
      const q = text
      clearPendingImage()
      await store.askImage(img, q)
      const conv = store.getCurrentConversation()
      if (conv && conv.messages.length > 0 && !route.params.convId) {
        router.replace('/c/' + conv.id)
      }
    } else if (tutorMode.value) {
      // 多模态导师答疑模式（功能④：/tutor/enhanced-answer）
      await store.askTutor(text)
      const conv = store.getCurrentConversation()
      if (conv && conv.messages.length > 0 && !route.params.convId) {
        router.replace('/c/' + conv.id)
      }
    } else {
      await store.sendMessageStream(text, () => { scrollToBottom() })
      const conv = store.getCurrentConversation()
      if (conv && conv.messages.length > 0 && !route.params.convId) {
        router.replace('/c/' + conv.id)
      }
    }
  } catch (e: any) {
    // BugFix：原 catch {} 静默吞掉异常，导致「发不出消息却无任何反馈」。
    // 现在将错误打到控制台并展示给用户，便于定位（后端恢复后此处自然恢复）。
    console.error('[ChatView] 发送消息失败:', e)
    sendError.value = e?.message || '消息发送失败，请稍后重试'
  } finally {
    isLoading.value = false
    scrollToBottom()
  }
}

function scrollToBottom() {
  showScrollBtn.value = false
  const len = currentMessages.value.length
  if (len > 0 && virtualizer.value) {
    virtualizer.value.scrollToIndex(len - 1, { align: 'end' })
  }
}

function newConversation() { store.createConversation(); router.push('/') }

function onScroll() {
  const el = messagesRef.value
  if (!el) return
  showScrollBtn.value = el.scrollHeight - el.scrollTop - el.clientHeight > 300
}

// 虚拟滚动时同步滚动按钮状态（防抖避免布局抖动）
let scrollThrottleTimer: ReturnType<typeof setTimeout> | null = null
watch(() => virtualizer.value?.scrollOffset, () => {
  if (scrollThrottleTimer) return
  scrollThrottleTimer = setTimeout(() => {
    scrollThrottleTimer = null
    onScroll()
  }, 100)
})

// 滚动到底部时自动滚动（仅新消息追加时触发，不深度监听）
watch(currentMessages, () => {
  if (!showScrollBtn.value) {
    setTimeout(scrollToBottom, 50)
  }
})

function toggleReason(msgId: string) {
  if (collapsedReasons.has(msgId)) collapsedReasons.delete(msgId)
  else collapsedReasons.add(msgId)
}

function truncateStr(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) + '…' : s
}
function onImgError(e: Event) {
  (e.target as HTMLElement).style.display = 'none'
}

// 代码块复制/下载
function onCodeAction(e: MouseEvent) {
  const btn = (e.target as HTMLElement).closest('.code-action-btn') as HTMLElement
  if (!btn) return
  const action = btn.dataset.action
  const code = btn.dataset.code || ''
  if (action === 'copy') {
    navigator.clipboard.writeText(code).then(() => {
      btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>'
      setTimeout(() => {
        btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
      }, 1000)
    }).catch(() => {})
  } else if (action === 'download') {
    const lang = btn.dataset.lang || 'txt'
    const b = new Blob([code], { type: 'text/plain' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(b)
    a.download = 'code.' + lang
    a.click()
    URL.revokeObjectURL(a.href)
  }
}

onMounted(() => {
  const convId = route.params.convId
  if (convId && typeof convId === 'string') {
    if (!store.switchToConversation(convId)) router.replace('/')
  } else {
    // 有历史对话则恢复最新一条，否则才新建
    const existing = store.conversations
    if (existing && existing.length > 0) {
      store.switchToConversation(existing[0]!.id)
    } else {
      store.createConversation()
    }
  }
  document.addEventListener('click', onCodeAction)
  setTimeout(() => chatInputRef.value?.focusInput(), 300)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onCodeAction)
})
</script>

<template>
  <div class="chat-layout">
    <aside class="chat-sidebar" :class="{ collapsed: !sidebarOpen }">
      <div class="sidebar-header">
        <button class="new-chat-btn" @click="newConversation">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
          新对话
        </button>
        <span class="xfyun-badge" title="本对话由讯飞星火 X2 大模型驱动">
          <span v-html="icons.sparkle" class="xfyun-badge-icon"></span>讯飞星火 X2
        </span>
        <button class="sidebar-toggle" @click="toggleSidebar" title="收起侧边栏">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M15 18l-6-6 6-6"/></svg>
        </button>
      </div>
      <div class="sidebar-conversations">
        <div v-for="conv in conversations" :key="conv.id"
             class="sidebar-conv-item"
             :class="{ active: conv.id === currentConvId }"
             @click="selectConversation(conv.id)">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          <span class="conv-title">{{ conv.title || '新对话' }}</span>
          <button class="conv-delete" @click="removeConversation(conv.id, $event)" title="删除对话">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </div>
        <EmptyState v-if="conversations.length === 0" :icon="icons.chat" title="暂无对话记录" description="开始一次 408 问答，对话会保存在这里" />
      </div>
    </aside>
    <div class="chat-main">
      <button v-if="!sidebarOpen" class="chat-menu-btn" @click="toggleSidebar" title="展开侧边栏">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 12h18M3 6h18M3 18h18"/></svg>
      </button>
      <!-- 画像快捷入口 -->
      <div class="chat-profile-bar">
        <button v-if="currentUser" class="chat-profile-btn" @click="showProfile = true" title="查看学生画像">
          <span class="cpb-avatar">🧑</span>
          <span class="cpb-level">{{ profileLevelLabel }}</span>
          <span class="cpb-weak" v-if="profileWeakCount > 0">{{ profileWeakCount }} 个薄弱点</span>
        </button>
        <button v-if="memoryOverview" class="chat-memory-btn" @click="router.push('/memory')" title="查看学情记忆中心">
          <span>🧠</span>
          <span class="cpb-weak" v-if="memoryOverview.weak_points?.length">{{ memoryOverview.weak_points.length }} 个记忆薄弱点</span>
        </button>
        <button v-if="skillInfo" class="chat-skill-badge" @click="router.push(`/skills/${route.query.skill}`)">
          {{ skillInfo.icon }} {{ skillInfo.name }}
        </button>
      </div>
      <div ref="messagesRef" class="chat-messages" @scroll="onScroll">
      <div v-if="currentMessages.length === 0" class="chat-greeting">
        <div class="greeting-icon" v-html="icons.chat"></div>
        <h1>408考研智能学习助手</h1>
        <p>输入你想学的408知识点，我来帮你讲解、分析和练习</p>
        <div class="greeting-powered">由 <strong>讯飞星火 X2</strong> 大模型驱动 · 融合 10 项讯飞开放平台能力</div>
        <div class="greeting-chips">
          <button v-for="q in suggestedPrompts" :key="q" class="greeting-chip" type="button" @click="sendMessage(q)">{{ q }}</button>
        </div>
      </div>

      <div v-else class="chat-messages-inner" :style="{ height: virtualizer ? `${virtualizer.getTotalSize()}px` : 'auto' }">
        <div v-for="vItem in virtualizer?.getVirtualItems() ?? []" :key="vItem.index"
             class="message" :class="currentMessages[vItem.index]!.role"
             :style="{ transform: `translateY(${vItem.start}px)` }">
          <template v-if="currentMessages[vItem.index]!.role === 'user'">
            <div class="message-avatar" v-html="icons.user"></div>
            <div class="message-bubble">
              <img v-if="currentMessages[vItem.index]!.imageBase64" :src="currentMessages[vItem.index]!.imageBase64" class="user-image" alt="上传图片" />
              <!-- 用户消息：纯文本插值，杜绝 v-html 自 XSS；white-space 保留换行 -->
              <div class="message-text" style="white-space: pre-line">{{ currentMessages[vItem.index]!.content }}</div>
            </div>
          </template>
          <template v-else>
            <div class="message-avatar" v-html="icons.sparkle"></div>
            <div class="message-bubble">
              <!-- 按时间顺序渲染 segments -->
              <template v-for="(seg, si) in currentMessages[vItem.index]!.segments" :key="si">
                <!-- 非 content 片段（thinking、tool_call）统一为弱化的卡片 -->
                <div v-if="seg.type !== 'content'" class="meta-card" :class="{ collapsed: collapsedReasons.has(currentMessages[vItem.index]!.id + '-' + si) }">
                  <div class="meta-card-header" role="button" tabindex="0" @click.stop="toggleReason(currentMessages[vItem.index]!.id + '-' + si)" @keydown.enter.stop="toggleReason(currentMessages[vItem.index]!.id + '-' + si)" @keydown.space.prevent.stop="toggleReason(currentMessages[vItem.index]!.id + '-' + si)">
                    <span class="meta-card-label">{{ seg.type === 'reasoning' ? '💭 Thinking' : '🔧 ' + seg.toolName }}</span>
                    <span v-if="seg.duration" class="meta-card-duration">{{ (seg.duration / 1000).toFixed(1) }}s</span>
                    <svg width="12" height="12" viewBox="0 0 14 14" fill="none"><path d="M11.8486 5.5L11.4238 5.92383L8.69727 8.65137C8.44157 8.90706 8.21562 9.13382 8.01172 9.29785C7.79912 9.46883 7.55595 9.61756 7.25 9.66602C7.08435 9.69222 6.91565 9.69222 6.75 9.66602C6.44405 9.61756 6.20088 9.46883 5.98828 9.29785C5.78438 9.13382 5.55843 8.90706 5.30273 8.65137L2.57617 5.92383L2.15137 5.5L3 4.65137L3.42383 5.07617L6.15137 7.80273C6.42595 8.07732 6.59876 8.24849 6.74023 8.3623C6.87291 8.46904 6.92272 8.47813 6.9375 8.48047C6.97895 8.48703 7.02105 8.48703 7.0625 8.48047C7.07728 8.47813 7.12709 8.46904 7.25977 8.3623C7.40124 8.24849 7.57405 8.07732 7.84863 7.80273L10.5762 5.07617L11 4.65137L11.8486 5.5Z" fill="currentColor"/></svg>
                  </div>
                  <div v-if="!collapsedReasons.has(currentMessages[vItem.index]!.id + '-' + si)" class="meta-card-body">
                    <div v-if="seg.type === 'reasoning'" class="markdown-body" v-html="renderMarkdownSafe(seg.content || '')"></div>
                    <div v-if="seg.type === 'tool_call'" class="tool-args">{{ truncateStr(seg.toolArgs || '', 200) }}</div>
                  </div>
                </div>

                <!-- content 片段：用户主要看的内容 -->
                <div v-if="seg.type === 'content' && seg.content" class="markdown-body" v-html="renderMarkdownSafe(seg.content)"></div>
                <span class="stream-cursor" v-if="seg.type === 'content' && isLoading && vItem.index === currentMessages.length - 1 && si === currentMessages[vItem.index]!.segments.length - 1"></span>
              </template>

              <div v-if="currentMessages[vItem.index]!.segments.length === 0 && !currentMessages[vItem.index]!.content" class="typing-indicator"><span></span><span></span><span></span></div>

              <!-- 导师答疑：SVG 图解（功能④多模态） -->
              <div v-if="currentMessages[vItem.index]!.svgDiagram" class="tutor-media-block tutor-svg-block">
                <div class="tutor-media-label"><span v-html="icons.chart" class="tutor-media-icon"></span> SVG 图解</div>
                <div class="tutor-svg-container" v-html="sanitizeSvg(currentMessages[vItem.index]!.svgDiagram!)"></div>
              </div>
              <!-- 导师答疑：短视频脚本（功能④多模态） -->
              <div v-if="currentMessages[vItem.index]!.videoScript" class="tutor-media-block tutor-video-block">
                <div class="tutor-media-label"><span v-html="icons.play" class="tutor-media-icon"></span> 短视频脚本</div>
                <div class="tutor-video-content markdown-body" v-html="renderMarkdownSafe(currentMessages[vItem.index]!.videoScript!)"></div>
              </div>

              <!-- 语音朗读按钮 -->
              <div class="tts-controls" v-if="getSpeakableText(currentMessages[vItem.index]!)">
                <button class="speak-btn"
                        :class="{ speaking: speakingId === currentMessages[vItem.index]!.id }"
                        :title="speakingId === currentMessages[vItem.index]!.id ? '暂停' : '朗读'"
                        @click="speakMessage(currentMessages[vItem.index]!.id, getSpeakableText(currentMessages[vItem.index]!)!)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polygon v-if="speakingId === currentMessages[vItem.index]!.id" points="6 4 18 4 18 20 6 20"/>
                    <template v-else>
                      <path d="M11 5L6 9H2v6h4l5 4V5z"/>
                      <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>
                    </template>
                  </svg>
                </button>
                <select class="tts-speed-select" v-model="ttsSpeed" @click.stop title="语速">
                  <option :value="0.5">0.5x</option>
                  <option :value="0.75">0.75x</option>
                  <option :value="1.0">1x</option>
                  <option :value="1.25">1.25x</option>
                  <option :value="1.5">1.5x</option>
                  <option :value="2.0">2x</option>
                </select>
              </div>
              <!-- 快捷操作按钮 -->
              <div class="quick-actions" v-if="currentMessages[vItem.index]!.role === 'assistant' && getSpeakableText(currentMessages[vItem.index]!)">
                <button class="qa-btn" @click="router.push('/practice')" title="做一道相关练习题">📝 做练习题</button>
                <button class="qa-btn" @click="router.push('/resource')" title="生成相关学习资源">🤖 生成资源</button>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <button v-if="showScrollBtn" class="scroll-bottom-btn" aria-label="滚动到底部" @click="scrollToBottom">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M11.8486 5.5L11.4238 5.92383L8.69727 8.65137C8.44157 8.90706 8.21562 9.13382 8.01172 9.29785C7.79912 9.46883 7.55595 9.61756 7.25 9.66602C7.08435 9.69222 6.91565 9.69222 6.75 9.66602C6.44405 9.61756 6.20088 9.46883 5.98828 9.29785C5.78438 9.13382 5.55843 8.90706 5.30273 8.65137L2.57617 5.92383L2.15137 5.5L3 4.65137L3.42383 5.07617L6.15137 7.80273C6.42595 8.07732 6.59876 8.24849 6.74023 8.3623C6.87291 8.46904 6.92272 8.47813 6.9375 8.48047C6.97895 8.48703 7.02105 8.48703 7.0625 8.48047C7.07728 8.47813 7.12709 8.46904 7.25977 8.3623C7.40124 8.24849 7.57405 8.07732 7.84863 7.80273L10.5762 5.07617L11 4.65137L11.8486 5.5Z" fill="currentColor"/></svg>
    </button>

    <div class="chat-input-area">
      <div v-if="pendingImage" class="image-preview-chip">
        <img :src="pendingImage" alt="预览" />
        <span class="image-preview-name">{{ pendingImageName || '图片' }}</span>
        <button class="image-preview-remove" @click="clearPendingImage" title="移除图片">✕</button>
        <span class="image-preview-hint">将使用讯飞图片理解回答你的问题</span>
      </div>
      <div class="chat-mode-bar">
        <button class="mode-toggle" :class="{ active: tutorMode, 'mode-tutor': tutorMode }" @click="tutorMode = !tutorMode" :title="tutorMode ? '切换为普通对话' : '切换为多模态导师答疑'">
          <span v-html="icons.sparkle" class="mode-toggle-icon"></span>
          {{ tutorMode ? '多模态导师答疑' : '普通对话' }}
        </button>
        <span v-if="tutorMode" class="mode-hint">提问将获得 文字解答 + SVG图解 + 短视频脚本 的多模态答疑</span>
      </div>
      <div v-if="sendError" class="chat-send-error" role="button" tabindex="0" aria-label="关闭错误提示" @click="sendError = null" @keydown.enter="sendError = null" title="点击关闭">
        ⚠️ {{ sendError }}
      </div>
      <div class="chat-input-wrapper">
        <ChatInput ref="chatInputRef" :disabled="isLoading" @send="sendMessage" @image="onImageSelected" />
      </div>
    </div>
    </div>
  </div>
  <!-- 教学视频播放器 -->
  <VideoPlayer
    v-if="showTeachingVideo && teachingVideoHtml"
    :html="teachingVideoHtml"
    :title="teachingVideoTopic + ' - 教学视频'"
    @close="showTeachingVideo = false"
  />
</template>

<style scoped>
/* ── 侧边栏 ── */
.chat-layout { display: flex; height:100vh; width:100%; position: relative; }
.chat-sidebar { width: 280px; min-width: 280px; display: flex; flex-direction: column; background: var(--glass-bg); backdrop-filter: blur(var(--glass-blur)); -webkit-backdrop-filter: blur(var(--glass-blur)); border-right: 1px solid var(--glass-border); transition: all 0.25s ease; overflow: hidden; }
.chat-sidebar.collapsed { width:0; min-width:0; border-right: none; }
.sidebar-header { display: flex; align-items: center; gap:0.375rem; padding:0.75rem; border-bottom: 1px solid var(--glass-border); }
.xfyun-badge { display:inline-flex; align-items:center; gap:0.25rem; margin-left:auto; padding:0.1875rem 0.5rem; font-size:0.6875rem; font-weight:600; line-height:1; color:var(--accent-primary); background:var(--accent-primary-10); border:1px solid var(--accent-primary-20); border-radius:999px; white-space:nowrap; }
.xfyun-badge-icon { display:inline-flex; }
.xfyun-badge-icon :deep(svg) { width:12px; height:12px; }
.greeting-powered { margin-top:0.625rem; font-size:0.8125rem; color:var(--text-muted); }
.greeting-powered strong { color:var(--accent-primary); font-weight:600; }
.new-chat-btn { flex: 1; display: flex; align-items: center; gap:0.375rem; padding:0.5rem 0.75rem; border-radius:var(--radius-sm); border: 1px solid var(--glass-border); background: var(--glass-bg); color: var(--text-primary); cursor: pointer; font-size:0.8125rem; transition: var(--transition); }
.new-chat-btn:hover { background: var(--bg-card-hover); border-color: var(--accent-primary); color: var(--accent-primary); }
.sidebar-toggle { width:2rem; height:2rem; display: flex; align-items: center; justify-content: center; border-radius:var(--radius-sm); border: none; background: transparent; color: var(--text-muted); cursor: pointer; transition: var(--transition); flex-shrink: 0; }
.sidebar-toggle:hover { background: var(--bg-card-hover); color: var(--text-primary); }
.sidebar-conversations { flex: 1; overflow-y: auto; padding:0.375rem; }
.sidebar-conv-item { display: flex; align-items: center; gap:0.5rem; padding:0.625rem; border-radius:var(--radius-sm); cursor: pointer; transition: var(--transition); font-size:0.8125rem; color: var(--text-secondary); }
.sidebar-conv-item:hover { background: var(--bg-card-hover); color: var(--text-primary); }
.sidebar-conv-item.active { background: var(--accent-primary); color: var(--text-user); }
.conv-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conv-delete { width:1.5rem; height:1.5rem; display: flex; align-items: center; justify-content: center; border-radius:0.25rem; border: none; background: transparent; color: var(--text-muted); cursor: pointer; opacity: 0; transition: var(--transition); flex-shrink: 0; }
.sidebar-conv-item:hover .conv-delete { opacity: 1; }
.conv-delete:hover { background: var(--accent-danger-20); color: var(--accent-danger); }
.sidebar-empty { text-align: center; padding:2.5rem 0.75rem; color: var(--text-muted); font-size:0.8125rem; }
.chat-main { flex: 1; display: flex; flex-direction: column; position: relative; min-width:0; }
.chat-menu-btn { position: absolute; top: 12px; left: 12px; z-index: 10; width: 2.75rem; height: 2.75rem; display: flex; align-items: center; justify-content: center; border-radius: var(--radius-sm); border: 1px solid var(--glass-border); background: var(--glass-bg); backdrop-filter: blur(var(--glass-blur)); -webkit-backdrop-filter: blur(var(--glass-blur)); color: var(--text-secondary); cursor: pointer; transition: var(--transition); }
.chat-menu-btn:hover { background: var(--bg-card-hover); color: var(--accent-primary); }

.meta-card { border: 1px solid var(--glass-border); border-radius: var(--radius-sm); margin-bottom: 0.25rem; background: var(--glass-bg); backdrop-filter: blur(var(--glass-blur)); -webkit-backdrop-filter: blur(var(--glass-blur)); overflow: hidden; }
.meta-card-header { display: flex; align-items: center; gap:0.375rem; padding:0.25rem 0.625rem; background: var(--color-surface); cursor: pointer; user-select: none; transition: var(--transition); font-size:0.75rem; color: var(--text-muted); }
.meta-card-header:hover { background: var(--bg-card-hover); }
.meta-card-label { font-weight: 500; display: flex; align-items: center; gap:0.25rem; }
.meta-card-duration { margin-left:auto; font-weight: 400; font-size:0.6875rem; opacity: 0.6; white-space: nowrap; }
.meta-card-body { font-size:0.75rem; color: var(--text-muted); padding:0.375rem 0.625rem; line-height:1.5; opacity: 0.8; max-height:18.75rem; overflow-y: auto; }
.tool-args { font-family: var(--font-mono); font-size:0.6875rem; word-break: break-all; }
.scroll-bottom-btn { position: absolute; bottom: 100%; right: 20px; margin-bottom: 8px; z-index: 50; width: 2.75rem; height: 2.75rem; border-radius: 50%; background: var(--glass-bg); backdrop-filter: blur(var(--glass-blur)); -webkit-backdrop-filter: blur(var(--glass-blur)); color: var(--text-secondary); border: 1px solid var(--glass-border); display: flex; align-items: center; justify-content: center; cursor: pointer; box-shadow: var(--shadow-md), var(--glow-primary); transition: var(--transition); animation: btn-in 0.2s ease; }
.scroll-bottom-btn:hover { background: var(--glass-bg-hover); color: var(--accent-primary); box-shadow: var(--shadow-card-hover), var(--glow-primary-strong); }
@keyframes btn-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

/* ── 用户上传图片 & 待发送预览 ── */
.user-image {
  max-width:13.75rem;
  max-height:13.75rem;
  border-radius:var(--radius-sm);
  margin-bottom:0.375rem;
  display: block;
  border: 1px solid var(--glass-border);
}
.image-preview-chip {
  display: flex;
  align-items: center;
  gap:0.625rem;
  padding:0.5rem 0.75rem;
  margin-bottom:0.5rem;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  border-radius:var(--radius-md);
  font-size:0.75rem;
  color: var(--text-secondary);
}
.image-preview-chip img {
  width:2.5rem; height:2.5rem; object-fit: cover; border-radius:var(--radius-sm);
  flex-shrink: 0;
}
.image-preview-name { font-weight: 500; color: var(--text-primary); max-width:10rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.image-preview-remove {
  width:1.375rem; height:1.375rem; border-radius:50%; border: none; cursor: pointer;
  background: var(--accent-danger-20); color: var(--accent-danger); font-size:0.75rem; flex-shrink: 0;
}
.image-preview-remove:hover { background: var(--accent-danger-20); }
.image-preview-hint { color: var(--text-muted); margin-left:auto; }

/* ── 语音朗读按钮 ── */
.speak-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width:1.75rem; height:1.75rem; border-radius:50%; border: none;
  background: transparent; color: var(--text-muted); cursor: pointer;
  transition: var(--transition); margin-top:0.25rem; flex-shrink: 0;
}
.speak-btn:hover { background: var(--bg-card-hover); color: var(--accent-primary); }
.speak-btn.speaking { color: var(--accent-primary); background: var(--accent-primary-20); animation: speak-pulse 1.5s ease-in-out infinite; }
@keyframes speak-pulse {
  0%, 100% { box-shadow: 0 0 0 0 var(--accent-primary-30); }
  50% { box-shadow: 0 0 0 6px transparent; }

/* ── 快捷操作按钮 ── */
.quick-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.qa-btn {
  padding: 4px 12px; border-radius: 6px; border: 1px solid var(--glass-border);
  background: var(--glass-bg); color: var(--text-secondary); cursor: pointer;
  font-size: 12px; transition: var(--transition); white-space: nowrap;
}
.qa-btn:hover { background: var(--bg-card-hover); color: var(--accent-primary); border-color: var(--accent-primary); }
}

/* ── TTS 语速选择 ── */
.tts-controls { display: inline-flex; align-items: center; gap:0.25rem; margin-top:0.25rem; }
.tts-speed-select {
  appearance: none; -webkit-appearance: none;
  padding:0.0625rem 0.25rem; font-size:0.625rem; border: 1px solid var(--glass-border);
  border-radius:0.25rem; background: var(--glass-bg); color: var(--text-muted);
  cursor: pointer; outline: none; transition: var(--transition); width: 44px; text-align: center;
}
.tts-speed-select:hover { border-color: var(--accent-primary); color: var(--accent-primary); }
.tts-speed-select:focus { border-color: var(--accent-primary); }

/* ── 问候页建议提示词 ── */
.greeting-chips {
  display: flex;
  flex-wrap: wrap;
  gap:0.5rem;
  justify-content: center;
  margin-top:1.5rem;
  max-width:32rem;
}
.greeting-chip {
  padding:0.5rem 0.875rem;
  border-radius:var(--radius-full);
  border:1px solid var(--glass-border);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  color: var(--text-secondary);
  font-size:0.8125rem;
  cursor: pointer;
  transition: var(--transition);
}
.greeting-chip:hover {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
  transform: translateY(-2px);
  box-shadow: var(--shadow-card-hover), var(--glow-primary);
}

/* ── 导师答疑模式切换 ── */
.chat-profile-bar { display:flex; align-items:center; gap:8px; padding:8px 16px; border-bottom:1px solid var(--color-border); flex-shrink:0; }
.chat-profile-btn { display:flex; align-items:center; gap:6px; padding:4px 12px; border-radius:20px; border:1px solid var(--color-border); background:var(--color-surface); font-size:12px; color:var(--color-text-2); cursor:pointer; transition:all 0.15s; }
.chat-profile-btn:hover { border-color:var(--color-border-focus); color:var(--color-text); }
.cpb-avatar { font-size:16px; }
.cpb-level { font-weight:500; }
.cpb-weak { font-size:0.75rem; padding:0.0625rem 0.375rem; border-radius:var(--radius-xs); background:color-mix(in srgb, var(--accent-warm) 12%, transparent); color:var(--accent-warm); }
.chat-skill-badge { display:flex; align-items:center; gap:0.25rem; padding:0.25rem 0.625rem; border-radius:var(--radius-full); border:1px solid var(--color-border-focus); background:var(--accent-primary-10); font-size:0.75rem; color:var(--accent); cursor:pointer; }
.chat-skill-badge:hover { background:var(--accent-primary-20); }

.chat-mode-bar {
  display: flex;
  align-items: center;
  gap:0.625rem;
  max-width:var(--chat-max-width, 900px);
  margin:0 auto 0.5rem;
}
.chat-send-error {
  max-width:var(--chat-max-width, 900px);
  margin:0 auto 0.5rem;
  padding:0.5rem 0.875rem;
  border-radius:var(--radius-sm);
  background:color-mix(in srgb, var(--accent-danger, #ef4444) 12%, transparent);
  border:1px solid color-mix(in srgb, var(--accent-danger, #ef4444) 40%, transparent);
  color:var(--accent-danger, #ef4444);
  font-size:0.8125rem;
  font-weight:600;
  cursor:pointer;
}
.mode-toggle {
  display: inline-flex;
  align-items: center;
  gap:0.375rem;
  padding:0.3125rem 0.875rem;
  border-radius:var(--radius-full);
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  color: var(--text-secondary);
  font-size:0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: var(--transition);
}
.mode-toggle:hover { border-color: var(--text-muted); color: var(--text-primary); }
.mode-toggle.mode-tutor {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
  background: var(--accent-primary-10);
  box-shadow: var(--glow-primary);
}
.mode-toggle-icon { display: inline-flex; }
.mode-toggle-icon svg { width:0.875rem; height:0.875rem; }
.mode-hint { font-size:0.6875rem; color: var(--text-muted); }

/* ── 导师答疑多模态卡片 ── */
.tutor-media-block {
  margin-top:0.625rem;
  border-radius:var(--radius-sm);
  overflow: hidden;
  animation: fade-up 0.3s ease both;
}
.tutor-svg-block {
  border: 1px solid var(--accent-primary-20);
  background: var(--accent-primary-10);
}
.tutor-video-block {
  border: 1px solid var(--glass-border);
  background: var(--bg-tertiary);
}
.tutor-media-label {
  display: flex;
  align-items: center;
  gap:0.3125rem;
  padding:0.3125rem 0.625rem;
  font-size:0.6875rem;
  font-weight: 600;
  color: var(--accent-primary);
  background: var(--accent-primary-10);
}
.tutor-media-icon { display: inline-flex; }
.tutor-media-icon svg { width:0.75rem; height:0.75rem; }
.tutor-svg-container {
  padding:0.625rem;
  display: flex;
  justify-content: center;
  background: var(--bg-primary);
}
.tutor-svg-container svg { max-width: 100%; height: auto; }
.tutor-video-content {
  padding:0.5rem 0.75rem;
  font-size:0.8125rem;
  line-height:1.6;
  color: var(--text-secondary);
}
</style>
