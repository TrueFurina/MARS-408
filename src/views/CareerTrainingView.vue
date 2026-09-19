<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { api, friendlyError } from '@/utils/api'

/* ===================== 类型与常量 ===================== */
type Step = 'select' | 'briefing' | 'battle' | 'report'
interface Scenario { id: string; type: string; subtype: string; type_label: string; subtype_label: string; title: string; difficulty_default: string }
interface Turn { role: 'interviewer' | 'student'; text: string; mode?: string; dimension?: string; evidence?: any }

const DIM_LABEL: Record<string, string> = {
  expression: '表达逻辑', stress: '抗压应变', decompose: '方案拆解',
  collab: '协作沟通', presentation: '技术汇报', problem_solving: '问题解决',
}
const DIM_ORDER = ['expression', 'stress', 'decompose', 'collab', 'presentation', 'problem_solving']
const MODE_LABEL: Record<string, string> = { normal: '常规追问', escalating: '逐步加压', catfish: '鲶鱼反诘' }
const MODE_CLASS: Record<string, string> = { normal: 'm-normal', escalating: 'm-escalating', catfish: 'm-catfish' }
const DIFF_LABEL: Record<string, string> = { easy: '简单', medium: '中等', hard: '困难' }

/* ===================== 响应式状态 ===================== */
const step = ref<Step>('select')
const scenarios = ref<Scenario[]>([])
const scenarioId = ref('')
const difficulty = ref('medium')
const maxTurns = ref(6)
const loadingScenarios = ref(true)
const busy = ref(false)
const errorMsg = ref('')

const session = ref<any>(null)
const turns = ref<Turn[]>([])
const answerInput = ref('')
const assessment = ref<any>(null)
const improvement = ref<any>(null)
const evidenceChain = ref<any[]>([])
const battleScroll = ref<HTMLElement | null>(null)

const currentScenario = computed(() => scenarios.value.find(s => s.id === scenarioId.value))
const turnsDone = computed(() => turns.value.filter(t => t.role === 'student').length)
const progressText = computed(() => `${turnsDone.value}/${session.value?.max_turns ?? maxTurns.value}`)

/* ===================== 拉取场景 ===================== */
async function loadScenarios() {
  loadingScenarios.value = true
  try {
    const res = await api.get<any>('/career/scenarios')
    scenarios.value = res.scenarios || []
  } catch (e) {
    errorMsg.value = friendlyError(e, '场景加载失败')
  } finally {
    loadingScenarios.value = false
  }
}
loadScenarios()

/* ===================== 启动实训 ===================== */
async function startTraining() {
  if (!scenarioId.value) { errorMsg.value = '请先选择一个实训情景'; return }
  busy.value = true; errorMsg.value = ''
  try {
    const res = await api.post<any>('/career/session/start', {
      scenario_id: scenarioId.value, difficulty: difficulty.value, max_turns: maxTurns.value,
    })
    session.value = res
    turns.value = [{ role: 'interviewer', text: res.next_question.question, mode: 'normal', dimension: res.next_question.probe_dimension }]
    step.value = 'briefing'
  } catch (e) {
    errorMsg.value = friendlyError(e, '启动失败')
  } finally { busy.value = false }
}

function enterBattle() { step.value = 'battle' }

/* ===================== 提交一轮作答 ===================== */
async function submitAnswer() {
  const text = answerInput.value.trim()
  if (!text || busy.value) return
  busy.value = true; errorMsg.value = ''
  turns.value.push({ role: 'student', text })
  answerInput.value = ''
  await scrollBottom()
  try {
    const res = await api.post<any>(`/career/session/${session.value.session_id}/answer`, { answer: text })
    const idx = turns.value.length - 1
    const mine = turns.value[idx]
    if (mine) mine.evidence = res.last_evidence
    if (res.status === 'finished') {
      assessment.value = res.assessment
      improvement.value = res.improvement
      evidenceChain.value = res.evidence_chain || []
      step.value = 'report'
    } else {
      turns.value.push({
        role: 'interviewer', text: res.next_question.question,
        mode: res.next_question.mode, dimension: res.next_question.probe_dimension,
      })
      await scrollBottom()
    }
  } catch (e) {
    errorMsg.value = friendlyError(e, '提交失败')
    turns.value.pop() // 失败回滚学生气泡
  } finally { busy.value = false }
}

