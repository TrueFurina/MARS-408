<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useStudyStore } from '@/stores/studyStore'
import { api } from '@/utils/api'
import { renderMarkdownSafe } from '@/utils/markdown'
import { icons } from '@/components/icons'
import ErrorBoundary from '@/components/ErrorBoundary.vue'

const router = useRouter()
const store = useStudyStore()
const loading = ref(true)
const error = ref('')
const assessment = ref<{
  mastery: Record<string, number>
  activity: string
  weak_focus: string[]
  trend: string
  adjustment: string
  by_subject: Record<string, { total: number; correct: number; accuracy: number }>
  total_questions: number
  overall_accuracy: number
  llm_assessed: boolean
} | null>(null)

const quizHistory = ref<{ subject: string; correct: boolean; difficulty?: string; timestamp?: string }[]>([])

// ── 路径调整建议（功能⑤闭环）──
interface PathFeedback {
  adjusted: boolean
  message: string
  inserted_nodes?: string[]
  action?: string
}
interface EvalReport {
  weak_points?: Array<{ topic: string; priority: string; suggestion: string }>
  overall?: { avg_mastery?: number; trend?: string; efficiency?: string }
  adjustment?: { action?: string; description?: string; focus_areas?: string[] }
}
const pathFeedback = ref<PathFeedback | null>(null)
const evalReport = ref<EvalReport | null>(null)
const feedbackLoading = ref(false)
const feedbackError = ref('')
const memoryOverview = ref<any>(null)

// L1/L2/L3 三层学情记忆健康度（低侵入联动：展示记忆层状态，失败不影响主流程）
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞评估页 */ }
}

async function loadAssessment() {
  loading.value = true
  error.value = ''
  try {
    // 从后端拉取真实答题历史（修复 quizHistory 为空的问题）
    try {
      const histData = await api.get<any>('/quiz/history')
      if (histData?.records?.length) {
        quizHistory.value = histData.records.map((r: any) => ({
          subject: r.subject || 'unknown',
          correct: !!r.correct,
          difficulty: r.difficulty,
          timestamp: r.timestamp,
        }))
      }
    } catch { /* 静默降级，用空数组 */ }

    // 即使没有答题记录，也尝试获取评估数据（后端会返回空数据）
    const r = await store.fetchAssessment(quizHistory.value)
    if (r) {
      assessment.value = r
    } else {
      // API 失败或无数据时，用本地答题历史构建兜底评估数据
      const total = quizHistory.value.length
      const correct = total > 0 ? quizHistory.value.filter(q => q.correct).length : 0
      const bySubject: Record<string, { total: number; correct: number; accuracy: number }> = {}
      const mastery: Record<string, number> = {}
      for (const q of quizHistory.value) {
        const subj = q.subject || 'unknown'
        if (!bySubject[subj]) bySubject[subj] = { total: 0, correct: 0, accuracy: 0 }
        bySubject[subj].total++
        if (q.correct) bySubject[subj].correct++
      }
      for (const [k, v] of Object.entries(bySubject)) {
        v.accuracy = v.total > 0 ? +(v.correct / v.total).toFixed(2) : 0
        mastery[k] = v.accuracy
      }
      assessment.value = {
        mastery,
        activity: total > 10 ? '高活跃' : total > 3 ? '中等活跃' : total > 0 ? '低活跃' : '暂无数据',
        weak_focus: Object.entries(mastery).filter(([, v]) => v < 0.5).map(([k]) => k),
        trend: total === 0 ? '--' : (correct / total) > 0.7 ? '上升' : (correct / total) > 0.4 ? '稳定' : '下降',
        adjustment: total === 0 ? '' : (correct / total) < 0.5 ? '建议加强基础概念复习' : '保持当前学习节奏',
        by_subject: bySubject,
        total_questions: total,
        overall_accuracy: total > 0 ? +(correct / total).toFixed(2) : 0,
        llm_assessed: false,
      }
    }
    // 评估数据加载完后绘制雷达图 + 加载路径调整建议
    nextTick(() => drawMasteryRadar())
    if (quizHistory.value.length > 0) {
      loadPathFeedback()
    }
  } catch (e: any) {
    const msg = e?.message || '加载失败'
    // 401 认证错误提示重新登录
    if (msg.includes('401') || msg.includes('Unauthorized') || msg.includes('登录')) {
      error.value = '登录已过期，请重新登录'
    } else {
      // API 不可用时，用本地答题历史构建兜底评估
      const total = quizHistory.value.length
      const correct = total > 0 ? quizHistory.value.filter(q => q.correct).length : 0
      const bySubject: Record<string, { total: number; correct: number; accuracy: number }> = {}
      const mastery: Record<string, number> = {}
      for (const q of quizHistory.value) {
        const subj = q.subject || 'unknown'
        if (!bySubject[subj]) bySubject[subj] = { total: 0, correct: 0, accuracy: 0 }
        bySubject[subj].total++
        if (q.correct) bySubject[subj].correct++
      }
      for (const [k, v] of Object.entries(bySubject)) {
        v.accuracy = v.total > 0 ? +(v.correct / v.total).toFixed(2) : 0
        mastery[k] = v.accuracy
      }
      assessment.value = {
        mastery,
        activity: total > 10 ? '高活跃' : total > 3 ? '中等活跃' : total > 0 ? '低活跃' : '暂无数据',
        weak_focus: Object.entries(mastery).filter(([, v]) => v < 0.5).map(([k]) => k),
        trend: total === 0 ? '--' : (correct / total) > 0.7 ? '上升' : (correct / total) > 0.4 ? '稳定' : '下降',
        adjustment: total === 0 ? '' : (correct / total) < 0.5 ? '建议加强基础概念复习' : '保持当前学习节奏',
        by_subject: bySubject,
        total_questions: total,
        overall_accuracy: total > 0 ? +(correct / total).toFixed(2) : 0,
        llm_assessed: false,
      }
      if (total === 0) {
        error.value = ''
      }
    }
  } finally {
    loading.value = false
  }
}

