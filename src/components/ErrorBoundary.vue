<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'

defineProps<{
  title?: string
}>()

const error = ref<Error | null>(null)
const hasError = ref(false)

onErrorCaptured((err: Error) => {
  error.value = err
  hasError.value = true
  console.error('[ErrorBoundary]', err)
  return false // 阻止继续冒泡
})

function reset() {
  hasError.value = false
  error.value = null
}
</script>

<template>
  <div v-if="hasError" class="error-boundary">
    <div class="eb-icon">⚠️</div>
    <div class="eb-title">{{ title || '页面加载异常' }}</div>
    <div class="eb-desc">{{ error?.message || '发生了意外错误，请刷新重试' }}</div>
    <button class="eb-btn" @click="reset">重试</button>
  </div>
  <slot v-else />
</template>

<style scoped>
.error-boundary {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 80px 20px; text-align: center; min-height: 300px;
}
.eb-icon { font-size: 48px; margin-bottom: 16px; }
.eb-title { font-size: 18px; font-weight: 700; color: var(--text-primary); margin-bottom: 8px; }
.eb-desc { font-size: 14px; color: var(--text-muted); max-width: 400px; line-height: 1.6; margin-bottom: 24px; }
.eb-btn {
  padding: 10px 28px; border: none; border-radius: var(--radius-md);
  background: var(--accent-primary); color: #fff; font-size: 14px; font-weight: 600;
  cursor: pointer; transition: var(--transition);
}
.eb-btn:hover { opacity: 0.9; transform: translateY(-1px); }
</style>