/* 提前结束（至少4轮后端才出报告） */
async function finishEarly() {
  if (busy.value) return
  busy.value = true; errorMsg.value = ''
  try {
    const res = await api.post<any>(`/career/session/${session.value.session_id}/end`, { force: false })
    if (res.status === 'insufficient') { errorMsg.value = res.message; busy.value = false; return }
    assessment.value = res.assessment; improvement.value = res.improvement
    evidenceChain.value = res.evidence_chain || []
    step.value = 'report'
  } catch (e) {
    errorMsg.value = friendlyError(e, '结束失败')
  } finally { busy.value = false }
}

function restart() {
  step.value = 'select'; session.value = null; assessment.value = null
  improvement.value = null; evidenceChain.value = []; turns.value = []; answerInput.value = ''
}

async function scrollBottom() {
  await nextTick()
  battleScroll.value?.scrollTo({ top: battleScroll.value.scrollHeight, behavior: 'smooth' })
}

/* ===================== 六维雷达（纯 SVG） ===================== */
const radar = computed(() => {
  const dims = assessment.value?.dimensions || {}
  const cx = 130, cy = 130, R = 88, n = 6
  const angle = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2
  const point = (i: number, ratio: number): [number, number] => {
    const r = R * ratio
    return [cx + r * Math.cos(angle(i)), cy + r * Math.sin(angle(i))]
  }
  const rings = [1, 2, 3, 4, 5].map(lv =>
    DIM_ORDER.map((_, i) => point(i, lv / 5).map(v => v.toFixed(1)).join(',')).join(' '))
  const axes = DIM_ORDER.map((_, i) => {
    const [x, y] = point(i, 1)
    return { x: x.toFixed(1), y: y.toFixed(1) }
  })
  const labels = DIM_ORDER.map((d, i) => {
    const [x, y] = point(i, 1.18)
    return { x: x.toFixed(1), y: (y + 4).toFixed(1), text: DIM_LABEL[d] }
  })
  const dataPts = DIM_ORDER.map((d, i) => {
    const sc = dims[d]?.score
    return point(i, sc ? sc / 5 : 0).map(v => v.toFixed(1)).join(',')
  }).join(' ')
  return { rings, axes, labels, dataPts }
})

const dimRows = computed(() => {
  const dims = assessment.value?.dimensions || {}
  return DIM_ORDER.map(d => ({ key: d, label: DIM_LABEL[d], ...(dims[d] || {}) }))
})
const levelLabel: Record<string, string> = {
  excellent: '优秀', good: '良好', average: '一般', weak: '薄弱', insufficient: '证据不足',
}
function levelClass(lv?: string) { return `lv-${lv || 'none'}` }
</script>

