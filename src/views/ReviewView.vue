<script setup lang="ts">
import { errMessage } from '@/utils/errorMessage'
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/utils/api'
import EmptyState from '@/components/EmptyState.vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import { useStudyStore, SUBJECT_TO_COURSE, COURSE_MAP } from '@/stores/studyStore'
import { icons } from '@/components/icons'

const router = useRouter()
const store = useStudyStore()
const summary = ref<any>(null)
const loading = ref(true)
const error = ref('')

/**
 * 将后端按章节级 key 聚合的 by_subject 重新按「专业四科」聚合。
 * 后端 quiz_history 里 subject 字段是章节级 key（如 overview/ds_tree/cn_phys），
 * 直接展示会出现重复科目名或一堆章节名。这里用 SUBJECT_TO_COURSE 映射合并到四科。
 */
const byCourse = computed(() => {
  const raw = summary.value?.by_subject ?? []
  const merged: Record<string, { total: number; wrong: number; accuracy: number; weak_topics: string[] }> = {}
  for (const s of raw) {
    const courseKey = SUBJECT_TO_COURSE[s.subject] || s.subject
    if (!merged[courseKey]) {
      merged[courseKey] = { total: 0, wrong: 0, accuracy: 0, weak_topics: [] }
    }
    merged[courseKey].total += s.total ?? 0
    merged[courseKey].wrong += s.wrong ?? 0
    if (Array.isArray(s.weak_topics)) {
      merged[courseKey].weak_topics.push(...s.weak_topics)
    }
  }
  // 计算合并后的准确率，按 COURSE_MAP 固定顺序输出
  const result: { subject: string; subject_name: string; total: number; wrong: number; accuracy: number }[] = []
  for (const courseKey of Object.keys(COURSE_MAP)) {
    const d = merged[courseKey]
    if (!d || d.total === 0) continue
    d.accuracy = round2((d.total - d.wrong) / d.total)
    result.push({
      subject: courseKey,
      subject_name: COURSE_MAP[courseKey]?.name || courseKey,
      total: d.total,
      wrong: d.wrong,
      accuracy: d.accuracy,
    })
  }
  // 兜底：若有未识别的章节 key（不在四科映射里），单独列一行
  for (const [k, d] of Object.entries(merged)) {
    if (COURSE_MAP[k]) continue
    d.accuracy = round2((d.total - d.wrong) / Math.max(d.total, 1))
    result.push({ subject: k, subject_name: k, total: d.total, wrong: d.wrong, accuracy: d.accuracy })
  }
  return result
})

function round2(n: number): number {
  return Math.round(n * 100) / 100
}

onMounted(async () => {
  try {
    const res = await api.get<any>('/review/summary')
    summary.value = res
  } catch (e) {
    error.value = errMessage(e, '加载失败')
  } finally {
    loading.value = false
  }
  loadMemoryOverview()
})

// L1/L2/L3 三层学情记忆（低侵入联动：复习页展示记忆薄弱点，失败不影响主流程）
const memoryOverview = ref<any>(null)
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞复习页 */ }
}

function goPractice(courseKey: string) {
  // 跳转到练习页时传课程 key，PracticeView 会自动选中对应课程
  router.push('/practice?course=' + courseKey)
}
</script>

