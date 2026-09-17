<script setup lang="ts">
/**
 * TagList.vue — L2 复合组件：自动换行的标签/芯片列表
 *
 * 背景：审计发现 `display:flex; flex-wrap:wrap; gap:<N>` 在 5 个文件里被复制粘贴
 * （.chips / .tag-list / .path-topics / .next-step-tags / .gomarl-groups-list），
 * 间距各写各的（0.375rem / 8px / 0.5rem …）。本组件把它收敛为一处。
 *
 * 设计约束：与 Stack 一致 —— gap 只接受 --space-N 档位数字，从 API 层堵死裸值。
 * 本组件只负责"排"，不负责单个标签长什么样（那是 L1 Tag 的职责）。
 *
 * 用法：
 *   <TagList :gap="2">
 *     <span class="chip">数据结构</span>
 *     <span class="chip">计组</span>
 *   </TagList>
 */
interface Props {
  /** 间距档位，1..6 对应 --space-1..--space-6（4/8/12/16/20/24px）。芯片列表推荐 1~2 */
  gap?: 1 | 2 | 3 | 4 | 5 | 6
  /** 语义：默认是列表，用 ul/li 更利于读屏；传 true 则渲染为纯 div */
  as?: 'list' | 'group'
  /** 无障碍标签，描述这一组标签是什么（如"涉及知识点"） */
  label?: string
}
const props = withDefaults(defineProps<Props>(), {
  gap: 2,
  as: 'list',
  label: undefined,
})

const gapToken = `var(--space-${props.gap})`
</script>

<template>
  <ul
    v-if="as === 'list'"
    class="tag-list"
    :style="{ gap: gapToken }"
    :aria-label="label"
  >
    <li v-for="(slotItem, i) in $slots.default?.() ?? []" :key="i" class="tag-list__item">
      <component :is="slotItem" />
    </li>
  </ul>
  <div v-else class="tag-list" :style="{ gap: gapToken }" role="group" :aria-label="label">
    <slot />
  </div>
</template>

<style scoped>
.tag-list {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  min-width: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}
.tag-list__item {
  display: inline-flex;
  min-width: 0;
}
</style>
