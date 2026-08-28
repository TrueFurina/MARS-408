<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, friendlyError } from '@/utils/api'

interface WrongQuestion {
  id: number
  question_id: string
  question: Record<string, any>
  subject: string
  chapter: string
  knowledge_point: string
  wrong_answer: string
  correct_answer: string
  error_type: string
  wrong_count: number
  mastered: boolean
  last_wrong_at: string
  first_wrong_at: string
}

interface WrongStats {
  total: number
  mastered: number
  unmastered: number
  mastery_rate: number
  subject_distribution: { subject: string; count: number; mastered: number }[]
  error_type_distribution: { type: string; count: number }[]
}

const SUBJECT_NAMES: Record<string, string> = {
  computer_network: '计算机网络',
  data_structures: '数据结构',
  computer_organization: '计算机组成原理',
  operating_system: '操作系统',
  '数据结构': '数据结构',
  '计算机组成原理': '计算机组成原理',
  '操作系统': '操作系统',
  '计算机网络': '计算机网络',
  '综合': '综合',
}

const ERROR_TYPE_NAMES: Record<string, string> = {
  concept: '概念理解',
  calculation: '计算错误',
  careless: '粗心失误',
  memory: '记忆遗忘',
  quiz_wrong: '答题错误',
  retry_wrong: '重做仍错',
}

const loading = ref(true)
const error = ref('')
const questions = ref<WrongQuestion[]>([])
const stats = ref<WrongStats | null>(null)
const total = ref(0)
const page = ref(1)
const pageSize = 20
const filterSubject = ref('')
const filterMastered = ref<'' | 'true' | 'false'>('')
const activeTab = ref<'list' | 'stats'>('list')

