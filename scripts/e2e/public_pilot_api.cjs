/**
 * 公网全流程模拟（API 层）：真实账号 → 建班 → 发任务 → 学生加入 → 多轮对抗 → 报告
 * ============================================================================
 * 目的：按用户要求，后端上公网后用真实用户路径全流程模拟一遍，确认真实可用，
 *       发现问题即记录（后续修复）。
 *
 * ⚠️ 诚信边界：本脚本产生的账号/会话/报告全部是 **pilot_ 前缀的模拟数据**，
 *   属"接入/链路正确性"验证，**禁止当成效证据引用**（引用前必须跑
 *   `py-server/experiments/pilot_evidence_report.py`，且真实试用需真实学号账号）。
 *
 * 用法：node scripts/e2e/public_pilot_api.cjs
 * 依赖：公网服务已发布（https://mangdehenzhi.app.workbuddy.host）
 */
'use strict'

const fs = require('node:fs')
const path = require('node:path')

const BASE = process.env.PILOT_BASE || 'https://mangdehenzhi.app.workbuddy.host'
const ROOT = path.join(__dirname, '..', '..')

function envValue(key) {
  const f = path.join(ROOT, 'deploy', 'career-pilot', 'backend', '.env')
  const m = fs.readFileSync(f, 'utf8').match(new RegExp('^' + key + '=(.*)$', 'm'))
  return m ? m[1].trim() : ''
}

const T = { u: 'pilot_teacher', p: 'PilotTeacher#2026x' }
const S = { u: 'pilot_student', p: 'PilotStudent#2026x' }
const CLASS_NAME = '公网模拟班 ' + new Date().toISOString().slice(0, 10)

// 真实感学生回答（对抗实训的多轮作答；内容为模拟，但形态贴近真实学生）
const ANSWERS = [
  '我的系统用多智能体分工：检索、出题、评审各一个，主控编排。架构分三层，对外一个入口。',
  '如果依赖失效，我做了降级：先切兜底通道，再退回本地规则评分。代价是评分粒度变粗，用户可感知。',
  '实训场景里单 Agent 会失败在"追问"这一环：它不会根据上一轮回答调整问题深度，我们靠三角色互评解决。',
  '线上故障我们按影响面排优先级：先止血再定位。恢复时间 15 分钟，依据是上次同类故障的实际耗时。',
  '代码冲突我先确认对方诉求和交付时间，再谈实现；有隐患就给出可复现的最小用例，而不是直接否定。',
]

