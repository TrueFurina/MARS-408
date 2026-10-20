<script setup lang="ts">
// P4 教师端：建班 → 导花名册 → 发任务（任务码）→ 班级学情看板
// F1（2026-10-15）：学生个体下钻；F2：任务管理中心（进度 + 关闭）
import { ref, onMounted, watch } from 'vue'
import { api, friendlyError } from '@/utils/api'
import { CAREER_DIM_LABEL, CAREER_DIM_ORDER } from '@/data/careerDimensions'
import { useModalFocus } from '@/composables/useModalFocus'

interface ClassItem { class_id: string; class_name: string; student_count: number }
interface StudentItem { student_no: string; name: string; user_id: string | null; joined_at?: string }
interface TaskStat { started_count: number; finished_count: number; session_count: number }
interface TaskItem {
  task_id: string; join_code: string; scenario_id?: string; scenario_title?: string
  difficulty: string; max_turns: number; class_id: string
  status?: string; stats?: TaskStat
}
interface DashSession { session_id: string; status: string; turn_count: number; overall: number | null }
interface DashStudent {
  student_no: string; name: string; user_id: string | null; bound: boolean
  session_count: number; finished_count: number
  dimension_avg: Record<string, number>; overall_best: number | null
  sessions: DashSession[]
}
interface DashSummary {
  student_count: number
  /** 名册行已绑定账号的人数（凭码加入过）——与 started_count「已开练」是两个口径 */
  joined_count: number
  started_count: number; finished_count: number; assessed_count: number
  completion_rate: number
  dimension_avg: Record<string, number>
  weakest_dimensions: { dimension: string; avg: number }[]
  note: string
  /** 覆盖率说明：分母构成 + 谁没被计入（后端算，前端只渲染；旧响应无此字段） */
  coverage_note?: string
}
interface DashAttention extends DashStudent { reason: string; detail: string }
interface Dash {
  class_id: string; class_name: string; student_count: number
  students: DashStudent[]
  /** 班级级聚合（2026-10-14 新增；旧响应可能没有 ⇒ 前端按可选处理） */
  summary?: DashSummary
  attention?: DashAttention[]
}
interface ScenarioItem { id: string; title: string }
/** F1 学生个体下钻响应（GET /career/classes/{cid}/students/{uid}/detail） */
interface DetailSession {
  session_id: string; status: string; turn_count: number
  started_at: string; finished_at: string | null
  scenario_id: string; difficulty: string
  dimension_scores: Record<string, number>; overall: number | null
}
interface StudentDetail {
  student_no: string; name: string; user_id: string
  session_count: number; finished_count: number
  dimension_avg: Record<string, number>; overall_best: number | null
  sessions: DetailSession[]
}

/** attention.reason 的中文名（后端只给结构性事实标识，文案在前端） */
const REASON_LABEL: Record<string, string> = {
  not_started: '未开始', unfinished: '未完成', no_score: '无评分', lowest_score: '得分靠后',
}
const DIFF_LABEL: Record<string, string> = { easy: '简单', medium: '中等', hard: '困难' }
const STATUS_LABEL: Record<string, string> = { ongoing: '进行中', finished: '已完成' }

/** 维度 key → 中文名（未收录时回落原 key，不隐藏异常） */
function dimLabel(d: string) { return CAREER_DIM_LABEL[d] || d }

const classes = ref<ClassItem[]>([])
const scenarios = ref<ScenarioItem[]>([])
const newClassName = ref('')
const rosterText = ref('')
const activeClassId = ref('')
const students = ref<StudentItem[]>([])
const taskScenarioId = ref('')
const taskDifficulty = ref('medium')
const taskMaxTurns = ref(8)
const lastTask = ref<TaskItem | null>(null)
const dash = ref<Dash | null>(null)
const loading = ref(false)
const msg = ref('')

/* ── F2 任务管理中心（2026-10-15）── */
const tasks = ref<TaskItem[]>([])
const closingTaskId = ref('')

/* ── F1 学生个体下钻（2026-10-15）：焦点管理复用 P1-1 浮层 composable ── */
const detail = ref<StudentDetail | null>(null)
const detailLoading = ref(false)
const detailRef = ref<HTMLElement | null>(null)
const { activate: activateDetail, deactivate: deactivateDetail, trapTab: trapDetailTab } =
  useModalFocus(detailRef)
watch(detail, (d) => { if (d) activateDetail(); else deactivateDetail() })

async function loadClasses() {
  const res = await api.get<{ classes: ClassItem[] }>('/career/classes')
  classes.value = res.classes || []
}

async function loadScenarios() {
  const res = await api.get<{ scenarios: ScenarioItem[] }>('/career/scenarios')
  scenarios.value = res.scenarios || []
  if (!taskScenarioId.value && scenarios.value.length) {
    taskScenarioId.value = scenarios.value[0]?.id ?? ''
  }
}