const subjectOptions = computed(() => {
  if (!stats.value) return []
  return stats.value.subject_distribution.map(s => s.subject)
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

function toast(type: string, msg: string) {
  const t = (window as any).__toast
  if (t?.[type]) t[type](msg)
  else window.dispatchEvent(new CustomEvent('netlearn-toast', { detail: { type, message: msg } }))
}

function subjectName(s: string) {
  if (s.startsWith('ds_')) return '数据结构'
  if (s.startsWith('co_')) return '计算机组成原理'
  if (s.startsWith('os_')) return '操作系统'
  if (!s || s === 'unknown') return '综合'
  return SUBJECT_NAMES[s] || s
}

function errorTypeName(t: string) {
  return ERROR_TYPE_NAMES[t] || t
}

function formatDate(s: string) {
  if (!s) return ''
  try { return new Date(s).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }
  catch { return s }
}

function getQuestionText(q: WrongQuestion) {
  const qq = q.question || {}
  return qq.text || qq.question || qq.question_text || '(无题干)'
}

function getQuestionOptions(q: WrongQuestion): string[] {
  const qq = q.question || {}
  return qq.options || []
}

async function loadStats() {
  try {
    const res = await api.get<WrongStats>('/wrong-questions/stats')
    stats.value = res
  } catch (e) {
    console.warn('加载错题统计失败:', e)
  }
}

async function loadList() {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams()
    params.set('page', String(page.value))
    params.set('page_size', String(pageSize))
    if (filterSubject.value) params.set('subject', filterSubject.value)
    if (filterMastered.value !== '') params.set('mastered', filterMastered.value)
    const res: any = await api.get(`/wrong-questions?${params.toString()}`)
    questions.value = res.items || []
    total.value = res.total || 0
  } catch (e: any) {
    error.value = friendlyError(e, '加载错题失败')
  } finally {
    loading.value = false
  }
}

async function toggleMastered(q: WrongQuestion) {
  try {
    await api.put(`/wrong-questions/${q.id}/mastery`, { mastered: !q.mastered })
    q.mastered = !q.mastered
    toast('success', q.mastered ? '已标记为掌握' : '已取消掌握标记')
    loadStats()
  } catch (e: any) {
    toast('error', friendlyError(e, '操作失败'))
  }
}

async function deleteQ(q: WrongQuestion) {
  if (!confirm(`确定删除这道错题吗？`)) return
  try {
    await api.delete(`/wrong-questions/${q.id}`)
    toast('success', '已删除')
    loadList()
    loadStats()
  } catch (e: any) {
    toast('error', friendlyError(e, '删除失败'))
  }
}

function resetFilters() {
  filterSubject.value = ''
  filterMastered.value = ''
  page.value = 1
  loadList()
}

function changePage(p: number) {
  if (p < 1 || p > totalPages.value) return
  page.value = p
  loadList()
}

onMounted(() => {
  loadStats()
  loadList()
})
</script>

<template>
  <div class="page-section">
    <div class="section-title">📕 错题本</div>
    <div class="section-desc">自动收录答错的题目，按科目和知识点分类，支持标记掌握</div>

    <!-- 统计概览条 -->
    <div v-if="stats" class="stats-strip">
      <div class="stat-chip">
        <span class="stat-num">{{ stats.total }}</span>
        <span class="stat-label">错题总数</span>
      </div>
      <div class="stat-chip">
        <span class="stat-num mastered">{{ stats.mastered }}</span>
        <span class="stat-label">已掌握</span>
      </div>
      <div class="stat-chip">
        <span class="stat-num unmastered">{{ stats.unmastered }}</span>
        <span class="stat-label">待攻克</span>
      </div>
      <div class="stat-chip">
        <span class="stat-num rate">{{ stats.mastery_rate }}%</span>
        <span class="stat-label">掌握率</span>
      </div>
    </div>

    <!-- Tab -->
    <div class="tab-bar">
      <button class="tab-btn" :class="{ active: activeTab === 'list' }" @click="activeTab = 'list'">📋 错题列表</button>
      <button class="tab-btn" :class="{ active: activeTab === 'stats' }" @click="activeTab = 'stats'">📊 统计分析</button>
    </div>

    <!-- 列表视图 -->
    <div v-if="activeTab === 'list'">
      <!-- 筛选栏 -->
      <div class="filter-bar">
        <select v-model="filterSubject" @change="page = 1; loadList()" class="filter-select">
          <option value="">全部科目</option>
          <option v-for="s in subjectOptions" :key="s" :value="s">{{ subjectName(s) }}</option>
        </select>
        <select v-model="filterMastered" @change="page = 1; loadList()" class="filter-select">
          <option value="">全部状态</option>
          <option value="false">未掌握</option>
          <option value="true">已掌握</option>
        </select>
        <button class="filter-reset" @click="resetFilters">重置</button>
      </div>

      <div v-if="loading" class="empty-state"><div class="empty-title">加载中...</div></div>
      <div v-else-if="error" class="empty-state">
        <div class="empty-title">⚠️ 加载失败</div>
        <div class="empty-desc">{{ error }}</div>
        <button class="engine-btn" @click="loadList">重新加载</button>
      </div>
      <div v-else-if="questions.length === 0" class="empty-state">
        <div class="empty-title">🎉 暂无错题</div>
        <div class="empty-desc">继续练习，答错的题目会自动收录到这里</div>
      </div>
      <div v-else class="question-list">
        <div v-for="q in questions" :key="q.id" class="question-card glass-card" :class="{ mastered: q.mastered }">
          <div class="q-header">
            <span class="q-subject">{{ subjectName(q.subject) }}</span>
            <span v-if="q.chapter" class="q-chapter">{{ q.chapter }}</span>
            <span class="q-count" v-if="q.wrong_count > 1">×{{ q.wrong_count }}</span>
            <span v-if="q.mastered" class="q-badge mastered-badge">✅ 已掌握</span>
            <span v-else class="q-badge unmastered-badge">❌ 未掌握</span>
          </div>
          <div class="q-text" v-html="getQuestionText(q)"></div>
          <div v-if="getQuestionOptions(q).length" class="q-options">
            <div v-for="(opt, i) in getQuestionOptions(q)" :key="i" class="q-opt"
                 :class="{ 'opt-correct': opt.includes(q.correct_answer) || (typeof q.correct_answer === 'number' && i === q.correct_answer) }">
              {{ opt }}
            </div>
          </div>
          <div class="q-answer-row">
            <span class="q-correct-answer">正确答案: {{ q.correct_answer }}</span>
            <span class="q-wrong-answer">你的答案: <em>{{ q.wrong_answer || '(未记录)' }}</em></span>
          </div>
          <div class="q-meta">
            <span v-if="q.error_type" class="q-error-type">{{ errorTypeName(q.error_type) }}</span>
            <span class="q-time">最近错误: {{ formatDate(q.last_wrong_at) }}</span>
          </div>
          <div class="q-actions">
            <button class="action-btn" @click="toggleMastered(q)">
              {{ q.mastered ? '取消掌握' : '标记掌握' }}
            </button>
            <button class="action-btn danger" @click="deleteQ(q)">删除</button>
          </div>
        </div>
      </div>

      <!-- 分页 -->
      <div v-if="totalPages > 1 && !loading" class="pagination">
        <button :disabled="page <= 1" @click="changePage(page - 1)">上一页</button>
        <span class="page-info">{{ page }} / {{ totalPages }} (共 {{ total }} 题)</span>
        <button :disabled="page >= totalPages" @click="changePage(page + 1)">下一页</button>
      </div>
    </div>

    <!-- 统计视图 -->
    <div v-if="activeTab === 'stats'" class="stats-view">
      <div v-if="!stats" class="empty-state">暂无统计数据</div>
      <div v-else>
        <div class="stats-section">
          <div class="stats-section-title">📚 科目分布</div>
          <div class="bar-list">
            <div v-for="s in stats.subject_distribution" :key="s.subject" class="bar-item">
              <div class="bar-label">{{ subjectName(s.subject) }}</div>
              <div class="bar-track">
                <div class="bar-fill" :style="{ width: stats.total ? (s.count / stats.total * 100) + '%' : '0%' }"></div>
                <div class="bar-fill mastered-fill" :style="{ width: stats.total ? (s.mastered / stats.total * 100) + '%' : '0%' }"></div>
              </div>
              <div class="bar-num">{{ s.mastered }}/{{ s.count }}</div>
            </div>
          </div>
        </div>

        <div class="stats-section">
          <div class="stats-section-title">⚠️ 错误类型分布</div>
          <div class="tag-list">
            <div v-for="e in stats.error_type_distribution" :key="e.type" class="tag-item">
              <span class="tag-name">{{ errorTypeName(e.type) }}</span>
              <span class="tag-count">{{ e.count }} 题</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stats-strip {
  display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px;
}
.stat-chip {
  flex: 1; min-width: 100px; padding: 14px;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius-md); text-align: center;
}
.stat-num { display: block; font-size: 22px; font-weight: 700; color: var(--accent-primary); }
.stat-num.mastered { color: #22c55e; }
.stat-num.unmastered { color: #ef4444; }
.stat-num.rate { color: #f59e0b; }
.stat-label { font-size: 12px; color: var(--text-muted); }

.tab-bar { display: flex; gap: 8px; margin-bottom: 16px; border-bottom: 1px solid var(--glass-border); }
.tab-btn {
  padding: 8px 18px; background: transparent; border: none; cursor: pointer;
  font-size: 14px; color: var(--text-muted); border-bottom: 2px solid transparent;
  transition: var(--transition);
}
.tab-btn.active { color: var(--accent-primary); border-bottom-color: var(--accent-primary); font-weight: 600; }

.filter-bar { display: flex; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; align-items: center; }
.filter-select {
  padding: 7px 12px; border-radius: var(--radius-sm);
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  color: var(--text-primary); font-size: 13px; cursor: pointer;
}
.filter-reset {
  padding: 7px 14px; border-radius: var(--radius-sm); cursor: pointer;
  background: transparent; border: 1px solid var(--glass-border);
  color: var(--text-muted); font-size: 13px; transition: var(--transition);
}
.filter-reset:hover { border-color: var(--accent-primary); color: var(--accent-primary); }

.question-list { display: flex; flex-direction: column; gap: 12px; }
.question-card { padding: 16px; transition: var(--transition); }
.question-card.mastered { opacity: 0.7; border-color: rgba(34,197,94,0.3); }

.q-header { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
.q-subject {
  padding: 2px 10px; border-radius: 10px; font-size: 12px; font-weight: 600;
  background: var(--accent-primary-10); color: var(--accent-primary);
}
.q-chapter { font-size: 12px; color: var(--text-muted); }
.q-count {
  padding: 1px 7px; border-radius: 8px; font-size: 11px; font-weight: 700;
  background: rgba(239,68,68,0.15); color: #ef4444;
}
.q-badge { margin-left: auto; font-size: 12px; padding: 2px 8px; border-radius: 8px; }
.mastered-badge { background: rgba(34,197,94,0.12); color: #22c55e; }
.unmastered-badge { background: rgba(239,68,68,0.12); color: #ef4444; }

.q-text { font-size: 14px; line-height: 1.7; margin-bottom: 10px; color: var(--text-primary); }
.q-options { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
.q-opt {
  padding: 7px 12px; border-radius: var(--radius-sm); font-size: 13px;
  background: rgba(255,255,255,0.03); border: 1px solid var(--glass-border);
}
.q-opt.opt-correct {
  background: rgba(34,197,94,0.08); border-color: rgba(34,197,94,0.4); color: #22c55e;
}

.q-answer-row { display: flex; gap: 16px; font-size: 13px; margin-bottom: 8px; flex-wrap: wrap; }
.q-correct-answer { color: #22c55e; font-weight: 600; }
.q-wrong-answer { color: var(--text-muted); }
.q-wrong-answer em { color: #ef4444; font-style: normal; }

.q-meta { display: flex; gap: 12px; font-size: 12px; color: var(--text-muted); margin-bottom: 10px; }
.q-error-type {
  padding: 1px 8px; border-radius: 8px;
  background: rgba(245,158,11,0.1); color: #f59e0b;
}

.q-actions { display: flex; gap: 8px; }
.action-btn {
  padding: 6px 14px; border-radius: var(--radius-sm); cursor: pointer; font-size: 12px;
  background: var(--accent-primary-10); color: var(--accent-primary);
  border: 1px solid var(--accent-primary); transition: var(--transition);
}
.action-btn:hover { background: var(--accent-primary); color: white; }
.action-btn.danger { background: transparent; color: #ef4444; border-color: rgba(239,68,68,0.4); }
.action-btn.danger:hover { background: #ef4444; color: white; }

.pagination {
  display: flex; justify-content: center; align-items: center; gap: 14px;
  margin-top: 20px; padding: 14px;
}
.pagination button {
  padding: 6px 16px; border-radius: var(--radius-sm); cursor: pointer;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  color: var(--text-primary); font-size: 13px; transition: var(--transition);
}
.pagination button:hover:not(:disabled) { border-color: var(--accent-primary); color: var(--accent-primary); }
.pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
.page-info { font-size: 13px; color: var(--text-muted); }

.stats-view { display: flex; flex-direction: column; gap: 20px; }
.stats-section { padding: 16px; background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: var(--radius-md); }
.stats-section-title { font-size: 15px; font-weight: 600; margin-bottom: 14px; }

.bar-list { display: flex; flex-direction: column; gap: 10px; }
.bar-item { display: flex; align-items: center; gap: 10px; }
.bar-label { width: 120px; font-size: 13px; flex-shrink: 0; }
.bar-track { flex: 1; height: 22px; background: rgba(255,255,255,0.05); border-radius: 6px; position: relative; overflow: hidden; }
.bar-fill { position: absolute; left: 0; top: 0; height: 100%; background: rgba(239,68,68,0.35); border-radius: 6px; transition: width 0.5s; }
.bar-fill.mastered-fill { background: rgba(34,197,94,0.5); }
.bar-num { width: 60px; text-align: right; font-size: 13px; color: var(--text-muted); flex-shrink: 0; }

.tag-list { display: flex; gap: 10px; flex-wrap: wrap; }
.tag-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 14px; border-radius: 20px;
  background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.2);
}
.tag-name { font-size: 13px; }
.tag-count { font-size: 12px; color: var(--text-muted); }
</style>
