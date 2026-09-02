<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '@/utils/api'
import Skeleton from '@/components/Skeleton.vue'
import EmptyState from '@/components/EmptyState.vue'
import { icons } from '@/components/icons'

const emit = defineEmits(['back'])

const stepQuestions = ref<any[]>([])
const currentStepQuestion = ref<any>(null)
const currentStepIndex = ref(0)
const stepAnswers = ref<{ correct: boolean; hint: string; error_type: string }[]>([])
const stepFinished = ref(false)
const stepResult = ref<any>(null)
const stepLoading = ref(false)
const stepInput = ref('')
const stepError = ref('')

const stepOptionLabels = ['A', 'B', 'C', 'D', 'E', 'F']

async function loadStepQuestions() {
  stepLoading.value = true
  stepError.value = ''
  try {
    const data = await api.get<any>('/quiz/step-questions')
    stepQuestions.value = data.questions || []
  } catch (e: any) {
    stepError.value = '获取步骤化题目失败: ' + (e?.message || '')
  } finally {
    stepLoading.value = false
  }
}

async function startStepQuestion(qId: string) {
  stepLoading.value = true
  stepFinished.value = false
  stepAnswers.value = []
  stepResult.value = null
  currentStepIndex.value = 0
  stepError.value = ''
  try {
    const data = await api.get<any>(`/quiz/step-questions/${qId}`)
    currentStepQuestion.value = data
  } catch (e: any) {
    stepError.value = '获取题目详情失败: ' + (e?.message || '')
  } finally {
    stepLoading.value = false
  }
}

async function submitStepAnswer() {
  const answer = stepInput.value
  if (!answer.trim() || !currentStepQuestion.value) return
  stepLoading.value = true
  stepError.value = ''
  try {
    const data = await api.post<any>(`/quiz/step-questions/${currentStepQuestion.value.id}/answer`, {
      question_id: currentStepQuestion.value.id,
      step_index: currentStepIndex.value,
      answer: answer.trim(),
    })
    stepAnswers.value.push({ correct: data.correct, hint: data.hint, error_type: data.error_type })
    stepInput.value = ''

    if (data.finished) {
      stepFinished.value = true
      try {
        const wp = await api.get<any>('/quiz/weak-points')
        stepResult.value = { weak_points: wp.weak_points || [] }
      } catch { stepResult.value = { weak_points: [] } }
    } else {
      currentStepIndex.value = data.next_step
      // 更新当前步骤信息
      const qid = currentStepQuestion.value.id
      const resp = await api.get<any>(`/quiz/step-questions/${qid}`)
      currentStepQuestion.value.current_step = data.next_step
      currentStepQuestion.value.step_name = resp.step_name || `第${data.next_step+1}步`
      currentStepQuestion.value.step_description = resp.step_description || ''
      currentStepQuestion.value.step_type = resp.step_type || 'choice'
      currentStepQuestion.value.options = resp.options || []
    }
  } catch (e: any) {
    stepError.value = '提交答案失败: ' + (e?.message || '')
  } finally {
    stepLoading.value = false
  }
}

function reset() {
  currentStepQuestion.value = null
  stepAnswers.value = []
  stepFinished.value = false
  stepResult.value = null
  stepInput.value = ''
  loadStepQuestions()
}

// P2-6 补充：错因 → 推荐同类题（对接薄弱点追踪，形成闭环引导）
function recommendSimilar() {
  // 根据薄弱点概念/错因跳转刷题页，携带薄弱词供 PracticeView 读取
  const wp = stepResult.value?.weak_points || []
  const concept = wp[0]?.concept || currentStepQuestion.value?.chapter || ''
  if (concept) {
    sessionStorage.setItem('mars408_practice_topic', concept)
  }
  window.location.hash = '#/practice'
}

function goPractice() {
  sessionStorage.setItem('mars408_practice_focus', 'weak')
  window.location.hash = '#/practice'
}

// 键盘快捷键：1-6选择选项，Enter提交
function onKeydown(e: KeyboardEvent) {
  if (currentStepQuestion.value?.step_type === 'choice') {
    const idx = parseInt(e.key) - 1
    if (idx >= 0 && idx < (currentStepQuestion.value.options?.length || 0)) {
      stepInput.value = currentStepQuestion.value.options[idx]
    }
  }
  if (e.key === 'Enter' && stepInput.value.trim()) {
    submitStepAnswer()
  }
}

