<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useStudyStore } from '@/stores/studyStore'
import { icons } from '@/components/icons'
import StepQuiz from '@/components/StepQuiz.vue'
import { api } from '@/utils/api'

const store = useStudyStore()
const route = useRoute()
const showStepQuiz = ref(false)
const courseKey = ref('')
const subject = ref('')
const chapter = ref('')
const questionType = ref('all')
const difficulty = ref('all')
const questions = ref<any[]>([])
const loading = ref(false)
const error = ref('')

interface AnswerState { selected: number | null; revealed: boolean; correct: boolean }
const answers = ref<Record<number, AnswerState>>({})
const submitting = ref(false)
const feedback = ref<{
  total: number; correct: number; accuracy: number
  by_subject: Record<string, { total: number; correct: number; accuracy: number }>
  suggestions: string
  profileUpdated: boolean
} | null>(null)

// 题型中文显示（统一映射，覆盖所有可能 type，消除死分支）
const QUESTION_TYPE_LABELS: Record<string, string> = {
  choice: '选择题',
  single_choice: '选择题',
  fill: '填空题',
  short: '简答题',
  compute: '计算题',
}
function typeLabel(t: string): string {
  return QUESTION_TYPE_LABELS[t] || '题目'
}

// 难度中文显示
function difficultyLabel(d: string): string {
  const map: Record<string, string> = { easy: '简单', medium: '中等', hard: '困难' }
  return map[d] || d
}

// 从 URL query 自动选中课程（来自 ReviewView/ProfileView 跳转）
onMounted(async () => {
  // 确保 store.subjects 已加载（课程下拉依赖它）
  if (!store.subjects || Object.keys(store.subjects).length === 0) {
    try { await store.fetchSubjects() } catch { /* ignore */ }
  }
  const qCourse = route.query.course as string
  const qSubject = route.query.subject as string
  const qFocus = route.query.focus as string
  if (qCourse && store.courses[qCourse]) {
    courseKey.value = qCourse
    if (qSubject && store.courses[qCourse]?.chapters.some(c => c.key === qSubject)) {
      subject.value = qSubject
    }
  } else if (qFocus) {
    // 来自画像薄弱点跳转，尝试匹配章节
    for (const [ck, course] of Object.entries(store.courses)) {
      const found = course.chapters.find(c => c.name.includes(qFocus) || c.key === qFocus)
      if (found) {
        courseKey.value = ck
        subject.value = found.key
        break
      }
    }
  }
  loadMemoryOverview()
})

// L1/L2/L3 三层学情记忆（低侵入联动：刷题页展示记忆薄弱点提示，失败不影响主流程）
const memoryOverview = ref<any>(null)
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞刷题页 */ }
}

// 切换课程时清空章节选择（跳过首次挂载，避免与 onMounted URL 参数恢复冲突）
watch(courseKey, () => { subject.value = '' }, { flush: 'post' })

async function generateQuestions() {
  if (!subject.value) {
    error.value = '请先选择课程和章节'
    return
  }
  loading.value = true
  error.value = ''
  feedback.value = null
  answers.value = {}
  try {
    const result = await store.generateQuestions(
      subject.value,
      chapter.value,
      questionType.value,
      difficulty.value,
    )
    questions.value = (result && result.questions) || []
    if (questions.value.length === 0) {
      error.value = (result && result.message) || '未找到匹配的题目，请调整筛选条件'
    }
  } catch (e: any) {
    const msg = e?.message || '获取题目失败'
    error.value = msg.includes('401') || msg.includes('Unauthorized') || msg.includes('登录')
      ? '登录已过期，请重新登录后使用智能出题功能'
      : msg
    questions.value = []
  } finally {
    loading.value = false
  }
}

function selectAnswer(qIdx: number, optIdx: number) {
  const q = questions.value[qIdx]
  if (!q || answers.value[qIdx]?.revealed) return
  if (q.type === 'choice' || q.type === 'single_choice') {
    answers.value[qIdx] = { selected: optIdx, revealed: false, correct: q.answer === optIdx }
  } else {
    answers.value[qIdx] = { selected: optIdx, revealed: false, correct: false }
  }
}

function revealAnswer(qIdx: number) {
  const a = answers.value[qIdx]
  if (!a) return
  a.revealed = true
}

function allRevealed() {
  return questions.value.every((_, i) => answers.value[i]?.revealed)
}

