<script setup lang="ts">
import { errMessage } from '@/utils/errorMessage'
import { ref, onMounted, computed } from 'vue'
import { api } from '@/utils/api'
import type { operations } from '@/types/api.generated'

// 答题历史响应类型直接绑后端契约（py-server/api/quiz.py 的 QuizHistoryResponse）。
// 2026-10-29 该路由补了 response_model，三处调用点才真正有类型可绑。
type QuizHistoryResponse =
  operations['get_quiz_history_api_quiz_history_get']['responses'][200]['content']['application/json']
import Skeleton from '@/components/Skeleton.vue'
import Stack from '@/components/Stack.vue'
import EmptyState from '@/components/EmptyState.vue'
import DiagnosticReview from '@/components/DiagnosticReview.vue'
import { icons } from '@/components/icons'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import { useStudyStore } from '@/stores/studyStore'

const store = useStudyStore()

const history = ref<any[]>([])
const stats = ref({ total: 0, correct: 0, accuracy: 0 })
const loading = ref(true)
const error = ref('')
const filter = ref('all')

// 章节级 key → 中文名（与后端 memory_service/review 映射一致）
function subjectName(key: string): string {
  return store.subjects[key]?.name || key
}

// 后端存的是 easy/medium/hard，直接显示会漏出英文，映射成中文
const DIFFICULTY_LABELS: Record<string, string> = { easy: '简单', medium: '中等', hard: '困难' }
function difficultyLabel(d: string): string {
  return DIFFICULTY_LABELS[d] || '未知难度'
}

onMounted(async () => {
  try {
    const data = await api.get<QuizHistoryResponse>('/quiz/history')
    stats.value = {
      total: data?.total ?? 0,
      correct: data?.correct ?? 0,
      accuracy: data?.accuracy ?? 0,
    }
    history.value = (data?.records || []).reverse()
  } catch (e) {
    error.value = errMessage(e, '加载失败')
  } finally {
    loading.value = false
  }
  loadMemoryOverview()
  loadDiagHistory()
})

// L1/L2/L3 三层学情记忆（低侵入联动：答题历史页展示记忆薄弱点，失败不影响主流程）
const memoryOverview = ref<any>(null)
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞答题历史页 */ }
}

// 入学测评记录：整场测评与逐题明细单独存在 user_diagnostic_history，
// 不在 user_quiz_history 里（那张表一行只有科目/对错，装不下题干与作答）。
const diagRecords = ref<any[]>([])
const diagOpen = ref<Record<string, boolean>>({})
async function loadDiagHistory() {
  try {
    const res: any = await api.get('/diagnostic/history')
    diagRecords.value = res?.records || []
  } catch {
    diagRecords.value = []
  }
}

const filteredHistory = computed(() => {
  if (filter.value === 'all') return history.value
  return history.value.filter((r: any) => filter.value === 'wrong' ? !r.correct : r.correct)
})
</script>

<template>
  <ErrorBoundary title="答题历史加载异常">
  <div class="qh-embedded">
    <div class="qh-eyebrow">QUIZ HISTORY</div>
    <div class="qh-title">答题历史</div>
    <div class="qh-desc">查看答题记录，复习错题，追踪薄弱点</div>

    <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
    <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip qh-strip">
      <span class="memory-mini-chip qh-strip-label">记忆薄弱点</span>
      <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" class="memory-mini-chip">{{ w }}</span>
    </div>

    <div v-if="loading">
      <div class="skeleton-row">
        <Skeleton v-for="i in 4" :key="i" variant="block" width="5rem" height="3rem" radius="var(--radius-sm)" />
      </div>
      <div class="skeleton-list">
        <Skeleton v-for="i in 5" :key="i" variant="block" height="3.5rem" radius="var(--radius-md)" />
      </div>
    </div>
    <div v-else-if="error" class="engine-error">{{ error }}</div>
    <div v-else>
      <!-- 四项统计：原先居中 + 玻璃卡 + 正确率绿/错题红两处写死色，改成左对齐的中性统计条 -->
      <div class="qh-stats">
        <div class="qh-stat"><span class="qh-value">{{ stats.total }}</span><span class="qh-label">总题数</span></div>
        <div class="qh-stat"><span class="qh-value">{{ stats.correct }}</span><span class="qh-label">答对</span></div>
        <div class="qh-stat"><span class="qh-value">{{ ((stats?.accuracy ?? 0) * 100).toFixed(0) }}%</span><span class="qh-label">正确率</span></div>
        <div class="qh-stat"><span class="qh-value">{{ stats.total - stats.correct }}</span><span class="qh-label">错题</span></div>
      </div>

      <!-- 入学测评记录：做过几场、每场对多少，点开可逐题核对 -->
      <div v-if="diagRecords.length" class="qh-diag">
        <div class="qh-diag-head">
          <span class="qh-diag-title">入学测评记录</span>
          <span class="qh-diag-count">{{ diagRecords.length }} 次</span>
        </div>
        <div v-for="rec in diagRecords" :key="rec.session_id" class="qh-diag-card">
          <div class="qh-diag-sum" role="button" tabindex="0"
               @click="diagOpen[rec.session_id] = !diagOpen[rec.session_id]"
               @keydown.enter="diagOpen[rec.session_id] = !diagOpen[rec.session_id]"
               @keydown.space.prevent="diagOpen[rec.session_id] = !diagOpen[rec.session_id]">
            <div class="qh-diag-meta">
              <span class="qh-diag-time">{{ rec.taken_at }}</span>
              <span class="qh-diag-acc">{{ (rec.overall_accuracy * 100).toFixed(0) }}%</span>
            </div>
            <div class="qh-diag-sub">
              答对 {{ (rec.details || []).filter((d: any) => d.is_correct).length }} / {{ (rec.details || []).length }} 题
              <span class="qh-diag-toggle">{{ diagOpen[rec.session_id] ? '收起' : '核对答案' }}</span>
            </div>
          </div>
          <DiagnosticReview v-if="diagOpen[rec.session_id]" :details="rec.details || []" :default-open="true" />
        </div>
      </div>

      <div class="qh-filter">
        <button class="qh-filter-btn" :class="{ active: filter === 'all' }" :aria-selected="filter === 'all'" @click="filter = 'all'">全部</button>
        <button class="qh-filter-btn" :class="{ active: filter === 'wrong' }" :aria-selected="filter === 'wrong'" @click="filter = 'wrong'">错题</button>
        <button class="qh-filter-btn" :class="{ active: filter === 'correct' }" :aria-selected="filter === 'correct'" @click="filter = 'correct'">正确</button>
      </div>

      <EmptyState v-if="history.length === 0" :icon="icons.history" title="暂无答题记录" description="去「智能出题」页面开始练习吧" />

      <Stack v-else :gap="2">
        <div v-for="(r, i) in filteredHistory" :key="i" class="qh-item">
          <span class="qh-badge" :class="r.correct ? 'qh-badge--ok' : 'qh-badge--bad'">{{ r.correct ? '正确' : '错误' }}</span>
          <div class="qh-body">
            <div class="qh-subject">{{ subjectName(r.subject) || '未知科目' }}</div>
            <div class="qh-difficulty">{{ difficultyLabel(r.difficulty) }}</div>
          </div>
          <div class="qh-time">{{ r.timestamp || '' }}</div>
        </div>
      </Stack>
    </div>
  </div>
  </ErrorBoundary>
