<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

interface Toast {
  id: number
  type: 'success' | 'error' | 'info' | 'warning'
  message: string
  duration: number
}

const toasts = ref<Toast[]>([])
let nextId = 0

function addToast(type: Toast['type'], message: string, duration = 3000) {
  const id = nextId++
  toasts.value.push({ id, type, message, duration })
  setTimeout(() => removeToast(id), duration)
}

function removeToast(id: number) {
  toasts.value = toasts.value.filter(t => t.id !== id)
}

// 暴露全局方法
const instance = { addToast, success: (m: string) => addToast('success', m),
  error: (m: string) => addToast('error', m, 5000),
  info: (m: string) => addToast('info', m),
  warning: (m: string) => addToast('warning', m, 4000) }

defineExpose(instance)

// 挂载到 window 上供全局调用
onMounted(() => { (window as any).__toast = instance })
onUnmounted(() => { delete (window as any).__toast })
</script>

<template>
  <Teleport to="body">
    <div class="toast-container">
      <TransitionGroup name="toast">
        <div v-for="toast in toasts" :key="toast.id" :class="['toast-item', `toast-${toast.type}`]">
          <span class="toast-icon">{{ { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' }[toast.type] }}</span>
          <span class="toast-msg">{{ toast.message }}</span>
          <button class="toast-close" @click="removeToast(toast.id)" aria-label="关闭通知">✕</button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-container {
  position: fixed; top: 16px; right: 16px; z-index: 10000;
  display: flex; flex-direction: column; gap: 8px; pointer-events: none;
}
.toast-item {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 16px; border-radius: var(--radius-md);
  background: var(--color-elevated); border: 1px solid var(--glass-border);
  box-shadow: var(--shadow-lg); pointer-events: auto;
  min-width: 280px; max-width: 420px;
  font-size: 13px; color: var(--text-primary);
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
}
.toast-success { border-left: 4px solid var(--accent-success); }
.toast-error { border-left: 4px solid var(--accent-danger); }
.toast-info { border-left: 4px solid var(--accent-secondary); }
.toast-warning { border-left: 4px solid var(--accent-warm); }
.toast-icon { font-size: 16px; flex-shrink: 0; }
.toast-msg { flex: 1; line-height: 1.4; }
.toast-close {
  width: 20px; height: 20px; border: none; background: transparent;
  color: var(--text-muted); cursor: pointer; font-size: 12px;
  border-radius: 50%; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; transition: var(--transition);
}
.toast-close:hover { background: var(--bg-card-hover); color: var(--text-primary); }
.toast-enter-active { transition: all 0.3s ease; }
.toast-leave-active { transition: all 0.2s ease; }
.toast-enter-from { transform: translateX(100%); opacity: 0; }
.toast-leave-to { transform: translateX(100%); opacity: 0; }
</style>