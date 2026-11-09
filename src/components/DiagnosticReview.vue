<script setup lang="ts">
import { ref, computed } from 'vue'

// 入学测评的逐题核对面板。
// 入场测评交卷后、以及在「答题历史」里回看旧记录，用的是同一份渲染逻辑，
// 所以抽成组件——两处各写一遍必然会漂移（一边改了配色另一边还是旧色）。
const props = defineProps<{ details: any[]; defaultOpen?: boolean }>()

const open = ref(!!props.defaultOpen)

const okCount = computed(() => props.details.filter((d: any) => d.is_correct).length)
const badCount = computed(() => props.details.length - okCount.value)
</script>

<template>
  <div class="dg-review" v-if="details && details.length">
    <div
      class="dg-head"
      role="button"
      tabindex="0"
      @click="open = !open"
      @keydown.enter="open = !open"
      @keydown.space.prevent="open = !open"
    >
      <div>
        <div class="dg-title">逐题核对</div>
        <div class="dg-sub">共 {{ details.length }} 题 · 答对 {{ okCount }} 题 · 答错 {{ badCount }} 题</div>
      </div>
      <span class="dg-toggle">{{ open ? '收起' : '展开' }}</span>
    </div>

    <div class="dg-list" v-if="open">
      <div
        v-for="(d, idx) in details"
        :key="d.question_id"
        class="dg-item"
        :class="d.is_correct ? 'is-ok' : 'is-bad'"
      >
        <div class="dg-meta">
          <span class="dg-no">第 {{ idx + 1 }} 题</span>
          <span class="dg-tag">{{ d.subject_name }} · {{ d.topic }}</span>
          <span class="dg-badge">{{ d.is_correct ? '回答正确' : '回答错误' }}</span>
        </div>
        <div class="dg-q">{{ d.question }}</div>
        <div class="dg-options">
          <div
            v-for="opt in d.options"
            :key="opt"
            class="dg-opt"
            :class="{
              'is-correct': opt[0] === d.correct_answer,
              'is-wrong': opt[0] === d.user_answer && d.user_answer !== d.correct_answer,
            }"
          >
            <span class="dg-opt-mark" v-if="opt[0] === d.correct_answer">✓</span>
            <span class="dg-opt-mark" v-else-if="opt[0] === d.user_answer">✗</span>
            <span class="dg-opt-text">{{ opt }}</span>
            <span class="dg-opt-note" v-if="opt[0] === d.user_answer">你的作答</span>
            <span class="dg-opt-note dg-opt-note--right" v-else-if="opt[0] === d.correct_answer">正确答案</span>
          </div>
        </div>
        <div class="dg-answer">
          你选了 <strong v-if="d.user_answer">{{ d.user_answer }}</strong><span v-else>（未作答）</span>，
          正确答案 <strong>{{ d.correct_answer }}</strong>
        </div>
        <div class="dg-explain" v-if="d.explanation">{{ d.explanation }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dg-review { margin-top: var(--space-5); border: 1px solid var(--glass-border); border-radius: var(--radius-md); background: var(--glass-bg); overflow: hidden; }
.dg-head { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-4); cursor: pointer; }
.dg-title { font-size: 15px; font-weight: 700; color: var(--color-text); }
.dg-sub { margin-top: 4px; font-size: var(--text-xs); color: var(--color-text-2); }
.dg-toggle { flex-shrink: 0; font-size: var(--text-sm); color: var(--color-accent); }

.dg-list { border-top: 1px solid var(--color-border); padding: var(--space-3); display: flex; flex-direction: column; gap: var(--space-3); }
.dg-item { padding: var(--space-4); border-radius: var(--radius-sm); background: var(--color-card); border-left: 3px solid var(--color-border); }
.dg-item.is-ok { border-left-color: var(--color-success); }
.dg-item.is-bad { border-left-color: var(--color-danger); }
.dg-item.is-ok .dg-badge { color: var(--color-success); }
.dg-item.is-bad .dg-badge { color: var(--color-danger); }

.dg-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 10px; }
.dg-no { font-size: var(--text-xs); color: var(--color-text-3); }
.dg-tag { font-size: var(--text-xs); color: var(--color-text-2); padding: 2px 8px; border-radius: var(--radius-full); background: var(--color-surface-2); }
.dg-badge { margin-left: auto; font-size: var(--text-xs); font-weight: 600; padding: 2px 10px; border-radius: var(--radius-full); background: var(--color-surface-2); }

.dg-q { font-size: var(--text-base); font-weight: 600; color: var(--color-text); line-height: 1.6; margin-bottom: 10px; }
.dg-options { display: flex; flex-direction: column; gap: 6px; }
.dg-opt { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: var(--radius-sm); border: 1px solid var(--color-border); font-size: var(--text-sm); color: var(--color-text-2); }
.dg-opt.is-correct { border-color: var(--color-success); color: var(--color-text); }
.dg-opt.is-wrong { border-color: var(--color-danger); color: var(--color-text); }
.dg-opt-mark { flex-shrink: 0; width: 1rem; font-weight: 700; }
.dg-opt.is-correct .dg-opt-mark { color: var(--color-success); }
.dg-opt.is-wrong .dg-opt-mark { color: var(--color-danger); }
.dg-opt-text { flex: 1; min-width: 0; }
.dg-opt-note { flex-shrink: 0; font-size: var(--text-xs); color: var(--color-text-3); }
.dg-opt-note--right { color: var(--color-success); }

.dg-answer { margin-top: 10px; font-size: var(--text-sm); color: var(--color-text-2); }
.dg-answer strong { color: var(--color-text); }
.dg-explain { margin-top: 8px; padding: 10px 12px; border-radius: var(--radius-sm); background: var(--color-surface-2); font-size: var(--text-sm); line-height: 1.7; color: var(--color-text-2); }

@media (max-width: 640px) {
  .dg-item { padding: var(--space-3); }
  /* 手机上选项右侧的「你的作答 / 正确答案」标签会把选项文字压窄，改为只靠 ✓/✗ 与颜色区分 */
  .dg-opt-note { display: none; }
}
</style>