/** 调 /assessment/feedback 获取路径调整建议（功能⑤闭环） */
async function loadPathFeedback() {
  if (!quizHistory.value.length) return
  feedbackLoading.value = true
  feedbackError.value = ''
  try {
    const data = await api.post<any>('/assessment/feedback', {
      quiz_history: quizHistory.value,
      study_sessions: [],
      profile: store.studentProfile || {},
    })
    if (data?.path_adjustment) {
      pathFeedback.value = {
        adjusted: data.path_adjustment.adjusted ?? false,
        message: data.path_adjustment.message || '',
        inserted_nodes: data.path_adjustment.inserted_nodes || [],
        action: data.path_adjustment.action || '',
      }
    }
    if (data?.evaluation) {
      evalReport.value = data.evaluation
    }
  } catch (e: any) {
    feedbackError.value = e?.message || '路径调整建议加载失败'
  } finally {
    feedbackLoading.value = false
  }
}

function masteryColor(score: number): string {
  if (score >= 80) return 'var(--accent-success)'
  if (score >= 60) return 'var(--accent-tertiary)'
  if (score >= 40) return 'var(--accent-warm)'
  return 'var(--accent-danger)'
}

/** Canvas 取色：把语义令牌解析为实际色值（双主题安全，避免裸 hex） */
function resolveToken(name: string): string {
  if (typeof window === 'undefined') return '#7c6af2'
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || '#7c6af2'
}

const trendIcon = computed(() => {
  const t = assessment.value?.trend || ''
  if (t === '上升') return icons.trendUp
  if (t === '下降') return icons.trendDown
  return icons.trendFlat
})

const activityIcon = computed(() => {
  const a = assessment.value?.activity || ''
  if (a.includes('活跃')) return icons.fire
  if (a.includes('一般')) return icons.moon
  return icons.chart
})