onMounted(() => {
  loadStepQuestions()
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="step-quiz">
    <div class="step-quiz-header">
      <button class="step-back-btn" @click="emit('back')">← 返回普通出题</button>
      <span class="step-quiz-title">📋 步骤化答题</span>
    </div>
    <div class="step-quiz-desc">复杂题目拆成多步，每步独立判断，系统分析错因并追踪薄弱点</div>

    <div v-if="stepError" class="engine-error">{{ stepError }}</div>

    <!-- 题目列表 -->
    <div v-if="!currentStepQuestion" class="step-question-list">
      <div v-if="stepLoading" class="skeleton-list">
        <Skeleton v-for="i in 3" :key="i" variant="block" height="5rem" radius="var(--radius-md)" />
      </div>
      <EmptyState v-else-if="stepQuestions.length === 0" :icon="icons.quiz" title="暂无步骤化题目" description="启动后端即可获取" />
      <div v-else v-for="q in stepQuestions" :key="q.id" class="step-question-card glass-card" role="button" tabindex="0" @click="startStepQuestion(q.id)" @keydown.enter="startStepQuestion(q.id)" @keydown.space.prevent="startStepQuestion(q.id)">
        <div class="step-q-meta">
          <span class="quiz-tag" :class="q.difficulty">{{ q.difficulty === 'easy' ? '简单' : q.difficulty === 'medium' ? '中等' : '困难' }}</span>
          <span class="quiz-tag type">{{ q.subject === 'computer_network' ? '计网' : q.subject === 'data_structures' ? '数据结构' : q.subject === 'computer_organization' ? '计组' : 'OS' }}</span>
          <span class="step-count">{{ q.step_count }} 步</span>
        </div>
        <div class="step-q-title">{{ q.question_text }}</div>
        <div class="step-q-start">开始答题 →</div>
      </div>
    </div>

    <!-- 答题中 -->
    <div v-else class="step-answer-panel glass-card">
      <div class="step-progress">第 {{ currentStepIndex + 1 }} / {{ currentStepQuestion.total_steps }} 步</div>
      <div class="step-name">{{ currentStepQuestion.step_name }}</div>
      <div class="step-desc">{{ currentStepQuestion.step_description }}</div>

      <div v-if="currentStepQuestion.step_type === 'choice'" class="step-options">
        <div v-for="(opt, oi) in currentStepQuestion.options" :key="oi"
          class="step-option" :class="{ selected: stepInput === opt }"
          role="button" tabindex="0"
          @click="stepInput = opt"
          @keydown.enter="stepInput = opt"
          @keydown.space.prevent="stepInput = opt">
          <span class="step-opt-letter">{{ stepOptionLabels[Number(oi)] || oi }}</span>
          <span>{{ opt }}</span>
        </div>
      </div>
      <div v-else class="step-input-area">
        <input v-model="stepInput" class="step-input" placeholder="输入你的答案..." @keyup.enter="submitStepAnswer" />
      </div>

      <button class="engine-btn" :disabled="stepLoading || !stepInput.trim()" @click="submitStepAnswer">
        {{ stepLoading ? '提交中...' : '提交答案' }}
      </button>

      <div v-if="stepAnswers.length > 0" class="step-history">
        <div v-for="(sa, si) in stepAnswers" :key="si" class="step-history-item" :class="{ correct: sa.correct, wrong: !sa.correct }">
          <span class="step-h-icon">{{ sa.correct ? '✅' : '❌' }}</span>
          <span class="step-h-hint">{{ sa.hint }}</span>
        </div>
      </div>

      <div v-if="stepFinished" class="step-result">
        <div class="step-result-title">🎉 答题完成</div>
        <div class="step-result-stats">
          正确 {{ stepAnswers.filter(a => a.correct).length }}/{{ stepAnswers.length }}
          | 错因: {{ [...new Set(stepAnswers.filter(a => !a.correct).map(a => a.error_type))].join(', ') || '无' }}
        </div>
        <div v-if="stepResult?.weak_points?.length" class="step-weak-points">
          <div class="step-wp-title">📊 薄弱点分析</div>
          <div v-for="wp in stepResult.weak_points.slice(0,5)" :key="wp.concept" class="step-wp-item">
            <span class="step-wp-concept">{{ wp.concept }}</span>
            <span class="step-wp-count">出错 {{ wp.count }} 次</span>
          </div>
        </div>
        <!-- P2-6：错因 → 推荐同类题引导（薄弱点闭环） -->
        <div class="step-recommend" v-if="stepAnswers.some(a => !a.correct)">
          <div class="step-rec-title">🎯 针对薄弱点，建议下一步</div>
          <button class="engine-btn" @click="recommendSimilar">📝 做同类题巩固</button>
          <button class="engine-btn glow-secondary" @click="goPractice">🔍 查看薄弱点专项练习</button>
        </div>
        <button class="engine-btn" style="margin-top:1rem;" @click="reset">继续答题</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.step-quiz { margin-top:0.5rem; }
.step-quiz-header { display: flex; align-items: center; gap:0.75rem; margin-bottom:0.5rem; }
.step-back-btn { padding:0.375rem 0.875rem; border-radius:var(--radius-sm); border: 1px solid var(--glass-border); background: transparent; color: var(--text-secondary); font-size:0.8125rem; cursor: pointer; transition: var(--transition); }
.step-back-btn:hover { border-color: var(--accent-primary); color: var(--accent-primary); }
.step-quiz-title { font-size:1rem; font-weight: 700; color: var(--text-primary); }
.step-quiz-desc { font-size:0.8125rem; color: var(--text-muted); margin-bottom:1rem; }
.step-question-list { display: flex; flex-direction: column; gap:0.75rem; }
.step-question-card { padding:1rem 1.25rem; cursor: pointer; transition: var(--transition); }
.step-question-card:hover { border-color: var(--accent-primary); }
.step-q-meta { display: flex; gap:0.5rem; align-items: center; margin-bottom:0.5rem; }
.step-count { font-size:0.75rem; color: var(--text-muted); margin-left:auto; }
.step-q-title { font-size:0.875rem; line-height:1.6; color: var(--text-primary); margin-bottom:0.5rem; }
.step-q-start { font-size:0.75rem; color: var(--accent-primary); font-weight: 600; }
.step-answer-panel { padding:1.5rem; }
.step-progress { font-size:0.75rem; color: var(--text-muted); margin-bottom:0.5rem; }
.step-name { font-size:1.25rem; font-weight: 700; color: var(--text-primary); margin-bottom:0.375rem; }
.step-desc { font-size:0.875rem; color: var(--text-secondary); margin-bottom:1rem; line-height:1.6; }
.step-options { display: flex; flex-direction: column; gap:0.5rem; }
.step-option { display: flex; align-items: center; gap:0.625rem; padding:0.75rem 1rem; border-radius:var(--radius-sm); border: 1px solid var(--border-color); cursor: pointer; transition: var(--transition); }
.step-option:hover { border-color: var(--accent-primary); }
.step-option.selected { border-color: var(--accent-primary); box-shadow: 0 0 0 2px var(--accent-primary-10); }
.step-opt-letter { width:1.625rem; height:1.625rem; border-radius:50%; display: flex; align-items: center; justify-content: center; font-size:0.75rem; font-weight: 700; background: var(--bg-tertiary); color: var(--text-secondary); flex-shrink: 0; }
.step-option.selected .step-opt-letter { background: var(--accent-primary); color: var(--text-user); }
.step-input { width:100%; padding:0.625rem 0.875rem; border-radius:var(--radius-sm); border: 1px solid var(--border-color); background: var(--bg-input); color: var(--text-primary); font-size:0.875rem; }
.step-input:focus { border-color: var(--accent-primary); outline: none; }
.step-history { margin-top:1rem; display: flex; flex-direction: column; gap:0.375rem; }
.step-history-item { display: flex; align-items: center; gap:0.5rem; padding:0.5rem 0.75rem; border-radius:var(--radius-sm); font-size:0.8125rem; }
.step-history-item.correct { background: var(--accent-success-10); color: var(--accent-success); }
.step-history-item.wrong { background: var(--accent-danger-10); color: var(--accent-danger); }
.step-h-icon { flex-shrink: 0; }
.step-result { margin-top:1.25rem; padding:1rem; border-radius:var(--radius-sm); background: var(--bg-tertiary); }
.step-result-title { font-size:1.25rem; font-weight: 700; margin-bottom:0.5rem; color: var(--text-primary); }
.step-result-stats { font-size:0.8125rem; color: var(--text-secondary); margin-bottom:0.75rem; }
.step-weak-points { border-top: 1px solid var(--border-color); padding-top:0.75rem; }
/* P2-6：错因 → 推荐同类题引导 */
.step-recommend { margin-top:0.875rem; padding:0.75rem; border-radius:var(--radius-sm); background: var(--accent-primary-10); border: 1px solid var(--accent-primary-20); display:flex; flex-wrap:wrap; gap:0.5rem; align-items:center; }
.step-rec-title { width:100%; font-size:0.8125rem; font-weight:600; color: var(--text-primary); margin-bottom:0.25rem; }
.step-wp-title { font-size:0.875rem; font-weight: 600; margin-bottom:0.5rem; color: var(--text-primary); }
.step-wp-item { display: flex; gap:0.75rem; align-items: center; padding:0.375rem 0; font-size:0.8125rem; }
.step-wp-concept { flex: 1; color: var(--text-primary); }
.step-wp-count { color: var(--accent-danger); font-weight: 600; }
</style>