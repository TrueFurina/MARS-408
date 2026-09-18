<script setup lang="ts">
// 职业素养测评页（对照实验载体）：10 题分档计分 → 六维雷达条 → 前后测对比
import { computed, onMounted, ref } from 'vue'
import { api, ApiError } from '@/utils/api'

interface Question {
  id: number
  dim: string
  type: string
  stem: string
  options: string[]
}
interface SubmitResult {
  total_score: number
  dim_scores: Record<string, number>
  phase: string
  message: string
}
interface PhaseReport {
  total: number | null
  dims: Record<string, number>
}
interface Report {
  user_id: string
  pre: PhaseReport
  post: PhaseReport
  delta: Record<string, number | null> | null
  dimensions: string[]
}

const questions = ref<Question[]>([])
const dimensions = ref<string[]>([])
const currentIndex = ref(0)
const answers = ref<Record<number, number>>({})   // qid -> option_index
const phase = ref<'pre' | 'post'>('pre')
const className = ref('')
const userName = ref('')
const submitting = ref(false)
const loading = ref(true)
const errorMsg = ref('')
const result = ref<SubmitResult | null>(null)
const report = ref<Report | null>(null)

const answeredCount = computed(() => Object.keys(answers.value).length)
const allAnswered = computed(() => questions.value.length > 0 && answeredCount.value === questions.value.length)
const currentQ = computed(() => questions.value[currentIndex.value])

function scoreColor(score: number): string {
  if (score >= 90) return '#22c55e'
  if (score >= 75) return '#84cc16'
  if (score >= 60) return '#eab308'
  return '#ef4444'
}

async function loadReport() {
  try {
    report.value = await api.get<Report>('/literacy/report/demo')
  } catch {
    report.value = null // 无历史记录，正常（首次前测）
  }
}

onMounted(async () => {
  try {
    const data = await api.get<{ total: number; dimensions: string[]; questions: Question[] }>('/literacy/questions')
    questions.value = data.questions
    dimensions.value = data.dimensions
    await loadReport()
  } catch (e) {
    errorMsg.value = e instanceof ApiError ? e.message : '题库加载失败，请确认后端服务已启动'
  } finally {
    loading.value = false
  }
})

function pick(optionIndex: number) {
  if (!currentQ.value) return
  answers.value[currentQ.value.id] = optionIndex
  if (currentIndex.value < questions.value.length - 1) {
    setTimeout(() => { currentIndex.value++ }, 200)
  }
}

async function submit() {
  if (!allAnswered.value || submitting.value) return
  submitting.value = true
  errorMsg.value = ''
  try {
    result.value = await api.post<SubmitResult>('/literacy/submit', {
      phase: phase.value,
      class_name: className.value,
      user_name: userName.value,
      answers: Object.entries(answers.value).map(([qid, option_index]) => ({
        qid: Number(qid), option_index,
      })),
    })
    await loadReport()
  } catch (e) {
    errorMsg.value = e instanceof ApiError ? e.message : '提交失败，请重试'
  } finally {
    submitting.value = false
  }
}

function restart(nextPhase: 'pre' | 'post') {
  phase.value = nextPhase
  answers.value = {}
  currentIndex.value = 0
  result.value = null
}
</script>

