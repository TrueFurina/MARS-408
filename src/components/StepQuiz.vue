<script setup lang="ts">
import { errMessage } from '@/utils/errorMessage'
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '@/utils/api'
import type { operations } from '@/types/api.generated'

// /quiz/weak-points 返回（response_model=WeakPointsResponse）
type WeakPointsResp = operations['get_weak_points_api_quiz_weak_points_get']['responses'][200]['content']['application/json']
// /quiz/generate 返回（response_model=GenerateQuizResponse，精确嵌套子模型）
type GenerateQuizResp = operations['generate_quiz_api_quiz_generate_post']['responses'][200]['content']['application/json']
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
// P2 拓展：自适应选题开关 —— 开启后从 POST /quiz/generate(mode=adaptive) 拉取针对薄弱点的题
const adaptiveMode = ref(false)

const stepOptionLabels = ['A', 'B', 'C', 'D', 'E', 'F']

async function loadStepQuestions() {
  stepLoading.value = true
  stepError.value = ''
  try {
    if (adaptiveMode.value) {
      // P2 拓展：自适应选题 —— 后端按用户薄弱科目采样（network/transport 等归一化为 computer_network 等）
      const data = await api.post<GenerateQuizResp>('/quiz/generate', {
        subject: 'computer_network', difficulty: 'all', count: 5, mode: 'adaptive',
      })
      const qs = (data?.questions || []).map((q) => ({
        id: q.id,
        subject: q.subject,
        difficulty: q.difficulty,
        question_text: q.question_text,
        step_count: (q.steps?.length) || 0,
      }))
      if (qs.length > 0) {
        stepQuestions.value = qs
        return
      }
      // 自适应无匹配题（如无任何薄弱点）则回退全部题目
    }
    const data = await api.get<any>('/quiz/step-questions')
    stepQuestions.value = data.questions || []
  } catch (e) {
    stepError.value = '获取步骤化题目失败: ' + errMessage(e, '')
  } finally {
    stepLoading.value = false
  }
}

function setMode(v: boolean) {
  if (adaptiveMode.value === v) return
  adaptiveMode.value = v
  stepQuestions.value = []
  loadStepQuestions()
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
  } catch (e) {
    stepError.value = '获取题目详情失败: ' + errMessage(e, '')
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
        const wp = await api.get<WeakPointsResp>('/quiz/weak-points')
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
  } catch (e) {
    stepError.value = '提交答案失败: ' + errMessage(e, '')
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
    sessionStorage.setItem('mangdehenzhi_practice_topic', concept)
  }
  window.location.hash = '#/practice'
}