const hasData = computed(() => assessment.value && assessment.value.total_questions > 0)

// ── 掌握度雷达图（功能⑤可视化）──
const radarCanvas = ref<HTMLCanvasElement | null>(null)

/** 雷达图数据：从 mastery（0-1）转为 0-100 的科目掌握度 */
const radarData = computed(() => {
  const m = assessment.value?.mastery
  if (!m) return []
  return Object.entries(m).map(([key, val]) => ({
    label: store.subjects[key]?.name || key,
    value: Math.round((val ?? 0) * 100),
  }))
})

function drawMasteryRadar() {
  const canvas = radarCanvas.value
  if (!canvas || radarData.value.length < 3) return

  const wrapper = canvas.parentElement
  if (!wrapper) return
  const dpr = window.devicePixelRatio || 1
  const size = Math.min(wrapper.clientWidth, 360)

  canvas.width = size * dpr
  canvas.height = size * dpr
  canvas.style.width = size + 'px'
  canvas.style.height = size + 'px'

  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.scale(dpr, dpr)

  const cx = size / 2
  const cy = size / 2
  const radius = Math.min(cx, cy) * 0.68
  const n = radarData.value.length
  const angleStep = (Math.PI * 2) / n
  const values = radarData.value.map(d => d.value / 100)

  // 同心网格
  const gridLevels = [0.2, 0.4, 0.6, 0.8, 1.0]
  ctx.lineWidth = 1
  for (const level of gridLevels) {
    const r = radius * level
    ctx.beginPath()
    for (let i = 0; i <= n; i++) {
      const angle = -Math.PI / 2 + i * angleStep
      const x = cx + r * Math.cos(angle)
      const y = cy + r * Math.sin(angle)
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    }
    ctx.closePath()
    ctx.strokeStyle = `rgba(124, 106, 242, ${0.08 + level * 0.08})`
    ctx.stroke()
  }

  // 轴线
  for (let i = 0; i < n; i++) {
    const angle = -Math.PI / 2 + i * angleStep
    ctx.beginPath()
    ctx.moveTo(cx, cy)
    ctx.lineTo(cx + radius * Math.cos(angle), cy + radius * Math.sin(angle))
    ctx.strokeStyle = 'rgba(124, 106, 242, 0.15)'
    ctx.stroke()
  }

  // 数据区域
  ctx.beginPath()
  for (let i = 0; i <= n; i++) {
    const idx = i % n
    const angle = -Math.PI / 2 + i * angleStep
    const r = radius * (values[idx] ?? 0)
    const x = cx + r * Math.cos(angle)
    const y = cy + r * Math.sin(angle)
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
  }
  ctx.closePath()
  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius)
  grad.addColorStop(0, 'rgba(124, 106, 242, 0.35)')
  grad.addColorStop(0.5, 'rgba(124, 106, 242, 0.22)')
  grad.addColorStop(1, 'rgba(59, 130, 246, 0.08)')
  ctx.fillStyle = grad
  ctx.fill()
  ctx.strokeStyle = 'rgba(124, 106, 242, 0.7)'
  ctx.lineWidth = 2
  ctx.stroke()

  // 顶点 + 标签（语义令牌：双主题安全，经 getComputedStyle 解析为实际色值，杜绝非品牌裸 hex）
  const SUBJECT_TOKENS = [
    '--subject-ds', '--subject-cn', '--subject-co', '--subject-os',
    '--accent-warm', '--accent-success', '--accent-primary', '--accent-blue',
  ]
  for (let i = 0; i < n; i++) {
    const angle = -Math.PI / 2 + i * angleStep
    const r = radius * (values[i] ?? 0)
    const x = cx + r * Math.cos(angle)
    const y = cy + r * Math.sin(angle)
    const color = resolveToken(SUBJECT_TOKENS[i % SUBJECT_TOKENS.length] ?? '--accent-primary')

    ctx.beginPath()
    ctx.arc(x, y, 4, 0, Math.PI * 2)
    ctx.fillStyle = color
    ctx.fill()

    // 标签
    const labelR = radius + 22
    const lx = cx + labelR * Math.cos(angle)
    const ly = cy + labelR * Math.sin(angle)
    ctx.fillStyle = resolveToken('--color-text-2')
    ctx.font = '600 11px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    const item = radarData.value[i]
    if (item) {
      const label = item.label.length > 6 ? item.label.slice(0, 6) + '…' : item.label
      ctx.fillText(label, lx, ly)
      ctx.fillStyle = color
      ctx.font = '700 12px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.fillText(item.value + '%', lx, ly + 14)
    }
  }

  // 中心点
  ctx.beginPath()
  ctx.arc(cx, cy, 3, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(124, 106, 242, 0.5)'
  ctx.fill()
}