<template>
  <div class="career-page">
    <!-- ============ 步骤1：情景选择 ============ -->
    <template v-if="step === 'select'">
      <div class="c-header">
        <div class="c-title"> 职业素养对抗实训</div>
        <div class="c-desc">多智能体扮演高压职场对手，多轮追问并全程留证，结束后按证据中心设计（ECD）生成六维能力报告</div>
      </div>

      <div v-if="loadingScenarios" class="c-loading">正在加载实训情景…</div>
      <div v-else class="scenario-grid">
        <div v-for="s in scenarios" :key="s.id" class="scenario-card"
             :class="{ active: scenarioId === s.id }" @click="scenarioId = s.id">
          <div class="sc-type">{{ s.type_label }} · {{ s.subtype_label }}</div>
          <div class="sc-title">{{ s.title }}</div>
        </div>
      </div>

      <div class="opt-bar">
        <div class="opt-group">
          <span class="opt-label">难度</span>
          <button v-for="d in ['easy','medium','hard']" :key="d" class="chip"
                  :class="{ on: difficulty === d }" @click="difficulty = d">{{ DIFF_LABEL[d] }}</button>
        </div>
        <div class="opt-group">
          <span class="opt-label">对抗轮数</span>
          <button v-for="n in [4,6,8]" :key="n" class="chip"
                  :class="{ on: maxTurns === n }" @click="maxTurns = n">{{ n }} 轮</button>
        </div>
      </div>

      <div v-if="errorMsg" class="c-error">{{ errorMsg }}</div>
      <button class="primary-btn" :disabled="busy || !scenarioId" @click="startTraining">
        {{ busy ? '正在生成对抗脚本…' : '开始实训' }}
      </button>
    </template>

    <!-- ============ 步骤2：场景简报 ============ -->
    <template v-else-if="step === 'briefing'">
      <div class="brief-card">
        <div class="brief-tag">{{ currentScenario?.type_label }} · {{ currentScenario?.subtype_label }} · {{ DIFF_LABEL[difficulty] }}</div>
        <h2 class="brief-title">{{ session?.title }}</h2>
        <div class="brief-row"><b>情景背景</b><p>{{ session?.setting }}</p></div>
        <div class="brief-row"><b>你将扮演</b><p>{{ session?.student_role }}</p></div>
        <div class="brief-row"><b>对手是</b><p>{{ session?.interviewer_role }}</p></div>
        <div class="brief-opening">
          <span class="opening-label">对手开场提问</span>
          <p class="opening-q">“{{ session?.next_question.question }}”</p>
        </div>
        <p class="brief-tip">提示：共 {{ session?.max_turns }} 轮，对手可能在你回答空泛时<strong>逐步加压</strong>甚至触发<strong>鲶鱼反诘</strong>，请尽量给出具体步骤、数字与取舍，避免套话。</p>
        <div class="brief-actions">
          <button class="ghost-btn" @click="restart">换个情景</button>
          <button class="primary-btn" @click="enterBattle">进入对抗 →</button>
        </div>
      </div>
    </template>

    <!-- ============ 步骤3：多轮对抗 ============ -->
    <template v-else-if="step === 'battle'">
      <div class="battle-top">
        <div class="battle-title"> {{ session?.title }}</div>
        <div class="battle-progress">第 {{ progressText }} 轮</div>
      </div>
      <div ref="battleScroll" class="battle-stream">
        <div v-for="(t, i) in turns" :key="i" class="turn" :class="t.role">
          <template v-if="t.role === 'interviewer'">
            <div class="bubble interviewer">
              <span class="role-tag">对手</span>
              <span v-if="t.mode && t.mode !== 'normal'" class="mode-tag" :class="MODE_CLASS[t.mode]">{{ MODE_LABEL[t.mode] }}</span>
              <div class="bubble-text">{{ t.text }}</div>
            </div>
          </template>
          <template v-else>
            <div class="bubble student">
              <span class="role-tag me">我</span>
              <div class="bubble-text">{{ t.text }}</div>
            </div>
            <div v-if="t.evidence" class="evidence-mini">
              <span :class="['dot', t.evidence.template_suspect ? 'bad' : 'ok']"></span>
              信息密度 {{ Math.round((t.evidence.density ?? 0) * 100) }}%
              <span v-if="t.evidence.template_suspect" class="warn-text">· 疑似套话，可能触发加压</span>
              <span v-if="t.evidence.dimension_hits?.length">· 命中 {{ t.evidence.dimension_hits.length }} 个维度证据</span>
            </div>
          </template>
        </div>
        <div v-if="busy" class="bubble interviewer typing">对手正在思考下一个问题…</div>
      </div>

      <div v-if="errorMsg" class="c-error">{{ errorMsg }}</div>
      <div class="answer-bar">
        <textarea v-model="answerInput" class="answer-input" rows="3"
                  placeholder="像真实场景一样口头/文字作答：先给结论，再讲步骤、依据与取舍…"
                  :disabled="busy" @keydown.ctrl.enter="submitAnswer"></textarea>
        <div class="answer-actions">
          <button class="ghost-btn" :disabled="busy || turnsDone < 1" @click="finishEarly">提前结束出报告</button>
          <button class="primary-btn" :disabled="busy || !answerInput.trim()" @click="submitAnswer">
            {{ busy ? '处理中…' : '提交作答 (Ctrl+Enter)' }}
          </button>
        </div>
      </div>
    </template>

    <!-- ============ 步骤4：六维报告 ============ -->
    <template v-else>
      <div class="report-head">
        <div class="c-title"> 六维素养评估报告</div>
        <div class="overall">
          综合得分
          <span class="overall-score">{{ assessment?.overall ?? '—' }}</span>
          <span class="overall-full">/ 5</span>
          <span class="src-tag">{{ assessment?.assessment_source === 'llm' ? 'AI评估' : '规则评估' }}</span>
        </div>
      </div>
      <p class="report-summary">{{ assessment?.summary }}</p>

      <div class="report-grid">
        <div class="radar-card">
          <svg viewBox="0 0 260 260" class="radar-svg">
            <polygon v-for="(ring, i) in radar.rings" :key="i" :points="ring" class="radar-ring" />
            <line v-for="(ax, i) in radar.axes" :key="'a'+i" :x1="130" :y1="130" :x2="ax.x" :y2="ax.y" class="radar-axis" />
            <polygon :points="radar.dataPts" class="radar-data" />
            <text v-for="(lb, i) in radar.labels" :key="'l'+i" :x="lb.x" :y="lb.y" class="radar-label">{{ lb.text }}</text>
          </svg>
        </div>

        <div class="dim-card">
          <div v-for="row in dimRows" :key="row.key" class="dim-row">
            <div class="dim-meta">
              <span class="dim-name">{{ row.label }}</span>
              <span class="dim-score">{{ row.score ?? '—' }}</span>
              <span class="dim-level" :class="levelClass(row.level)">{{ levelLabel[row.level as string] || '—' }}</span>
            </div>
            <div class="dim-bar"><div class="dim-fill" :style="{ width: '100%', transform: 'scaleX(' + ((row.score || 0) / 5) + ')', transformOrigin: 'left' }"></div></div>
            <div class="dim-rationale">{{ row.rationale }}</div>
            <div v-if="row.evidence_quotes?.length" class="dim-evidence">
              <span class="ev-label">证据引用</span>
              <span v-for="(q, i) in row.evidence_quotes" :key="i" class="ev-quote">「{{ q }}」</span>
            </div>
          </div>
        </div>
      </div>

      <div class="sw-block">
        <div class="sw-strength"> 最突出优点：{{ assessment?.strength || '—' }}</div>
        <div class="sw-weak"> 待改进：
          <ul><li v-for="(w, i) in assessment?.weaknesses" :key="i">{{ w }}</li></ul>
        </div>
      </div>

      <div v-if="improvement" class="plan-block">
        <h3> 针对性提升路径</h3>
        <div v-for="(a, i) in improvement.actions" :key="i" class="plan-item">
          <span class="plan-dim">{{ DIM_LABEL[a.dimension] || a.dimension }}</span>
          <span class="plan-do">{{ a.do }}</span>
          <span class="plan-freq">{{ a.frequency }}</span>
        </div>
        <p class="plan-encourage">{{ improvement.encouragement }}</p>
      </div>

      <details class="replay">
        <summary>查看完整对抗记录与证据链（{{ turns.filter(t=>t.role==='student').length }} 轮）</summary>
        <div v-for="(t, i) in turns" :key="i" class="replay-turn" :class="t.role">
          <b>{{ t.role === 'interviewer' ? '对手' : '我' }}：</b>{{ t.text }}
        </div>
      </details>

      <div class="report-actions">
        <button class="ghost-btn" @click="step = 'battle'">返回对抗</button>
        <button class="primary-btn" @click="restart">再来一场 →</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.career-page { max-width: 960px; margin: 0 auto; padding: 18px var(--space-4) 60px; color: var(--text-primary); }