async function createClass() {
  const name = newClassName.value.trim()
  if (!name) return
  loading.value = true
  try {
    await api.post<{ class_id: string }>('/career/classes', { class_name: name })
    newClassName.value = ''
    msg.value = `班级「${name}」已创建`
    await loadClasses()
  } catch (e) {
    msg.value = friendlyError(e, '操作失败')
  } finally {
    loading.value = false
  }
}

async function importRoster(cls: ClassItem) {
  if (!rosterText.value.trim()) {
    msg.value = '请先粘贴花名册（每行：学号 姓名）'
    return
  }
  loading.value = true
  try {
    const res = await api.post<{ imported: number; students: StudentItem[] }>(
      `/career/classes/${cls.class_id}/students`, { roster: rosterText.value })
    msg.value = `已导入 ${res.imported} 名学生到「${cls.class_name}」`
    rosterText.value = ''
    await selectClass(cls.class_id)
    await loadClasses()
  } catch (e) {
    msg.value = friendlyError(e, '操作失败')
  } finally {
    loading.value = false
  }
}

async function selectClass(classId: string) {
  activeClassId.value = classId
  dash.value = null
  try {
    const res = await api.get<{ students: StudentItem[] }>(
      `/career/classes/${classId}/students`)
    students.value = res.students || []
  } catch (e) {
    msg.value = friendlyError(e, '操作失败')
  }
  const cls = classes.value.find(c => c.class_id === classId)
  if (cls) await loadTasks(cls)
  await loadFeedback()
}

/* ── F2 任务管理中心：本班任务列表（含参与进度）── */
async function loadTasks(cls: ClassItem) {
  try {
    const res = await api.get<{ tasks: TaskItem[] }>(`/career/tasks?class_id=${cls.class_id}`)
    tasks.value = res.tasks || []
  } catch (e) {
    tasks.value = []
    msg.value = friendlyError(e, '任务列表加载失败')
  }
}

/** 关闭任务：学生端不再出现；历史会话/评分不动（后端语义） */
async function closeTask(t: TaskItem) {
  closingTaskId.value = t.task_id
  try {
    await api.post(`/career/tasks/${t.task_id}/close`, {})
    msg.value = `任务 ${t.join_code} 已关闭（已完成场次与评分保留）`
    const cls = classes.value.find(c => c.class_id === activeClassId.value)
    if (cls) await loadTasks(cls)
  } catch (e) {
    msg.value = friendlyError(e, '关闭失败')
  } finally { closingTaskId.value = '' }
}

/* ── F1 学生个体下钻：看板点姓名 → 该生在班内全部会话明细 ── */
async function openStudentDetail(s: DashStudent) {
  if (!s.user_id) {
    msg.value = '该学生尚未绑定账号（未加入），暂无实训明细'
    return
  }
  detailLoading.value = true
  try {
    detail.value = await api.get<StudentDetail>(
      `/career/classes/${activeClassId.value}/students/${s.user_id}/detail`)
  } catch (e) {
    msg.value = friendlyError(e, '明细加载失败')
  } finally { detailLoading.value = false }
}

function closeStudentDetail() {
  detail.value = null
}

/** ISO/SQLite 时间串 → 紧凑显示（PG 返 ISO、SQLite 返 'YYYY-MM-DD HH:MM:SS'） */
function shortTime(ts: string | null): string {
  if (!ts) return '—'
  return ts.slice(0, 16).replace('T', ' ')
}

async function createTask() {
  if (!activeClassId.value || !taskScenarioId.value) {
    msg.value = '请先选择班级与情景'
    return
  }
  loading.value = true
  try {
    const res = await api.post<TaskItem>('/career/tasks', {
      class_id: activeClassId.value,
      scenario_id: taskScenarioId.value,
      difficulty: taskDifficulty.value,
      max_turns: taskMaxTurns.value,
    })
    lastTask.value = res
    msg.value = `任务已发布，任务码：${res.join_code}`
  } catch (e) {
    msg.value = friendlyError(e, '操作失败')
  } finally {
    loading.value = false
  }
}

async function loadDashboard(cls: ClassItem) {
  loading.value = true
  try {
    dash.value = await api.get<Dash>(`/career/classes/${cls.class_id}/dashboard`)
    activeClassId.value = cls.class_id
  } catch (e) {
    msg.value = friendlyError(e, '操作失败')
  } finally {
    loading.value = false
  }
  await loadFeedback()
}

