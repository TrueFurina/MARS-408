<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  /** 进度值 0-100 */
  value: number
  /** 画布尺寸（px） */
  size?: number
  /** 环线宽度（px） */
  stroke?: number
  /** 环心下方小标签 */
  label?: string
  /** 纯色描边（CSS 颜色）。省略则使用品牌渐变 */
  color?: string
}>(), {
  size: 96,
  stroke: 9,
})

const clamped = computed(() => Math.max(0, Math.min(100, Number(props.value) || 0)))
const radius = computed(() => (props.size - props.stroke) / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)
const offset = computed(() => circumference.value * (1 - clamped.value / 100))
const center = computed(() => props.size / 2)
const gradId = `ring-grad-${Math.random().toString(36).slice(2, 9)}`
const strokeColor = computed(() => props.color || `url(#${gradId})`)
</script>

<template>
  <div
    class="ring-progress"
    :style="{ width: size + 'px', height: size + 'px' }"
    role="img"
    :aria-label="`掌握度 ${Math.round(value)}%`"
  >
    <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`">
      <defs v-if="!color">
        <linearGradient :id="gradId" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" :style="{ stopColor: 'var(--accent-primary)' }" />
          <stop offset="100%" :style="{ stopColor: 'var(--accent-secondary)' }" />
        </linearGradient>
      </defs>
      <circle
        :cx="center"
        :cy="center"
        :r="radius"
        fill="none"
        stroke="var(--glass-border)"
        :stroke-width="stroke"
        class="ring-track"
      />
      <circle
        :cx="center"
        :cy="center"
        :r="radius"
        fill="none"
        :stroke="strokeColor"
        :stroke-width="stroke"
        :stroke-dasharray="circumference"
        :stroke-dashoffset="offset"
        stroke-linecap="round"
        class="ring-value"
        :transform="`rotate(-90 ${center} ${center})`"
      />
    </svg>
    <div class="ring-center">
      <span class="ring-num">{{ Math.round(value) }}<span class="ring-pct">%</span></span>
      <span v-if="label" class="ring-label">{{ label }}</span>
    </div>
  </div>
</template>

<style scoped>
.ring-progress {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.ring-progress svg { display: block; }
.ring-track { opacity: 0.55; }
.ring-value {
  transition: stroke-dashoffset 1s cubic-bezier(0.22, 1, 0.36, 1);
}
.ring-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
.ring-num {
  font-size: 1.25rem;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.0312rem;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.ring-pct {
  font-size: 0.75rem;
  font-weight: 700;
  margin-left: 1px;
  color: var(--text-secondary);
}
.ring-label {
  font-size: 0.6875rem;
  color: var(--text-muted);
  margin-top: 2px;
  font-weight: 600;
}
</style>