</template>

<style scoped>
.qh-eyebrow { font-size: 0.6875rem; font-weight: 600; letter-spacing: 0.16em; color: var(--color-accent); margin-bottom: 6px; }
/* 嵌在「错题本」的 tab 里，只能是区块级标题 */
.qh-title { font-size: 17px; font-weight: 700; letter-spacing: -0.01em; color: var(--color-text); line-height: 1.3; }
.qh-desc { font-size: var(--text-sm); color: var(--color-text-2); margin-top: 4px; padding-bottom: var(--space-3); border-bottom: 1px solid var(--color-border); margin-bottom: var(--space-4); }
.qh-strip { margin-bottom: var(--space-4); }
.qh-strip-label { color: var(--color-accent); }

.qh-stats { display: flex; gap: var(--space-8); flex-wrap: wrap; margin-bottom: var(--space-5); }
.qh-stat { display: flex; flex-direction: column; align-items: flex-start; min-width: 4.5rem; }
.qh-value { font-size: 24px; font-weight: 800; color: var(--color-text); line-height: 1.1; }
.qh-label { font-size: var(--text-xs); color: var(--color-text-3); margin-top: 4px; }

.qh-filter { display: flex; gap: var(--space-2); margin-bottom: var(--space-4); }
.qh-filter-btn { padding: 6px var(--space-4); border-radius: var(--radius-full); border: 1px solid var(--color-border); background: transparent; color: var(--color-text-2); font-size: var(--text-sm); cursor: pointer; transition: var(--transition); }
.qh-filter-btn.active { background: var(--color-accent-solid); color: var(--text-user); border-color: var(--color-accent-solid); }

.qh-item { display: flex; align-items: center; gap: var(--space-3); padding: var(--space-3) var(--space-4); background: var(--color-card); border: 1px solid var(--color-border); border-radius: 9px; }
.qh-badge { flex-shrink: 0; padding: 2px 8px; border-radius: var(--radius-full); font-size: var(--text-2xs); font-weight: 600; background: var(--color-surface-2); color: var(--color-text-2); }
.qh-badge--bad { background: var(--accent-primary-10); color: var(--color-accent); }
.qh-body { flex: 1; min-width: 0; }
.qh-subject { font-size: var(--text-base); font-weight: 600; color: var(--color-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.qh-difficulty { font-size: var(--text-xs); color: var(--color-text-3); margin-top: 2px; }
.qh-time { font-size: var(--text-2xs); color: var(--color-text-3); white-space: nowrap; flex-shrink: 0; }

/* ── 入学测评记录（整场测评 + 逐题核对，数据来自 user_diagnostic_history） ── */
.qh-diag { margin-bottom: var(--space-5); padding: var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-card); }
.qh-diag-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: var(--space-3); }
.qh-diag-title { font-size: 14px; font-weight: 700; color: var(--color-text); }
.qh-diag-count { font-size: var(--text-xs); color: var(--color-text-3); }
.qh-diag-card { padding-top: var(--space-3); margin-top: var(--space-3); border-top: 1px solid var(--color-border); }
.qh-diag-card:first-of-type { padding-top: 0; margin-top: 0; border-top: none; }
.qh-diag-sum { cursor: pointer; }
.qh-diag-meta { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); }
.qh-diag-time { font-size: var(--text-xs); color: var(--color-text-2); }
.qh-diag-acc { font-size: 20px; font-weight: 800; color: var(--color-text); line-height: 1.1; }
.qh-diag-sub { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); margin-top: 4px; font-size: var(--text-xs); color: var(--color-text-3); }
.qh-diag-toggle { flex-shrink: 0; color: var(--color-accent); }

@media (max-width: 640px) {
  .qh-stats { gap: var(--space-5); }
  .qh-value { font-size: 20px; }
  .qh-time { display: none; }
}
</style>
