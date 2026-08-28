<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useStudyStore, type StudentProfile } from '@/stores/studyStore'
import { api } from '@/utils/api'
import { icons } from '@/components/icons'
import { renderMarkdownSafe } from '@/utils/markdown'

const router = useRouter()
const store = useStudyStore()

const messages = ref<{ role: string; content: string }[]>([])
const inputText = ref('')
const loading = ref(false)
const completed = ref(false)
const messagesRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

// 发送消息
async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || loading.value || completed.value) return

  inputText.value = ''
  messages.value.push({ role: 'user', content: text })
  scrollToBottom()

  loading.value = true
  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 60000)
    const data = await api.post<any>('/profile/build', {
      message: text,
      history: messages.value.slice(0, -1).map(m => ({ role: m.role, content: m.content })),
    })
    clearTimeout(timeoutId)

    messages.value.push({ role: 'assistant', content: data.reply })

    // 如果画像完成
    if (data.completed && data.profile) {
      completed.value = true
      store.saveProfile(data.profile as StudentProfile)
      // 延迟后跳转到聊天页
      setTimeout(() => router.push('/'), 1500)
    }
  } catch (e: any) {
    const msg = e?.name === 'AbortError'
      ? '讯飞星火响应超时（X2 深度推理较慢），请稍后重试，或在设置页切换到 DeepSeek 通道。'
      : '抱歉，我现在有点卡顿，请稍后再试。'
    messages.value.push({ role: 'assistant', content: msg })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

// 初始化：获取开场白
onMounted(async () => {
  try {
    const data = await api.post<any>('/profile/build', { message: '', history: [] })
    if (data?.reply) {
      messages.value.push({ role: 'assistant', content: data.reply })
    }
  } catch {
    messages.value.push({ role: 'assistant', content: '你好！我是你的408考研学习助手。你之前学过计算机基础课程吗？' })
  }
  scrollToBottom()
  setTimeout(() => inputRef.value?.focus(), 300)
})

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}
</script>

<template>
  <div class="profile-builder">
    <!-- 顶部 -->
    <div class="profile-builder-header">
      <div class="profile-builder-title">👋 初次见面，先认识一下你</div>
      <div class="profile-builder-desc">
        跟我聊几句，让我了解你的408基础，为你定制专属学习计划
        <span v-if="completed" style="color:var(--accent-success);font-weight:600;">
          ✅ 已了解！正在跳转...
        </span>
      </div>
    </div>

    <!-- 对话区 -->
    <div ref="messagesRef" class="profile-chat">
      <div v-for="(msg, i) in messages" :key="i"
        class="profile-msg"
        :class="msg.role"
      >
        <div class="profile-msg-avatar" v-if="msg.role === 'assistant'">
          <span v-html="icons.sparkle"></span>
        </div>
        <!-- 用户消息用纯文本插值(white-space 保留换行)，助手消息走 DOMPurify 净化的 renderMarkdownSafe -->
        <div class="profile-msg-bubble" :style="msg.role === 'user' ? 'white-space: pre-line;' : ''">
          <template v-if="msg.role === 'user'">{{ msg.content }}</template>
          <div v-else class="markdown-body" v-html="renderMarkdownSafe(msg.content)"></div>
        </div>
        <div class="profile-msg-avatar user-avatar" v-if="msg.role === 'user'">
          <span v-html="icons.user"></span>
        </div>
      </div>

      <div v-if="loading" class="profile-msg assistant">
        <div class="profile-msg-avatar"><span v-html="icons.sparkle"></span></div>
        <div class="profile-msg-bubble">
          <div class="typing-indicator"><span></span><span></span><span></span></div>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="profile-input-area">
      <div class="profile-input-wrapper">
        <textarea
          ref="inputRef"
          v-model="inputText"
          placeholder="输入你的回答..."
          :disabled="loading || completed"
          rows="1"
          @keydown="onKeydown"
          class="profile-input"
        ></textarea>
        <button
          class="profile-send-btn"
          :disabled="!inputText.trim() || loading || completed"
          @click="sendMessage"
          v-html="icons.send"
        ></button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.profile-builder {
  display: flex;
  flex-direction: column;
  height:100%;
  max-width:45rem;
  margin:0 auto;
  width:100%;
}
.profile-builder-header {
  text-align: center;
  padding:2.25rem 1.25rem 1.25rem;
  flex-shrink: 0;
  position: relative;
}
.profile-builder-header::before {
  content: '';
  position: absolute;
  inset:0;
  background: var(--gradient-hero);
  pointer-events: none;
  border-radius:0;
}
.profile-builder-title {
  font-size:1.5rem;
  font-weight: 800;
  color: var(--text-primary);
  margin-bottom:0.5rem;
  position: relative;
  letter-spacing:-0.0187rem;
}
.profile-builder-desc {
  font-size:0.9375rem;
  color: var(--text-secondary);
  position: relative;
}
.profile-chat {
  flex: 1;
  overflow-y: auto;
  padding:0 1.25rem 1rem;
}
.profile-msg {
  display: flex;
  gap:0.625rem;
  margin-bottom:1rem;
  animation: fade-up 0.3s ease both;
}
.profile-msg.user {
  flex-direction: row-reverse;
}
.profile-msg-avatar {
  width:2.125rem;
  height:2.125rem;
  border-radius:50%;
  background: var(--gradient-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: #fff;
  box-shadow: var(--shadow-glow);
}
.profile-msg-avatar svg { width:1.125rem; height:1.125rem; }
.user-avatar {
  background: var(--gradient-primary);
  color: #fff;
  box-shadow: var(--glow-primary);
}
.profile-msg-bubble {
  max-width:80%;
  padding:0.875rem 1.125rem;
  border-radius:var(--radius-lg);
  font-size:0.9375rem;
  line-height:1.7;
}
.profile-msg.assistant .profile-msg-bubble {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  border-bottom-left-radius:0.375rem;
}
.profile-msg.user .profile-msg-bubble {
  background: var(--gradient-primary);
  color: #fff;
  border-bottom-right-radius:0.375rem;
  box-shadow: 0 2px 8px var(--accent-primary-20);
}
.profile-input-area {
  flex-shrink: 0;
  padding:0 1.25rem 1.25rem;
}
.profile-input-wrapper {
  display: flex;
  gap:0.5rem;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  border-radius:var(--radius-lg);
  padding:0.625rem 0.75rem;
  transition: var(--transition);
}
.profile-input-wrapper:focus-within {
  border-color: var(--border-glow);
  box-shadow: 0 0 0 3px var(--accent-primary-10);
}
.profile-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-primary);
  font-size:0.9375rem;
  line-height:1.5;
  resize: none;
  font-family: inherit;
  max-height:6.25rem;
}
.profile-input::placeholder { color: var(--text-muted); }
.profile-send-btn {
  width:2.25rem;
  height:2.25rem;
  border-radius:var(--radius-sm);
  background: var(--gradient-primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: var(--transition-bounce);
}
.profile-send-btn:hover:not(:disabled) { transform: translateY(-1px) scale(1.05); box-shadow: var(--shadow-glow), var(--glow-primary); }
.profile-send-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.profile-send-btn svg { width:1.125rem; height:1.125rem; }
</style>
