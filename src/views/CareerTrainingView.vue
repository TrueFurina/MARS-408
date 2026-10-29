<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { api, friendlyError } from '@/utils/api'
import type { operations } from '@/types/api.generated'
import { CAREER_DIM_LABEL as DIM_LABEL, CAREER_DIM_ORDER as DIM_ORDER } from '@/data/careerDimensions'

/* ===================== 类型与常量 ===================== */
type Step = 'select' | 'briefing' | 'battle' | 'report'
// 情景展示字段直接绑后端契约（py-server/api/career_training.py 的 CareerScenarioItem）。
// 2026-10-29 起该路由有了 response_model，生成类型才真正可用 —— 此前它是裸 dict，
// 前端只能手写一份"看着对"的接口，后端改名时 tsc 抓不到。
type ScenarioListResponse =
  operations['scenarios_api_career_scenarios_get']['responses'][200]['content']['application/json']
type Scenario = ScenarioListResponse['scenarios'][number]
interface Turn { role: 'interviewer' | 'student'; text: string; mode?: string; dimension?: string; evidence?: any }

const MODE_LABEL: Record<string, string> = { normal: '常规追问', escalating: '逐步加压', catfish: '鲶鱼反诘' }
const MODE_CLASS: Record<string, string> = { normal: 'm-normal', escalating: 'm-escalating', catfish: 'm-catfish' }
const DIFF_LABEL: Record<string, string> = { easy: '简单', medium: '中等', hard: '困难' }
// F5: 前后测阶段（老师安排前后测时选；不标记则不参与前后测对比）
const PHASE_LABEL: Record<string, string> = { '': '不标记', pre: '前测', post: '后测' }

/* ===================== 响应式状态 ===================== */
const step = ref<Step>('select')
const scenarios = ref<Scenario[]>([])
const scenarioId = ref('')
const difficulty = ref('medium')
const maxTurns = ref(6)
const phase = ref<string>('')           // F5: 前后测标记（''=不标记 / pre / post）
const loadingScenarios = ref(true)
const busy = ref(false)
const errorMsg = ref('')
// 终评已异步化（公网网关约 60s 超时，终评两次串行 LLM 必然超时 ⇒ 后端先回 generating）
const reportPending = ref(false)
const progressMsg = ref('')

const session = ref<any>(null)
const turns = ref<Turn[]>([])
const answerInput = ref('')
const assessment = ref<any>(null)
const improvement = ref<any>(null)
const evidenceChain = ref<any[]>([])
const battleScroll = ref<HTMLElement | null>(null)
const busyExport = ref(false)
const exportError = ref('')

/* 教师任务：凭任务码加入后，场景/难度/轮数由任务决定，会话须带 task_id 才会进班级看板 */
const joinCode = ref('')
const joinedTask = ref<any>(null)
const joining = ref(false)

const currentScenario = computed(() => scenarios.value.find(s => s.id === scenarioId.value))
const turnsDone = computed(() => turns.value.filter(t => t.role === 'student').length)
const progressText = computed(() => `${turnsDone.value}/${session.value?.max_turns ?? maxTurns.value}`)

/**
 * 任务码前端校验 —— 与后端契约对齐，不是自造规则：
 *   · 长度：后端 `TaskJoinRequest.join_code = Field(..., min_length=4, max_length=16)`
 *   · 字符：后端生成侧是 `uuid.uuid4().hex[:6].upper()`，即大写十六进制；
 *     用户手输时统一大写并只接受 [A-Z0-9]，能挡住空格/中文/标点这类
 *     「必然匹配不到」的输入，避免把无意义请求打到后端再吃一个 404。
 *
 * 此前模板写死 `maxlength="12"`，与后端 16 的上限不一致：13–16 位的码
 * 会被输入框静默截断，用户看到「任务码无效」却看不出是自己少输了后 4 位。
 */
const JOIN_CODE_MIN = 4
const JOIN_CODE_MAX = 16
const JOIN_CODE_PATTERN = /^[A-Z0-9]+$/