let resizeHandler: (() => void) | null = null
onMounted(() => {
  loadAssessment()
  loadMemoryOverview()
  resizeHandler = () => drawMasteryRadar()
  window.addEventListener('resize', resizeHandler)
})
onUnmounted(() => {
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
})

// 评估数据变化时重绘雷达
watch(assessment, () => { nextTick(() => drawMasteryRadar()) })

/** 跳转到学习路径页（闭环：评估→动态调整路径） */
function goToLearningPath() {
  router.push('/learning-path')
}
</script>

<template>
  <div class="page-section">
    <ErrorBoundary title="学习评估异常">
      <div class="section-title">
      <span v-html="icons.barChart" class="section-title-icon"></span>
      学习效果评估
    </div>
    <div class="section-desc">多维度学习数据分析与AI智能评估建议，评估结果动态调整学习路径</div>

    <!-- 加载 -->
    <div v-if="loading" class="empty-state">
      <div v-for="i in 4" :key="i" class="skeleton" style="width:100%;height:80px;margin-bottom:12px;"></div>
    </div>

<!-- 错误/空态 -->
    <div v-else-if="error" class="empty-state">
      <div class="empty-title"><span v-html="icons.warning" class="inline-icon"></span> {{ error }}</div>
      <div class="empty-desc">先去练习页面完成答题后，再来查看学习效果评估</div>
      <button class="engine-btn" style="margin-top:12px;" @click="$router.push('/practice')">去练习</button>
    </div>

    <!-- 评估仪表盘 -->
    <div v-else class="assessment-grid">
      <!-- 无数据时的引导提示 -->
      <div v-if="assessment?.total_questions === 0" class="assessment-card glass-card no-data-hero">
        <div class="no-data-icon" v-html="icons.barChart"></div>
        <div class="no-data-title">还没有学习数据</div>
        <div class="no-data-desc">完成练习后，AI 将自动分析你的学习数据，生成多维度评估报告</div>
        <div class="no-data-features">
          <div class="nd-feature"><span v-html="icons.target"></span> 掌握度雷达图</div>
          <div class="nd-feature"><span v-html="icons.bookOpen"></span> 各科正确率分析</div>
          <div class="nd-feature"><span v-html="icons.lightbulb"></span> AI 学习建议</div>
          <div class="nd-feature"><span v-html="icons.path"></span> 学习路径自动调整</div>
        </div>
        <button class="engine-btn" style="margin-top:16px;" @click="$router.push('/practice')">
          <span v-html="icons.quiz" class="inline-icon"></span> 开始练习
        </button>
      </div>

      <!-- 有数据时展示完整评估 -->
      <template v-if="(assessment?.total_questions ?? 0) > 0">
      <!-- 总览卡片 -->
      <div class="assessment-card glass-card overview">
        <div class="card-title"><span v-html="icons.clipboard" class="card-title-icon"></span> 学习总览</div>
        <div class="overview-stats">
          <div class="ov-stat"><span class="ov-val">{{ assessment!.total_questions }}</span><span class="ov-label">答题数</span></div>
          <div class="ov-stat"><span class="ov-val" :style="{color: masteryColor(assessment!.overall_accuracy * 100)}">{{ ((assessment?.overall_accuracy ?? 0) * 100).toFixed(0) }}%</span><span class="ov-label">正确率</span></div>
          <div class="ov-stat"><span class="ov-val"><span v-html="activityIcon" class="inline-icon"></span>{{ assessment!.activity }}</span><span class="ov-label">活跃度</span></div>
          <div class="ov-stat"><span class="ov-val"><span v-html="trendIcon" class="inline-icon"></span> {{ assessment!.trend }}</span><span class="ov-label">趋势</span></div>
        </div>
        <!-- L1/L2/L3 三层学情记忆健康度（低侵入联动） -->
        <div v-if="memoryOverview" class="memory-mini-strip">
          <span class="memory-mini-chip">🧠 {{ memoryOverview.memory_level || 'L3' }}</span>
          <span class="memory-mini-chip">画像 {{ memoryOverview.profile_dimensions ?? 0 }}/8 维</span>
          <span class="memory-mini-chip">掌握度 {{ memoryOverview.mastery_points ?? 0 }} 点</span>
          <span class="memory-mini-chip">情景事件 {{ memoryOverview.episodic_count ?? 0 }}</span>
        </div>
      </div>

      <!-- 掌握度雷达图（功能⑤可视化） -->
      <div v-if="radarData.length >= 3" class="assessment-card glass-card radar-card">
        <div class="card-title"><span v-html="icons.target" class="card-title-icon"></span> 掌握度雷达图</div>
        <div class="radar-wrapper">
          <canvas ref="radarCanvas" class="radar-canvas"></canvas>
        </div>
      </div>

      <!-- 各科正确率 -->
      <div class="assessment-card glass-card">
        <div class="card-title"><span v-html="icons.bookOpen" class="card-title-icon"></span> 各科正确率</div>
        <div v-for="(data, subject) in assessment!.by_subject" :key="subject" class="subject-row">
          <span class="subject-label">{{ store.subjects[subject]?.name || subject }}</span>
          <div class="subject-bar-bg"><div class="subject-bar-fill" :style="{width: (data.accuracy * 100) + '%', background: masteryColor(data.accuracy * 100)}"></div></div>
          <span class="subject-pct">{{ ((data?.accuracy ?? 0) * 100).toFixed(0) }}%</span>
          <span class="subject-count">({{ data.correct }}/{{ data.total }})</span>
        </div>
      </div>

      <!-- 薄弱点 -->
      <div class="assessment-card glass-card">
        <div class="card-title"><span v-html="icons.target" class="card-title-icon"></span> 薄弱知识点</div>
        <div v-if="assessment!.weak_focus?.length" class="weak-list">
          <div v-for="w in assessment!.weak_focus" :key="w" class="weak-item">{{ store.subjects[w]?.name || w }}</div>
        </div>
        <div v-else class="weak-empty"><span v-html="icons.chart" class="inline-icon"></span>暂无薄弱点数据</div>
      </div>

      <!-- AI建议 -->
      <div class="assessment-card glass-card suggestion">
        <div class="card-title"><span v-html="icons.lightbulb" class="card-title-icon"></span> AI 学习建议</div>
        <div v-if="assessment!.llm_assessed" class="suggestion-text markdown-body" v-html="renderMarkdownSafe(assessment!.adjustment || '')"></div>
        <div v-else class="suggestion-text">完成更多练习后，AI 将生成个性化学习建议</div>
      </div>

      <!-- 路径调整建议（功能⑤闭环：评估→动态调整路径） -->
      <div class="assessment-card glass-card path-feedback-card">
        <div class="card-title">
          <span v-html="icons.path" class="card-title-icon"></span> 学习路径调整建议
          <span v-if="pathFeedback?.adjusted" class="path-adjusted-badge">已调整</span>
        </div>
        <div v-if="feedbackLoading" class="path-feedback-loading">
          <div class="skeleton" style="width:100%;height:24px;margin-bottom:8px;"></div>
          <div class="skeleton" style="width:80%;height:20px;"></div>
        </div>
        <div v-else-if="feedbackError" class="suggestion-text" style="color:var(--accent-danger);">{{ feedbackError }}</div>
        <template v-else-if="pathFeedback">
          <div class="path-feedback-message">{{ pathFeedback.message || '基于评估结果的分析建议' }}</div>
          <!-- 建议下一步学习（功能⑤核心 UI 提示） -->
          <div v-if="pathFeedback.inserted_nodes?.length || evalReport?.adjustment?.focus_areas?.length" class="next-step-section">
            <div class="next-step-label"><span v-html="icons.sparkle" class="inline-icon"></span> 建议下一步学习</div>
            <div class="next-step-tags">
              <span v-for="(node, i) in (pathFeedback.inserted_nodes?.length ? pathFeedback.inserted_nodes : evalReport?.adjustment?.focus_areas)" :key="i" class="next-step-tag">{{ node }}</span>
            </div>
          </div>
          <!-- 薄弱点建议（来自 evaluation） -->
          <div v-if="evalReport?.weak_points?.length" class="weak-suggestion-list">
            <div v-for="(wp, i) in evalReport.weak_points.slice(0, 3)" :key="i" class="weak-suggestion-item">
              <span class="weak-suggestion-topic">{{ wp.topic }}</span>
              <span class="weak-suggestion-desc">{{ wp.suggestion }}</span>
            </div>
          </div>
          <button class="engine-btn path-go-btn" @click="goToLearningPath">
            <span v-html="icons.path" class="inline-icon"></span> 去查看 / 调整学习路径
          </button>