/** CSV 单元格转义：含逗号 / 引号 / 换行时加双引号并转义内部引号（防姓名等破列） */
function csvCell(v: unknown): string {
  const s = v == null ? '' : String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

/** 导出班级看板 CSV（过程性考核依据落盘；与素养测评导出一致，纯前端生成，零后端依赖） */
function exportDashCsv() {
  if (!dash.value) return
  const d = dash.value
  // 维度列：固定取 canonical 六维（CAREER_DIM_ORDER，与后端 agents/career_state.DIMENSIONS
  // 同序同集），无数据留空。**不按数据键取列** —— 2026-10-15 浏览器走查实测：某轮评估
  // 对「技术汇报」无证据（score=null）时，按数据键取列会让该维整列消失，"全班六维"
  // 名不副实，且跨班级/场次合并 CSV 会错列。
  const dims: string[] = [...CAREER_DIM_ORDER]
  const head = ['学号', '姓名', '是否加入', '完成场次', '总会话', 'best_overall', ...dims.map(dimLabel)]
  const rows = d.students.map(s =>
    [s.student_no || '', s.name, s.bound ? '已加入' : '未加入',
     s.finished_count, s.session_count, s.overall_best ?? '',
     ...dims.map(dim => s.dimension_avg[dim] ?? '')])
  // 末尾附班级六维均分（有聚合才有）
  if (d.summary) {
    rows.push(['', `班级均分（${d.summary.student_count}人）`, '',
      d.summary.finished_count, d.summary.started_count, '',
      ...dims.map(dim => d.summary!.dimension_avg[dim] ?? '')])
  }
  const csv = [head, ...rows].map(r => r.map(csvCell).join(',')).join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `对抗实训看板_${d.class_name}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
  // 浏览器下载不进页面、也不报错：点了没反应时教师会以为导出坏了（2026-10-20 实测
  // 点击后 .msg 仍是上一次操作的文案）。这里给一条显式回执。
  msg.value = `已导出 CSV：${d.class_name}（${rows.length} 行，含表头与班级均分行）`
}

/** F7：导出班级学情一页纸（后端渲染自包含 HTML，浏览器另存为 PDF；镜像学生端证据一页纸） */
const busyExportReport = ref(false)
async function exportClassReport() {
  const cid = activeClassId.value
  if (!cid || busyExportReport.value) return
  busyExportReport.value = true
  try {
    const { blob: reportBlob, ok, status } = await api.getBlob(
      `/career/classes/${encodeURIComponent(cid)}/export-report`)
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
      a.download = `班级学情报告_${dash.value?.class_name || cid}.html`
      a.click()
      msg.value = '弹窗被浏览器拦截，已改为下载 HTML 文件（浏览器打开后可另存为 PDF）'
    } else {
      msg.value = '班级报告已在新标签页打开，在浏览器中「打印/另存为 PDF」即可归档'
    }
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (e) {
    msg.value = friendlyError(e, '导出班级报告失败')
  } finally {
    busyExportReport.value = false
  }
}

/* ── F6 课后简评：本班学生的真实提交（按班级过滤；无提交如实显示空）── */
interface FeedbackItem {
  id: string; session_id: string; user_id: string; rating: number
  comment: string; created_at: string; student_name: string; class_name: string
}
const feedback = ref<FeedbackItem[]>([])

async function loadFeedback() {
  if (!activeClassId.value) return
  try {
    const res = await api.get<{ feedback: FeedbackItem[] }>(
      `/career/feedback?class_id=${encodeURIComponent(activeClassId.value)}`)
    feedback.value = res.feedback || []
  } catch {
    feedback.value = []  // 加载失败按空处理，不阻塞看板
  }
}

/* ── F8 场景生成器（2026-10-18）：岗位方向 → 生成 draft → 人工审核 → 激活入库 ── */
interface JobDirection { key: string; label: string; default_scenario_type: string }
interface GeneratedScenario {
  id: string; type: string; subtype: string; type_label: string; subtype_label: string
  title: string; difficulty_default: string; setting: string; student_role: string
  interviewer_role: string; opening_question: string; probe_tree: string[]
  dimension_weights: Record<string, number>; focus_points: string[]
  bars_anchor: Record<string, Record<string, string>>; rubric_version: string
  generated?: boolean; job_direction?: string
}
const SCENARIO_TYPE_LABEL: Record<string, string> = {
  defense: '技术方案答辩', review: '需求评审质询', incident: '故障排查沟通', conflict: '团队冲突协调',
}

const jobDirections = ref<JobDirection[]>([])
const genDirection = ref('')
const genType = ref('')          // '' = 用岗位默认情景类型
const genDifficulty = ref('medium')
const genBusy = ref(false)
const genResult = ref<GeneratedScenario | null>(null)
const drafts = ref<GeneratedScenario[]>([])
const activatingId = ref('')

async function loadJobDirections() {
  try {
    const res = await api.get<{ directions: JobDirection[] }>('/career/scenario-job-directions')
    jobDirections.value = res.directions || []
  } catch { jobDirections.value = [] }
}

async function loadDrafts() {
  try {
    const res = await api.get<{ drafts: GeneratedScenario[] }>('/career/scenarios/drafts')
    drafts.value = res.drafts || []
  } catch { drafts.value = [] }
}

async function generateScenario() {
  if (!genDirection.value || genBusy.value) return
  genBusy.value = true; msg.value = ''
  try {
    const res = await api.post<{ scenario_id: string; scenario: GeneratedScenario; status: string }>(
      '/career/scenarios/generate', {
        job_direction: genDirection.value,
        scenario_type: genType.value || undefined,
        difficulty: genDifficulty.value,
      })
    genResult.value = res.scenario
    await loadDrafts()
    msg.value = '已生成草稿，请人工审核后激活入库'
  } catch (e) {
    msg.value = friendlyError(e, '场景生成失败')
  } finally { genBusy.value = false }
}

async function activateDraft(id: string) {
  if (!id || activatingId.value) return
  activatingId.value = id; msg.value = ''
  try {
    await api.post(`/career/scenarios/${encodeURIComponent(id)}/activate`)
    msg.value = '已激活入库，进入发任务可选场景列表'
    genResult.value = null
    await loadDrafts()
    await loadScenarios()   // 刷新发任务下拉，让新场景可选
  } catch (e) {
    msg.value = friendlyError(e, '激活失败')
  } finally { activatingId.value = '' }
}

onMounted(() => {
  loadClasses().catch(() => {})
  loadScenarios().catch(() => {})
  loadJobDirections().catch(() => {})
  loadDrafts().catch(() => {})
})
</script>

<template>
  <div class="teacher-career">
    <header class="page-head">
      <h1>对抗实训 · 教师端</h1>
      <p class="sub">建班、导入花名册、发布任务码，查看班级六维学情看板</p>
    </header>

    <p v-if="msg" class="msg" role="status">{{ msg }}</p>

    <section class="grid">
      <!-- 建班 -->
      <div class="card">
        <h2>1 · 建班</h2>
        <div class="row">
          <input v-model="newClassName" placeholder="班级名称，如：信息安全1班"
                 @keyup.enter="createClass" />
          <button :disabled="loading" @click="createClass">创建</button>
        </div>
        <ul class="class-list">
          <li v-for="c in classes" :key="c.class_id"
              :class="{ active: c.class_id === activeClassId }">
            <button class="link" @click="selectClass(c.class_id)">
              {{ c.class_name }}（{{ c.student_count }}人）
            </button>
            <button class="link dim" @click="loadDashboard(c)">看板</button>
          </li>
        </ul>
      </div>

      <!-- 花名册 + 发任务 -->
      <div class="card">
        <h2>2 · 花名册与任务</h2>
        <p class="hint">当前班级：{{ classes.find(c => c.class_id === activeClassId)?.class_name || '（未选）' }}</p>
        <textarea v-model="rosterText" rows="5"
                  placeholder="每行一条：&#10;01 张三&#10;02 李四&#10;（也可只写姓名）"></textarea>
        <!-- 操作口径：学生凭码加入时按**姓名**匹配花名册行，对不上会退回「第一个未绑定行」，
             成绩会记到名单里的另一人名下（2026-10-20 浏览器 E2E 实测：名册写「张三」、
             学生注册名「学生2」→ 后端 matched_by=first_unbound，看板上显示成"张三已绑定"）。
             这条风险必须在导入前说清，不能等数据错位了才发现。 -->
        <p class="hint">姓名请与学生注册时填写的姓名完全一致：加入时按姓名匹配花名册，对不上会按名单顺序绑定，看板上的姓名会与该生本人不符。</p>
        <button :disabled="loading || !activeClassId" @click="importRoster(classes.find(c => c.class_id === activeClassId)!)">
          导入花名册
        </button>

        <div class="row task-row">
          <select v-model="taskScenarioId">
            <option v-for="s in scenarios" :key="s.id" :value="s.id">{{ s.title }}</option>
          </select>
          <select v-model="taskDifficulty">
            <option value="easy">简单</option>
            <option value="medium">中等</option>
            <option value="hard">困难</option>
          </select>
          <input v-model.number="taskMaxTurns" type="number" min="4" max="12" />
          <button :disabled="loading || !activeClassId" @click="createTask">发布任务</button>
        </div>

        <div v-if="lastTask" class="join-code" data-testid="join-code">
          任务码：<strong>{{ lastTask.join_code }}</strong>
          <span class="dim">{{ lastTask.scenario_title }}</span>
        </div>

        <!-- F2 任务管理中心：本班任务 + 参与进度（按真实会话计，不虚构"已加入"） -->
        <div v-if="tasks.length" class="task-mgmt">
          <p class="agg-k">本班任务（{{ tasks.length }}）</p>
          <ul class="task-list">
            <li v-for="t in tasks" :key="t.task_id" :class="{ closed: t.status === 'closed' }">
              <div class="tl-head">
                <strong>{{ t.scenario_title || t.scenario_id }}</strong>
                <span class="tl-code">码 {{ t.join_code }}</span>
                <span class="tag" :class="t.status === 'closed' ? 'tag-closed' : 'tag-open'">
                  {{ t.status === 'closed' ? '已关闭' : '进行中' }}
                </span>
              </div>
              <div class="tl-meta">
                {{ DIFF_LABEL[t.difficulty] || t.difficulty }} · {{ t.max_turns }} 轮 ·
                已开始 {{ t.stats?.started_count ?? 0 }} 人 · 已完成 {{ t.stats?.finished_count ?? 0 }} 人
              </div>
              <button v-if="t.status !== 'closed'" class="link dim"
                      :disabled="closingTaskId === t.task_id"
                      @click="closeTask(t)">
                {{ closingTaskId === t.task_id ? '关闭中…' : '关闭任务' }}
              </button>
            </li>
          </ul>
        </div>

        <ul v-if="students.length" class="roster">
          <li v-for="(s, i) in students" :key="i">
            {{ s.student_no || '—' }} · {{ s.name }}
            <span class="dim">{{ s.user_id ? '已绑定' : '未绑定' }}</span>
          </li>
        </ul>
      </div>

      <!-- 看板 -->
      <div class="card wide">
        <h2>3 · 班级学情看板</h2>
        <p v-if="!dash" class="hint">点击班级右侧「看板」查看聚合学情</p>
        <template v-else>
          <div class="dash-exports">
            <button class="link" @click="exportDashCsv">导出 CSV（过程性考核依据）</button>
            <!-- F7：班级学情一页纸（自包含 HTML，浏览器另存为 PDF） -->
            <button class="link" :disabled="busyExportReport" @click="exportClassReport">
              {{ busyExportReport ? '生成中…' : '导出一页纸报告（PDF）' }}
            </button>
          </div>
          <!-- 班级级聚合：直接回答"这个班整体怎么样、哪里最弱、谁要关注" -->
          <div v-if="dash.summary" class="agg">
            <div class="stats">
              <!-- 加入 / 开练 / 完成 是三个不同口径，别合并成一个"参与"：
                   学生凭码加入只绑定花名册，不产生会话；合并会让"已加入但未开练"
                   显示成参与 0，教师会误判成没人来（2026-10-20 浏览器 E2E 实测）。 -->
              <div class="stat"><span class="k">已加入</span><span class="v">{{ dash.summary.joined_count ?? 0 }}/{{ dash.summary.student_count }}</span></div>
              <div class="stat"><span class="k">已开练</span><span class="v">{{ dash.summary.started_count }}/{{ dash.summary.student_count }}</span></div>
              <div class="stat"><span class="k">完成</span><span class="v">{{ dash.summary.finished_count }}/{{ dash.summary.student_count }}</span></div>
              <div class="stat"><span class="k">完成率</span><span class="v">{{ Math.round(dash.summary.completion_rate * 100) }}%</span></div>
              <div class="stat"><span class="k">可评估</span><span class="v">{{ dash.summary.assessed_count }}</span></div>
            </div>
            <p class="agg-line">
              <span class="agg-k">最弱维度</span>
              <span v-for="w in dash.summary.weakest_dimensions" :key="w.dimension" class="chip weak-chip">
                {{ dimLabel(w.dimension) }} {{ w.avg }}
              </span>
              <span v-if="!dash.summary.weakest_dimensions.length" class="dim">暂无（还没有可评估的维度分）</span>
            </p>
            <p class="agg-line">
              <span class="agg-k">全班六维均分</span>
              <template v-if="Object.keys(dash.summary.dimension_avg).length">
                <!-- 固定渲染 canonical 六维：无数据的维度显「无数据」而非消失（2026-10-15 走查修复） -->
                <span v-for="d in CAREER_DIM_ORDER" :key="d"
                      :class="['chip', { dim: dash.summary.dimension_avg[d] === undefined }]">
                  {{ dimLabel(d) }} {{ dash.summary.dimension_avg[d] ?? '无数据' }}
                </span>
              </template>
              <span v-else class="dim">暂无</span>
            </p>
            <p class="hint">{{ dash.summary.note }}</p>
            <!-- 覆盖率：直接引用后端 coverage_note，不在此重算比率（单一真值源） -->
            <p v-if="dash.summary.coverage_note" class="hint hint-cov">
              {{ dash.summary.coverage_note }}
            </p>
          </div>

          <!-- 需关注学生：只列结构性事实 + 可反查的明细 -->
          <div v-if="dash.attention?.length" class="attention">
            <p class="agg-k">需关注（{{ dash.attention.length }}）</p>
            <ul>
              <li v-for="(a, i) in dash.attention" :key="i">
                <span class="tag" :class="'r-' + a.reason">{{ REASON_LABEL[a.reason] || a.reason }}</span>
                <b>{{ a.name }}</b>
                <span class="dim">{{ a.detail }}</span>
              </li>
            </ul>
          </div>

          <table>
            <thead>
              <tr>
                <th>学号</th><th>姓名</th><th>完成/场次</th><th>best overall</th><th>六维均分</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(s, i) in dash.students" :key="i">
                <td>{{ s.student_no || '—' }}</td>
                <td>
                  <!-- F1：点姓名下钻该生全部会话明细（未绑定账号不可点） -->
                  <button v-if="s.user_id" class="link" @click="openStudentDetail(s)">{{ s.name }}</button>
                  <template v-else>{{ s.name }}</template>
                  <span v-if="!s.bound" class="dim">（未加入）</span>
                </td>
                <td>{{ s.finished_count }} / {{ s.session_count }}</td>
                <td>{{ s.overall_best ?? '—' }}</td>
                <td>
                  <span v-for="(v, d) in s.dimension_avg" :key="d" class="chip">{{ dimLabel(d) }} {{ v }}</span>
                  <span v-if="!Object.keys(s.dimension_avg).length" class="dim">—</span>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- F6 课后简评：本班学生真实提交（按班级过滤；无提交如实显示空） -->
          <div class="feedback">
            <p class="agg-k">课后简评（{{ feedback.length }}）</p>
            <div v-if="feedback.length" class="fb-list">
              <div v-for="f in feedback" :key="f.id" class="fb-row">
                <b>{{ f.student_name || f.user_id }}</b>
                <span class="fb-stars">{{ '★'.repeat(f.rating) }}{{ '☆'.repeat(5 - f.rating) }}</span>
                <span class="dim">{{ shortTime(f.created_at) }}</span>
                <span v-if="f.comment" class="fb-comment">「{{ f.comment }}」</span>
              </div>
            </div>
            <p v-else class="hint">本班学生还没有提交课后简评。</p>
          </div>
        </template>
      </div>

      <!-- 4 · 场景生成器（F8：岗位方向 → 生成 draft → 人工审核 → 激活入库） -->
      <div class="card wide">
        <h2>4 · 场景生成器</h2>
        <p class="hint">按岗位方向生成新对抗情景（草稿），人工审核后激活进入发任务可选列表。黄金样本保留不变。</p>
        <div class="row">
          <select v-model="genDirection">
            <option value="" disabled>选择岗位方向</option>
            <option v-for="d in jobDirections" :key="d.key" :value="d.key">{{ d.label }}</option>
          </select>
          <select v-model="genType">
            <option value="">情景类型（默认岗位类型）</option>
            <option v-for="(label, k) in SCENARIO_TYPE_LABEL" :key="k" :value="k">{{ label }}</option>
          </select>
          <select v-model="genDifficulty">
            <option value="easy">简单</option>
            <option value="medium">中等</option>
            <option value="hard">困难</option>
          </select>
          <button :disabled="genBusy || !genDirection" @click="generateScenario">
            {{ genBusy ? '生成中…' : '生成场景' }}
          </button>
        </div>

        <!-- 生成结果预览（人工审核） -->
        <div v-if="genResult" class="gen-preview">
          <div class="gen-head">
            <strong>{{ genResult.title }}</strong>
            <span class="tag">{{ genResult.type_label }} · {{ genResult.subtype_label }} · {{ DIFF_LABEL[genResult.difficulty_default] || genResult.difficulty_default }}</span>
          </div>
          <p class="gen-setting">{{ genResult.setting }}</p>
          <p class="gen-line"><b>学生角色</b>{{ genResult.student_role }}</p>
          <p class="gen-line"><b>对手角色</b>{{ genResult.interviewer_role }}</p>
          <p class="gen-line"><b>开场</b>“{{ genResult.opening_question }}”</p>
          <div class="gen-line"><b>追问方向</b>
            <ul class="gen-list"><li v-for="(p, i) in genResult.probe_tree" :key="i">{{ p }}</li></ul>
          </div>
          <div class="gen-line"><b>重点考察</b>
            <span v-for="(f, i) in genResult.focus_points" :key="i" class="chip">{{ f }}</span>
          </div>
          <div class="gen-line"><b>BARS 锚点</b>
            <div v-for="(levels, d) in genResult.bars_anchor" :key="d" class="gen-bars">
              <span class="dim">{{ dimLabel(d) }}</span>
              1分「{{ levels['1'] }}」 · 3分「{{ levels['3'] }}」 · 5分「{{ levels['5'] }}」
            </div>
          </div>
          <div class="gen-actions">
            <button class="link" @click="genResult = null">放弃</button>
            <button :disabled="activatingId === genResult.id" @click="activateDraft(genResult.id)">
              {{ activatingId === genResult.id ? '激活中…' : '审核通过并激活' }}
            </button>
          </div>
        </div>

        <!-- 待审核草稿列表 -->
        <div v-if="drafts.length" class="gen-drafts">
          <p class="agg-k">待审核草稿（{{ drafts.length }}）</p>
          <ul class="gen-draft-list">
            <li v-for="d in drafts" :key="d.id">
              <div class="tl-head">
                <strong>{{ d.title }}</strong>
                <span class="dim">{{ d.type_label }} · {{ d.job_direction }}</span>
              </div>
              <button :disabled="activatingId === d.id" @click="activateDraft(d.id)">
                {{ activatingId === d.id ? '激活中…' : '激活入库' }}
              </button>
            </li>
          </ul>
        </div>
      </div>
    </section>

    <!-- F1 学生个体下钻抽屉（焦点圈闭 + Esc 关闭，复用 useModalFocus） -->
    <div v-if="detail" class="drawer-mask" @click.self="closeStudentDetail">
      <div ref="detailRef" class="drawer" tabindex="-1" role="dialog" aria-modal="true"
           aria-label="学生实训明细" @keydown.esc="closeStudentDetail" @keydown.tab="trapDetailTab">
        <div class="drawer-head">
          <h3>{{ detail.name }}<span class="dim">（{{ detail.student_no || '无学号' }}）</span> · 实训明细</h3>
          <button class="link" @click="closeStudentDetail" aria-label="关闭明细">×</button>
        </div>
        <p v-if="detailLoading" class="hint">加载中…</p>
        <template v-else>
          <p class="hint">
            共 {{ detail.session_count }} 场（完成 {{ detail.finished_count }} 场）·
            best overall {{ detail.overall_best ?? '—' }}
          </p>
          <p v-if="Object.keys(detail.dimension_avg).length" class="agg-line">
            <span class="agg-k">六维均分</span>
            <span v-for="(v, d) in detail.dimension_avg" :key="d" class="chip">{{ dimLabel(d) }} {{ v }}</span>
          </p>
          <table v-if="detail.sessions.length">
            <thead>
              <tr><th>开始时间</th><th>状态</th><th>轮数</th><th>overall</th><th>六维得分</th></tr>
            </thead>
            <tbody>
              <tr v-for="s in detail.sessions" :key="s.session_id">
                <td>{{ shortTime(s.started_at) }}</td>
                <td>{{ STATUS_LABEL[s.status] || s.status }}</td>
                <td>{{ s.turn_count }}</td>
                <td>{{ s.overall ?? '—' }}</td>
                <td>
                  <span v-for="(v, d) in s.dimension_scores" :key="d" class="chip">{{ dimLabel(d) }} {{ v }}</span>
                  <span v-if="!Object.keys(s.dimension_scores).length" class="dim">—</span>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-else class="hint">该生在班内还没有任何实训会话。</p>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.teacher-career { padding: var(--space-5); max-width: 1080px; margin: 0 auto; }
.page-head h1 { margin: 0 0 .25rem; font-size: 1.4rem; }
.sub { color: var(--text-dim, var(--color-text-3)); margin: 0 0 var(--space-4); }
.msg { background: var(--accent-soft, var(--color-surface-2)); padding: .5rem .75rem; border-radius: 8px; }
.grid { display: grid; grid-template-columns: 1fr 1.4fr; gap: var(--space-4); }
.card { border: 1px solid var(--border, var(--color-border)); border-radius: 12px; padding: var(--space-4); background: var(--bg-card); }
.card.wide { grid-column: 1 / -1; }
.card h2 { margin: 0 0 .75rem; font-size: 1.05rem; }
.row { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; margin-bottom: .75rem; }
.row input, .row select { flex: 1; min-width: 6rem; }
.task-row { margin-top: var(--space-4); }
textarea { width: 100%; box-sizing: border-box; margin-bottom: .5rem; }
button { cursor: pointer; }
button:disabled { opacity: .5; cursor: not-allowed; }
.link { background: none; border: none; padding: .15rem .25rem; color: var(--accent); }
.link.dim, .dim { color: var(--text-dim, var(--color-text-3)); }
.dash-export { margin-bottom: var(--space-3); }
.dash-exports { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: var(--space-3); }
.dash-exports .link { padding: 0; }
/* F6 课后简评 */
.feedback { margin-top: var(--space-4); border-top: 1px dashed var(--border-color); padding-top: var(--space-3); }
.feedback .agg-k { font-size: var(--text-sm); font-weight: var(--weight-semibold); margin: 0 0 var(--space-2); }
.fb-list { display: grid; gap: 6px; }
.fb-row { display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; font-size: var(--text-sm); }
.fb-stars { color: var(--color-warning); letter-spacing: 1px; }
.fb-comment { color: var(--text-secondary); }
.class-list, .roster { list-style: none; padding: 0; margin: .5rem 0 0; }
.class-list li, .roster li { display: flex; justify-content: space-between; gap: .5rem; padding: .3rem 0; border-bottom: 1px dashed var(--border, var(--color-border)); }
.class-list li.active { font-weight: var(--weight-semibold); }
.join-code { margin: .75rem 0; padding: .5rem .75rem; border-radius: 8px; background: var(--accent-soft, var(--color-surface-2)); font-size: 1.05rem; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: .45rem .5rem; border-bottom: 1px solid var(--border, var(--color-border)); font-size: .92rem; }
.chip { display: inline-block; margin-right: .35rem; padding: .1rem .4rem; border-radius: 999px; background: var(--accent-soft, var(--color-surface-2)); font-size: .8rem; }
.hint { color: var(--text-dim, var(--color-text-3)); font-size: .9rem; }
/* 覆盖率说明：与口径说明同字号但更强调（含分母与未纳入人数，教师引用数字前必读） */
.hint-cov { margin-top: 2px; padding-left: 8px; border-left: 2px solid var(--color-warning, #d48806); }

/* 班级级聚合 */
.agg { margin-bottom: var(--space-4); padding-bottom: var(--space-3); border-bottom: 1px dashed var(--border, var(--color-border)); }
.stats { display: flex; gap: var(--space-4); flex-wrap: wrap; margin-bottom: .6rem; }
.stat { display: flex; flex-direction: column; min-width: 4.5rem; }
.stat .k { font-size: .78rem; color: var(--text-dim, var(--color-text-3)); }
.stat .v { font-size: 1.25rem; font-weight: var(--weight-bold); }
.agg-line { margin: .35rem 0; display: flex; align-items: center; gap: .35rem; flex-wrap: wrap; }
.agg-k { font-size: .82rem; color: var(--text-dim, var(--color-text-3)); margin-right: .25rem; }
.weak-chip { background: var(--accent-soft, var(--color-surface-2)); border: 1px solid currentColor; color: var(--color-warning, var(--accent)); }
/* 需关注 */
.attention { margin-bottom: var(--space-3); }
.attention ul { list-style: none; padding: 0; margin: .35rem 0 0; }
.attention li { padding: .3rem 0; border-bottom: 1px dashed var(--border, var(--color-border)); display: flex; align-items: baseline; gap: .4rem; flex-wrap: wrap; }
.tag { font-size: .75rem; padding: .1rem .45rem; border-radius: 999px; background: var(--accent-soft, var(--color-surface-2)); }
.r-not_started, .r-unfinished { color: var(--color-warning, var(--accent)); }
.r-no_score, .r-lowest_score { color: var(--text-dim, var(--color-text-3)); }

/* F2 任务管理中心（2026-10-15） */
.task-mgmt { margin-top: var(--space-4); }
.task-list { list-style: none; padding: 0; margin: .35rem 0 0; display: grid; gap: .5rem; }
.task-list li { padding: .5rem .65rem; border: 1px solid var(--border, var(--color-border)); border-radius: 10px; }
.task-list li.closed { opacity: .55; }
.tl-head { display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; font-size: .92rem; }
.tl-code { color: var(--text-dim, var(--color-text-3)); font-size: .82rem; }
.tl-meta { margin: .25rem 0; font-size: .82rem; color: var(--text-dim, var(--color-text-3)); }
.tag { font-size: .72rem; padding: .1rem .5rem; border-radius: 999px; }
.tag-open { background: var(--accent-soft, var(--color-surface-2)); color: var(--accent); }
.tag-closed { background: var(--color-surface-2, var(--bg-card)); color: var(--text-dim, var(--color-text-3)); }

/* F1 学生个体下钻抽屉（2026-10-15） */
.drawer-mask { position: fixed; inset: 0; background: var(--color-overlay); display: flex;
  align-items: flex-start; justify-content: center; padding: 6vh var(--space-4) var(--space-4);
  overflow-y: auto; z-index: 50; }
.drawer { width: min(760px, 100%); background: var(--bg-card); color: var(--text-primary, inherit);
  border: 1px solid var(--border, var(--color-border)); border-radius: 14px; padding: var(--space-4); }
.drawer-head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-3); }
.drawer-head h3 { margin: 0; font-size: 1.05rem; }
.drawer table { margin-top: var(--space-3); }

/* F8 场景生成器（2026-10-18） */
.gen-preview { margin-top: var(--space-3); border: 1px solid var(--border, var(--color-border));
  border-radius: 10px; padding: var(--space-3); background: var(--bg-secondary, var(--color-surface-1)); }
.gen-head { display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; margin-bottom: .5rem; }
.gen-setting { font-size: .92rem; line-height: 1.6; margin: .4rem 0; }
.gen-line { font-size: .9rem; margin: .35rem 0; }
.gen-line b { color: var(--text-dim, var(--color-text-3)); margin-right: .35rem; }
.gen-list { margin: .25rem 0 0; padding-left: 1.1rem; }
.gen-bars { margin: .2rem 0; font-size: .85rem; color: var(--text-secondary); }
.gen-actions { display: flex; gap: .75rem; justify-content: flex-end; margin-top: .5rem; }
.gen-drafts { margin-top: var(--space-3); border-top: 1px dashed var(--border, var(--color-border)); padding-top: var(--space-3); }
.gen-draft-list { list-style: none; padding: 0; margin: .35rem 0 0; display: grid; gap: .4rem; }
.gen-draft-list li { display: flex; justify-content: space-between; align-items: center; gap: .5rem;
  padding: .4rem .5rem; border: 1px dashed var(--border, var(--color-border)); border-radius: 8px; }

@media (max-width: 760px) { .grid { grid-template-columns: 1fr; } }
</style>