async function submitAnswers() {
  if (submitting.value) return
  submitting.value = true
  try {
    const payload = {
      answers: questions.value.map((q, i) => ({
        question_id: q.id || `q${i}`,
        answer: answers.value[i]?.selected,
        subject: q.subject || subject.value, // 透传章节 key 给后端记录
      })),
      subject: subject.value,
    }
    const result = await store.submitQuiz(payload)
    feedback.value = result
  } catch (e: any) {
    feedback.value = {
      total: questions.value.length,
      correct: 0,
      accuracy: 0,
      by_subject: {},
      suggestions: '提交失败，请检查后端',
      profileUpdated: false,
    }
  } finally {
    submitting.value = false
  }
}

const canSubmit = computed(() => questions.value.length > 0 && !allRevealed())

async function refreshQuestions() { await generateQuestions() }
</script>

<template>
  <div class="page-section">
    <div class="section-title">智能出题</div>
    <div class="section-desc">根据知识点自动生成练习题，答题后更新学生画像</div>

    <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
    <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">
      <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);">🧠 记忆薄弱点:</span>
      <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" style="padding:3px 10px;border-radius:12px;background:rgba(239,68,68,0.12);color:var(--accent-danger);">{{ w }}</span>
    </div>

    <div class="mode-tabs" style="margin-bottom:14px;">
      <button class="mode-tab" :class="{ active: !showStepQuiz }" @click="showStepQuiz = false"><span class="tab-ic" v-html="icons.edit"></span>普通出题</button>
      <button class="mode-tab" :class="{ active: showStepQuiz }" @click="showStepQuiz = true"><span class="tab-ic" v-html="icons.clipboard"></span>步骤化答题</button>
      <router-link to="/quiz-history" class="mode-tab" style="text-decoration:none;margin-left:auto;"><span class="tab-ic" v-html="icons.chart"></span>答题历史</router-link>
    </div>

    <StepQuiz v-if="showStepQuiz" @back="showStepQuiz = false" />

    <div v-if="!showStepQuiz" class="rag-config">
      <select v-model="courseKey" class="rag-select">
        <option value="">选择课程</option>
        <option v-for="(course, ck) in store.courses" :key="ck" :value="ck">{{ course.name }}</option>
      </select>
      <select v-model="subject" class="rag-select">
        <option value="">选择章节</option>
        <template v-if="courseKey && store.courses[courseKey]">
          <option v-for="ch in (store.courses[courseKey]?.chapters ?? [])" :key="ch.key" :value="ch.key">{{ ch.name }}</option>
        </template>
      </select>
      <select v-model="questionType" class="rag-select">
        <option value="all">全部题型</option>
        <option value="choice">选择题</option>
        <option value="fill">填空题</option>
        <option value="compute">计算题</option>
      </select>
      <select v-model="difficulty" class="rag-select">
        <option value="all">全部难度</option>
        <option value="easy">简单</option>
        <option value="medium">中等</option>
        <option value="hard">困难</option>
      </select>
      <button class="engine-btn" @click="generateQuestions" :disabled="loading || !subject">
        {{ loading ? '生成中...' : '生成题目' }}
      </button>
    </div>

    <!-- 错误 -->
    <div v-if="error" class="engine-error" style="margin-bottom:16px;">
      {{ error }}
      <button v-if="error.includes('后端') || error.includes('失败')" class="engine-btn" style="margin-left:12px;padding:4px 12px;font-size:12px;" @click="generateQuestions">重试</button>
    </div>

    <!-- 加载 -->
    <div v-if="loading" class="empty-state">
      <div class="empty-title">正在生成题目...</div>
      <div class="empty-desc">AI 正在根据知识点生成练习题目</div>
    </div>

    <!-- 空态 -->
    <div v-else-if="!loading && questions.length === 0 && !error" class="empty-state">
      <div class="empty-quiz-icon" v-html="icons.quiz"></div>
      <div class="empty-title">选择课程开始练习</div>
      <div class="empty-desc">选择 408 四科中的任一课程和章节，点击「生成题目」，AI 将自动生成练习题</div>
    </div>

    <!-- 题目列表 -->
    <div v-else-if="questions.length > 0" class="quiz-list">
      <div v-for="(q, idx) in questions" :key="idx" class="quiz-card glass-card">
        <div class="quiz-meta">
          <span class="quiz-tag type">{{ typeLabel(q.type) }}</span>
          <span class="quiz-tag" :class="q.difficulty">{{ difficultyLabel(q.difficulty) }}</span>
          <span class="quiz-source">{{ q.source || q.subject || '' }}</span>
        </div>
        <div class="quiz-stem">{{ q.text }}</div>
        <div v-if="(q.type === 'choice' || q.type === 'single_choice') && q.options" class="quiz-options">
          <div v-for="(opt, oi) in q.options" :key="oi"
            class="quiz-option"
            :class="{
              selected: answers[idx]?.selected === oi,
              correct: answers[idx]?.revealed && q.answer === oi,
              wrong: answers[idx]?.revealed && answers[idx]?.selected === oi && q.answer !== oi,
            }"
            @click="selectAnswer(idx, oi as number)">
            <span class="option-letter">{{ 'ABCDEFGH'[oi as number] }}</span>
            <span class="option-text">{{ opt }}</span>
            <span v-if="answers[idx]?.revealed && q.answer === oi" class="option-correct">✓</span>
            <span v-if="answers[idx]?.revealed && answers[idx]?.selected === oi && q.answer !== oi" class="option-wrong">✗</span>
          </div>
        </div>
        <div v-if="answers[idx]?.revealed && q.explanation" class="quiz-explanation">
          <strong>解析：</strong>{{ q.explanation }}
        </div>
        <button v-if="answers[idx] && !answers[idx].revealed" class="reveal-btn" @click="revealAnswer(idx)">查看答案</button>
      </div>

      <div class="quiz-actions">
        <button class="engine-btn" @click="submitAnswers" :disabled="submitting || !canSubmit">
          {{ submitting ? '提交中...' : '提交并更新画像' }}
        </button>
        <button class="engine-btn glow-secondary" @click="refreshQuestions" :disabled="loading">
          重新生成
        </button>
      </div>

      <!-- 反馈 -->
      <div v-if="feedback" class="feedback-panel glass-card">
        <div class="feedback-title"><span class="tab-ic" v-html="icons.chart"></span>答题结果</div>
        <div class="feedback-stats">
          <div class="feedback-stat">
            <span class="feedback-stat-value" :style="{color: (feedback?.accuracy ?? 0) >= 0.6 ? 'var(--accent-success)' : 'var(--accent-danger)'}">
              {{ ((feedback?.accuracy ?? 0) * 100).toFixed(0) }}%
            </span>
            <span class="feedback-stat-label">正确率</span>
          </div>
          <div class="feedback-stat">
            <span class="feedback-stat-value">{{ feedback.correct }}/{{ feedback.total }}</span>
            <span class="feedback-stat-label">答对题数</span>
          </div>
        </div>
        <div v-if="feedback.suggestions" class="feedback-suggestions">
          <strong><span class="tab-ic" v-html="icons.lightbulb"></span>学习建议：</strong>{{ feedback.suggestions }}
        </div>
        <div v-if="feedback.profileUpdated" class="feedback-profile-updated">
          <span class="tab-ic" v-html="icons.checkCircle"></span> 画像已更新
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.quiz-list { display: flex; flex-direction: column; gap:1rem; }
.quiz-card {
  padding:1.25rem;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  border-radius:var(--radius-md);
}
.quiz-meta { display: flex; gap:0.5rem; margin-bottom:0.75rem; flex-wrap: wrap; align-items: center; }
.quiz-tag {
  font-size:0.6875rem; padding:0.1875rem 0.625rem; border-radius:var(--radius-full);
  font-weight: 600;
}
.quiz-tag.type { background: rgba(139,92,246,0.12); color: var(--subject-ds); }
.quiz-tag.easy { background: var(--accent-success-10); color: var(--accent-success); }
.quiz-tag.medium { background: rgba(245,158,11,0.12); color: var(--accent-warm); }
.quiz-tag.hard { background: var(--accent-danger-10); color: var(--accent-danger); }
.quiz-source { font-size:0.6875rem; color: var(--text-muted); margin-left:auto; }
.quiz-stem { font-size:0.9375rem; line-height:1.7; color: var(--text-primary); margin-bottom:0.875rem; }
.quiz-options { display: flex; flex-direction: column; gap:0.5rem; }
.quiz-option {
  display: flex; align-items: center; gap:0.75rem;
  padding:0.75rem 1rem; border-radius:var(--radius-sm);
  border: 1px solid var(--border-color); cursor: pointer;
  transition: var(--transition); background: var(--bg-input);
}
.quiz-option:hover { border-color: var(--accent-primary); background: var(--accent-primary-10); }
.quiz-option.selected { border-color: var(--accent-primary); box-shadow: 0 0 0 2px var(--accent-primary-10); }
.quiz-option.correct { border-color: var(--accent-success); background: var(--accent-success-10); }
.quiz-option.wrong { border-color: var(--accent-danger); background: var(--accent-danger-10); }
.option-letter {
  width:1.75rem; height:1.75rem; border-radius:50%;
  display: flex; align-items: center; justify-content: center;
  font-size:0.8125rem; font-weight: 700; flex-shrink: 0;
  background: var(--bg-tertiary); color: var(--text-secondary);
}
.quiz-option.selected .option-letter { background: var(--accent-primary); color: #fff; }
.quiz-option.correct .option-letter { background: var(--accent-success); color: #fff; }
.quiz-option.wrong .option-letter { background: var(--accent-danger); color: #fff; }
.option-text { flex: 1; font-size:0.875rem; color: var(--text-primary); }
.option-correct { color: var(--accent-success); font-weight: 700; font-size:1rem; }
.option-wrong { color: var(--accent-danger); font-weight: 700; font-size:1rem; }
.quiz-explanation {
  margin-top:0.75rem; padding:0.75rem 1rem; border-radius:var(--radius-sm);
  background: var(--bg-tertiary); font-size:0.8125rem; line-height:1.6;
  color: var(--text-secondary); border-left: 3px solid var(--accent-primary);
}
.reveal-btn {
  margin-top:0.625rem; padding:0.5rem 1.125rem; border-radius:var(--radius-full);
  border: 1px solid var(--border-color); background: var(--bg-tertiary);
  color: var(--text-secondary); font-size:0.8125rem; font-weight: 600; cursor: pointer;
  transition: var(--transition);
}
.reveal-btn:hover { border-color: var(--accent-primary); color: var(--accent-primary); }
.quiz-actions { display: flex; gap:0.75rem; margin-top:0.5rem; flex-wrap: wrap; }
.feedback-panel { padding:1.25rem; margin-top:1rem; }
.feedback-title { font-size:1rem; font-weight: 700; margin-bottom:0.875rem; color: var(--text-primary); }
.feedback-stats { display: flex; gap:1.5rem; margin-bottom:0.875rem; }
.feedback-stat { text-align: center; }
.feedback-stat-value { font-size:1.5rem; font-weight: 800; display: block; }
.feedback-stat-label { font-size:0.75rem; color: var(--text-muted); }
.feedback-suggestions { font-size:0.8125rem; color: var(--text-secondary); line-height:1.6; padding:0.75rem; background: var(--bg-tertiary); border-radius:var(--radius-sm); }
.feedback-profile-updated { margin-top:0.625rem; font-size:0.8125rem; color: var(--accent-success); font-weight: 600; }
.tab-ic {
  width: 1rem;
  height: 1rem;
  display: inline-flex;
  vertical-align: -2px;
  margin-right: 0.375rem;
}
.tab-ic :deep(svg) {
  width: 100%;
  height: 100%;
}
.empty-quiz-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 12px;
  opacity: 0.3;
  color: var(--accent-primary);
}
.empty-quiz-icon :deep(svg) {
  width: 100%;
  height: 100%;
}
.auto-match-hint {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.625rem 1rem; margin-bottom: 1rem;
  background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.2);
  border-radius: var(--radius-sm); font-size: 0.8125rem; color: var(--accent-warm);
}

/* ── 整改4：移动端适配（组委会点评"无多端"） ── */
@media (max-width: 768px) {
  .quiz-tabs, .practice-tabs { flex-wrap: wrap; gap: 0.375rem; }
  .quiz-tabs .tab-btn, .practice-tabs .tab-btn { flex: 1 1 auto; padding: 0.5rem 0.625rem; font-size: 0.8125rem; }
  .practice-header { flex-direction: column; align-items: stretch; gap: 0.625rem; }
  .practice-header .practice-title { font-size: 1.125rem; }
  .practice-header .practice-desc { font-size: 0.8125rem; }
  .quiz-list { gap: 0.75rem; }
  .quiz-card { padding: 0.875rem; }
  .step-answer-panel { padding: 1rem; }
  .step-options .step-option { padding: 0.625rem 0.75rem; font-size: 0.8125rem; }
  .step-quiz-header { flex-wrap: wrap; }
  .feedback-stats { gap: 0.75rem; flex-wrap: wrap; }
}
@media (max-width: 480px) {
  .quiz-meta { gap: 0.25rem; }
  .quiz-actions { flex-direction: column; gap: 0.5rem; }
  .quiz-actions .engine-btn { width: 100%; }
  .memory-mini-strip { font-size: 0.6875rem; }
}
</style>