</template>
        <div v-else class="suggestion-text">完成评估后将生成路径调整建议</div>
      </div>
      </template>
    </div>
    </ErrorBoundary>
  </div>
</template>

<style scoped>
.inline-icon { display: inline-flex; vertical-align: middle; margin-right:0.25rem; }
.inline-icon svg { width:1rem; height:1rem; }
.section-title-icon { display: inline-flex; vertical-align: middle; margin-right:0.375rem; }
.section-title-icon svg { width:1.25rem; height:1.25rem; }
.card-title-icon { display: inline-flex; vertical-align: middle; margin-right:0.375rem; }
.card-title-icon svg { width:1.125rem; height:1.125rem; }
.assessment-grid { display: grid; gap:1rem; }
.assessment-card { padding:1.25rem; }
.card-title { font-size:0.9375rem; font-weight: 600; color: var(--text-primary); margin-bottom:0.875rem; display: flex; align-items: center; }
.overview-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.ov-stat { text-align: center; }
.ov-val { font-size:1.375rem; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; justify-content: center; gap:0.25rem; }
.ov-label { font-size:0.75rem; color: var(--text-muted); margin-top:0.25rem; display: block; }
.subject-row { display: flex; align-items: center; gap:0.625rem; margin-bottom:0.625rem; }
.subject-label { width:5rem; font-size:0.8125rem; color: var(--text-secondary); flex-shrink: 0; }
.subject-bar-bg { flex: 1; height:0.5rem; background: var(--bg-tertiary); border-radius:var(--radius-full); overflow: hidden; }
.subject-bar-fill { height:100%; border-radius:var(--radius-full); transition: width 0.6s ease; }
.subject-pct { font-size:0.8125rem; font-weight: 600; color: var(--text-primary); width:2.5rem; text-align: right; }
.subject-count { font-size:0.75rem; color: var(--text-muted); }
.weak-list { display: flex; flex-direction: column; gap:0.375rem; }
.weak-item { padding:0.5rem 0.75rem; background: var(--bg-tertiary); border-radius:var(--radius-sm); font-size:0.8125rem; color: var(--text-primary); border-left: 3px solid var(--accent-danger); }
.weak-empty { font-size:0.8125rem; color: var(--text-muted); }
.suggestion-text { font-size:0.875rem; line-height:1.7; color: var(--text-secondary); }