const results = []
function record(name, ok, detail) {
  results.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}\n      ${String(detail).slice(0, 300)}`)
}

async function api(method, url, body, token) {
  const headers = { 'Content-Type': 'application/json' }
  // X-App-Token：CloudStudio 沙箱网关会把 Authorization 替换成平台 token（2026-10-15 实测），
  // 应用自有 JWT 必须走自定义头；本地/dev 两个头都带（后端优先 X-App-Token）。
  if (token) {
    headers['X-App-Token'] = token
    headers['Authorization'] = 'Bearer ' + token
  }
  const res = await fetch(BASE + url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  let data = null
  try { data = await res.json() } catch { /* 非 JSON */ }
  return { status: res.status, data }
}

async function step(name, fn) {
  try {
    const r = await fn()
    record(name, r.ok, r.detail)
    return r.value
  } catch (e) {
    record(name, false, '异常：' + (e && e.message ? e.message : e))
    return undefined
  }
}

async function main() {
  console.log('=== 公网全流程模拟（API 层）===')
  console.log(`BASE: ${BASE} / ${new Date().toISOString()}\n`)

  // 0) 公网健康
  await step('公网 /api/status', async () => {
    const r = await api('GET', '/api/status')
    return { ok: r.status === 200 && r.data && r.data.status === 'ok', detail: JSON.stringify(r.data).slice(0, 120), value: r.data }
  })

  // 1) admin 建教师账号（production 不播演示账户；公开注册只出 student）
  let teacherToken = null
  await step('admin 登录 → 创建教师账号', async () => {
    const ap = envValue('ADMIN_PASSWORD')
    if (!ap) return { ok: false, detail: '读不到 ADMIN_PASSWORD' }
    const login = await api('POST', '/api/auth/login', { username: 'admin', password: ap })
    if (login.status !== 200 || !login.data || !login.data.token) {
      return { ok: false, detail: 'admin 登录失败：' + JSON.stringify(login.data).slice(0, 150) }
    }
    const created = await api('POST', '/api/admin/users', {
      username: T.u, password: T.p, display_name: '公网模拟教师', role: 'teacher',
    }, login.data.token)
    // ⚠️ production 模式会把 409「已存在」的 detail 也掩藏成通用错误文本，
    // 所以不能靠响应文本判断是否已存在 —— 一律以「随后能否登录」为准（幂等重跑）。
    const tl = await api('POST', '/api/auth/login', { username: T.u, password: T.p })
    if (tl.status !== 200 || !tl.data || !tl.data.token) {
      return { ok: false, detail: `创建(${created.status})与登录(${tl.status})均失败：${JSON.stringify(tl.data || created.data).slice(0, 150)}` }
    }
    teacherToken = tl.data.token
    const existed = created.status !== 200 && created.status !== 201
    return { ok: true, detail: `教师 ${T.u} 就绪${existed ? '（已存在，直接登录）' : '（新建）'}` }
  })

  // 2) 公开注册学生账号
  let studentToken = null
  await step('公开注册学生账号', async () => {
    const reg = await api('POST', '/api/auth/register', { username: S.u, password: S.p })
    if (reg.status === 200 && reg.data && reg.data.token) {
      studentToken = reg.data.token
      return { ok: true, detail: `学生 ${S.u} 注册即登录` }
    }
    // 已存在 → 改走登录
    const lg = await api('POST', '/api/auth/login', { username: S.u, password: S.p })
    if (lg.status === 200 && lg.data && lg.data.token) {
      studentToken = lg.data.token
      return { ok: true, detail: `学生 ${S.u} 已存在，登录成功` }
    }
    return { ok: false, detail: '注册/登录均失败：' + JSON.stringify(reg.data).slice(0, 150) }
  })

  if (!teacherToken || !studentToken) {
    console.log('\n账号未就绪，终止后续流程。')
    process.exit(1)
  }

  // 3) 教师：建班 → 花名册 → 发任务
  let classId = null
  let joinCode = null
  await step('教师建班 → 导入花名册 → 发布任务', async () => {
    const cls = await api('POST', '/api/career/classes', { class_name: CLASS_NAME }, teacherToken)
    if (cls.status !== 200 || !cls.data) return { ok: false, detail: '建班失败：' + JSON.stringify(cls.data).slice(0, 200) }
    classId = cls.data.id || cls.data.class_id
    if (!classId) return { ok: false, detail: '建班响应无 id：' + JSON.stringify(cls.data).slice(0, 200) }

    const roster = `1001 公网学生甲\n1002 公网学生乙\n${S.u} ${S.u}`
    const imp = await api('POST', `/api/career/classes/${classId}/students`, { roster }, teacherToken)
    if (imp.status !== 200) return { ok: false, detail: '花名册失败：' + JSON.stringify(imp.data).slice(0, 200) }

    const scen = await api('GET', '/api/career/scenarios', undefined, studentToken)
    const scenarios = (scen.data && (scen.data.scenarios || scen.data.items || scen.data)) || []
    const first = Array.isArray(scenarios) ? scenarios[0] : null
    if (!first || !first.id) return { ok: false, detail: '无可用场景：' + JSON.stringify(scen.data).slice(0, 200) }

    const task = await api('POST', '/api/career/tasks', {
      class_id: classId, scenario_id: first.id, difficulty: 'medium', max_turns: 5,
    }, teacherToken)
    if (task.status !== 200 || !task.data) return { ok: false, detail: '发任务失败：' + JSON.stringify(task.data).slice(0, 200) }
    joinCode = task.data.join_code || task.data.code
    if (!joinCode) return { ok: false, detail: '任务响应无 join_code：' + JSON.stringify(task.data).slice(0, 200) }
    return { ok: true, detail: `班级 ${classId}｜场景 ${first.id}｜任务码 ${joinCode}`, value: joinCode }
  })

  // 4) 学生：凭码加入 → 开始会话 → 多轮真实回答
  let sessionId = null
  let taskId = null
  let scenarioId = null
  await step('学生凭任务码加入班级', async () => {
    if (!joinCode) return { ok: false, detail: '无任务码' }
    const j = await api('POST', '/api/career/task/join', { join_code: joinCode }, studentToken)
    if (j.status !== 200) return { ok: false, detail: '加入失败：' + JSON.stringify(j.data).slice(0, 200) }
    taskId = j.data.task_id
    scenarioId = j.data.scenario_id
    if (!taskId || !scenarioId) return { ok: false, detail: '加入响应缺 task_id/scenario_id：' + JSON.stringify(j.data).slice(0, 200) }
    return { ok: true, detail: `加入成功：task=${taskId} 场景=${scenarioId} 绑定=${j.data.bound_name || '?'}`, value: j.data }
  })

  await step('学生开始对抗会话', async () => {
    if (!taskId || !scenarioId) return { ok: false, detail: '无 task_id/scenario_id' }
    // StartRequest 要 task_id + scenario_id（不是 join_code）
    const s = await api('POST', '/api/career/session/start', {
      task_id: taskId, scenario_id: scenarioId, difficulty: 'medium', max_turns: 5,
    }, studentToken)
    if (s.status !== 200 || !s.data) return { ok: false, detail: '开始会话失败：' + JSON.stringify(s.data).slice(0, 250) }
    sessionId = s.data.session_id || s.data.id
    if (!sessionId) return { ok: false, detail: '响应无 session_id：' + JSON.stringify(s.data).slice(0, 200) }
    return { ok: true, detail: `会话 ${sessionId}｜首题：${(s.data.question || s.data.first_question || '').slice(0, 80)}`, value: sessionId }
  })

  if (sessionId) {
    const t0 = Date.now()
    let answered = 0
    for (let i = 0; i < ANSWERS.length; i++) {
      const a = await api('POST', `/api/career/session/${sessionId}/answer`, { answer: ANSWERS[i] }, studentToken)
      if (a.status !== 200) {
        record(`第 ${i + 1} 轮作答（真实 LLM）`, false, JSON.stringify(a.data).slice(0, 200))
        continue
      }
      answered++
      const d = a.data || {}
      // 下一问字段名在不同形态下不同（next_question / question / pending.question），
      // 且可能是对象 —— 统一取文本，取不到即进入结束
      const rawNext = d.next_question || d.question || (d.pending && d.pending.question) || ''
      const nextQ = typeof rawNext === 'string' ? rawNext : JSON.stringify(rawNext)
      const isEnd = !nextQ || d.status === 'finished'
      record(`第 ${i + 1} 轮作答（真实 LLM）`, true, `下一问：${nextQ.slice(0, 100) || '（进入结束）'}`)
      if (isEnd) break
    }
    record('多轮作答汇总', answered >= 3, `完成 ${answered}/${ANSWERS.length} 轮，耗时 ${((Date.now() - t0) / 1000).toFixed(1)}s`)

    await step('结束会话 → 拉取六维报告', async () => {
      const e = await api('POST', `/api/career/session/${sessionId}/end`, {}, studentToken)
      const rep = await api('GET', `/api/career/session/${sessionId}/report`, undefined, studentToken)
      // report 的真实字段是 assessment（其内可能是 {dimensions:{...}} 或维度分平铺）
      const assessment = (rep.data && rep.data.assessment) || {}
      const dims = assessment.dimensions || assessment
      const dimCount = dims && typeof dims === 'object' ? Object.keys(dims).length : 0
      return {
        ok: rep.status === 200 && dimCount > 0,
        detail: `end=${e.status} report=${rep.status}｜维度数=${dimCount}｜${JSON.stringify(assessment).slice(0, 180)}`,
        value: rep.data,
      }
    })
  }

  // 5) 教师看板
  await step('教师看板（班级聚合）', async () => {
    if (!classId) return { ok: false, detail: '无 classId' }
    const d = await api('GET', `/api/career/classes/${classId}/dashboard`, undefined, teacherToken)
    if (d.status !== 200) return { ok: false, detail: JSON.stringify(d.data).slice(0, 250) }
    const s = d.data.summary || {}
    return { ok: true, detail: `summary=${JSON.stringify(s).slice(0, 220)}` }
  })

  const failed = results.filter((r) => !r.ok)
  console.log('\n=== 汇总 ===')
  console.log(`通过 ${results.length - failed.length}/${results.length}`)
  if (failed.length) failed.forEach((f) => console.log(`  - ${f.name}: ${String(f.detail).slice(0, 200)}`))

  fs.mkdirSync(path.join(ROOT, '_e2e_tmp_mdhz'), { recursive: true })
  fs.writeFileSync(
    path.join(ROOT, '_e2e_tmp_mdhz', 'public_pilot_api_result.json'),
    JSON.stringify({ at: new Date().toISOString(), base: BASE, classId, joinCode, sessionId, results }, null, 2),
    'utf8',
  )
  console.log('\n结果已写入 _e2e_tmp_mdhz/public_pilot_api_result.json')
  process.exit(failed.length ? 1 : 0)
}

main()
