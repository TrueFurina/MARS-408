<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { api } from '@/utils/api'
import EmptyState from '@/components/EmptyState.vue'
import Skeleton from '@/components/Skeleton.vue'
import { icons } from '@/components/icons'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import { useStudyStore } from '@/stores/studyStore'

const store = useStudyStore()

const overview = ref<any>(null)
const kbStats = ref<any>(null)
const classPerf = ref<any>(null)
const loading = ref(true)
const error = ref('')

// 章节级 key → 中文名（循环8-P2：知识库统计英文 key 显示修复）
function subjectName(key: string): string {
  return store.subjects[key]?.name || key
}

onMounted(async () => {
  try {
    const [o, k, c] = await Promise.all([
      api.get<any>('/teacher/students/overview').catch(() => null),
      api.get<any>('/teacher/knowledge-base/stats').catch(() => null),
      api.get<any>('/teacher/analytics/class-performance').catch(() => null),
    ])
    overview.value = o
    kbStats.value = k
    classPerf.value = c
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
  loadMemoryOverview()
})

// L1/L2/L3 三层学情记忆（低侵入联动：教师端页展示记忆薄弱点，失败不影响主流程）
const memoryOverview = ref<any>(null)
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞教师端页 */ }
}

// ── 多角色1：班级掌握度分布（简化条形图，无外部图表依赖） ──
const masteryBars = computed(() => {
  const raw = classPerf.value?.chapter_perf || classPerf.value?.by_subject
  if (!Array.isArray(raw) || !raw.length) return []
  // 取前 8 个章节，按掌握度排序（弱→强）
  return [...raw]
    .filter(c => typeof c.avg_mastery === 'number' || typeof c.mastery === 'number')
    .sort((a, b) => (a.avg_mastery ?? a.mastery ?? 0) - (b.avg_mastery ?? b.mastery ?? 0))
    .slice(0, 8)
    .map(c => ({
      name: subjectName(c.chapter || c.subject || '未知'),
      value: c.avg_mastery ?? c.mastery ?? 0,
    }))
})

// 学生列表筛选（按掌握度区间 + 搜索）
const studentFilter = ref<'all' | 'weak' | 'strong'>('all')
const studentSearch = ref('')
const filteredStudents = computed(() => {
  const list = overview.value?.students || []
  return list
    .filter((s: any) => {
      if (studentFilter.value === 'weak' && (s.mastery ?? 0) >= 60) return false
      if (studentFilter.value === 'strong' && (s.mastery ?? 0) < 70) return false
      if (studentSearch.value && !String(s.name || '').includes(studentSearch.value)) return false
      return true
    })
    .slice(0, 8)
})
</script>

