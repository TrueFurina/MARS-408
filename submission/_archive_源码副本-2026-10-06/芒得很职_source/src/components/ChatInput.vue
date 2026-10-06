<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { useStudyStore } from '@/stores/studyStore'
import { icons } from '@/components/icons'

const store = useStudyStore()

const props = defineProps<{
  disabled?: boolean
  placeholder?: string
}>()

const emit = defineEmits<{
  send: [text: string]
  image: [file: File]
}>()

const inputText = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

const SCROLL_THRESHOLD_EM = 21.3 // 和 max-height 一致，超过即启用滚动

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  const fontSize = parseFloat(getComputedStyle(el).fontSize)
  el.style.height = 'auto'
  const sh = el.scrollHeight
  el.style.height = sh + 'px'
  el.style.overflowY = sh >= fontSize * SCROLL_THRESHOLD_EM ? 'auto' : 'hidden'
}

function handleSend() {
  const text = inputText.value.trim()
  if (!text || props.disabled) return
  emit('send', text)
  inputText.value = ''
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
  }
}

function triggerImage() {
  fileInputRef.value?.click()
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) emit('image', file)
  input.value = ''
}

function onKeydown(e: KeyboardEvent) {
  // Ctrl+Enter / Cmd+Enter 发送消息
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault()
    handleSend()
    return
  }
  // Enter 发送（Shift+Enter 换行）
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

function focusInput() {
  nextTick(() => textareaRef.value?.focus())
}

defineExpose({ focusInput })
</script>

<template>
  <div class="chat-input-box">
    <textarea
      ref="textareaRef"
      v-model="inputText"
      :placeholder="placeholder || '输入你的408问题，如「解释TCP三次握手」「二叉树遍历」「Cache映射」...'"
      :disabled="disabled"
      rows="1"
      aria-label="输入你的408考研问题，例如解释TCP三次握手、二叉树遍历、Cache映射"
      @input="autoResize"
      @keydown="onKeydown"
    ></textarea>
    <div class="input-bottom-bar">
      <div class="input-bottom-left">
        <label class="deep-think-btn" :class="{ active: store.thinkingMode }">
          <input type="checkbox" v-model="store.thinkingMode" />
          <svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <circle cx="10" cy="10" r="1.8" fill="currentColor" stroke="none"/>
            <ellipse cx="10" cy="10" rx="9" ry="4.2" transform="rotate(-45 10 10)"/>
            <ellipse cx="10" cy="10" rx="9" ry="4.2" transform="rotate(45 10 10)"/>
          </svg>
          <span>深度思考</span>
        </label>
        <label class="agent-btn" :class="{ active: store.agentMode }">
          <input type="checkbox" v-model="store.agentMode" />
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <rect x="2" y="2" width="12" height="12" rx="3" stroke="currentColor" fill="none"/>
            <circle cx="8" cy="6" r="1.5" fill="currentColor" stroke="none"/>
            <circle cx="5.5" cy="11" r="1.5" fill="currentColor" stroke="none"/>
            <circle cx="10.5" cy="11" r="1.5" fill="currentColor" stroke="none"/>
            <line x1="8" y1="7.5" x2="5.5" y2="9.5"/>
            <line x1="8" y1="7.5" x2="10.5" y2="9.5"/>
          </svg>
          <span>Agent模式</span>
        </label>
      </div>
      <div class="input-bottom-right">
        <button class="input-action-btn" title="上传图片(讯飞看图问答)" aria-label="上传图片（讯飞看图问答）" @click="triggerImage" v-html="icons.attach"></button>
        <input ref="fileInputRef" type="file" accept="image/*" hidden @change="onFileChange" />
        <button
          class="send-btn"
          :disabled="!inputText.trim() || disabled"
          @click="handleSend"
          title="发送"
          aria-label="发送消息"
          v-html="icons.send"
        ></button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-input-box {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap:0;
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  border-radius:var(--radius-lg);
  padding:1rem 1rem 0.625rem;
  transition: var(--transition);
  box-shadow: var(--shadow-sm);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.chat-input-box:focus-within {
  border-color: var(--border-focus);
  box-shadow: 0 4px 20px var(--accent-primary-10);
}

.chat-input-box textarea {
  width:100%;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-primary);
  font-size:1rem;
  line-height:1.6;
  resize: none;
  overflow-y: hidden;
  padding:0 0 0.5rem;
  max-height:21.3em;
  min-height:3.7em;
  font-family: inherit;
}
.chat-input-box textarea::placeholder {
  color: var(--text-muted);
}

.input-bottom-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top:0.5rem;
}

.input-bottom-left {
  display: flex;
  align-items: center;
  gap:0.625rem;
  margin-left:-0.375rem;
}
.input-bottom-right {
  display: flex;
  align-items: center;
  gap:0.25rem;
}

.deep-think-btn {
  display: inline-flex;
  align-items: center;
  gap:0.3125rem;
  padding:0.3125rem 0.75rem;
  border-radius:var(--radius-sm);
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-muted);
  font-size:0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition);
  user-select: none;
}
.deep-think-btn input, .agent-btn input {
  position: absolute; width:0.0625rem; height:0.0625rem; padding:0; margin:-0.0625rem;
  opacity: 0; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
}
.deep-think-btn:hover {
  border-color: var(--accent-1);
  color: var(--accent-1);
}
.deep-think-btn.active {
  border-color: var(--accent-1);
  background: var(--accent-1-light);
  color: var(--accent-1);
}
.deep-think-btn svg { flex-shrink: 0; }

.agent-btn {
  display: inline-flex;
  align-items: center;
  gap:0.3125rem;
  padding:0.3125rem 0.75rem;
  border-radius:var(--radius-sm);
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-muted);
  font-size:0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition);
  user-select: none;
}
.agent-btn:hover {
  border-color: var(--accent-1);
  color: var(--accent-1);
}
.agent-btn.active {
  border-color: var(--accent-1);
  background: var(--accent-1-light);
  color: var(--accent-1);
}
.agent-btn svg { flex-shrink: 0; }

/* 切换标签：隐藏 checkbox 但仍可键盘聚焦，聚焦时显示焦点环（WCAG 2.4.7） */
.deep-think-btn:focus-within, .agent-btn:focus-within {
  outline: 2px solid var(--accent-primary);
  outline-offset: 2px;
  border-color: var(--accent-primary);
}

.input-action-btn {
  width:2.75rem;
  height:2.75rem;
  border-radius:var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition);
  color: var(--text-muted);
  flex-shrink: 0;
}
.input-action-btn:hover {
  background: var(--bg-card-hover);
  color: var(--text-secondary);
}
:deep(.input-action-btn svg) { width:1.375rem; height:1.375rem; }

.send-btn {
  width:2.75rem;
  height:2.75rem;
  border-radius:var(--radius-sm);
  background: var(--gradient-accent);
  color: var(--text-inverse);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition);
  box-shadow: 0 2px 8px var(--accent-primary-20);
}
.send-btn:hover {
  transform: scale(1.05);
  box-shadow: 0 4px 12px var(--accent-primary-20);
}
.send-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}
:deep(.send-btn svg) { width:1.125rem; height:1.125rem; }

.deep-think-btn svg { width:1.125rem; height:1.125rem; }
.input-bottom-right { gap:0.5rem; }
</style>