<template>
  <div class="rev-embedded">
    <ErrorBoundary title="错题复盘异常">
      <div class="rev-eyebrow">WRONG ANSWER REVIEW</div>
      <div class="rev-title">错题复盘</div>
      <div class="rev-desc">按专业四科统计错题情况，点击科目进入针对性练习</div>

    <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
    <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip rev-strip">
      <span class="memory-mini-chip rev-strip-label">记忆薄弱点</span>
      <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" class="memory-mini-chip">{{ w }}</span>
    </div>

    <div v-if="loading" class="empty-state"><div class="empty-title">加载中...</div></div>
    <EmptyState v-else-if="error" :icon="icons.xCircle" :title="error" />
    <div v-else-if="summary" class="rev-body">
      <!-- 父页「错题本」顶部已有一排统计卡，这里不再放第二张概览卡，
           三数字压成一行摘要，避免两个统计模块叠在一起 -->
      <div class="rev-summary">
        <span class="rev-sum-item"><b>{{ summary.total_questions }}</b>总题</span>
        <span class="rev-sum-item"><b>{{ summary.total_wrong }}</b>错题</span>
        <span class="rev-sum-item"><b>{{ (summary.overall_accuracy * 100).toFixed(0) }}%</b>正确率</span>
      </div>

      <div class="rev-card" v-if="byCourse.length">
        <div class="rev-card-title">专业四科统计</div>
        <div v-for="s in byCourse" :key="s.subject" class="rev-subject-row" role="button" tabindex="0" :aria-label="'复习 ' + s.subject_name" @click="goPractice(s.subject)" @keydown.enter="goPractice(s.subject)" @keydown.space.prevent="goPractice(s.subject)">
          <span class="rev-subject-name">{{ s.subject_name }}</span>
          <span class="rev-subject-acc">{{ (s.accuracy * 100).toFixed(0) }}%</span>
          <span class="rev-subject-count">{{ s.wrong }}/{{ s.total }} 错</span>
        </div>
      </div>

      <div class="rev-card" v-if="summary.weak_topics?.length">
        <div class="rev-card-title">薄弱知识点</div>
        <div class="rev-tags">
          <span v-for="topic in summary.weak_topics" :key="topic" class="rev-tag">{{ topic }}</span>
        </div>
      </div>

      <div class="rev-card" v-if="summary.recommendation">
        <div class="rev-card-title">学习建议</div>
        <div class="rev-text">{{ summary.recommendation }}</div>
      </div>
    </div>
    <EmptyState v-else :icon="icons.search" title="暂无答题记录" description="去做一些练习题，错题会自动记录在这里" />
    </ErrorBoundary>
  </div>
</template>

<style scoped>
.rev-eyebrow { font-size: 0.6875rem; font-weight: 600; letter-spacing: 0.16em; color: var(--color-accent); margin-bottom: 6px; }
/* 嵌在「错题本」的 review Tab 里，父页已有整页页头，这里只能是区块级标题 */
.rev-title { font-size: 17px; font-weight: 700; letter-spacing: -0.01em; color: var(--color-text); line-height: 1.3; }
.rev-desc { font-size: var(--text-sm); color: var(--color-text-2); margin-top: 4px; padding-bottom: var(--space-3); border-bottom: 1px solid var(--color-border); margin-bottom: var(--space-4); }
.rev-strip { margin-bottom: var(--space-4); }
.rev-strip-label { color: var(--color-accent); }

.rev-body { display: flex; flex-direction: column; gap: var(--space-4); }
.rev-summary { display: flex; gap: var(--space-5); flex-wrap: wrap; font-size: var(--text-xs); color: var(--color-text-3); }
.rev-sum-item b { font-size: var(--text-md); font-weight: 700; color: var(--color-text); margin-right: 5px; }
.rev-card { padding: var(--space-4) var(--space-5); background: var(--color-card); border: 1px solid var(--color-border); border-radius: 12px; box-shadow: var(--shadow-card); }
.rev-card-title { font-size: var(--text-md); font-weight: 600; color: var(--color-text); margin-bottom: var(--space-3); }

.rev-subject-row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: var(--space-3); padding: var(--space-2) 0; cursor: pointer; border-bottom: 1px solid var(--color-border); transition: var(--transition); }
.rev-subject-row:last-child { border-bottom: none; }
.rev-subject-row:hover { background: var(--color-surface-2); }
.rev-subject-name { font-size: var(--text-sm); color: var(--color-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
/* 准确率原先是绿/橙/红三色写死，四个科目四组色相；统一中性，颜色交给图表承担 */
.rev-subject-acc { font-size: var(--text-base); font-weight: 600; color: var(--color-text); min-width: 44px; text-align: right; }
.rev-subject-count { font-size: var(--text-xs); color: var(--color-text-3); min-width: 56px; text-align: right; white-space: nowrap; }

.rev-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.rev-tag { padding: 3px 10px; border-radius: var(--radius-full); font-size: var(--text-xs); background: var(--color-surface-2); border: 1px solid var(--color-border); color: var(--color-text-2); }
.rev-text { font-size: var(--text-sm); line-height: 1.7; color: var(--color-text-2); }

@media (max-width: 640px) {
  .rev-summary { gap: var(--space-4); }
  .rev-subject-row { gap: var(--space-2); }
  .rev-subject-acc { min-width: 40px; }
  .rev-subject-count { min-width: 52px; }
}
</style>