<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/utils/api'
import type { operations } from '@/types/api.generated'
import DiagnosticReview from '@/components/DiagnosticReview.vue'

// 契约类型：取自后端 response_model（py-server/api/diagnostic.py）
type DiagnosticStartResp = operations['start_diagnostic_api_diagnostic_start_get']['responses'][200]['content']['application/json']
type DiagnosticSubmitResp = operations['submit_diagnostic_api_diagnostic_submit_post']['responses'][200]['content']['application/json']

const router = useRouter()
const questions = ref<any[]>([])
const answers = ref<Record<string, string>>({})
const step = ref<'start' | 'doing' | 'result'>('start')
const result = ref<any>(null)
const loading = ref(false)
const memoryOverview = ref<any>(null)

onMounted(() => {
  fetchQuestions()
  loadMemoryOverview()
})

// L1/L2/L3 三层学情记忆（低侵入联动：诊断前展示记忆薄弱点，失败不影响主流程）
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞诊断页 */ }
}

async function fetchQuestions() {
  loading.value = true
  try {
    const res = await api.get<DiagnosticStartResp>('/diagnostic/start')
    questions.value = res.questions || []
    step.value = 'doing'
  } catch (e) {
    console.error('获取诊断题失败:', e)
  } finally {
    loading.value = false
  }
}

function selectAnswer(qId: string, option: string) {
  answers.value[qId] = option
}

async function submit() {
  loading.value = true
  try {
    const res = await api.post<DiagnosticSubmitResp>('/diagnostic/submit', { answers: answers.value })
    result.value = res
    step.value = 'result'
  } catch (e) {
    console.error('提交诊断失败:', e)
  } finally {
    loading.value = false
  }
}

function goHome() {
  router.push('/kaoyan')
}
</script>

