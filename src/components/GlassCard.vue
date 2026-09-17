<script setup lang="ts">
/**
 * GlassCard.vue — L2 复合组件：玻璃态卡片
 *
 * 背景：审计发现玻璃态样式在 4+ 个文件里被复制粘贴（.glass-card），
 * 且各家用不同令牌（有的用 --border-color，有的用 --glass-border）。
 * 实测 --color-border 与 --color-glass-border 在深色主题下**完全相同**
 * （均为 rgba(255,255,255,0.09)），浅色下仅差 1% 透明度，故统一收敛为
 * --glass-border（语义更准确），属于零视觉风险。
 *
 * 设计约束：与 Stack 一致 —— padding 只接受 --space-N 档位数字，堵死裸值。
 *
 * 用法：
 *   <GlassCard :padding="6" radius="lg">...</GlassCard>
 *   <GlassCard :padding="4" hoverable>...</GlassCard>
 */
interface Props {
  /** 内边距档位，2..8 对应 --space-2..--space-8 */
  padding?: 2 | 3 | 4 | 5 | 6 | 7 | 8
  /** 圆角档位 */
  radius?: 'sm' | 'md' | 'lg' | 'xl'
  /** 是否启用 hover 抬起效果（默认关闭，避免列表页误触） */
  hoverable?: boolean
  /** 是否作为区块容器（加上下外边距）。用于取代 .engine-section 的组合用法 */
  section?: boolean
}
const props = withDefaults(defineProps<Props>(), {
  padding: 4,
  radius: 'md',
  hoverable: false,
  section: false,
})

const paddingToken = `var(--space-${props.padding})`
</script>

<template>
  <div
    class="glass-card"
    :class="[`glass-card--radius-${radius}`, { 'glass-card--hover': hoverable, 'glass-card--section': section }]"
    :style="{ padding: paddingToken }"
  >
    <slot />
  </div>
</template>

<style scoped>
.glass-card {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  min-width: 0;
}
.glass-card--radius-sm {
  border-radius: var(--radius-sm);
}
.glass-card--radius-md {
  border-radius: var(--radius-md);
}
.glass-card--radius-lg {
  border-radius: var(--radius-lg);
}
.glass-card--radius-xl {
  border-radius: var(--radius-xl);
}
.glass-card--hover {
  transition: transform var(--transition), box-shadow var(--transition);
}
.glass-card--hover:hover {
  transform: translateY(-2px);
}
.glass-card--section {
  margin-bottom: var(--space-8);
}
</style>