.c-header { margin-bottom: var(--space-4); }
.c-title { font-size: 22px; font-weight: var(--weight-bold); }
.c-desc { font-size: var(--text-sm); color: var(--text-secondary); margin-top: 6px; line-height: 1.6; }
.c-loading, .c-error { padding: 14px; border-radius: 10px; font-size: var(--text-sm); margin: var(--space-3) 0; }
.c-loading { background: var(--bg-secondary); }
.c-error { background: var(--accent-danger-10); color: var(--accent-danger); }

/* 情景卡片 */
.scenario-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: var(--space-3); }
.scenario-card { padding: 14px; border-radius: 14px; background: var(--bg-card);
  border: 1.5px solid var(--border-color); cursor: pointer; transition: .15s; }
.scenario-card:hover { transform: translateY(-2px); border-color: var(--accent-primary); }
.scenario-card.active { border-color: var(--accent-primary); box-shadow: 0 0 0 3px var(--accent-primary-15); }
.sc-type { font-size: var(--text-2xs); color: var(--accent-primary); font-weight: var(--weight-semibold); margin-bottom: 6px; }
.sc-title { font-size: var(--text-base); font-weight: var(--weight-semibold); line-height: 1.5; }

.opt-bar { display: flex; gap: var(--space-6); flex-wrap: wrap; margin: 18px 0; }
.opt-group { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
.opt-label { font-size: var(--text-sm); color: var(--text-secondary); }
.chip { padding: 5px 14px; border-radius: 16px; border: 1px solid var(--border-color);
  background: var(--bg-card); font-size: var(--text-sm); cursor: pointer; color: var(--text-primary); }
.chip.on { background: var(--accent-primary); color: var(--color-text-on-accent); border-color: transparent; }

.primary-btn { padding: 10px 22px; border-radius: 10px; border: none; cursor: pointer; font-size: var(--text-base); font-weight: var(--weight-semibold);
  background: var(--accent-primary); color: var(--color-text-on-accent); }
.primary-btn:disabled { opacity: .5; cursor: not-allowed; }
.ghost-btn { padding: 10px 18px; border-radius: 10px; cursor: pointer; font-size: var(--text-base);
  background: transparent; border: 1px solid var(--border-color); color: var(--text-primary); }
.ghost-btn:disabled { opacity: .5; cursor: not-allowed; }

/* 简报 */
.brief-card { background: var(--bg-card); border: 1px solid var(--border-color);
  border-radius: 16px; padding: 22px; }
.brief-tag { display: inline-block; font-size: var(--text-xs); color: var(--accent-primary);
  background: var(--accent-primary-10); padding: var(--space-1) var(--space-3); border-radius: 12px; }
.brief-title { font-size: 19px; margin: var(--space-3) 0 var(--space-4); line-height: 1.5; }
.brief-row { margin-bottom: var(--space-3); font-size: var(--text-base); line-height: 1.6; }
.brief-row b { display: block; font-size: var(--text-xs); color: var(--text-secondary); margin-bottom: 3px; }
.brief-row p { margin: 0; }
.brief-opening { background: var(--bg-secondary); border-left: 3px solid var(--accent-primary);
  border-radius: 8px; padding: var(--space-3) 14px; margin: 14px 0; }
.opening-label { font-size: var(--text-2xs); color: var(--text-secondary); }
.opening-q { margin: 6px 0 0; font-size: var(--text-md); font-weight: var(--weight-semibold); line-height: 1.6; }
.brief-tip { font-size: 12.5px; color: var(--text-secondary); line-height: var(--leading-relaxed); }
.brief-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: var(--space-4); }