/* ── 雷达图 ── */
.radar-card { display: flex; flex-direction: column; align-items: center; }
.radar-wrapper { width: 100%; display: flex; justify-content: center; padding: 0.5rem 0; }
.radar-canvas { max-width: 360px; }

/* ── 路径调整建议卡片 ── */
.path-feedback-card { border: 1px solid var(--accent-primary-20); }
.path-adjusted-badge {
  margin-left: auto;
  font-size:0.625rem;
  padding:0.125rem 0.5rem;
  border-radius:var(--radius-full);
  background: var(--accent-success-10);
  color: var(--accent-success);
  font-weight: 700;
}
.path-feedback-loading { padding: 0.5rem 0; }
.path-feedback-message { font-size:0.875rem; line-height:1.6; color: var(--text-secondary); margin-bottom:0.75rem; }
.next-step-section { margin-bottom:0.75rem; }
.next-step-label { font-size:0.8125rem; font-weight: 600; color: var(--accent-primary); margin-bottom:0.375rem; display: flex; align-items: center; }
.next-step-tags { display: flex; flex-wrap: wrap; gap:0.375rem; }
.next-step-tag {
  font-size:0.75rem;
  padding:0.25rem 0.625rem;
  border-radius:var(--radius-full);
  background: var(--accent-primary-10);
  color: var(--accent-primary);
  font-weight: 600;
  border: 1px solid var(--accent-primary-20);
}
.weak-suggestion-list { display: flex; flex-direction: column; gap:0.375rem; margin-bottom:0.75rem; }
.weak-suggestion-item {
  padding:0.5rem 0.75rem;
  background: var(--bg-tertiary);
  border-radius:var(--radius-sm);
  border-left: 3px solid var(--accent-warm);
}
.weak-suggestion-topic { font-size:0.8125rem; font-weight: 600; color: var(--text-primary); display: block; }
.weak-suggestion-desc { font-size:0.75rem; color: var(--text-muted); margin-top:0.125rem; display: block; }
.path-go-btn { margin-top:0.25rem; }

