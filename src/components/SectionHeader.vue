<script setup lang="ts">
/**
 * SectionHeader.vue — L2 复合组件：区块标题 + 描述
 *
 * 背景：`.engine-section-title` + `.engine-desc` 这一对在 5 个文件里被整段复制
 * （CompareProfilesPanel / FrugalRAGPanel / GOMARLPanel / TeachingRulesPanel / EngineView）。
 * 原本都是 `<div>`，本组件改用真正的 **h2/h3/h4**，顺带修掉"标题无语义"的问题。
 *
 * 用法：
 *   <SectionHeader title="算法引擎" description="..." />
 *   <SectionHeader :level="3">
 *     <template #title><Icon /> 对比画像</template>
 *     <template #description>...</template>
 *   </SectionHeader>
 */
interface Props {
  /** 标题文案；也可通过 #title 插槽传入（便于塞图标） */
  title?: string
  /** 描述文案；也可通过 #description 插槽传入 */
  description?: string
  /** 标题层级，影响语义与字号。区块主标题用 2，子区块用 3 */
  level?: 2 | 3 | 4
}
withDefaults(defineProps<Props>(), {
  title: undefined,
  description: undefined,
  level: 2,
})
</script>

<template>
  <header class="section-header">
    <component :is="`h${level}`" class="section-header__title">
      <slot name="title">{{ title }}</slot>
    </component>
    <p v-if="description || $slots.description" class="section-header__desc">
      <slot name="description">{{ description }}</slot>
    </p>
  </header>
</template>

<style scoped>
.section-header {
  display: block;
}
.section-header__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  /* 标题与描述之间保留 4px 呼吸感。注：原 `.engine-section-title` 在 5 个文件中
     有 4 个没有此行、仅 EngineView 有；此处统一采用"有"的一方（视觉更正确）。
     这是一个**有意的 4px 设计收敛**，非纯等价替换，已在交付文档中记录。 */
  margin: 0 0 var(--space-1);
  font-size: var(--text-xl);
  font-weight: var(--weight-bold);
  color: var(--text-primary);
  line-height: var(--leading-snug);
}
.section-header__desc {
  margin: 0 0 var(--space-4);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-normal);
}
</style>