/* 对抗 */
.battle-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.battle-title { font-size: var(--text-lg); font-weight: var(--weight-bold); }
.battle-progress { font-size: var(--text-sm); color: var(--accent-primary); font-weight: var(--weight-semibold); }
.battle-stream { height: 46vh; min-height: 300px; overflow-y: auto; padding: 14px;
  background: var(--bg-secondary); border-radius: 14px; display: flex; flex-direction: column; gap: var(--space-3); }
.turn { display: flex; flex-direction: column; }
.turn.interviewer { align-items: flex-start; }
.turn.student { align-items: flex-end; }
.bubble { max-width: 82%; padding: 10px 14px; border-radius: 14px; font-size: var(--text-base); line-height: 1.6; }
.bubble.interviewer { background: var(--bg-card); border: 1px solid var(--border-color);
  border-top-left-radius: 4px; }
.bubble.student { background: var(--accent-primary); color: var(--color-text-on-accent); border-top-right-radius: 4px; }
.role-tag { display: inline-block; font-size: 10px; padding: 1px 7px; border-radius: 8px; margin-right: 6px;
  background: var(--accent-primary-15); color: var(--accent-primary); vertical-align: middle; }
.role-tag.me { background: rgba(255,255,255,.25); color: var(--color-text-on-accent); }
.mode-tag { display: inline-block; font-size: 10px; padding: 1px 7px; border-radius: 8px; vertical-align: middle; margin-right: 6px; }
.m-escalating { background: rgba(var(--warning-rgb),.16); color: var(--color-warning); }
.m-catfish { background: var(--accent-danger-10); color: var(--accent-danger); }
.bubble-text { display: inline; }
.typing { color: var(--text-secondary); font-size: var(--text-sm); font-style: italic; }
.evidence-mini { font-size: var(--text-2xs); color: var(--text-secondary); margin-top: var(--space-1); padding: 0 6px; }
.dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: var(--space-1); }
.dot.ok { background: var(--accent-success); } .dot.bad { background: var(--accent-warm); }
.warn-text { color: var(--color-warning); }

