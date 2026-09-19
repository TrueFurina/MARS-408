<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/utils/api'

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
    const res = await api.get<any>('/diagnostic/start')
    questions.value = res.questions || []
    step.value = 'doing'
  } catch (e: any) {
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
    const res = await api.post<any>('/diagnostic/submit', { answers: answers.value })
    result.value = res
    step.value = 'result'
  } catch (e: any) {
    console.error('提交诊断失败:', e)
  } finally {
    loading.value = false
  }
}

function goHome() {
  router.push('/')
}
</script>

<template>
  <div class="diagnostic-page">
    <div class="diag-header">
      <div class="diag-title"> 入学测评</div>
      <div class="diag-desc">完成 20 道诊断题，系统将自动生成你的学习画像和推荐路径</div>
    </div>

    <!-- L1/L2/L3 三层学情记忆健康度（低侵入联动） -->
    <div v-if="memoryOverview" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">
      <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);"> {{ memoryOverview.memory_level || 'L3' }}</span>
      <span style="padding:3px 10px;border-radius:12px;background:var(--bg-tertiary);color:var(--text-secondary);">画像 {{ memoryOverview.profile_dimensions ?? 0 }}/8 维</span>
      <span style="padding:3px 10px;border-radius:12px;background:var(--bg-tertiary);color:var(--text-secondary);">薄弱点: {{ memoryOverview.weak_points?.length ?? 0 }} 个</span>
    </div>

    <div v-if="loading" class="diag-loading">加载中...</div>

    <div v-else-if="step === 'doing'" class="diag-body">
      <div class="diag-progress">已完成 {{ Object.keys(answers).length }}/{{ questions.length }} 题</div>
      <div class="diag-questions">
        <div v-for="(q, i) in questions" :key="q.id" class="diag-question-card">
          <div class="q-number">第 {{ i + 1 }} 题</div>
          <div class="q-subject">{{ q.subject_name }} · {{ q.topic }}</div>
          <div class="q-text">{{ q.question }}</div>
          <div class="q-options">
            <div v-for="opt in q.options" :key="opt"
                 class="q-option"
                 :class="{ selected: answers[q.id] === opt[0] }"
                 @click="selectAnswer(q.id, opt[0])">
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
    </div>
  </div>
</template>

<style scoped>
.diagnostic-page { max-width: 800px; margin: 0 auto; padding: var(--space-6); }
.diag-header { text-align: center; margin-bottom: var(--space-6); }
.diag-title { font-size: var(--text-3xl); font-weight: var(--weight-bold); margin-bottom: var(--space-2); }
.diag-desc { font-size: var(--text-base); color: var(--text-muted); }
.diag-loading { text-align: center; padding: 60px; color: var(--text-muted); }
.diag-progress { font-size: var(--text-base); color: var(--accent-primary); margin-bottom: var(--space-4); text-align: center; }
.diag-question-card { background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: var(--radius-md); padding: var(--space-4); margin-bottom: var(--space-4); }
.q-number { font-size: var(--text-xs); color: var(--text-muted); margin-bottom: var(--space-1); }
.q-subject { font-size: var(--text-xs); color: var(--accent-primary); margin-bottom: var(--space-2); }
.q-text { font-size: var(--text-md); font-weight: var(--weight-medium); margin-bottom: var(--space-3); line-height: 1.5; }
.q-options { display: flex; flex-direction: column; gap: var(--space-2); }
.q-option { padding: 10px 14px; border-radius: var(--radius-sm); border: 1px solid var(--glass-border); cursor: pointer; transition: var(--transition); font-size: var(--text-base); }
.q-option:hover { border-color: var(--accent-primary); }
.q-option.selected { border-color: var(--accent-primary); background: var(--accent-primary-10); color: var(--accent-primary); }
.diag-submit { display: block; margin: var(--space-6) auto; padding: var(--space-3) var(--space-8); border: none; border-radius: var(--radius-md); background: var(--accent-primary); color: var(--color-text-on-accent); font-size: var(--text-lg); font-weight: var(--weight-semibold); cursor: pointer; }
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
.og-card:hover { border-color: var(--accent-primary); box-shadow: 0 4px 20px rgba(0,0,0,0.08); transform: translateY(-2px); }
.og-icon { font-size: 28px; margin-bottom: var(--space-2); }
.og-name { font-size: var(--text-base); font-weight: var(--weight-semibold); color: var(--text-primary); margin-bottom: 6px; }
.og-desc { font-size: var(--text-xs); color: var(--text-muted); line-height: 1.5; }
</style>