const joinCodeError = computed(() => {
  const code = joinCode.value.trim().toUpperCase()
  if (!code) return ''
  if (code.length < JOIN_CODE_MIN || code.length > JOIN_CODE_MAX) {
    return `任务码应为 ${JOIN_CODE_MIN}–${JOIN_CODE_MAX} 位（当前 ${code.length} 位）`
  }
  if (!JOIN_CODE_PATTERN.test(code)) return '任务码只能包含字母和数字'
  return ''
})

/* ===================== 拉取场景 ===================== */
async function loadScenarios() {
  loadingScenarios.value = true
  try {
    const res = await api.get<ScenarioListResponse>('/career/scenarios')
    scenarios.value = res.scenarios || []
  } catch (e) {
    errorMsg.value = friendlyError(e, '场景加载失败')
  } finally {
    loadingScenarios.value = false
  }
}
loadScenarios()

/* ===================== 凭任务码加入教师实训 ===================== */
async function joinByCode() {
  const code = joinCode.value.trim().toUpperCase()
  if (!code || joining.value) return
  // 前端先挡：格式必然无效的码不发给后端（省一次往返，也给用户即时反馈）
  if (joinCodeError.value) { errorMsg.value = joinCodeError.value; return }
  joining.value = true; errorMsg.value = ''
  try {
    const res = await api.post<any>('/career/task/join', { join_code: code })
    joinedTask.value = res
    // 任务已锁定场景/难度/轮数，不再由学生自选
    scenarioId.value = res.scenario_id
    difficulty.value = res.difficulty || 'medium'
    maxTurns.value = Number(res.max_turns) || 6
  } catch (e) {
    joinedTask.value = null
    errorMsg.value = friendlyError(e, '任务码无效或加入失败')
  } finally { joining.value = false }
}

function quitTask() {
  joinedTask.value = null; joinCode.value = ''; scenarioId.value = ''
}

/* ===================== F3 学生任务中心（2026-10-15）=====================
 * 我已绑定班级的开放任务：免手输任务码，一键加入。
 * 一键加入仍走既有 POST /career/task/join（不开第二条信任链），
 * 加入后场景/难度/轮数锁定逻辑与手输任务码完全一致。 */
const myTasks = ref<any[]>([])

async function loadMyTasks() {
  try {
    const res = await api.get<any>('/career/my-tasks')
    myTasks.value = res.tasks || []
  } catch {
    myTasks.value = []  // 未加入任何班级等场景：静默为空，不打扰主流程
  }
}
loadMyTasks()

async function joinTaskDirect(t: any) {
  joinCode.value = String(t.join_code || '')
  await joinByCode()
}

/* ===================== F6 知情同意（2026-10-15）=====================
 * 首次进入先拉取同意状态；无记录时展示同意书门禁（不强制——不同意也可
 * 自由练习，但数据不纳入试用分析，这与 CONSENT_TEXT 的承诺一致）。 */
const consent = ref<{ agreed: boolean | null; text: string; version: string }>({
  agreed: null, text: '', version: '',
})
const consentBusy = ref(false)

async function loadConsent() {
  try {
    const res = await api.get<any>('/career/consent')
    consent.value = { agreed: res.consent?.agreed ?? null, text: res.text || '', version: res.version || '' }
  } catch {
    consent.value.agreed = null  // 拉取失败不当成已同意，按未同意展示门禁
  }
}
loadConsent()

async function submitConsent(agreed: boolean) {
  if (consentBusy.value) return
  consentBusy.value = true
  try {
    const res = await api.post<any>('/career/consent', { agreed })
    consent.value.agreed = res.agreed
  } catch (e) {
    errorMsg.value = friendlyError(e, '同意记录保存失败')
  } finally { consentBusy.value = false }
}

/* ===================== F6 课后简评（2026-10-15）=====================
 * 报告步骤底部：1-5 分 + 选填留言；仅本人本场一次（重复提交为更新）。 */
const myRating = ref(0)
const myComment = ref('')
const feedbackBusy = ref(false)
const feedbackDone = ref<{ rating: number; updated: boolean } | null>(null)

