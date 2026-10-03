<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  /** 插图（SVG 字符串，如 icons.x）或 emoji 文本 */
  icon?: string
  title?: string
  description?: string
  /** 强调色（CSS 颜色，默认品牌紫） */
  accent?: string
}>(), {
  title: '暂无数据',
  accent: 'var(--accent-primary)',
})

const accentColor = computed(() => props.accent)
</script>

<template>
  <div class="nl-empty" role="status" aria-live="polite">
    <div v-if="icon" class="nl-empty-icon" :style="{ color: accentColor }" v-html="icon"></div>
    <div class="nl-empty-title">{{ title }}</div>
    <div v-if="description" class="nl-empty-desc">{{ description }}</div>
    <div v-if="$slots.action" class="nl-empty-actions">
      <slot name="action" />
    </div>
  </div>
</template>

<style scoped>
.nl-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 1.5rem;
  text-align: center;
  gap: 0.875rem;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  margin: 1.5rem auto;
  max-width: 30rem;
  animation: nl-empty-fade-up 0.4s ease both;
}
.nl-empty-icon {
  width: 4.5rem;
  height: 4.5rem;
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, v-bind(accentColor) 12%, transparent);
  border: 1px solid color-mix(in srgb, v-bind(accentColor) 22%, transparent);
  box-shadow: 0 8px 24px color-mix(in srgb, v-bind(accentColor) 18%, transparent);
}
.nl-empty-icon :deep(svg) {
  width: 2.25rem;
  height: 2.25rem;
  opacity: 0.92;
}
.nl-empty-title {
  font-size: 1.0625rem;
  font-weight: 700;
  color: var(--text-secondary);
}
.nl-empty-desc {
  font-size: 0.8125rem;
  max-width: 22.5rem;
  line-height: 1.6;
  color: var(--text-muted);
}
.nl-empty-actions {
  display: flex;
  gap: 0.625rem;
  margin-top: 0.375rem;
  flex-wrap: wrap;
  justify-content: center;
}
@keyframes nl-empty-fade-up {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