<template>
  <div class="diagnostic-page">
    <div class="diag-header">
      <div class="diag-eyebrow">LEARNING DIAGNOSTIC</div>
      <div class="diag-title">入学测评</div>
      <div class="diag-desc">完成 20 道诊断题，系统将自动生成你的学习画像和推荐路径</div>
    </div>

    <!-- L1/L2/L3 三层学情记忆健康度（低侵入联动） -->
    <div v-if="memoryOverview" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">
      <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);"> {{ memoryOverview.memory_level || 'L3' }}</span>
      <span style="padding:3px 10px;border-radius:12px;background:var(--color-surface-2);color:var(--color-text-2);">画像 {{ memoryOverview.profile_dimensions ?? 0 }}/8 维</span>
      <span style="padding:3px 10px;border-radius:12px;background:var(--color-surface-2);color:var(--color-text-2);">薄弱点: {{ memoryOverview.weak_points?.length ?? 0 }} 个</span>
    </div>

    <div v-if="loading" class="diag-loading">加载中...</div>

    <div v-else-if="step === 'doing'" class="diag-body">
      <div class="diag-progress">
        <span class="diag-progress-label">已完成 {{ Object.keys(answers).length }}/{{ questions.length }} 题</span>
        <div class="diag-progress-track" role="progressbar" :aria-valuenow="Object.keys(answers).length" aria-valuemin="0" :aria-valuemax="questions.length">
          <div class="diag-progress-fill" :style="{ width: Math.round(Object.keys(answers).length / Math.max(1, questions.length) * 100) + '%' }"></div>
        </div>
      </div>
      <div class="diag-questions">
        <div v-for="(q, i) in questions" :key="q.id" class="diag-question-card">
          <div class="q-number">第 {{ i + 1 }} 题</div>
          <div class="q-subject">{{ q.subject_name }} · {{ q.topic }}</div>
          <div class="q-text">{{ q.question }}</div>
          <div class="q-options" role="radiogroup" aria-label="选项">
            <div v-for="opt in q.options" :key="opt"
                 class="q-option"
                 :class="{ selected: answers[q.id] === opt[0] }"
                 role="radio"
                 :aria-checked="answers[q.id] === opt[0]"
                 tabindex="0"
                 @click="selectAnswer(q.id, opt[0])"
                 @keydown.enter.prevent="selectAnswer(q.id, opt[0])"
                 @keydown.space.prevent="selectAnswer(q.id, opt[0])">
              {{ opt }}
            </div>
          </div>
        </div>
      </div>
      <button class="diag-submit" :disabled="Object.keys(answers).length < questions.length" @click="submit">
        提交测评 ({{ Object.keys(answers).length }}/{{ questions.length }})
      </button>
    </div>

    <div v-else-if="step === 'result' && result" class="diag-result">
      <div class="result-title"> 测评完成！</div>
      <div class="result-accuracy">整体正确率: <strong>{{ (result.overall_accuracy * 100).toFixed(0) }}%</strong></div>
      <div class="result-subjects">
        <div v-for="r in result.results" :key="r.subject" class="result-subject-card">
          <div class="rs-name">{{ r.subject_name }}</div>
          <div class="rs-accuracy" :style="{ color: r.accuracy >= 0.7 ? 'var(--accent-success)' : r.accuracy >= 0.4 ? 'var(--accent-warm)' : 'var(--accent-danger)' }">
            {{ (r.accuracy * 100).toFixed(0) }}%
          </div>
          <div class="rs-weak" v-if="r.weak_topics.length">薄弱: {{ r.weak_topics.join('、') }}</div>
        </div>
      </div>
      <div class="result-recommend">{{ result.overall_recommendation }}</div>

      <!-- 新手引导：诊断后的下一步行动 -->
      <div class="onboard-guide">
        <div class="og-title"> 接下来建议这样做</div>
        <div class="og-grid">
          <div class="og-card" role="button" tabindex="0" @click="router.push('/chat')" @keydown.enter="router.push('/chat')" @keydown.space.prevent="router.push('/chat')">
            <div class="og-icon"></div>
            <div class="og-name">智能对话学习</div>
            <div class="og-desc">向 AI 助教提问，针对薄弱点查漏补缺</div>
          </div>
          <div class="og-card" role="button" tabindex="0" @click="router.push('/practice')" @keydown.enter="router.push('/practice')" @keydown.space.prevent="router.push('/practice')">
            <div class="og-icon"></div>
            <div class="og-name">刷题巩固</div>
            <div class="og-desc">针对薄弱知识点生成专项练习</div>
          </div>
          <div class="og-card" role="button" tabindex="0" @click="router.push('/learning-path')" @keydown.enter="router.push('/learning-path')" @keydown.space.prevent="router.push('/learning-path')">
            <div class="og-icon"></div>
            <div class="og-name">查看学习路径</div>
            <div class="og-desc">了解四科学习顺序和推荐进度</div>
          </div>
          <div class="og-card" role="button" tabindex="0" @click="router.push('/knowledge')" @keydown.enter="router.push('/knowledge')" @keydown.space.prevent="router.push('/knowledge')">
            <div class="og-icon"></div>
            <div class="og-name">浏览知识图谱</div>
            <div class="og-desc">可视化四科知识点关联关系</div>
          </div>
        </div>
      </div>

      <button class="diag-submit" @click="goHome">返回首页</button>

      <!-- 逐题核对：交卷后展开可看到自己选了什么、正确答案是什么、为什么 -->
      <DiagnosticReview :details="result.details" default-open />
    </div>
  </div>
</template>

<style scoped>
/* 原来 800px 居中 + 页头居中 + 紫色大字进度，在宽屏上只剩中间一条窄带，
   左侧大片空白；与全站左对齐的版式不一致。这里改成左对齐的分区式页头。 */
