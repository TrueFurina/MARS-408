<script setup lang="ts">
// 教师端：班级素养六维报告（前后测聚合 + 逐人明细）——对照实验过程性考核依据
import { onMounted, ref } from 'vue'
import { api, ApiError } from '@/utils/api'

interface ClassAvg { [dim: string]: number | null }
interface StudentRow {
  user_id: string
  user_name: string
  phase: string
  total: number
  dims: Record<string, number>
}
interface ClassReport {
  class_name: string
  student_count: number
  class_avg: { pre: ClassAvg; post: ClassAvg }
  students: StudentRow[]
  dimensions: string[]
}

const className = ref('信息安全1班-实验组')
const report = ref<ClassReport | null>(null)
const loading = ref(false)
const errorMsg = ref('')
const queried = ref('')

function scoreColor(score: number | null | undefined): string {
  if (score == null) return '#94a3b8'
  if (score >= 90) return '#22c55e'
  if (score >= 75) return '#84cc16'
  if (score >= 60) return '#eab308'
  return '#ef4444'
}

function fmt(v: number | null | undefined): string {
  return v == null ? '—' : String(v)
}

/** 前后测均值差（班级级，用于效应量预览） */
function deltaOf(dim: string): number | null {
  if (!report.value) return null
  const pre = report.value.class_avg.pre[dim] ?? null
  const post = report.value.class_avg.post[dim] ?? null
  if (pre == null || post == null) return null
  return Math.round((post - pre) * 10) / 10
}

async function load() {
  if (!className.value.trim() || loading.value) return
  loading.value = true
  errorMsg.value = ''
  try {
    report.value = await api.post<ClassReport>('/literacy/class-report', { class_name: className.value.trim() })
    queried.value = className.value.trim()
  } catch (e) {
    report.value = null
    errorMsg.value = e instanceof ApiError ? e.message : '报告加载失败'
  } finally {
    loading.value = false
  }
}

