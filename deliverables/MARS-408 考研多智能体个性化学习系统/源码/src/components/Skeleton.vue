<script setup lang="ts">
/**
 * Skeleton.vue — 统一骨架屏组件
 * 封装 main.css 的 .skeleton / skeleton-shimmer 动画；自动受 prefers-reduced-motion 保护。
 * 用法：
 *   <Skeleton variant="card" />                      单卡片
 *   <Skeleton variant="text" :count="3" />           多行文本（末行收窄）
 *   <Skeleton variant="avatar" />                     头像占位
 *   <Skeleton variant="title" width="12rem" />       标题占位
 *   <Skeleton variant="block" height="4rem" radius="var(--radius-md)" /> 自定义块
 */
interface Props {
  variant?: 'block' | 'text' | 'title' | 'card' | 'avatar' | 'circle' | 'chart'
  width?: string
  height?: string
  radius?: string
  count?: number
  label?: string
}
const props = withDefaults(defineProps<Props>(), {
  variant: 'block',
  width: '100%',
  height: undefined,
  radius: undefined,
  count: 1,
  label: '加载中',
})
</script>

<template>
  <div
    v-if="variant === 'text' && count > 1"
    class="skeleton-stack"
    role="status"
    aria-busy="true"
    :aria-label="label"
  >
    <div
      v-for="i in count"
      :key="i"
      class="skeleton skeleton-text"
      :style="{ width: i === count ? '60%' : width }"
    ></div>
  </div>
  <div
    v-else
    class="skeleton"
    :class="`skeleton-${variant}`"
    role="status"
    aria-busy="true"
    :aria-label="label"
    :style="{ width, height, borderRadius: radius }"
  ></div>
</template>