.answer-bar { margin-top: var(--space-3); }
.answer-input { width: 100%; box-sizing: border-box; border-radius: 12px; padding: var(--space-3); font-size: var(--text-base); resize: vertical;
  border: 1px solid var(--border-color); background: var(--bg-card); color: var(--text-primary); font-family: inherit; }
.answer-actions { display: flex; justify-content: space-between; margin-top: 10px; gap: 10px; flex-wrap: wrap; }

/* 报告 */
.report-head { display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 10px; }
.overall { font-size: var(--text-sm); color: var(--text-secondary); }
.overall-score { font-size: var(--text-4xl); font-weight: 800; color: var(--accent-primary); margin: 0 2px; }
.overall-full { color: var(--text-secondary); }
.src-tag { margin-left: var(--space-2); font-size: var(--text-2xs); padding: 2px var(--space-2); border-radius: 10px; background: var(--bg-secondary); }
.report-summary { font-size: var(--text-base); line-height: var(--leading-relaxed); background: var(--bg-card);
  border: 1px solid var(--border-color); border-radius: 12px; padding: var(--space-3) 14px; margin: var(--space-3) 0; }
.report-grid { display: grid; grid-template-columns: 280px 1fr; gap: 14px; }
@media (max-width: 720px) { .report-grid { grid-template-columns: 1fr; } }
.radar-card, .dim-card { background: var(--bg-card); border: 1px solid var(--border-color);
  border-radius: 14px; padding: 14px; }
