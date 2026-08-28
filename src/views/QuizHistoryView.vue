<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { api } from '@/utils/api'
import Skeleton from '@/components/Skeleton.vue'
import EmptyState from '@/components/EmptyState.vue'
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

onMounted(async () => {
  try {
    const data = await api.get<any>('/quiz/history')
    stats.value = {
      total: data?.total ?? 0,
      correct: data?.correct ?? 0,
      accuracy: data?.accuracy ?? 0,
    }
    history.value = (data?.records || []).reverse()
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
  loadMemoryOverview()
})

// L1/L2/L3 三层学情记忆（低侵入联动：答题历史页展示记忆薄弱点，失败不影响主流程）
const memoryOverview = ref<any>(null)
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞答题历史页 */ }
}

const filteredHistory = computed(() => {
  if (filter.value === 'all') return history.value
  return history.value.filter((r: any) => filter.value === 'wrong' ? !r.correct : r.correct)
})
</script>

<template>
  <ErrorBoundary title="答题历史加载异常">
  <div class="page-section">
    <div class="section-title">📊 答题历史与错题本</div>
    <div class="section-desc">查看答题记录，复习错题，追踪薄弱点</div>

    <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
    <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">
      <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);">🧠 记忆薄弱点:</span>
      <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" style="padding:3px 10px;border-radius:12px;background:rgba(239,68,68,0.12);color:var(--accent-danger);">{{ w }}</span>
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
      <div class="history-stats">
        <div class="history-stat"><span class="h-value">{{ stats.total }}</span><span class="h-label">总题数</span></div>
        <div class="history-stat"><span class="h-value">{{ stats.correct }}</span><span class="h-label">答对</span></div>
        <div class="history-stat"><span class="h-value" :style="{color: (stats?.accuracy ?? 0) >= 0.6 ? 'var(--accent-success)' : 'var(--accent-danger)'}">{{ ((stats?.accuracy ?? 0) * 100).toFixed(0) }}%</span><span class="h-label">正确率</span></div>
        <div class="history-stat"><span class="h-value" style="color:var(--accent-danger);">{{ stats.total - stats.correct }}</span><span class="h-label">错题</span></div>
      </div>

      <div class="filter-bar">
        <button class="filter-btn" :class="{ active: filter === 'all' }" @click="filter = 'all'">全部</button>
        <button class="filter-btn" :class="{ active: filter === 'wrong' }" @click="filter = 'wrong'">❌ 错题</button>
        <button class="filter-btn" :class="{ active: filter === 'correct' }" @click="filter = 'correct'">✅ 正确</button>
      </div>

      <EmptyState v-if="history.length === 0" :icon="icons.history" title="暂无答题记录" description="去「智能出题」页面开始练习吧" />

      <div v-else class="history-list">
        <div v-for="(r, i) in filteredHistory" :key="i" class="history-item glass-card" :class="{ wrong: !r.correct, correct: r.correct }">
          <div class="h-icon">{{ r.correct ? '✅' : '❌' }}</div>
          <div class="h-body">
            <div class="h-subject">{{ subjectName(r.subject) || '未知科目' }}</div>
            <div class="h-difficulty">{{ r.difficulty || '未知难度' }}</div>
          </div>
          <div class="h-time">{{ r.timestamp || '' }}</div>
        </div>
      </div>
    </div>
  </div>
  </ErrorBoundary>
</template>

<style scoped>
.history-stats { display: flex; gap:1rem; margin-bottom:1.25rem; flex-wrap: wrap; }
.history-stat { flex: 1; min-width: 80px; text-align: center; padding: 16px; border-radius: var(--radius-md); background: var(--glass-bg); backdrop-filter: blur(var(--glass-blur)); border: 1px solid var(--glass-border); }
.h-value { display: block; font-size:1.75rem; font-weight: 800; color: var(--text-primary); }
.h-label { font-size:0.75rem; color: var(--text-muted); margin-top:0.25rem; display: block; }
.filter-bar { display: flex; gap: 8px; margin-bottom: 16px; }
.filter-btn { padding: 6px 16px; border-radius: var(--radius-full); border: 1px solid var(--glass-border); background: transparent; color: var(--text-secondary); font-size: 13px; cursor: pointer; transition: var(--transition); }
.filter-btn.active { background: var(--accent-primary); color: var(--text-user); border-color: var(--accent-primary); }
.history-list { display: flex; flex-direction: column; gap:0.5rem; }
.history-item { display: flex; align-items: center; gap:0.75rem; padding:0.75rem 1rem; }
.history-item.wrong { border-left: 3px solid var(--accent-danger); }
.history-item.correct { border-left: 3px solid var(--accent-success); }
.h-icon { font-size:1.25rem; flex-shrink: 0; }
.h-body { flex: 1; }
.h-subject { font-size:0.875rem; font-weight: 600; color: var(--text-primary); }
.h-difficulty { font-size:0.75rem; color: var(--text-muted); margin-top:0.125rem; }
.h-time { font-size:0.6875rem; color: var(--text-muted); white-space: nowrap; }
</style>