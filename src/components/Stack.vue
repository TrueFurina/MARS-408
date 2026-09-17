<script setup lang="ts">
/**
 * Stack.vue — L2 复合组件：纵向/横向堆叠容器
 *
 * 背景：审计发现 `display:flex; flex-direction:column; gap:<N>` 在 5 个文件里
 * 被复制粘贴（.alert-list / .quiz-options / .step-options / .history-list /
 * .test-input-area），间距值各写各的。本组件把它收敛为一处。
 *
 * 设计约束：
 *   - gap **只接受 --space-N 的档位数字**，组件内部拼成 var(--space-N)。
 *     从 API 层面堵死"传裸 px/rem"的可能 —— 这是本组件存在的意义。
 *   - 不渲染任何视觉样式（无背景/边框/圆角），只负责布局，避免喧宾夺主。
 *
 * 用法：
 *   <Stack :gap="3">...</Stack>
 *   <Stack direction="row" :gap="2" align="center" justify="between">...</Stack>
 */
interface Props {
  /** 主轴方向 */
  direction?: 'column' | 'row'
  /** 间距档位，1..12 对应 --space-1..--space-12（4/8/12/16/20/24/28/32/36/40/44/48px） */
  gap?: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12
  /** 交叉轴对齐 */
  align?: 'stretch' | 'center' | 'start' | 'end' | 'baseline'
  /** 主轴对齐 */
  justify?: 'start' | 'center' | 'end' | 'between' | 'around'
  /** 是否换行（direction=row 时常用） */
  wrap?: boolean
}
const props = withDefaults(defineProps<Props>(), {
  direction: 'column',
  gap: 3,
  align: 'stretch',
  justify: 'start',
  wrap: false,
})

/** 档位数字 → 令牌。刻意不接受字符串，杜绝 '10px' 这类裸值流入 */
const gapToken = `var(--space-${props.gap})`
</script>

<template>
  <div
    class="stack"
    :class="[
      `stack--${direction}`,
      `stack--align-${align}`,
      `stack--justify-${justify}`,
      { 'stack--wrap': wrap },
    ]"
    :style="{ gap: gapToken }"
  >
    <slot />
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  min-width: 0;
}
.stack--column {
  flex-direction: column;
}
.stack--row {
  flex-direction: row;
}
.stack--wrap {
  flex-wrap: wrap;
}
.stack--align-stretch {
  align-items: stretch;
}
.stack--align-center {
  align-items: center;
}
.stack--align-start {
  align-items: flex-start;
}
.stack--align-end {
  align-items: flex-end;
}
.stack--align-baseline {
  align-items: baseline;
}
.stack--justify-start {
  justify-content: flex-start;
}
.stack--justify-center {
  justify-content: center;
}
.stack--justify-end {
  justify-content: flex-end;
}
.stack--justify-between {
  justify-content: space-between;
}
.stack--justify-around {
  justify-content: space-around;
}
</style>
