<script setup lang="ts">
import { errMessage } from '@/utils/errorMessage'
import { ref, onMounted, onUnmounted, computed, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useStudyStore } from '@/stores/studyStore'
import { api } from '@/utils/api'
import type { operations } from '@/types/api.generated'

// 答题历史响应类型直接绑后端契约（py-server/api/quiz.py 的 QuizHistoryResponse）。
// 2026-10-29 该路由补了 response_model，三处调用点才真正有类型可绑。
type QuizHistoryResponse =
  operations['get_quiz_history_api_quiz_history_get']['responses'][200]['content']['application/json']
import { renderMarkdownSafe } from '@/utils/markdown'
import { withAlpha } from '@/utils/themeTokens'
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
// /assessment/feedback 返回（response_model=AssessmentFeedbackResponse；evaluation/path_adjustment 为 LLM 产物 dict，
// 生成类型退化为 {[key:string]:unknown} 无法直接收口到上面两个精确接口，故手写精确响应类型）
interface AssessmentFeedbackResp {
  status: string
  evaluation: EvalReport
  path_adjustment: PathFeedback
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
      const histData = await api.get<QuizHistoryResponse>('/quiz/history')
      if (histData?.records?.length) {
        quizHistory.value = histData.records.map((r) => ({
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
  } catch (e) {
    const msg = errMessage(e, '加载失败')
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
    const data = await api.post<AssessmentFeedbackResp>('/assessment/feedback', {
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
  } catch (e) {
    feedbackError.value = errMessage(e, '路径调整建议加载失败')
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
  if (typeof window === 'undefined') return 'var(--color-accent)'
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

/** 顶点配色已统一为 --color-accent，此处仅保图例圆点的语义令牌占位 */
const RADAR_TOKENS = ['--color-accent']

/** 窄屏用的图例：13 个科目名挤在 340px 画布周围必然叠字，
 *  手机上改成画布只留图形与顶点，名称和百分比排成两列清单放到图下方。 */
const radarLegend = computed(() =>
  radarData.value.map((d) => ({
    label: d.label,
    value: d.value,
    color: 'var(--color-accent)',
  }))
)

function drawMasteryRadar() {
  const canvas = radarCanvas.value
  if (!canvas || radarData.value.length < 3) return

  const wrapper = canvas.parentElement
  if (!wrapper) return
  const dpr = window.devicePixelRatio || 1
  // 上限 440（原 360 让 1100px 宽的卡里只剩中间一条）；
  // 同时用 viewport 宽度兜底：手机上 wrapper 可能因 flex 撑到溢出宽，只信 clientWidth 会让 canvas 超出屏幕被裁
  // 上限与 CSS 的 max-width:520px 对齐：位图按 520 生成、显示也最多 520，避免位图比显示小被拉伸。
  // 同时用 viewport 宽度兜底：手机上 wrapper 可能因 flex 撑到溢出宽，只信 clientWidth 会让 canvas 超出屏幕被裁
  const size = Math.min(wrapper.clientWidth, 520, window.innerWidth - 48)
  // 布局未就绪或容器塌陷时 size 可能是 0 / 负数，直接画会抛
  // "createRadialGradient ... r1 provided is less than 0" 并被 ErrorBoundary 挂到页头。
  if (!Number.isFinite(size) || size < 80) return

  // 位图按 size*dpr，显示尺寸也显式给定：
  // 只靠 CSS 的 width:100% + aspect-ratio，canvas 的高度会塌陷、父容器不跟着撑高，
  // 结果是雷达下半圈被卡片下沿裁掉、卡片底部留一大片空。
  canvas.width = size * dpr
  canvas.height = size * dpr
  canvas.style.width = size + 'px'
  canvas.style.height = size + 'px'

  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.scale(dpr, dpr)

  const cx = size / 2
  const cy = size / 2
  // 半径系数分两档：桌面画布大，用 0.66 填满；手机画布小，用 0.58 给最外圈标签留出上下空间，
  // 否则底部两项（存储系统 / 线性表）的百分比会贴着卡片下沿。
  // 再夹一次下限：任何情况下半径不能为负，否则 createRadialGradient 会抛错。
  // 半径系数分三档：手机不画外圈百分比（名称与数值交给下方图例），不必为标签留边，
  // 用 0.84 把画布填满；桌面才需要给 11px 标签留出上下空间。
  const compactView = window.innerWidth <= 640
  const radius = Math.max(8, Math.min(cx, cy) * (compactView ? 0.84 : (size >= 420 ? 0.66 : 0.58)))
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
    ctx.strokeStyle = withAlpha(resolveToken('--color-accent'), 0.08 + level * 0.08)
    ctx.stroke()
  }

  // 轴线
  for (let i = 0; i < n; i++) {
    const angle = -Math.PI / 2 + i * angleStep
    ctx.beginPath()
    ctx.moveTo(cx, cy)
    ctx.lineTo(cx + radius * Math.cos(angle), cy + radius * Math.sin(angle))
    ctx.strokeStyle = withAlpha(resolveToken('--color-accent'), 0.15)
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
  grad.addColorStop(0, withAlpha(resolveToken('--color-accent'), 0.35))
  grad.addColorStop(0.5, withAlpha(resolveToken('--color-accent'), 0.22))
  grad.addColorStop(1, withAlpha(resolveToken('--color-accent'), 0.05))
  ctx.fillStyle = grad
  ctx.fill()
  ctx.strokeStyle = withAlpha(resolveToken('--color-accent'), 0.7)
  ctx.lineWidth = 2
  ctx.stroke()

  // 顶点 + 标签（语义令牌：双主题安全，经 getComputedStyle 解析为实际色值，杜绝非品牌裸 hex）
  const compact = window.innerWidth <= 640
  for (let i = 0; i < n; i++) {
    const angle = -Math.PI / 2 + i * angleStep
    const r = radius * (values[i] ?? 0)
    const x = cx + r * Math.cos(angle)
    const y = cy + r * Math.sin(angle)
    // 顶点原按 RADAR_TOKENS 每维一色（16 个顶点呈绿/橙/红/紫彩虹），与全站单一主色冲突；
    // 统一主色，强弱差异只靠半径表达。
    const color = resolveToken('--color-accent')

    ctx.beginPath()
    ctx.arc(x, y, 4, 0, Math.PI * 2)
    ctx.fillStyle = color
    ctx.fill()

    // 窄屏不画文字：340px 画布放 16 组「名称 + 百分比」，顶部两个必然重叠、长名必被截断。
    // 名称与数值改由下方 .radar-legend 两列清单承载。
    if (compact) continue

    // 宽屏也只标百分比：16 个维度的长科目名（「计算机网络概述」8 字）在 520 画布上
    // 相邻标签只有约 100px 弧长，必然互相压住。名称已由右侧「各科正确率」列表给出。
    const labelR = radius + 18
    const lx = cx + labelR * Math.cos(angle)
    const ly = cy + labelR * Math.sin(angle)
    const lyName = Math.max(12, Math.min(size - 14, ly))
    ctx.fillStyle = resolveToken('--color-text-3')
    ctx.font = '600 11px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    const item = radarData.value[i]
    if (item) ctx.fillText(item.value + '%', lx, lyName)
  }

  // 中心点
  ctx.beginPath()
  ctx.arc(cx, cy, 3, 0, Math.PI * 2)
  ctx.fillStyle = withAlpha(resolveToken('--color-accent'), 0.5)
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
      <div class="as-eyebrow">LEARNING ASSESSMENT</div>
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
          <div class="ov-stat"><span class="ov-val">{{ ((assessment?.overall_accuracy ?? 0) * 100).toFixed(0) }}%</span><span class="ov-label">正确率</span></div>
          <div class="ov-stat"><span class="ov-val"><span v-html="activityIcon" class="inline-icon"></span>{{ assessment!.activity }}</span><span class="ov-label">活跃度</span></div>
          <div class="ov-stat"><span class="ov-val"><span v-html="trendIcon" class="inline-icon"></span> {{ assessment!.trend }}</span><span class="ov-label">趋势</span></div>
        </div>
        <!-- L1/L2/L3 三层学情记忆健康度（低侵入联动） -->
        <div v-if="memoryOverview" class="memory-mini-strip">
          <span class="memory-mini-chip"> {{ memoryOverview.memory_level || 'L3' }}</span>
          <span class="memory-mini-chip">画像 {{ memoryOverview.profile_dimensions ?? 0 }}/8 维</span>
          <span class="memory-mini-chip">掌握度 {{ memoryOverview.mastery_points ?? 0 }} 点</span>
          <span class="memory-mini-chip">情景事件 {{ memoryOverview.episodic_count ?? 0 }}</span>
        </div>
      </div>

      <!-- 掌握度雷达图（功能⑤可视化） -->
      <!-- 雷达图 + 各科正确率：桌面上两卡并排。各自独占一整行时，雷达画布只有 340 左右，
           卡片却有 1100 多宽，左右各剩一大片空白 —— 这是"评估页看着空"的主因。 -->
      <div class="assessment-row">
      <div v-if="radarData.length >= 3" class="assessment-card glass-card radar-card">
        <div class="card-title"><span v-html="icons.target" class="card-title-icon"></span> 掌握度雷达图</div>
        <div class="radar-wrapper">
          <canvas ref="radarCanvas" class="radar-canvas"></canvas>
        </div>
        <!-- 窄屏图例：画布上不再画文字，名称与数值在这里成两列 -->
        <div class="radar-legend">
          <div v-for="(it, i) in radarLegend" :key="i" class="radar-legend-item">
            <span class="radar-legend-dot" :style="{ background: it.color }"></span>
            <span class="radar-legend-name">{{ it.label }}</span>
            <span class="radar-legend-val">{{ it.value }}%</span>
          </div>
        </div>
      </div>

      <!-- 各科正确率 -->
      <div class="assessment-card glass-card">
        <div class="card-title"><span v-html="icons.bookOpen" class="card-title-icon"></span> 各科正确率</div>
        <div v-for="(data, subject) in assessment!.by_subject" :key="subject" class="subject-row">
          <span class="subject-label">{{ store.subjects[subject]?.name || subject }}</span>
          <div class="subject-bar-bg"><div class="subject-bar-fill" :style="{width: '100%', transform: 'scaleX(' + data.accuracy + ')' }"></div></div>
          <span class="subject-pct">{{ ((data?.accuracy ?? 0) * 100).toFixed(0) }}%</span>
          <span class="subject-count">({{ data.correct }}/{{ data.total }})</span>
        </div>
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
.inline-icon { display: inline-flex; vertical-align: middle; margin-right:var(--space-1); }
.inline-icon svg { width:1rem; height:1rem; }
.section-title-icon { display: inline-flex; vertical-align: middle; margin-right:0.375rem; }
.section-title-icon svg { width:1.25rem; height:1.25rem; }
.card-title-icon { display: inline-flex; vertical-align: middle; margin-right:0.375rem; }
.card-title-icon svg { width:1.125rem; height:1.125rem; }
.assessment-grid { display: grid; gap:var(--space-4); }
.assessment-card { padding:var(--space-5); }
.as-eyebrow { font-size: 11px; line-height: 1; letter-spacing: 0.16em; text-transform: uppercase; color: var(--accent-primary); font-weight: 600; margin-bottom: 10px; }
.card-title { font-size:var(--text-md); font-weight: var(--weight-semibold); color: var(--text-primary); margin-bottom:0.875rem; display: flex; align-items: center; }
.overview-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-3); }
.ov-stat { text-align: left; }
.ov-val { font-size:1.5rem; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; justify-content: flex-start; gap:var(--space-1); line-height:1.15; }
.ov-label { font-size:var(--text-xs); color: var(--color-text-3); margin-top:4px; display: block; }
/* 名称列定宽 + 进度条吃掉剩余空间：之前是 flex，label 只给 5rem（80px），
   「计算机网络概述」8 个字要 112px，被压成两行，13 行列表看着就散。 */
.subject-row { display: grid; grid-template-columns: 7rem minmax(0, 1fr) auto auto; align-items: center; gap:0.625rem; margin-bottom:0.625rem; }
.subject-label { font-size:var(--text-sm); color: var(--color-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.subject-bar-bg { height:0.375rem; background: var(--color-border); border-radius:var(--radius-full); overflow: hidden; }
/* 条色统一走主色：原先按 masteryColor 上绿/青/琥珀三色，和全站"单一主色"方向冲突，
   右侧 16 行变成一条彩虹。强弱已由条长表达，颜色不再重复编码。 */
.subject-bar-fill { height:100%; border-radius:var(--radius-full); width:100%; background: var(--color-accent); transform-origin:left; transition: transform var(--duration-slow) var(--ease-standard); }
.subject-pct { min-width:2.5rem; font-size:var(--text-sm); font-weight: var(--weight-semibold); color: var(--color-text); text-align: right; }
.subject-count { font-size:var(--text-xs); color: var(--color-text-3); white-space: nowrap; }
.weak-list { display: flex; flex-direction: column; gap:0.375rem; }
.weak-item { padding:var(--space-2) var(--space-3); background: var(--accent-primary-05); border-radius:var(--radius-sm); font-size:var(--text-sm); color: var(--color-text); border-left: 3px solid var(--color-accent); }
.weak-empty { font-size:var(--text-sm); color: var(--color-text-3); }
.suggestion-text { font-size:var(--text-base); line-height:var(--leading-relaxed); color: var(--text-secondary); }

/* ── 雷达图 ── */
/* 整卡原来 align-items:center，连带标题也居中；标题应与其它卡一样贴左，只有画布居中 */
.radar-card { display: flex; flex-direction: column; align-items: stretch; }
/* 原来 flex + center 居中；canvas 的位图宽度（size*dpr）远大于容器，会被 flex-shrink 压成一条，
   反而比 CSS 尺寸更小。改 block + margin auto 居中，尺寸完全由 canvas 自身决定。 */
.radar-wrapper { width: 100%; display: block; padding: var(--space-2) 0 var(--space-4); }
/* 原来 360px，在 1100px 宽的卡里居中，两侧各留 350px 空白；放大到 440 让卡内更饱满。
   显示宽高由 CSS 定（位图在 JS 里按 size*dpr 生成），aspect-ratio 保证不被压扁。 */
/* 画布显示尺寸由 JS 显式设定（size px），这里只做居中与兜底上限。
   wrapper 用 block 而非 flex：flex 会 shrink 画布，导致位图与显示尺寸不一致。 */
.radar-canvas { display: block; margin: 0 auto; max-width: 100%; }

/* 雷达 + 各科正确率两栏。左侧给雷达多一点，右侧列表够放下 13 行。
   雷达卡不存在时（数据不足 3 维）右卡自动占满整行。 */
/* 雷达 + 各科正确率两栏。左侧给雷达多一点，右侧列表够放下 13 行。
   雷达卡不存在时（数据不足 3 维）右卡自动占满整行。 */
.assessment-row { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: var(--space-4); align-items: start; margin-bottom: var(--space-4); }
@media (max-width: 900px) { .assessment-row { grid-template-columns: minmax(0, 1fr); } }

/* 窄屏图例：桌面隐藏（桌面上画布内已有名称，再列一遍是重复） */
.radar-legend { display: none; }
@media (max-width: 640px) {
  .radar-legend { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px var(--space-4); margin-top: var(--space-2); }
  .radar-legend-item { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .radar-legend-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
  .radar-legend-name { font-size: var(--text-xs); color: var(--color-text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .radar-legend-val { font-size: var(--text-xs); font-weight: 600; color: var(--color-text); margin-left: auto; flex-shrink: 0; }
}
@media (max-width: 900px) { .assessment-row { grid-template-columns: minmax(0, 1fr); } }

/* ── 路径调整建议卡片 ── */
.path-feedback-card { border: 1px solid var(--accent-primary-20); }
.path-adjusted-badge {
  margin-left: auto;
  font-size:0.625rem;
  padding:0.125rem var(--space-2);
  border-radius:var(--radius-full);
  background: var(--accent-success-10);
  color: var(--accent-success);
  font-weight: var(--weight-bold);
}
.path-feedback-loading { padding: var(--space-2) 0; }
.path-feedback-message { font-size:var(--text-base); line-height:1.6; color: var(--text-secondary); margin-bottom:var(--space-3); }
.next-step-section { margin-bottom:var(--space-3); }
.next-step-label { font-size:var(--text-sm); font-weight: var(--weight-semibold); color: var(--accent-primary); margin-bottom:0.375rem; display: flex; align-items: center; }
.next-step-tags { display: flex; flex-wrap: wrap; gap:0.375rem; }
.next-step-tag {
  font-size:var(--text-xs);
  padding:var(--space-1) 0.625rem;
  border-radius:var(--radius-full);
  background: var(--accent-primary-10);
  color: var(--accent-primary);
  font-weight: var(--weight-semibold);
  border: 1px solid var(--accent-primary-20);
}
.weak-suggestion-list { display: flex; flex-direction: column; gap:0.375rem; margin-bottom:var(--space-3); }
.weak-suggestion-item {
  padding:var(--space-2) var(--space-3);
  background: var(--bg-tertiary);
  border-radius:var(--radius-sm);
  border-left: 3px solid var(--accent-warm);
}
.weak-suggestion-topic { font-size:var(--text-sm); font-weight: var(--weight-semibold); color: var(--text-primary); display: block; }
.weak-suggestion-desc { font-size:var(--text-xs); color: var(--text-muted); margin-top:0.125rem; display: block; }
.path-go-btn { margin-top:var(--space-1); }

/* ── 无数据引导 ── */
.no-data-hero { text-align: center; padding: var(--space-10) var(--space-8); }
.no-data-icon { margin-bottom: var(--space-4); opacity: 0.4; }
.no-data-icon :deep(svg) { width: 3rem; height: 3rem; }
.no-data-title { font-size: var(--text-xl); font-weight: var(--weight-bold); color: var(--text-primary); margin-bottom: var(--space-2); }
.no-data-desc { font-size: var(--text-base); color: var(--text-muted); margin-bottom: var(--space-5); max-width: 400px; margin-left: auto; margin-right: auto; }
.no-data-features { display: flex; justify-content: center; flex-wrap: wrap; gap: var(--space-2); margin-bottom: var(--space-2); }
.nd-feature { font-size: var(--text-xs); padding: 0.375rem var(--space-3); background: var(--bg-tertiary); border-radius: var(--radius-full); color: var(--text-secondary); display: flex; align-items: center; gap: var(--space-1); }
.nd-feature :deep(svg) { width: 0.875rem; height: 0.875rem; }

/* ── 多角色2：移动端响应式适配 ── */
@media (max-width: 768px) {
  .assessment-grid { grid-template-columns: 1fr; }
  .overview-stats { grid-template-columns: repeat(2, 1fr); }
  .assessment-card { padding: var(--space-4); }
  /* 手机单栏卡宽约 326（含内边距），名称列 6.25rem 刚好放下 8 个字，进度条还剩 ~110 */
  .subject-row { grid-template-columns: 6.25rem minmax(0, 1fr) auto auto; gap: var(--space-2); }
  .radar-canvas { max-width: 100%; }
}
@media (max-width: 480px) {
  .overview-stats { grid-template-columns: repeat(2, 1fr); gap: var(--space-2); }
  .ov-val { font-size: var(--text-xl); }
  .suggestion-text { font-size: var(--text-sm); }
}
</style>
