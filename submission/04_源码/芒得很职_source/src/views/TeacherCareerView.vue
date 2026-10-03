<script setup lang="ts">
// P4 教师端：建班 → 导花名册 → 发任务（任务码）→ 班级学情看板
import { ref, onMounted } from 'vue'
import { api, friendlyError } from '@/utils/api'

interface ClassItem { class_id: string; class_name: string; student_count: number }
interface StudentItem { student_no: string; name: string; user_id: string | null; joined_at?: string }
interface TaskItem {
  task_id: string; join_code: string; scenario_title?: string
  difficulty: string; max_turns: number; class_id: string
}
interface DashSession { session_id: string; status: string; turn_count: number; overall: number | null }
interface DashStudent {
  student_no: string; name: string; user_id: string | null; bound: boolean
  session_count: number; finished_count: number
  dimension_avg: Record<string, number>; overall_best: number | null
  sessions: DashSession[]
}
interface Dash { class_id: string; class_name: string; student_count: number; students: DashStudent[] }
interface ScenarioItem { id: string; title: string }

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
}

onMounted(() => {
  loadClasses().catch(() => {})
  loadScenarios().catch(() => {})
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
        <table v-else>
          <thead>
            <tr>
              <th>学号</th><th>姓名</th><th>完成/场次</th><th>best overall</th><th>六维均分</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(s, i) in dash.students" :key="i">
              <td>{{ s.student_no || '—' }}</td>
              <td>{{ s.name }}<span v-if="!s.bound" class="dim">（未加入）</span></td>
              <td>{{ s.finished_count }} / {{ s.session_count }}</td>
              <td>{{ s.overall_best ?? '—' }}</td>
              <td>
                <span v-for="(v, d) in s.dimension_avg" :key="d" class="chip">{{ d }} {{ v }}</span>
                <span v-if="!Object.keys(s.dimension_avg).length" class="dim">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.teacher-career { padding: 1.25rem; max-width: 1080px; margin: 0 auto; }
.page-head h1 { margin: 0 0 .25rem; font-size: 1.4rem; }
.sub { color: var(--text-dim, var(--color-text-3)); margin: 0 0 1rem; }
.msg { background: var(--accent-soft, var(--color-surface-2)); padding: .5rem .75rem; border-radius: 8px; }
.grid { display: grid; grid-template-columns: 1fr 1.4fr; gap: 1rem; }
.card { border: 1px solid var(--border, var(--color-border)); border-radius: 12px; padding: 1rem; background: var(--bg-card); }
.card.wide { grid-column: 1 / -1; }
.card h2 { margin: 0 0 .75rem; font-size: 1.05rem; }
.row { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; margin-bottom: .75rem; }
.row input, .row select { flex: 1; min-width: 6rem; }
.task-row { margin-top: 1rem; }
textarea { width: 100%; box-sizing: border-box; margin-bottom: .5rem; }
button { cursor: pointer; }
button:disabled { opacity: .5; cursor: not-allowed; }
.link { background: none; border: none; padding: .15rem .25rem; color: var(--accent); }
.link.dim, .dim { color: var(--text-dim, var(--color-text-3)); }
.class-list, .roster { list-style: none; padding: 0; margin: .5rem 0 0; }
.class-list li, .roster li { display: flex; justify-content: space-between; gap: .5rem; padding: .3rem 0; border-bottom: 1px dashed var(--border, var(--color-border)); }
.class-list li.active { font-weight: 600; }
.join-code { margin: .75rem 0; padding: .5rem .75rem; border-radius: 8px; background: var(--accent-soft, var(--color-surface-2)); font-size: 1.05rem; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: .45rem .5rem; border-bottom: 1px solid var(--border, var(--color-border)); font-size: .92rem; }
.chip { display: inline-block; margin-right: .35rem; padding: .1rem .4rem; border-radius: 999px; background: var(--accent-soft, var(--color-surface-2)); font-size: .8rem; }
.hint { color: var(--text-dim, var(--color-text-3)); font-size: .9rem; }
@media (max-width: 760px) { .grid { grid-template-columns: 1fr; } }
</style>