.radar-svg { width: 100%; max-width: 260px; display: block; margin: 0 auto; }
.radar-ring { fill: none; stroke: var(--border-color); stroke-width: 1; }
.radar-axis { stroke: var(--border-color); stroke-width: 1; }
.radar-data { fill: var(--accent-primary-20); stroke: var(--accent-primary); stroke-width: 2; }
.radar-label { font-size: var(--text-2xs); fill: var(--text-secondary); text-anchor: middle; }
.dim-row { margin-bottom: var(--space-3); }
.dim-row:last-child { margin-bottom: 0; }
.dim-meta { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-1); }
.dim-name { font-size: var(--text-sm); font-weight: var(--weight-semibold); }
.dim-score { font-size: var(--text-sm); font-weight: var(--weight-bold); color: var(--accent-primary); }
.dim-level { font-size: 10.5px; padding: 1px var(--space-2); border-radius: 9px; background: var(--bg-secondary); }
.lv-excellent, .lv-good { color: var(--accent-success); }
.lv-average { color: var(--color-warning); } .lv-weak, .lv-insufficient { color: var(--accent-danger); }
.dim-bar { height: 6px; border-radius: 4px; background: var(--bg-secondary); overflow: hidden; }
.dim-fill { height: 100%; background: linear-gradient(90deg, var(--accent-primary), var(--accent-secondary)); border-radius: 4px; width: 100%; transform-origin: left; transition: transform var(--duration-slow) var(--ease-standard); }
.dim-rationale { font-size: 11.5px; color: var(--text-secondary); margin-top: var(--space-1); line-height: 1.5; }
.dim-evidence { margin-top: 5px; display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1) 6px; }
.ev-label { font-size: 10px; color: var(--accent-primary); font-weight: var(--weight-semibold); background: rgba(var(--accent-rgb),0.1); padding: 1px 6px; border-radius: 4px; }
.ev-quote { font-size: 10.5px; color: var(--text-secondary); background: var(--bg-soft, rgba(0,0,0,0.03)); padding: 1px 6px; border-radius: 4px; border-left: 2px solid var(--accent-primary); }

.sw-block { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); margin: 14px 0; }
@media (max-width: 720px) { .sw-block { grid-template-columns: 1fr; } }
.sw-strength, .sw-weak { background: var(--bg-card); border-radius: 12px; padding: var(--space-3) 14px;
  border: 1px solid var(--border-color); font-size: var(--text-sm); line-height: 1.6; }
.sw-weak ul { margin: 6px 0 0; padding-left: 18px; }
.plan-block { background: var(--bg-card); border: 1px solid var(--border-color);
  border-radius: 14px; padding: var(--space-4); margin-bottom: 14px; }
.plan-block h3 { margin: 0 0 10px; font-size: var(--text-md); }
.plan-item { display: flex; gap: 10px; align-items: baseline; padding: var(--space-2) 0; border-bottom: 1px dashed var(--border-color); font-size: var(--text-sm); flex-wrap: wrap; }
.plan-dim { flex-shrink: 0; font-weight: var(--weight-semibold); color: var(--accent-primary); min-width: 64px; }
.plan-do { flex: 1; line-height: 1.5; }
.plan-freq { flex-shrink: 0; font-size: var(--text-2xs); color: var(--text-secondary); }
.plan-encourage { font-size: 12.5px; color: var(--text-secondary); margin: 10px 0 0; }
.replay { background: var(--bg-card); border: 1px solid var(--border-color);
  border-radius: 12px; padding: 10px 14px; font-size: var(--text-sm); margin-bottom: 14px; }
.replay summary { cursor: pointer; font-weight: var(--weight-semibold); }
.replay-turn { margin-top: var(--space-2); line-height: 1.6; }
.replay-turn.interviewer { color: var(--text-secondary); }
.replay-turn.student { color: var(--text-primary); }
.report-actions { display: flex; gap: 10px; justify-content: flex-end; }
</style>