async function submitFeedback() {
  const sid = session.value?.session_id
  if (!sid || !myRating.value || feedbackBusy.value) return
  feedbackBusy.value = true
  try {
    const res = await api.post<any>(`/career/session/${encodeURIComponent(sid)}/feedback`, {
      rating: myRating.value, comment: myComment.value.trim(),
    })
    feedbackDone.value = { rating: res.rating, updated: res.updated }
  } catch (e) {
    errorMsg.value = friendlyError(e, '简评提交失败')
  } finally { feedbackBusy.value = false }
}

/* ===================== 启动实训 ===================== */
async function startTraining() {
  if (!scenarioId.value) { errorMsg.value = '请先选择一个实训情景'; return }
  busy.value = true; errorMsg.value = ''
  try {
    // task_id 必须透传：班级看板只统计带 task_id 的会话（db/career_store.class_dashboard）
    const payload: any = {
      scenario_id: scenarioId.value, difficulty: difficulty.value, max_turns: maxTurns.value,
    }
    if (joinedTask.value?.task_id) payload.task_id = joinedTask.value.task_id
    // F5: 仅在有选择时透传 phase（'' 不传，后端按未标记处理）
    if (phase.value) payload.phase = phase.value
    const res = await api.post<any>('/career/session/start', payload)
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
  busy.value = true; errorMsg.value = ''; progressMsg.value = ''
  // 末轮提交后不会再有「下一个问题」，后端会直接进入终评。
  // 实测（2026-10-20 公网）：末轮 answer 请求本身要 ~10s，这段时间 busy=true，
  // 若沿用默认提示，页面会显示「对手正在思考下一个问题…」——那是**错误反馈**，
  // 用户会以为还在等追问，实际已经在生成报告。故末轮提前把提示改成报告文案。
  const willFinish = turnsDone.value + 1 >= Number(session.value?.max_turns ?? maxTurns.value)
  if (willFinish) {
    progressMsg.value = '评估报告生成中（六维 ECD 评估 + 提升路径），约需 1–2 分钟…'
  }
  turns.value.push({ role: 'student', text })
  answerInput.value = ''
  await scrollBottom()
  try {
    const res = await api.post<any>(`/career/session/${session.value.session_id}/answer`, { answer: text })
    const idx = turns.value.length - 1
    const mine = turns.value[idx]
    if (mine) mine.evidence = res.last_evidence
    if (res.status === 'finished') {
      applyReport(res)
    } else if (res.status === 'finished_pending') {
      // 末轮触发终评：后台生成中，轮询报告（不要回滚学生气泡，作答已落库）
      reportPending.value = true
      progressMsg.value = res.message || '评估报告生成中…'
      await pollReport(session.value.session_id)
    } else {
      turns.value.push({
        role: 'interviewer', text: res.next_question.question,
        mode: res.next_question.mode, dimension: res.next_question.probe_dimension,
      })
      await scrollBottom()
    }
  } catch (e) {
    // 末轮终评若被网关掐断（504），后端仍在生成 —— 先试轮询，别回滚作答
    const sid = session.value?.session_id
    if (sid && await pollReport(sid, true)) { busy.value = false; return }
    errorMsg.value = friendlyError(e, '提交失败')
    turns.value.pop() // 失败回滚学生气泡
  } finally {
    reportPending.value = false
    busy.value = false
  }
}

/* 提前结束（至少4轮后端才出报告）
   终评走后台异步：end 立即回 generating，前端轮询 report 直到 ready。
   若 end 请求本身被网关掐断（504），后端其实仍在算 —— 不直接判失败，转轮询。 */
async function finishEarly() {
  if (busy.value) return
  const sid = session.value?.session_id
  if (!sid) return
  busy.value = true; errorMsg.value = ''
  reportPending.value = true; progressMsg.value = '评估报告生成中（六维 ECD 评估 + 提升路径），约需 1–2 分钟…'
  try {
    const res = await api.post<any>(`/career/session/${sid}/end`, { force: false })
    if (res.status === 'insufficient') {
      errorMsg.value = res.message
      reportPending.value = false; busy.value = false
      return
    }
    if (res.status === 'finished') { applyReport(res); return }
    await pollReport(sid)
  } catch (e) {
    const ok = await pollReport(sid, true)
    if (!ok) errorMsg.value = friendlyError(e, '结束失败')
  } finally {
    reportPending.value = false; busy.value = false
  }
}

/* 轮询报告：后端报告落库后返回完整内容（最多等 180 秒 —— 免费档 LLM 终评实测 ~65s）*/
async function pollReport(sid: string, silentOnError = false): Promise<boolean> {
  const deadline = Date.now() + 180_000
  while (Date.now() < deadline) {
    await new Promise(r => setTimeout(r, 3000))
    try {
      const r = await api.get<any>(`/career/session/${sid}/report`)
      if (r?.status === 'failed') {
        errorMsg.value = r.message || '报告生成失败，请重试结束'
        reportPending.value = false
        return false
      }
      if (r?.status === 'generating') {
        progressMsg.value = r.message || '评估报告生成中…'
        continue
      }
      if (r?.assessment && Object.keys(r.assessment).length) { applyReport(r); return true }
    } catch {
      if (silentOnError) continue  // 网关抖动：继续等
      throw new Error('报告拉取失败')
    }
  }
  progressMsg.value = ''
  errorMsg.value = '报告生成超时（超过 90 秒），请稍后重试结束'
  reportPending.value = false
  return false
}

function applyReport(r: any) {
  assessment.value = r.assessment
  improvement.value = r.improvement
  evidenceChain.value = r.evidence_chain || []
  reportPending.value = false
  step.value = 'report'
}

function restart() {
  step.value = 'select'; session.value = null; assessment.value = null
  improvement.value = null; evidenceChain.value = []; turns.value = []; answerInput.value = ''
  myRating.value = 0; myComment.value = ''; feedbackDone.value = null
}

/* 导出证据链「一页纸」：拉取自包含 HTML，新标签页打开（浏览器另存为 PDF） */
async function exportEvidenceOnePager() {
  const id = session.value?.session_id
  if (!id || busyExport.value) return
  busyExport.value = true
  exportError.value = ''
  try {
    const { blob: reportBlob, ok, status } = await api.getBlob(`/career/session/${encodeURIComponent(id)}/export-report`)
    if (!ok) {
      const text = await reportBlob.text().catch(() => '')
      throw new Error(`导出失败 (${status}) ${text.slice(0, 200)}`)
    }
    const html = await reportBlob.text()
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const win = window.open(url, '_blank')
    if (!win) {
      // 弹窗被拦截时降级为下载
      const a = document.createElement('a')
      a.href = url
      a.download = `evidence-${id}.html`
      a.click()
    }
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (e) {
    exportError.value = friendlyError(e, '导出证据一页纸失败')
  } finally {
    busyExport.value = false
  }
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
        <router-link class="growth-link" to="/career/growth">查看我的成长（六维趋势 · 前后测对比 · 证据金句）→</router-link>
      </div>

      <!-- F6 知情同意门禁：无同意记录时展示（不强制阻断——不同意也可自由练习） -->
      <div v-if="consent.agreed === null" class="consent-gate">
        <div class="cg-title"> 知情同意</div>
        <p class="cg-text">{{ consent.text }}</p>
        <div class="cg-actions">
          <button class="ghost-btn" :disabled="consentBusy" @click="submitConsent(false)">不同意</button>
          <button class="primary-btn" :disabled="consentBusy" @click="submitConsent(true)">
            {{ consentBusy ? '提交中…' : '同意并继续' }}
          </button>
        </div>
      </div>
      <div v-else-if="consent.agreed === false" class="consent-note">
        你已记录「不同意」：仍可自由练习，但本次数据不会纳入试用分析（可在刷新后重新考虑）。
      </div>

      <!-- 教师任务码：有码即加入老师布置的实训（加入后场景/难度/轮数由任务锁定） -->
      <div class="join-bar">
        <template v-if="!joinedTask">
          <span class="opt-label">有教师任务码？</span>
          <input
            v-model="joinCode"
            class="join-input"
            type="text"
            :maxlength="JOIN_CODE_MAX"
            placeholder="输入任务码，例如 A1B2C3"
            :disabled="joining"
            :aria-invalid="!!joinCodeError"
            aria-describedby="join-code-hint"
            @keydown.enter="joinByCode"
          >
          <button class="ghost-btn" :disabled="joining || !joinCode.trim() || !!joinCodeError" @click="joinByCode">
            {{ joining ? '加入中…' : '加入实训' }}
          </button>
          <!-- 错误提示放在 v-if 分支内部：插在 v-if / v-else 两个 template 之间会打断配对 -->
          <p v-if="joinCodeError" id="join-code-hint" class="join-code-error" role="alert">{{ joinCodeError }}</p>
        </template>
        <template v-else>
          <span class="join-badge">教师任务已加入</span>
          <span class="join-desc">任务码 <strong>{{ joinCode.toUpperCase() }}</strong> · 场景与轮数由老师设定</span>
          <span v-if="!joinedTask.roster_bound" class="join-warn">
            未在班级花名册匹配到你的姓名，教师看板会把你显示为「未认领」
          </span>
          <span v-else-if="joinedTask.bound_match === 'name'" class="join-ok">
            已按姓名匹配花名册：{{ joinedTask.bound_name }}
          </span>
          <span v-else class="join-warn">
            花名册未按姓名匹配到你，已按名单顺序绑定——看板显示的姓名可能与你本人不符
          </span>
          <button class="ghost-btn" @click="quitTask">退出任务</button>
        </template>
      </div>

      <!-- F3 我的任务：老师布置给我班的任务，一键加入（与手输任务码同一加入路径） -->
      <div v-if="!joinedTask && myTasks.length" class="my-tasks">
        <span class="opt-label">老师布置的任务（{{ myTasks.length }}）</span>
        <ul>
          <li v-for="t in myTasks" :key="t.task_id">
            <span class="mt-class">{{ t.class_name }}</span>
            <span class="mt-title">{{ t.scenario_title || t.scenario_id }}</span>
            <span class="mt-meta">{{ DIFF_LABEL[t.difficulty] || t.difficulty }} · {{ t.max_turns }} 轮 · 任务码 {{ t.join_code }}</span>
            <button class="ghost-btn" :disabled="joining" @click="joinTaskDirect(t)">加入</button>
          </li>
        </ul>
      </div>

      <div v-if="joinedTask" class="task-locked">
        <div class="tl-sub">{{ currentScenario?.type_label }} · {{ currentScenario?.subtype_label }}</div>
        <div class="tl-title">{{ currentScenario?.title || '（任务指定场景）' }}</div>
      </div>
      <div v-else-if="loadingScenarios" class="c-loading">正在加载实训情景…</div>
      <!-- 加载失败时 scenarios 为空：此前会渲染成一片空白网格，用户看不出是
           「加载失败」还是「本来就没有情景」，也没有重试入口，只能刷新整页 -->
      <div v-else-if="!scenarios.length" class="c-empty" role="alert">
        <p class="c-empty-text">{{ errorMsg || '暂时没有可用的实训情景' }}</p>
        <button class="ghost-btn" :disabled="loadingScenarios" @click="loadScenarios">重新加载</button>
      </div>
      <div v-else class="scenario-grid" role="radiogroup" aria-label="实训情景">
        <div v-for="s in scenarios" :key="s.id" class="scenario-card"
             :class="{ active: scenarioId === s.id }" role="radio" :aria-checked="scenarioId === s.id"
             tabindex="0"
             @click="scenarioId = s.id"
             @keydown.enter.prevent="scenarioId = s.id"
             @keydown.space.prevent="scenarioId = s.id">
          <div class="sc-type">{{ s.type_label }} · {{ s.subtype_label }}</div>
          <div class="sc-title">{{ s.title }}</div>
        </div>
      </div>

      <div v-if="!joinedTask" class="opt-bar">
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
        <div class="opt-group">
          <span class="opt-label">阶段（老师安排前后测时选）</span>
          <button v-for="p in ['', 'pre', 'post']" :key="p" class="chip"
                  :class="{ on: phase === p }" @click="phase = p">{{ PHASE_LABEL[p] }}</button>
        </div>
      </div>

      <div v-if="errorMsg" class="c-error">{{ errorMsg }}</div>
      <button class="primary-btn" :disabled="busy || !scenarioId" @click="startTraining">
        {{ busy ? '正在生成对抗脚本…' : (joinedTask ? '开始本次任务实训' : '开始实训') }}
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
        <!-- busy 期间若有明确的进度文案（末轮终评）就显示它，否则才是「等追问」 -->
        <div v-if="busy && !reportPending" class="bubble interviewer typing">{{ progressMsg || '对手正在思考下一个问题…' }}</div>
        <div v-if="reportPending" class="bubble interviewer typing">{{ progressMsg || '评估报告生成中…' }}</div>
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

      <div v-if="assessment?.highlights?.length || assessment?.risk_flags?.length" class="hl-block">
        <div v-if="assessment?.highlights?.length" class="hl-good">
          <div class="hl-title">表现亮点</div>
          <ul><li v-for="(h, i) in assessment.highlights" :key="i">{{ h }}</li></ul>
        </div>
        <div v-if="assessment?.risk_flags?.length" class="hl-risk">
          <div class="hl-title">风险提示</div>
          <ul><li v-for="(r, i) in assessment.risk_flags" :key="i">{{ r }}</li></ul>
        </div>
      </div>

      <div v-if="improvement" class="plan-block">
        <h3> 针对性提升路径</h3>
        <div v-for="(a, i) in improvement.actions" :key="i" class="plan-item">
          <span class="plan-dim">{{ DIM_LABEL[a.dimension] || a.dimension }}</span>
          <span class="plan-do">{{ a.do }}</span>
          <span class="plan-freq">{{ a.frequency }}</span>
        </div>
        <div v-if="improvement.learning_resources?.length" class="lr-block">
          <div class="lr-title"> 学习资源 · 方法论卡</div>
          <div v-for="(r, i) in improvement.learning_resources" :key="i" class="lr-card">
            <div class="lr-head">
              <span class="lr-dim">{{ DIM_LABEL[r.dimension] || r.dimension }}</span>
              <span class="lr-name">{{ r.title }}</span>
            </div>
            <ul><li v-for="(p, j) in r.points" :key="j">{{ p }}</li></ul>
          </div>
        </div>
        <p class="plan-encourage">{{ improvement.encouragement }}</p>
      </div>

      <details class="replay">
        <summary>查看完整对抗记录与证据链（{{ turns.filter(t=>t.role==='student').length }} 轮）</summary>
        <div v-for="(t, i) in turns" :key="i" class="replay-turn" :class="t.role">
          <b>{{ t.role === 'interviewer' ? '对手' : '我' }}：</b>{{ t.text }}
        </div>
      </details>

      <div v-if="exportError" class="c-error">{{ exportError }}</div>
      <div class="report-actions">
        <button class="ghost-btn" :disabled="busyExport" @click="exportEvidenceOnePager">导出证据一页纸</button>
        <button class="ghost-btn" @click="step = 'battle'">返回对抗</button>
        <button class="primary-btn" @click="restart">再来一场 →</button>
      </div>

      <!-- F6 课后简评：仅本人本场一次（重复提交为更新） -->
      <div class="feedback-card">
        <template v-if="!feedbackDone">
          <div class="fb-title">这场对抗体验如何？（1-5 分）</div>
          <div class="fb-stars">
            <button v-for="n in [1,2,3,4,5]" :key="n" class="fb-star"
                    :class="{ on: myRating >= n }" :aria-label="`${n} 分`"
                    @click="myRating = n">★</button>
          </div>
          <textarea v-model="myComment" class="fb-input" rows="2" maxlength="500"
                    placeholder="选填：哪里特别真实？哪里希望改进？（不超过 500 字）"></textarea>
          <button class="ghost-btn" :disabled="feedbackBusy || !myRating" @click="submitFeedback">
            {{ feedbackBusy ? '提交中…' : '提交简评' }}
          </button>
        </template>
        <div v-else class="fb-done">
          已收到你的简评（{{ feedbackDone.rating }} 分）{{ feedbackDone.updated ? '· 已更新' : '' }}，谢谢反馈！
        </div>
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
/* 情景列表空/失败态：给文案 + 重试按钮，替代此前的一片空白网格 */
.c-empty { padding: 18px 14px; border-radius: 10px; margin: var(--space-3) 0; text-align: center;
  background: var(--bg-secondary); border: 1px dashed var(--border-color); }
.c-empty-text { margin: 0 0 var(--space-3); font-size: var(--text-sm); color: var(--text-secondary); }

/* 教师任务码 / 任务锁定态 */
.join-bar { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap;
  background: var(--bg-secondary); border-radius: 12px; padding: 10px 12px; margin-bottom: var(--space-3); }
.join-input { flex: 1; min-width: 150px; max-width: 260px; padding: 8px 12px; border-radius: 9px;
  border: 1px solid var(--border-color); background: var(--bg-card); color: var(--text-primary); font-size: var(--text-sm); }
.join-badge { font-size: var(--text-2xs); font-weight: var(--weight-semibold); color: var(--accent-primary);
  background: var(--accent-primary-10); padding: 3px 10px; border-radius: 10px; }
.join-desc { font-size: var(--text-sm); color: var(--text-secondary); }
.join-warn { flex-basis: 100%; font-size: var(--text-2xs); color: var(--color-warning); }
/* 任务码校验失败：独占一行 + 红边输入框（不只靠颜色传达，文案本身已说明原因） */
.join-code-error { flex-basis: 100%; margin: 0; font-size: var(--text-2xs); color: var(--text-danger); }
.join-input[aria-invalid="true"] { border-color: var(--color-danger-border); }
.join-ok { font-size: var(--text-2xs); color: var(--accent-success); }
.task-locked { border: 1.5px solid var(--accent-primary); border-radius: 14px; padding: 14px;
  background: var(--bg-card); box-shadow: 0 0 0 3px var(--accent-primary-15); }
.tl-sub { font-size: var(--text-2xs); color: var(--accent-primary); font-weight: var(--weight-semibold); margin-bottom: 6px; }
.tl-title { font-size: var(--text-base); font-weight: var(--weight-semibold); line-height: 1.5; }

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

/* F3 我的任务（2026-10-15） */
.my-tasks { margin-bottom: var(--space-4); padding: .6rem .8rem; border: 1px dashed var(--border, var(--color-border)); border-radius: 10px; }
.my-tasks ul { list-style: none; margin: .4rem 0 0; padding: 0; display: grid; gap: .4rem; }
.my-tasks li { display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; font-size: var(--text-sm); }
.my-tasks li .ghost-btn { margin-left: auto; padding: 6px 14px; font-size: var(--text-sm); }
.mt-class { font-weight: var(--weight-semibold); }
.mt-title { color: var(--accent); }
.mt-meta { color: var(--text-secondary); font-size: var(--text-sm); }
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
.hl-block { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); margin: 0 0 14px; }
@media (max-width: 720px) { .hl-block { grid-template-columns: 1fr; } }
.hl-good, .hl-risk { background: var(--bg-card); border-radius: 12px; padding: var(--space-3) 14px;
  border: 1px solid var(--border-color); font-size: var(--text-sm); line-height: 1.6; }
.hl-good { border-left: 3px solid var(--accent-success); }
.hl-risk { border-left: 3px solid var(--accent-danger); }
.hl-title { font-weight: var(--weight-semibold); margin-bottom: 6px; }
.hl-good .hl-title { color: var(--accent-success); }
.hl-risk .hl-title { color: var(--accent-danger); }
.hl-good ul, .hl-risk ul { margin: 0; padding-left: 18px; }
.hl-good li, .hl-risk li { margin: 3px 0; }
.plan-block { background: var(--bg-card); border: 1px solid var(--border-color);
  border-radius: 14px; padding: var(--space-4); margin-bottom: 14px; }
.plan-block h3 { margin: 0 0 10px; font-size: var(--text-md); }
.plan-item { display: flex; gap: 10px; align-items: baseline; padding: var(--space-2) 0; border-bottom: 1px dashed var(--border-color); font-size: var(--text-sm); flex-wrap: wrap; }
.plan-dim { flex-shrink: 0; font-weight: var(--weight-semibold); color: var(--accent-primary); min-width: 64px; }
.plan-do { flex: 1; line-height: 1.5; }
.plan-freq { flex-shrink: 0; font-size: var(--text-2xs); color: var(--text-secondary); }
.plan-encourage { font-size: 12.5px; color: var(--text-secondary); margin: 10px 0 0; }
.lr-block { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border-color); }
.lr-title { font-size: var(--text-sm); font-weight: var(--weight-semibold); color: var(--accent-primary); margin-bottom: 8px; }
.lr-card { border: 1px solid var(--border-color); border-left: 3px solid var(--accent-success);
  border-radius: 8px; padding: 8px 12px; margin-bottom: 8px; }
.lr-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 4px; }
.lr-dim { font-size: var(--text-2xs); font-weight: var(--weight-semibold); color: var(--accent-success);
  background: var(--accent-primary-10); padding: 1px 8px; border-radius: 9px; flex-shrink: 0; }
