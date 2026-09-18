<script setup lang="ts">
/**
 * EngineSection.vue — L3 领域组件：算法引擎演示区块
 *
 * 背景：`.engine-section` + `.engine-section-title` + `.engine-tag` + `.engine-desc`
 * 这一整组在 5 个文件里被逐字复制（CompareProfilesPanel / FrugalRAGPanel /
 * GOMARLPanel / TeachingRulesPanel / EngineView），仅图标与文案不同。
 * 本组件把它收敛为一处。
 *
 * 设计收敛记录（非纯等价，诚实声明）：
 *   - backdrop-filter：4 个文件硬编码 `blur(12px)`，仅 CompareProfilesPanel 用
 *     `var(--glass-blur)`(=10px)。本组件统一用 `--glass-blur`，即那 4 处模糊从
 *     12px → 10px（-2px）。这是**有意的规范化**，视觉上几乎不可辨，但非零差异。
 *   - 标题与描述之间的 4px 呼吸感：沿用 SectionHeader 的"有"口径。
 *
 * 用法：
 *   <EngineSection :title="'GoMARL 共识引擎'" :desc="'...'" :tag="'NeuralMixer'">
 *     <template #icon><span v-html="icons.robot" /></template>
 *     <!-- 区块正文 -->
 *   </EngineSection>
 */
import SectionHeader from '@/components/SectionHeader.vue'
import GlassCard from '@/components/GlassCard.vue'

interface Props {
  /** 区块标题 */
  title: string
  /** 描述文案（必填，所有引擎区块都有说明） */
  desc?: string
  /** 右上角标签文案（如"实时状态"） */
  tag?: string
  /** 图标是否用强调色。原始 5 个文件中仅 FrugalRAGPanel 的图标带 --accent-primary，
   *  其余用默认文字色；为保留这一真实差异而设 */
  iconAccent?: boolean
}
withDefaults(defineProps<Props>(), {
  desc: undefined,
  tag: undefined,
  iconAccent: false,
})
</script>

<template>
  <GlassCard :padding="6" radius="lg" section>
    <SectionHeader :description="desc">
      <template #title>
        <span class="engine-icon" :class="{ 'engine-icon--accent': iconAccent }"><slot name="icon" /></span>
        {{ title }}
        <span v-if="tag" class="engine-tag">{{ tag }}</span>
      </template>
    </SectionHeader>
    <slot />
  </GlassCard>
</template>

<style scoped>
.engine-icon {
  display: inline-flex;
  align-items: center;
}
.engine-icon--accent {
  color: var(--accent-primary);
}
.engine-icon :deep(svg) {
  width: 1.375rem;
  height: 1.375rem;
}
.engine-tag {
  margin-left: auto;
  font-size: var(--text-2xs);
  padding: 0.1875rem var(--space-3);
  border-radius: var(--radius-full);
  background: var(--accent-primary-10);
  color: var(--accent-primary);
  font-weight: var(--weight-medium);
}
</style>