<template>
  <div class="literacy-page">
    <header class="page-head">
      <h1>职业素养测评</h1>
      <p class="sub">六维通用素养 · 行为情境分档计分（无对错口径，选项代表行为成熟度）</p>
    </header>

    <!-- 加载/错误态 -->
    <div v-if="loading" class="state-card">题库加载中…</div>
    <div v-else-if="errorMsg && !questions.length" class="state-card error">{{ errorMsg }}</div>

    <template v-else>
      <!-- 结果页 -->
      <section v-if="result" class="result-card">
        <div class="result-total">
          <span class="label">综合素养分</span>
          <span class="value" :style="{ color: scoreColor(result.total_score) }">{{ result.total_score }}</span>
          <span class="phase-tag">{{ result.phase === 'pre' ? '前测' : '后测' }}</span>
        </div>
        <div class="dim-bars">
          <div v-for="d in dimensions" :key="d" class="dim-row">
            <span class="dim-name">{{ d }}</span>
            <div class="bar-track">
              <div class="bar-fill" :style="{ width: (result.dim_scores[d] || 0) + '%', background: scoreColor(result.dim_scores[d] || 0) }" />
            </div>
            <span class="dim-score">{{ result.dim_scores[d] ?? 0 }}</span>
          </div>
        </div>
        <p class="result-msg">{{ result.message }}</p>
        <div class="result-actions">
          <button class="btn ghost" @click="restart('pre')">重做前测</button>
          <button class="btn primary" @click="restart('post')">进入后测（8 周实训后）</button>
        </div>

        <!-- 前后测对比 -->
        <div v-if="report && report.pre.total != null && report.post.total != null" class="delta-box">
          <h3>前后测对比</h3>
          <div class="delta-total">
            前测 {{ report.pre.total }} → 后测 {{ report.post.total }}
            <strong :style="{ color: (report.post.total! - report.pre.total!) >= 0 ? '#22c55e' : '#ef4444' }">
              {{ ((report.post.total! - report.pre.total!) !== 0 ? ((report.post.total! - report.pre.total!) > 0 ? '+' : '') + (report.post.total! - report.pre.total!).toFixed(1) : '') }}
            </strong>
          </div>
          <div class="dim-bars">
            <div v-for="d in dimensions" :key="'d-' + d" class="dim-row">
              <span class="dim-name">{{ d }}</span>
              <div class="bar-track">
                <div class="bar-fill" :style="{ width: (report.post.dims[d] || 0) + '%', background: scoreColor(report.post.dims[d] || 0) }" />
              </div>
              <span class="dim-score">{{ report.pre.dims[d] ?? '-' }} → {{ report.post.dims[d] ?? '-' }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 答题页 -->
      <section v-else class="quiz-card">
        <div class="quiz-meta">
          <span>第 {{ currentIndex + 1 }} / {{ questions.length }} 题</span>
          <span class="dim-tag">{{ currentQ?.dim }}</span>
          <span class="phase-switch">
            测评阶段：
            <label><input type="radio" value="pre" v-model="phase" /> 前测</label>
            <label><input type="radio" value="post" v-model="phase" /> 后测</label>
          </span>
        </div>
        <div class="progress-track"><div class="progress-fill" :style="{ width: (answeredCount / questions.length * 100) + '%' }" /></div>

        <h2 class="stem">{{ currentQ?.stem }}</h2>
        <div class="options">
          <button
            v-for="(opt, i) in currentQ?.options"
            :key="i"
            class="option-btn"
            :class="{ selected: answers[currentQ!.id] === i }"
            @click="pick(i)"
          >{{ opt }}</button>
        </div>

        <div class="quiz-nav">
          <button class="btn ghost" :disabled="currentIndex === 0" @click="currentIndex--">上一题</button>
          <button class="btn ghost" :disabled="currentIndex >= questions.length - 1" @click="currentIndex++">下一题</button>
        </div>

        <div class="submit-row">
          <input v-model="userName" class="text-input" placeholder="姓名（脱敏可填学号后4位）" />
          <input v-model="className" class="text-input" placeholder="班级（如：信息安全1班-实验组）" />
          <button class="btn primary" :disabled="!allAnswered || submitting" @click="submit">
            {{ submitting ? '提交中…' : `提交测评（${answeredCount}/${questions.length}）` }}
          </button>
        </div>
        <p v-if="errorMsg" class="error-text">{{ errorMsg }}</p>
      </section>
    </template>
  </div>
</template>

<style>
.literacy-page { max-width: 760px; margin: 0 auto; padding: var(--space-6) var(--space-4) var(--space-12); }
.page-head h1 { font-size: var(--text-3xl); margin: 0 0 var(--space-1); }
.page-head .sub { color: #64748b; font-size: var(--text-sm); margin: 0 0 var(--space-5); } /* token-exception */
.state-card { padding: var(--space-10); text-align: center; background: var(--surface); border-radius: 12px; border: 1px solid var(--border); }
.state-card.error { color: var(--color-danger); }

.quiz-card, .result-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: var(--space-6); }
.quiz-meta { display: flex; align-items: center; gap: var(--space-3); font-size: var(--text-sm); color: #64748b; margin-bottom: var(--space-2); flex-wrap: wrap; } /* token-exception */
.dim-tag { background: #eef2ff; color: #4f46e5; padding: 2px 10px; border-radius: 999px; font-size: var(--text-xs); } /* token-exception */
.phase-switch label { margin-right: 10px; cursor: pointer; }
.progress-track { height: 6px; background: #e2e8f0; border-radius: 999px; overflow: hidden; margin-bottom: var(--space-5); } /* token-exception */
.progress-fill { height: 100%; background: #4f46e5; transition: width .3s; } /* token-exception */
.stem { font-size: 17px; line-height: 1.6; margin: 0 0 18px; }
.options { display: flex; flex-direction: column; gap: 10px; }
.option-btn { text-align: left; padding: 14px var(--space-4); border-radius: 10px; border: 1.5px solid var(--border); background: transparent; cursor: pointer; font-size: var(--text-base); line-height: 1.5; transition: all .15s; }
.option-btn:hover { border-color: #a5b4fc; } /* token-exception */
.option-btn.selected { border-color: #4f46e5; background: #eef2ff; } /* token-exception */
.quiz-nav { display: flex; gap: 10px; margin-top: 18px; }
.submit-row { display: flex; gap: 10px; margin-top: 18px; flex-wrap: wrap; }
.text-input { flex: 1; min-width: 160px; padding: 9px var(--space-3); border: 1.5px solid var(--border); border-radius: 8px; font-size: var(--text-sm); }
.btn { padding: 9px 18px; border-radius: 8px; font-size: var(--text-base); cursor: pointer; border: 1.5px solid transparent; }
.btn.primary { background: #4f46e5; color: #fff; } /* token-exception */
.btn.primary:disabled { opacity: .5; cursor: not-allowed; }
.btn.ghost { background: transparent; border-color: var(--border); color: #475569; } /* token-exception */
.btn.ghost:disabled { opacity: .4; cursor: not-allowed; }

.result-total { text-align: center; margin-bottom: var(--space-6); }
.result-total .label { display: block; color: #64748b; font-size: var(--text-sm); } /* token-exception */
.result-total .value { font-size: 52px; font-weight: var(--weight-bold); }
.phase-tag { display: inline-block; margin-left: var(--space-2); background: #eef2ff; color: #4f46e5; padding: 2px 10px; border-radius: 999px; font-size: var(--text-xs); vertical-align: super; } /* token-exception */
.dim-bars { display: flex; flex-direction: column; gap: 10px; margin-bottom: var(--space-5); }
.dim-row { display: grid; grid-template-columns: 76px 1fr 96px; align-items: center; gap: var(--space-3); font-size: var(--text-sm); }
.bar-track { height: 10px; background: #f1f5f9; border-radius: 999px; overflow: hidden; } /* token-exception */
.bar-fill { height: 100%; border-radius: 999px; transition: width .5s; }
.dim-score { color: #475569; text-align: right; } /* token-exception */
.result-msg { text-align: center; color: var(--color-success); font-size: var(--text-sm); }
.result-actions { display: flex; gap: 10px; justify-content: center; margin-top: 14px; }

.delta-box { margin-top: var(--space-7); padding-top: var(--space-5); border-top: 1px dashed var(--border); }
.delta-box h3 { font-size: var(--text-md); margin: 0 0 10px; }
.delta-total { font-size: var(--text-base); margin-bottom: 14px; color: #334155; } /* token-exception */
.error-text { color: var(--color-danger); font-size: var(--text-sm); margin-top: 10px; }
</style>