function goPractice() {
  sessionStorage.setItem('mangdehenzhi_practice_focus', 'weak')
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
      <span class="step-quiz-title">步骤化答题</span>
    </div>
    <div class="step-quiz-desc">复杂题目拆成多步，每步独立判断，系统分析错因并追踪薄弱点</div>

    <div class="step-mode-tabs">
      <button class="step-mode-tab" :class="{ active: !adaptiveMode }" :aria-selected="!adaptiveMode" @click="setMode(false)">全部题目</button>
      <button class="step-mode-tab" :class="{ active: adaptiveMode }" :aria-selected="adaptiveMode" @click="setMode(true)">
        智能针对薄弱点
      </button>
    </div>

    <div v-if="stepError" class="engine-error">{{ stepError }}</div>

    <!-- 题目列表 -->
    <div v-if="!currentStepQuestion" class="step-question-list">
      <div v-if="stepLoading" class="skeleton-list">
        <Skeleton v-for="i in 3" :key="i" variant="block" height="5rem" radius="var(--radius-md)" />
      </div>
      <EmptyState v-else-if="stepQuestions.length === 0" :icon="icons.quiz" title="暂无步骤化题目" description="启动后端即可获取" />
      <div v-else v-for="q in stepQuestions" :key="q.id" class="step-question-card" role="button" tabindex="0" @click="startStepQuestion(q.id)" @keydown.enter="startStepQuestion(q.id)" @keydown.space.prevent="startStepQuestion(q.id)">
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
    <div v-else class="step-answer-panel">
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
          
          <span class="step-h-hint">{{ sa.hint }}</span>
        </div>
      </div>

      <div v-if="stepFinished" class="step-result">
        <div class="step-result-title">答题完成</div>
        <div class="step-result-stats">
          正确 {{ stepAnswers.filter(a => a.correct).length }}/{{ stepAnswers.length }}
          | 错因: {{ [...new Set(stepAnswers.filter(a => !a.correct).map(a => a.error_type))].join(', ') || '无' }}
        </div>
        <div v-if="stepResult?.weak_points?.length" class="step-weak-points">
          <div class="step-wp-title">薄弱点分析</div>
          <div v-for="wp in stepResult.weak_points.slice(0,5)" :key="wp.concept" class="step-wp-item">
            <span class="step-wp-concept">{{ wp.concept }}</span>
            <span class="step-wp-count">出错 {{ wp.count }} 次</span>
          </div>
        </div>
        <!-- P2-6：错因 → 推荐同类题引导（薄弱点闭环） -->
        <div class="step-recommend" v-if="stepAnswers.some(a => !a.correct)">
          <div class="step-rec-title">针对薄弱点，建议下一步</div>
          <button class="engine-btn" @click="recommendSimilar">做同类题巩固</button>
          <button class="engine-btn glow-secondary" @click="goPractice">查看薄弱点专项练习</button>
        </div>
        <button class="engine-btn step-continue" @click="reset">继续答题</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.step-quiz { margin-top: var(--space-2); }
.step-quiz-header { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-2); }
.step-back-btn { padding: 0.375rem 0.875rem; border-radius: 8px; border: 1px solid var(--color-border); background: transparent; color: var(--color-text-2); font-size: var(--text-sm); cursor: pointer; transition: var(--transition); }
.step-back-btn:hover { border-color: var(--color-border-focus); color: var(--color-text); }
.step-quiz-title { font-size: 17px; font-weight: 700; color: var(--color-text); }
.step-quiz-desc { font-size: var(--text-sm); color: var(--color-text-2); margin-bottom: var(--space-4); line-height: 1.6; }

.step-mode-tabs { display: inline-flex; gap: var(--space-1); margin-bottom: var(--space-4); padding: 3px; border-radius: 9px; border: 1px solid var(--color-border); background: var(--color-surface-2); }
.step-mode-tab { padding: 0.375rem 0.875rem; border-radius: 7px; border: none; background: transparent; color: var(--color-text-2); font-size: var(--text-sm); cursor: pointer; transition: var(--transition); }
.step-mode-tab:hover { color: var(--color-text); }
.step-mode-tab.active { background: var(--color-accent-solid); color: var(--text-user); font-weight: 600; }

.step-question-list { display: flex; flex-direction: column; gap: var(--space-3); }
/* 题目卡：原先靠 glass-card 的半透明 + 模糊，暗色下和背景几乎同色；改成实心卡片面 + 常规投影 */
.step-question-card { padding: var(--space-4) var(--space-5); cursor: pointer; transition: var(--transition); background: var(--color-card); border: 1px solid var(--color-border); border-radius: 10px; box-shadow: var(--shadow-card); }
.step-question-card:hover { border-color: var(--color-border-focus); box-shadow: var(--shadow-card-hover); transform: translateY(-2px); }
.step-q-meta { display: flex; gap: var(--space-2); align-items: center; margin-bottom: var(--space-2); }
.step-count { font-size: var(--text-xs); color: var(--color-text-3); margin-left: auto; }
.step-q-title { font-size: var(--text-base); line-height: 1.6; color: var(--color-text); margin-bottom: var(--space-2); }
.step-q-start { font-size: var(--text-xs); color: var(--color-accent); font-weight: 600; }