.diagnostic-page { max-width: 960px; margin: 0; padding: var(--space-6) var(--space-6) var(--space-10); }
.diag-header { text-align: left; margin-bottom: var(--space-5); }
.diag-eyebrow { font-size: 11px; line-height: 1; letter-spacing: 0.16em; text-transform: uppercase; color: var(--accent-primary); font-weight: 600; margin-bottom: 10px; }
.diag-title { font-size: 30px; font-weight: var(--weight-bold); margin-bottom: 8px; letter-spacing: -0.02em; }
.diag-desc { font-size: var(--text-base); color: var(--color-text-2); max-width: 640px; }
.diag-loading { text-align: left; padding: 60px 0; color: var(--color-text-2); }
.diag-progress { display: flex; align-items: center; gap: var(--space-4); margin-bottom: var(--space-4); }
.diag-progress-label { font-size: var(--text-sm); color: var(--color-text-2); white-space: nowrap; }
.diag-progress-track { flex: 1; height: 4px; border-radius: 2px; background: var(--color-surface-2); overflow: hidden; }
.diag-progress-fill { height: 100%; background: var(--color-accent-solid); border-radius: 2px; transition: width var(--duration-slow) var(--ease-standard); }
.diag-question-card { background: var(--color-card); border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: var(--space-5); margin-bottom: var(--space-4); }
.q-number { font-size: var(--text-xs); color: var(--color-text-3); margin-bottom: 6px; letter-spacing: 0.04em; }
.q-subject { font-size: var(--text-xs); color: var(--accent-primary); margin-bottom: var(--space-2); font-weight: 600; }
.q-text { font-size: var(--text-md); font-weight: var(--weight-medium); margin-bottom: var(--space-3); line-height: 1.55; }
.q-options { display: flex; flex-direction: column; gap: 8px; }
.q-option { padding: 11px 16px; border-radius: 9px; border: 1px solid var(--color-border); background: var(--color-surface-2); cursor: pointer; transition: var(--transition); font-size: var(--text-base); }
.q-option:hover { border-color: var(--accent-primary); }
.q-option.selected { border-color: var(--accent-primary); background: var(--accent-primary-10); color: var(--accent-primary); }
.diag-submit { display: block; margin: var(--space-6) 0; padding: var(--space-3) var(--space-8); border: none; border-radius: 10px; background: var(--color-accent-solid); color: var(--color-text-on-accent); font-size: var(--text-lg); font-weight: var(--weight-semibold); cursor: pointer; }
.diag-submit:disabled { opacity: 0.5; cursor: not-allowed; }
.result-title { font-size: 28px; font-weight: var(--weight-bold); text-align: center; margin-bottom: var(--space-4); }
.result-accuracy { text-align: center; font-size: var(--text-xl); margin-bottom: var(--space-6); }
.result-subjects { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); margin-bottom: var(--space-6); }
.result-subject-card { background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: var(--radius-md); padding: var(--space-4); text-align: center; }
.rs-name { font-size: var(--text-base); font-weight: var(--weight-medium); margin-bottom: var(--space-2); }
.rs-accuracy { font-size: var(--text-3xl); font-weight: var(--weight-bold); }
.rs-weak { font-size: var(--text-xs); color: var(--text-muted); margin-top: var(--space-2); }
.result-recommend { text-align: center; font-size: var(--text-md); color: var(--text-secondary); margin-bottom: var(--space-6); line-height: 1.6; padding: var(--space-4); background: var(--glass-bg); border-radius: var(--radius-md); }

/* ── 新手引导：诊断后下一步 ── */
.onboard-guide { margin-bottom: var(--space-6); }
.og-title { font-size: var(--text-lg); font-weight: var(--weight-bold); text-align: center; margin-bottom: var(--space-4); color: var(--text-primary); }
.og-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-3); }
@media (max-width: 768px) { .og-grid { grid-template-columns: repeat(2, 1fr); } }
.og-card { background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: var(--radius-md); padding: var(--space-4); text-align: center; cursor: pointer; transition: var(--transition); }
.og-card:hover { border-color: var(--accent-primary); box-shadow: var(--shadow-3); transform: translateY(-2px); }
.og-icon { font-size: 28px; margin-bottom: var(--space-2); }
.og-name { font-size: var(--text-base); font-weight: var(--weight-semibold); color: var(--text-primary); margin-bottom: 6px; }
.og-desc { font-size: var(--text-xs); color: var(--color-text-2); line-height: 1.5; }

/* 逐题核对的样式在 DiagnosticReview.vue 里，两处（交卷结果页 / 答题历史）共用一份 */

/* 手机上标题 30px 会把副标题挤成三行，题目卡的选项也要收窄内边距。 */
@media (max-width: 640px) {
  .diagnostic-page { padding: var(--space-5) var(--space-4) var(--space-8); }
  .diag-title { font-size: 24px; }
  .diag-desc { font-size: var(--text-sm); }
  .diag-question-card { padding: var(--space-4); }
  .q-option { padding: 12px 14px; }
  .diag-submit { width: 100%; margin: var(--space-5) 0; }
}</style>