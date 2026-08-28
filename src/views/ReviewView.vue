<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/utils/api'
import EmptyState from '@/components/EmptyState.vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import { useStudyStore, SUBJECT_TO_COURSE, COURSE_MAP } from '@/stores/studyStore'

const router = useRouter()
const store = useStudyStore()
const summary = ref<any>(null)
const loading = ref(true)
const error = ref('')

/**
 * 将后端按章节级 key 聚合的 by_subject 重新按「408 四科」聚合。
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
  } catch (e: any) {
    error.value = e?.message || '加载失败'
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
  <div class="page-section">
    <ErrorBoundary title="错题复盘异常">
      <div class="section-title">🔍 错题复盘</div>
    <div class="section-desc">按 408 四科统计错题情况，点击科目进入针对性练习</div>

    <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
    <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">
      <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);">🧠 记忆薄弱点:</span>
      <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" style="padding:3px 10px;border-radius:12px;background:rgba(239,68,68,0.12);color:var(--accent-danger);">{{ w }}</span>
    </div>

    <div v-if="loading" class="empty-state"><div class="empty-title">加载中...</div></div>
    <EmptyState v-else-if="error" icon="❌" :title="error" />
    <div v-else-if="summary">
      <div class="dashboard-grid">
        <div class="dash-card">
          <div class="dash-card-title">📊 答题概览</div>
          <div class="dash-stats">
            <div class="dash-stat"><span class="dash-value">{{ summary.total_questions }}</span><span class="dash-label">总题数</span></div>
            <div class="dash-stat"><span class="dash-value">{{ summary.total_wrong }}</span><span class="dash-label">错题数</span></div>
            <div class="dash-stat"><span class="dash-value">{{ (summary.overall_accuracy * 100).toFixed(0) }}%</span><span class="dash-label">正确率</span></div>
          </div>
        </div>

        <div class="dash-card" v-if="byCourse.length">
          <div class="dash-card-title">📚 408 四科统计</div>
          <div v-for="s in byCourse" :key="s.subject" class="subject-row" role="button" tabindex="0" :aria-label="'复习 ' + s.subject_name" @click="goPractice(s.subject)" @keydown.enter="goPractice(s.subject)" @keydown.space.prevent="goPractice(s.subject)">
            <span class="subject-name">{{ s.subject_name }}</span>
            <span class="subject-accuracy" :style="{ color: s.accuracy >= 0.7 ? 'var(--accent-success)' : s.accuracy >= 0.4 ? 'var(--accent-warm)' : 'var(--accent-danger)' }">{{ (s.accuracy * 100).toFixed(0) }}%</span>
            <span class="subject-count">{{ s.wrong }}/{{ s.total }} 错</span>
          </div>
        </div>
      </div>

      <div class="card" style="margin-top:20px;" v-if="summary.weak_topics?.length">
        <div class="card-title" style="margin-bottom:12px;">⚠️ 薄弱知识点</div>
        <div class="tag-list">
          <span v-for="topic in summary.weak_topics" :key="topic" class="tag tag-warning">{{ topic }}</span>
        </div>
      </div>

      <div class="card" style="margin-top:20px;" v-if="summary.recommendation">
        <div class="card-title" style="margin-bottom:8px;">💡 学习建议</div>
        <div class="recommendation-text">{{ summary.recommendation }}</div>
      </div>
    </div>
    <EmptyState v-else icon="📝" title="暂无答题记录" description="去做一些练习题，错题会自动记录在这里" />
    </ErrorBoundary>
  </div>
</template>

<style scoped>
.dash-stats { display: flex; gap: 16px; flex-wrap: wrap; padding: 12px 0; }
.dash-stat { display: flex; flex-direction: column; align-items: center; min-width: 80px; }
.dash-value { font-size: 28px; font-weight: 700; color: var(--accent-primary); }
.dash-label { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
.subject-row { display: flex; align-items: center; gap: 12px; padding: 8px 0; cursor: pointer; transition: var(--transition); border-bottom: 1px solid var(--glass-border); }
.subject-row:hover { background: var(--bg-card-hover); }
.subject-name { flex: 1; font-size: 14px; font-weight: 500; }
.subject-accuracy { font-size: 16px; font-weight: 700; min-width: 48px; text-align: right; }
.subject-count { font-size: 12px; color: var(--text-muted); min-width: 60px; text-align: right; }
.tag-list { display: flex; gap: 6px; flex-wrap: wrap; }
.tag { padding: 4px 10px; border-radius: 12px; font-size: 12px; }
.tag-warning { background: rgba(245, 158, 11, 0.15); color: var(--accent-warm); }
.recommendation-text { font-size: 14px; line-height: 1.6; color: var(--text-secondary); padding: 8px 0; }
</style>