.lr-name { font-size: var(--text-sm); font-weight: var(--weight-semibold); }
.lr-card ul { margin: 4px 0 0; padding-left: 18px; }
.lr-card li { font-size: 12.5px; color: var(--text-secondary); line-height: 1.6; margin: 2px 0; }
.replay { background: var(--bg-card); border: 1px solid var(--border-color);
  border-radius: 12px; padding: 10px 14px; font-size: var(--text-sm); margin-bottom: 14px; }
.replay summary { cursor: pointer; font-weight: var(--weight-semibold); }
.replay-turn { margin-top: var(--space-2); line-height: 1.6; }
.replay-turn.interviewer { color: var(--text-secondary); }
.replay-turn.student { color: var(--text-primary); }
.report-actions { display: flex; gap: 10px; justify-content: flex-end; }

/* F4 成长页入口 */
.growth-link { display: inline-block; margin-top: 8px; font-size: var(--text-sm); color: var(--accent-primary); text-decoration: none; }
.growth-link:hover { text-decoration: underline; }

/* F6 知情同意门禁 */
.consent-gate { background: var(--bg-card); border: 1px solid var(--accent-primary); border-radius: 12px;
  padding: var(--space-4); margin-bottom: var(--space-4); }
.cg-title { font-size: var(--text-md); font-weight: var(--weight-semibold); margin-bottom: var(--space-2); }
.cg-text { font-size: var(--text-sm); color: var(--text-secondary); line-height: 1.7; margin: 0 0 var(--space-3); }
.cg-actions { display: flex; gap: 10px; justify-content: flex-end; }
.consent-note { background: var(--bg-secondary); border-radius: 10px; padding: 10px 14px;
  font-size: var(--text-sm); color: var(--text-secondary); margin-bottom: var(--space-4); }

/* F6 课后简评 */
.feedback-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 12px;
  padding: var(--space-3) 14px; margin-top: 14px; }
.fb-title { font-size: var(--text-sm); font-weight: var(--weight-semibold); margin-bottom: var(--space-2); }
.fb-stars { display: flex; gap: 4px; margin-bottom: var(--space-2); }
.fb-star { background: none; border: none; font-size: 22px; line-height: 1; cursor: pointer;
  color: var(--text-dim, var(--text-secondary)); padding: 0 2px; }
.fb-star.on { color: var(--color-warning); }
.fb-input { width: 100%; box-sizing: border-box; border: 1px solid var(--border-color); border-radius: 8px;
  background: var(--bg-secondary); color: var(--text-primary); padding: 8px 10px;
  font-size: var(--text-sm); font-family: inherit; resize: vertical; margin-bottom: var(--space-2); }
.fb-done { font-size: var(--text-sm); color: var(--accent-primary); }
</style>
