<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'

defineProps<{
  title?: string
}>()

const error = ref<Error | null>(null)
const hasError = ref(false)
/** 重试计数：递增后强制重建子树，否则 reset 只是隐藏错误卡片、不会真正重跑子组件 */
const contentKey = ref(0)

onErrorCaptured((err: Error) => {
  error.value = err
  hasError.value = true
  console.error('[ErrorBoundary]', err)
  return false // 阻止继续冒泡
})

function reset() {
  hasError.value = false
  error.value = null
  contentKey.value++
}
</script>

<template>
  <div v-if="hasError" class="error-boundary" role="alert" aria-live="assertive">
    <div class="eb-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/>
        <line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    </div>
    <div class="eb-title">{{ title || '页面加载异常' }}</div>
    <div class="eb-desc">{{ error?.message || '发生了意外错误，请刷新重试' }}</div>
    <button class="eb-btn" @click="reset">重试</button>
  </div>
  <div v-else class="eb-content" :key="contentKey">
    <slot />
  </div>
</template>

<style scoped>
/* display:contents —— 包裹层不参与布局，避免破坏被包裹页面的高度/滚动契约 */
.eb-content { display: contents; }
.error-boundary {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: var(--space-20) var(--space-5); text-align: center; min-height: 300px;
}
.eb-icon { color: var(--accent-danger); margin-bottom: var(--space-4); line-height: 0; }
.eb-icon svg { width: 48px; height: 48px; }
.eb-title { font-size: var(--text-xl); font-weight: var(--weight-bold); color: var(--text-primary); margin-bottom: var(--space-2); }
.eb-desc { font-size: var(--text-base); color: var(--text-muted); max-width: 400px; line-height: 1.6; margin-bottom: var(--space-6); }
.eb-btn {
  padding: 10px var(--space-7); border: none; border-radius: var(--radius-md);
  background: var(--accent-primary); color: var(--color-text-on-accent); font-size: var(--text-base); font-weight: var(--weight-semibold);
  cursor: pointer; transition: var(--transition);
}
.eb-btn:hover { opacity: 0.9; transform: translateY(-1px); }
</style>