.step-answer-panel { padding: var(--space-6); background: var(--color-card); border: 1px solid var(--color-border); border-radius: 12px; box-shadow: var(--shadow-card); }
.step-progress { font-size: var(--text-xs); color: var(--color-text-3); margin-bottom: var(--space-2); }
.step-name { font-size: var(--text-xl); font-weight: 700; color: var(--color-text); margin-bottom: 0.375rem; line-height: 1.35; }
.step-desc { font-size: var(--text-sm); color: var(--color-text-2); margin-bottom: var(--space-4); line-height: 1.7; }

.step-options { display: flex; flex-direction: column; gap: var(--space-2); }
.step-option { display: flex; align-items: center; gap: 0.625rem; padding: var(--space-3) var(--space-4); border-radius: 9px; border: 1px solid var(--color-border); background: var(--color-surface-2); cursor: pointer; transition: var(--transition); }
.step-option:hover { border-color: var(--color-border-focus); }
.step-option.selected { border-color: var(--color-accent); box-shadow: 0 0 0 2px var(--accent-primary-15); }
.step-opt-letter { width: 1.625rem; height: 1.625rem; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: var(--text-xs); font-weight: 700; background: var(--color-card); color: var(--color-text-2); flex-shrink: 0; }
.step-option.selected .step-opt-letter { background: var(--color-accent-solid); color: var(--text-user); }
.step-input { width: 100%; padding: 0.625rem 0.875rem; border-radius: 9px; border: 1px solid var(--color-border); background: var(--color-surface-2); color: var(--color-text); font-size: var(--text-base); }
.step-input:focus { border-color: var(--color-border-focus); outline: none; }

/* 步骤历史：原先绿底绿字 / 红底红字两套色相，改成中性底 + 左侧状态条 */
.step-history { margin-top: var(--space-4); display: flex; flex-direction: column; gap: 0.375rem; }
.step-history-item { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-2) var(--space-3); border-radius: 7px; font-size: var(--text-sm); color: var(--color-text-2); background: var(--color-surface-2); border-left: 3px solid var(--color-border); }
.step-history-item.correct { border-left-color: var(--color-accent-solid); }
.step-history-item.wrong { border-left-color: var(--accent-primary-30); }

.step-result { margin-top: var(--space-5); padding: var(--space-4); border-radius: 10px; background: var(--color-surface-2); border: 1px solid var(--color-border); }
.step-result-title { font-size: var(--text-lg); font-weight: 700; margin-bottom: var(--space-2); color: var(--color-text); }
.step-result-stats { font-size: var(--text-sm); color: var(--color-text-2); margin-bottom: var(--space-3); line-height: 1.6; }
.step-weak-points { border-top: 1px solid var(--color-border); padding-top: var(--space-3); }

/* P2-6：错因 → 推荐同类题引导 */
.step-recommend { margin-top: 0.875rem; padding: var(--space-3); border-radius: 9px; background: var(--color-card); border: 1px solid var(--color-border); display: flex; flex-wrap: wrap; gap: var(--space-2); align-items: center; }
.step-rec-title { width: 100%; font-size: var(--text-sm); font-weight: 600; color: var(--color-text); margin-bottom: var(--space-1); }
.step-wp-title { font-size: var(--text-base); font-weight: 600; margin-bottom: var(--space-2); color: var(--color-text); }
.step-wp-item { display: flex; gap: var(--space-3); align-items: center; padding: 0.375rem 0; font-size: var(--text-sm); }
.step-wp-concept { flex: 1; color: var(--color-text); }
.step-wp-count { color: var(--color-text-2); font-weight: 600; white-space: nowrap; }
.step-continue { margin-top: var(--space-4); }

@media (max-width: 640px) {
  .step-answer-panel { padding: var(--space-4); }
  .step-name { font-size: var(--text-lg); }
  .step-question-card { padding: var(--space-3) var(--space-4); }
}
</style>