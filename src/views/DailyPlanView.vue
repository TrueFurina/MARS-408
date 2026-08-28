<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, friendlyError } from '@/utils/api'

interface DailyTask {
  id: string
  type: string
  title: string
  subject: string
  chapter: string
  progress: number
  completed: boolean
  estimated_minutes: number
}

interface DailyPlan {
  id: number
  plan_date: string
  tasks: DailyTask[]
  total_tasks: number
  completed_tasks: number
  completion_rate: number
  target_exam_date: string
  target_score: number
  created_at: string
  updated_at: string
}

const loading = ref(true)
const error = ref('')
const plan = ref<DailyPlan | null>(null)
const history = ref<DailyPlan[]>([])
const activeTab = ref<'today' | 'history'>('today')
const selectedDate = ref(formatToday())

function formatToday() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function formatDisplayDate(dateStr: string) {
  try {
    const d = new Date(dateStr)
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const target = new Date(d)
    target.setHours(0, 0, 0, 0)
    const diff = Math.round((target.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
    if (diff === 0) return '今天'
    if (diff === -1) return '昨天'
    if (diff === 1) return '明天'
    return `${d.getMonth() + 1}月${d.getDate()}日`
  } catch { return dateStr }
}

function toast(type: string, msg: string) {
  const t = (window as any).__toast
  if (t?.[type]) t[type](msg)
  else window.dispatchEvent(new CustomEvent('netlearn-toast', { detail: { type, message: msg } }))
}

function taskIcon(type: string) {
  const icons: Record<string, string> = {
    wrong_review: '📕',
    study: '📖',
    practice: '✏️',
    summary: '📝',
  }
  return icons[type] || '📌'
}

function subjectColor(subject: string) {
  const colors: Record<string, string> = {
    '数据结构': '#3b82f6',
    '计算机组成原理': '#10b981',
    '操作系统': '#f59e0b',
    '计算机网络': '#8b5cf6',
    '综合': '#6b7280',
  }
  return colors[subject] || 'var(--accent-primary)'
}

const completedMinutes = computed(() => {
  if (!plan.value) return 0
  return plan.value.tasks
    .filter(t => t.completed)
    .reduce((sum, t) => sum + (t.estimated_minutes || 0), 0)
})

const totalMinutes = computed(() => {
  if (!plan.value) return 0
  return plan.value.tasks.reduce((sum, t) => sum + (t.estimated_minutes || 0), 0)
})

async function loadPlan(date?: string) {
  loading.value = true
  error.value = ''
  try {
    const url = date && date !== formatToday() ? `/daily-plan?date=${date}` : '/daily-plan'
    plan.value = await api.get<DailyPlan>(url)
  } catch (e: any) {
    error.value = friendlyError(e, '加载计划失败')
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  try {
    const res: any = await api.get('/daily-plan/history?days=14')
    history.value = res.plans || []
  } catch (e) {
    console.warn('加载历史计划失败:', e)
  }
}

async function toggleTask(task: DailyTask) {
  if (!plan.value) return
  try {
    const updated = await api.put<DailyPlan>(`/daily-plan/${plan.value.id}/task`, {
      task_id: task.id,
      completed: !task.completed,
      progress: !task.completed ? 100 : task.progress,
    })
    plan.value = updated
    if (!task.completed) toast('success', `已完成: ${task.title}`)
  } catch (e: any) {
    toast('error', friendlyError(e, '操作失败'))
  }
}

async function updateProgress(task: DailyTask, newProgress: number) {
  if (!plan.value) return
  try {
    const updated = await api.put<DailyPlan>(`/daily-plan/${plan.value.id}/task`, {
      task_id: task.id,
      progress: newProgress,
    })
    plan.value = updated
  } catch (e: any) {
    toast('error', friendlyError(e, '更新进度失败'))
  }
}

async function resetPlan() {
  if (!plan.value) return
  if (!confirm('确定要重置今日计划吗？所有任务进度将归零。')) return
  try {
    plan.value = await api.post<DailyPlan>(`/daily-plan/${plan.value.id}/reset`)
    toast('success', '计划已重置')
  } catch (e: any) {
    toast('error', friendlyError(e, '重置失败'))
  }
}

function changeDate(offset: number) {
  const d = new Date(selectedDate.value)
  d.setDate(d.getDate() + offset)
  selectedDate.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  loadPlan(selectedDate.value)
}

onMounted(() => {
  loadPlan()
  loadHistory()
})
</script>

<template>
  <div class="page-section">
    <div class="section-title">📅 每日学习计划</div>
    <div class="section-desc">为你自动生成每日学习任务，追踪学习进度</div>

    <!-- Tab -->
    <div class="tab-bar">
      <button class="tab-btn" :class="{ active: activeTab === 'today' }" @click="activeTab = 'today'">🎯 今日计划</button>
      <button class="tab-btn" :class="{ active: activeTab === 'history' }" @click="activeTab = 'history'">📆 历史回顾</button>
    </div>

    <!-- 今日计划 -->
    <div v-if="activeTab === 'today'">
      <!-- 日期切换 -->
      <div class="date-nav">
        <button class="date-btn" @click="changeDate(-1)">◀</button>
        <div class="date-label">
          <span class="date-main">{{ formatDisplayDate(selectedDate) }}</span>
          <span class="date-sub">{{ selectedDate }}</span>
        </div>
        <button class="date-btn" @click="changeDate(1)">▶</button>
      </div>

      <div v-if="loading" class="empty-state"><div class="empty-title">加载中...</div></div>
      <div v-else-if="error" class="empty-state">
        <div class="empty-title">⚠️ 加载失败</div>
        <div class="empty-desc">{{ error }}</div>
        <button class="engine-btn" @click="loadPlan(selectedDate)">重新加载</button>
      </div>
      <div v-else-if="plan">
        <!-- 进度总览 -->
        <div class="plan-overview glass-card">
          <div class="overview-top">
            <div class="progress-ring-wrap">
              <svg class="progress-ring" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="42" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="8"/>
                <circle cx="50" cy="50" r="42" fill="none" stroke="var(--accent-primary)" stroke-width="8"
                        stroke-linecap="round" :stroke-dasharray="264"
                        :stroke-dashoffset="264 - 264 * plan.completion_rate / 100"
                        transform="rotate(-90 50 50)"/>
              </svg>
              <div class="progress-text">
                <span class="rate-num">{{ plan.completion_rate }}%</span>
                <span class="rate-label">完成率</span>
              </div>
            </div>
            <div class="overview-stats">
              <div class="ov-stat">
                <strong>{{ plan.completed_tasks }}</strong>/{{ plan.total_tasks }}
                <span>任务</span>
              </div>
              <div class="ov-stat">
                <strong>{{ completedMinutes }}</strong>/{{ totalMinutes }}
                <span>分钟</span>
              </div>
            </div>
          </div>
          <div class="overview-actions">
            <button class="action-btn" @click="resetPlan">🔄 重置计划</button>
          </div>
        </div>

        <!-- 任务列表 -->
        <div class="task-list">
          <div v-for="task in plan.tasks" :key="task.id" class="task-card glass-card" :class="{ completed: task.completed }">
            <div class="task-left">
              <button class="check-btn" :class="{ checked: task.completed }" @click="toggleTask(task)">
                <span v-if="task.completed">✓</span>
              </button>
            </div>
            <div class="task-body">
              <div class="task-header">
                <span class="task-icon">{{ taskIcon(task.type) }}</span>
                <span class="task-title">{{ task.title }}</span>
                <span class="task-subject" :style="{ background: subjectColor(task.subject) + '20', color: subjectColor(task.subject) }">
                  {{ task.subject }}
                </span>
              </div>
              <div class="task-progress-row">
                <input type="range" min="0" max="100" :value="task.progress" class="progress-slider"
                       @input="(e: any) => updateProgress(task, parseInt(e.target.value))"
                       :disabled="task.completed"/>
                <span class="progress-pct">{{ task.progress }}%</span>
              </div>
              <div class="task-meta">
                <span class="task-time">⏱ 预计 {{ task.estimated_minutes }} 分钟</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 鼓励语 -->
        <div v-if="plan.completion_rate === 100" class="encourage-msg">
          🎉 太棒了！今日任务全部完成，继续保持！
        </div>
        <div v-else-if="plan.completion_rate >= 50" class="encourage-msg half">
          💪 已经完成一半以上了，加油！
        </div>
      </div>
    </div>

    <!-- 历史回顾 -->
    <div v-if="activeTab === 'history'" class="history-view">
      <div v-if="history.length === 0" class="empty-state">
        <div class="empty-title">暂无历史记录</div>
        <div class="empty-desc">完成计划后，这里会展示你的学习轨迹</div>
      </div>
      <div v-else class="history-list">
        <div v-for="h in history" :key="h.id" class="history-card glass-card">
          <div class="h-date">{{ formatDisplayDate(h.plan_date) }} <small>{{ h.plan_date }}</small></div>
          <div class="h-bar-wrap">
            <div class="h-bar">
              <div class="h-bar-fill" :style="{ width: h.completion_rate + '%' }"></div>
            </div>
            <span class="h-rate">{{ h.completion_rate }}%</span>
          </div>
          <div class="h-meta">
            <span>{{ h.completed_tasks }}/{{ h.total_tasks }} 任务</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tab-bar { display: flex; gap: 8px; margin-bottom: 16px; border-bottom: 1px solid var(--glass-border); }
.tab-btn {
  padding: 8px 18px; background: transparent; border: none; cursor: pointer;
  font-size: 14px; color: var(--text-muted); border-bottom: 2px solid transparent;
}
.tab-btn.active { color: var(--accent-primary); border-bottom-color: var(--accent-primary); font-weight: 600; }

.date-nav { display: flex; align-items: center; justify-content: center; gap: 20px; margin-bottom: 16px; }
.date-btn {
  width: 36px; height: 36px; border-radius: 50%; cursor: pointer;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  color: var(--text-primary); font-size: 14px; transition: var(--transition);
}
.date-btn:hover { border-color: var(--accent-primary); color: var(--accent-primary); }
.date-label { text-align: center; }
.date-main { display: block; font-size: 18px; font-weight: 700; }
.date-sub { font-size: 12px; color: var(--text-muted); }

.plan-overview {
  padding: 20px; margin-bottom: 16px;
  display: flex; flex-direction: column; gap: 16px;
}
.overview-top { display: flex; align-items: center; gap: 24px; }
.progress-ring-wrap { position: relative; width: 100px; height: 100px; flex-shrink: 0; }
.progress-ring { width: 100%; height: 100%; transform: scale(1); }
.progress-text {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  text-align: center;
}
.rate-num { display: block; font-size: 20px; font-weight: 700; color: var(--accent-primary); }
.rate-label { font-size: 11px; color: var(--text-muted); }
.overview-stats { flex: 1; display: flex; flex-direction: column; gap: 8px; }
.ov-stat { font-size: 14px; color: var(--text-muted); }
.ov-stat strong { font-size: 22px; color: var(--text-primary); margin-right: 6px; }
.ov-stat span { font-size: 12px; }
.overview-actions { display: flex; gap: 8px; }
.action-btn {
  padding: 7px 16px; border-radius: var(--radius-sm); cursor: pointer; font-size: 13px;
  background: var(--accent-primary-10); color: var(--accent-primary);
  border: 1px solid var(--accent-primary); transition: var(--transition);
}
.action-btn:hover { background: var(--accent-primary); color: white; }

.task-list { display: flex; flex-direction: column; gap: 10px; }
.task-card {
  display: flex; gap: 14px; padding: 14px 16px;
  transition: var(--transition);
}
.task-card.completed { opacity: 0.6; }
.task-card.completed .task-title { text-decoration: line-through; }

.check-btn {
  width: 24px; height: 24px; border-radius: 50%; cursor: pointer; flex-shrink: 0;
  background: transparent; border: 2px solid var(--glass-border);
  display: flex; align-items: center; justify-content: center;
  color: white; font-size: 13px; font-weight: 700; transition: var(--transition);
  margin-top: 2px;
}
.check-btn.checked { background: #22c55e; border-color: #22c55e; }
.check-btn:hover { border-color: var(--accent-primary); }

.task-body { flex: 1; min-width: 0; }
.task-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.task-icon { font-size: 16px; }
.task-title { font-size: 14px; font-weight: 600; flex: 1; min-width: 0; }
.task-subject {
  padding: 2px 8px; border-radius: 8px; font-size: 11px; font-weight: 600;
}

.task-progress-row { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.progress-slider {
  flex: 1; -webkit-appearance: none; appearance: none; height: 6px;
  border-radius: 3px; background: rgba(255,255,255,0.08); outline: none; cursor: pointer;
}
.progress-slider::-webkit-slider-thumb {
  -webkit-appearance: none; width: 14px; height: 14px; border-radius: 50%;
  background: var(--accent-primary); cursor: pointer; border: 2px solid white;
}
.progress-slider:disabled { opacity: 0.4; cursor: not-allowed; }
.progress-pct { font-size: 12px; color: var(--text-muted); width: 38px; text-align: right; }

.task-meta { font-size: 12px; color: var(--text-muted); }

.encourage-msg {
  margin-top: 16px; padding: 14px 20px; border-radius: var(--radius-md); text-align: center;
  background: linear-gradient(135deg, rgba(34,197,94,0.12), rgba(16,185,129,0.08));
  border: 1px solid rgba(34,197,94,0.3); font-size: 14px; font-weight: 500;
}
.encourage-msg.half {
  background: linear-gradient(135deg, rgba(245,158,11,0.12), rgba(234,88,12,0.08));
  border-color: rgba(245,158,11,0.3);
}

.history-view { display: flex; flex-direction: column; gap: 10px; }
.history-card { padding: 14px 18px; }
.h-date { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.h-date small { font-weight: 400; color: var(--text-muted); margin-left: 8px; font-size: 12px; }
.h-bar-wrap { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.h-bar { flex: 1; height: 10px; background: rgba(255,255,255,0.06); border-radius: 5px; overflow: hidden; }
.h-bar-fill { height: 100%; background: linear-gradient(90deg, var(--accent-primary), #8b5cf6); border-radius: 5px; transition: width 0.5s; }
.h-rate { font-size: 13px; font-weight: 600; color: var(--accent-primary); min-width: 48px; text-align: right; }
.h-meta { font-size: 12px; color: var(--text-muted); }
</style>