<template>
  <ErrorBoundary title="教师端加载异常">
  <div class="page-section">
    <div class="section-title"><span v-html="icons.dashboard" class="section-title-icon"></span>教师端看板</div>
    <div class="section-desc">学生进度、知识库统计、班级分析</div>

    <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
    <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">
      <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);">🧠 记忆薄弱点:</span>
      <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" style="padding:3px 10px;border-radius:12px;background:rgba(239,68,68,0.12);color:var(--accent-danger);">{{ w }}</span>
    </div>

    <div v-if="loading" class="skeleton-grid-2">
      <Skeleton variant="card" />
      <Skeleton variant="card" />
      <Skeleton variant="card" class="skeleton-span-2" />
    </div>
    <div v-else-if="error" class="engine-error">{{ error }}</div>
    <div v-else-if="!overview && !kbStats && !classPerf" class="dashboard-grid">
      <EmptyState :icon="icons.chart" title="暂无教师数据" description="登录后系统将自动同步学生数据，请稍后再查看。" />
    </div>
    <div v-else>
      <!-- 学生概览 -->
      <div class="dashboard-grid">
        <div class="dash-card" v-if="overview">
          <div class="dash-card-title"><span v-html="icons.user" class="card-title-icon"></span>学生概览</div>
          <div class="dash-stats">
            <div class="dash-stat"><span class="dash-value">{{ overview.total_students }}</span><span class="dash-label">总学生</span></div>
            <div class="dash-stat"><span class="dash-value">{{ overview.active_today }}</span><span class="dash-label">今日活跃</span></div>
            <div class="dash-stat"><span class="dash-value">{{ overview.avg_mastery }}%</span><span class="dash-label">平均掌握度</span></div>
            <div class="dash-stat"><span class="dash-value">{{ overview.avg_progress }}</span><span class="dash-label">平均进度</span></div>
          </div>
          <div class="student-list" v-if="overview.students">
            <!-- 筛选控件（多角色1：按掌握度区间 + 搜索） -->
            <div class="student-filter">
              <select v-model="studentFilter" class="filter-select">
                <option value="all">全部学生</option>
                <option value="weak">薄弱（<60%）</option>
                <option value="strong">优秀（≥70%）</option>
              </select>
              <input v-model="studentSearch" class="filter-input" placeholder="搜索学生..." />
            </div>
            <div v-for="s in filteredStudents" :key="s.id" class="student-row">
              <span class="student-name">{{ s.name }}</span>
              <span class="student-progress">进度: {{ s.progress }}</span>
              <span class="student-mastery" :style="{color: s.mastery >= 70 ? 'var(--accent-success)' : s.mastery >= 50 ? 'var(--accent-warm)' : 'var(--accent-danger)'}">{{ s.mastery }}%</span>
            </div>
          </div>
        </div>

        <div class="dash-card" v-if="kbStats">
          <div class="dash-card-title"><span v-html="icons.knowledge" class="card-title-icon"></span>知识库统计</div>
          <div class="dash-stats">
            <div class="dash-stat"><span class="dash-value">{{ kbStats.total_docs }}</span><span class="dash-label">总文档</span></div>
            <div class="dash-stat" v-for="(count, subj) in kbStats.by_subject" :key="subj">
              <span class="dash-value">{{ count }}</span><span class="dash-label">{{ subjectName(String(subj)) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 班级分析 -->
      <div class="dash-card" v-if="classPerf" style="margin-top:16px;">
        <div class="dash-card-title"><span v-html="icons.chart" class="card-title-icon"></span>班级分析</div>
        <!-- 掌握度条形图（多角色1：章节级可视化） -->
        <div v-if="masteryBars.length" class="mastery-bars">
          <div v-for="bar in masteryBars" :key="bar.name" class="mastery-bar-row">
            <span class="mb-name" :title="bar.name">{{ bar.name }}</span>
            <div class="mb-track">
              <div class="mb-fill" :style="{ width: Math.min(100, bar.value) + '%', background: bar.value >= 70 ? 'var(--accent-success)' : bar.value >= 50 ? 'var(--accent-warm)' : 'var(--accent-danger)' }"></div>
            </div>
            <span class="mb-value">{{ bar.value }}%</span>
          </div>
        </div>
        <div v-if="classPerf.weak_areas" class="weak-list" style="margin-top:12px;">
          <div v-for="(w, i) in classPerf.weak_areas.slice(0,8)" :key="i" class="weak-item">
            <span class="weak-rank">#{{ Number(i)+1 }}</span>
            <span class="weak-name">{{ w.area || w.name || w }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
  </ErrorBoundary>
</template>

<style scoped>
.dashboard-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 768px) { .dashboard-grid { grid-template-columns: 1fr; } }
.dash-card { padding: 20px; background: var(--glass-bg); backdrop-filter: blur(var(--glass-blur)); border: 1px solid var(--glass-border); border-radius: var(--radius-md); }
.dash-card-title { font-size:1rem; font-weight: 700; margin-bottom:0.875rem; color: var(--text-primary); }
.dash-stats { display: flex; gap:1rem; flex-wrap: wrap; margin-bottom:1rem; }
.dash-stat { text-align: center; min-width:4.375rem; padding:0.5rem; background: var(--bg-tertiary); border-radius:var(--radius-sm); }
.dash-value { display: block; font-size:1.375rem; font-weight: 800; color: var(--accent-primary); }
.dash-label { font-size:0.6875rem; color: var(--text-muted); }
.student-list { display: flex; flex-direction: column; gap:0.375rem; }
.student-filter { display: flex; gap:0.5rem; margin-bottom:0.625rem; }
.filter-select, .filter-input { padding:0.375rem 0.625rem; border-radius:var(--radius-sm); border:1px solid var(--glass-border); background:var(--bg-tertiary); color:var(--text-primary); font-size:0.75rem; }
.filter-input { flex:1; min-width:0; }
/* 多角色1：班级掌握度条形图 */
.mastery-bars { display:flex; flex-direction:column; gap:0.5rem; }
.mastery-bar-row { display:flex; align-items:center; gap:0.5rem; }
.mb-name { width:7rem; font-size:0.75rem; color:var(--text-secondary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.mb-track { flex:1; height:0.5rem; border-radius:var(--radius-full); background:var(--bg-tertiary); overflow:hidden; }
.mb-fill { height:100%; border-radius:var(--radius-full); transition:width 0.5s ease; }
.mb-value { width:2.75rem; font-size:0.75rem; font-weight:700; color:var(--text-primary); text-align:right; }
.student-row { display: flex; align-items: center; gap:0.75rem; padding:0.5rem 0.75rem; border-radius:var(--radius-sm); background: var(--bg-secondary); font-size:0.8125rem; }
.student-name { flex: 1; color: var(--text-primary); font-weight: 500; }
.student-progress { color: var(--text-muted); }
.student-mastery { font-weight: 700; }
.weak-list { display: flex; flex-wrap: wrap; gap:0.5rem; }
.weak-item { display: flex; align-items: center; gap:0.375rem; padding:0.375rem 0.75rem; border-radius:var(--radius-full); background: var(--accent-danger-10); color: var(--accent-danger); font-size:0.75rem; }
.weak-rank { font-weight: 700; opacity: 0.6; }
</style>