/** 导出 CSV（过程性考核依据落盘） */
function exportCsv() {
  if (!report.value) return
  const dims = report.value.dimensions
  const head = ['user_id', 'user_name', 'phase', 'total', ...dims].join(',')
  const lines = report.value.students.map(s =>
    [s.user_id, s.user_name, s.phase, s.total, ...dims.map(d => s.dims[d] ?? '')].join(','))
  const blob = new Blob(['\ufeff' + [head, ...lines].join('\n')], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `素养测评_${queried.value}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}

onMounted(load)
</script>

<template>
  <div class="literacy-teacher">
    <header class="page-head">
      <h1>班级素养六维报告</h1>
      <p class="sub">职业素养测评聚合 · 前后测对照 · 过程性考核依据导出</p>
    </header>

    <div class="toolbar">
      <input v-model="className" class="text-input" placeholder="班级名称（如：信息安全1班-实验组）" @keyup.enter="load" />
      <button class="btn primary" :disabled="loading" @click="load">{{ loading ? '加载中…' : '查询报告' }}</button>
      <button v-if="report" class="btn ghost" @click="exportCsv">导出 CSV</button>
    </div>

    <div v-if="errorMsg" class="state-card error">{{ errorMsg }}</div>

    <template v-if="report">
      <section class="card">
        <div class="card-head">
          <h2>{{ queried }} · {{ report.student_count }} 名学生</h2>
        </div>
        <table class="avg-table">
          <thead>
            <tr>
              <th>维度</th>
              <th>前测均值</th>
              <th>后测均值</th>
              <th>差值</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in report.dimensions" :key="d">
              <td class="dim-name">{{ d }}</td>
              <td :style="{ color: scoreColor(report.class_avg.pre[d]) }">{{ fmt(report.class_avg.pre[d]) }}</td>
              <td :style="{ color: scoreColor(report.class_avg.post[d]) }">{{ fmt(report.class_avg.post[d]) }}</td>
              <td>
                <span v-if="deltaOf(d) != null" :style="{ color: deltaOf(d)! >= 0 ? '#22c55e' : '#ef4444' }">
                  {{ deltaOf(d)! > 0 ? '+' : '' }}{{ deltaOf(d) }}
                </span>
                <span v-else class="muted">—</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p class="hint">差值列为负或"—"时，说明该维度尚未完成后测或后测均值下降——用于 W8 后测前的过程性检查。</p>
      </section>

      <section class="card">
        <h2>逐人明细</h2>
        <table class="stu-table">
          <thead>
            <tr><th>学号/ID</th><th>姓名</th><th>阶段</th><th>综合分</th><th v-for="d in report.dimensions" :key="d">{{ d }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="s in report.students" :key="s.user_id + s.phase">
              <td class="mono">{{ s.user_id }}</td>
              <td>{{ s.user_name || '—' }}</td>
              <td><span class="phase-tag" :class="s.phase">{{ s.phase === 'pre' ? '前测' : '后测' }}</span></td>
              <td :style="{ color: scoreColor(s.total), fontWeight: 600 }">{{ s.total }}</td>
              <td v-for="d in report.dimensions" :key="d">{{ fmt(s.dims[d] ?? null) }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>

    <div v-else-if="!errorMsg && !loading" class="state-card">输入班级名称查询素养测评聚合报告</div>
  </div>
</template>

<style scoped>
.literacy-teacher { max-width: 960px; margin: 0 auto; padding: var(--space-6) var(--space-4) var(--space-12); }
.page-head h1 { font-size: 22px; margin: 0 0 var(--space-1); }
.page-head .sub { color: #64748b; font-size: var(--text-sm); margin: 0 0 18px; }
.toolbar { display: flex; gap: 10px; margin-bottom: 18px; flex-wrap: wrap; }
.text-input { flex: 1; min-width: 220px; padding: 9px var(--space-3); border: 1.5px solid var(--border, #e2e8f0); border-radius: 8px; font-size: var(--text-sm); }
.btn { padding: 9px 18px; border-radius: 8px; font-size: var(--text-base); cursor: pointer; border: 1.5px solid transparent; }
.btn.primary { background: #4f46e5; color: #fff; }
.btn.primary:disabled { opacity: .5; cursor: not-allowed; }
.btn.ghost { background: transparent; border-color: var(--border, #e2e8f0); color: #475569; }
.card { background: var(--surface, #fff); border: 1px solid var(--border, #e2e8f0); border-radius: 12px; padding: var(--space-5); margin-bottom: 18px; }
.card h2 { font-size: var(--text-md); margin: 0 0 var(--space-3); }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.avg-table, .stu-table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
.avg-table th, .avg-table td, .stu-table th, .stu-table td { padding: var(--space-2) 10px; text-align: left; border-bottom: 1px solid var(--border, #f1f5f9); }
.avg-table th, .stu-table th { color: #64748b; font-weight: var(--weight-medium); font-size: var(--text-xs); }
.dim-name { font-weight: var(--weight-semibold); color: #334155; }
.mono { font-family: ui-monospace, monospace; font-size: var(--text-xs); color: #64748b; }
.muted { color: #94a3b8; }
.phase-tag { padding: 2px var(--space-2); border-radius: 999px; font-size: var(--text-xs); }
.phase-tag.pre { background: #f1f5f9; color: #475569; }
.phase-tag.post { background: #eef2ff; color: #4f46e5; }
.hint { color: #94a3b8; font-size: var(--text-xs); margin: var(--space-3) 0 0; }
.state-card { padding: var(--space-10); text-align: center; background: var(--surface, #fff); border-radius: 12px; border: 1px solid var(--border, #e2e8f0); color: #64748b; }
.state-card.error { color: var(--color-danger); }
.stu-table { max-height: 420px; overflow-y: auto; display: block; }
.stu-table thead { display: table; width: 100%; }
.stu-table tbody { display: table; width: 100%; }
</style>