/* ── 无数据引导 ── */
.no-data-hero { text-align: center; padding: 2.5rem 2rem; }
.no-data-icon { margin-bottom: 1rem; opacity: 0.4; }
.no-data-icon :deep(svg) { width: 3rem; height: 3rem; }
.no-data-title { font-size: 1.125rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.5rem; }
.no-data-desc { font-size: 0.875rem; color: var(--text-muted); margin-bottom: 1.25rem; max-width: 400px; margin-left: auto; margin-right: auto; }
.no-data-features { display: flex; justify-content: center; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.5rem; }
.nd-feature { font-size: 0.75rem; padding: 0.375rem 0.75rem; background: var(--bg-tertiary); border-radius: var(--radius-full); color: var(--text-secondary); display: flex; align-items: center; gap: 0.25rem; }
.nd-feature :deep(svg) { width: 0.875rem; height: 0.875rem; }

/* ── 多角色2：移动端响应式适配 ── */
@media (max-width: 768px) {
  .assessment-grid { grid-template-columns: 1fr; }
  .overview-stats { grid-template-columns: repeat(2, 1fr); }
  .assessment-card { padding: 1rem; }
  .subject-label { width: 4rem; }
  .radar-canvas { max-width: 100%; }
}
@media (max-width: 480px) {
  .overview-stats { grid-template-columns: repeat(2, 1fr); gap: 8px; }
  .ov-val { font-size: 1.125rem; }
  .suggestion-text { font-size: 0.8125rem; }
}
</style>
