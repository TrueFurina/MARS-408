/**
 * 教师端「对抗实训控制台」全流程（真浏览器，不是只打 API）。
 *
 * 为什么必须走浏览器：教师端的三件事——建班、导入花名册、发任务码——
 * 在 API 层早有集成测试覆盖，但「教师本人能不能在页面上完成它们」没人验过，
 * 尤其**花名册绑定链路**是试点的前置卡点：
 *   - 名册为空 → 学生凭码加入仍然 200，但 roster_bound=false，看板永远统计不到他；
 *   - 名册姓名与学生注册姓名不一致 → bind_student 退回「第一个未绑定行」，
 *     成绩会记到别人名下，而这一错位在页面上是否可见，只有浏览器能回答。
 *
 * 用法（仓库根）：
 *   NODE_PATH=<puppeteer-core 所在 node_modules>
 *   E2E_BASE=http://127.0.0.1:5300/MARS-408/app/ \
 *   E2E_TEACHER=e2e_teacher1020 E2E_TEACHER_PASS=xxx \
 *   E2E_STU_MATCH=e2e_stu1_1020 E2E_STU_MATCH_PASS=xxx \
 *   E2E_STU_MISMATCH=e2e_stu2_1020 E2E_STU_MISMATCH_PASS=xxx \
 *   E2E_WRITE=1 node scripts/e2e/teacher_console_ui.cjs
 *
 * E2E_WRITE=0（默认）＝只读巡检：不建班、不导入、不发码，只验证页面能加载、
 * 班级列表/看板/导出可用（线上环境用它，避免在生产库里留垃圾）。
 *
 * 判读口径：
 *   - 真信号是 net 列的 4xx/5xx + 控制台错误；
 *   - 「未绑定」「暂无」是**诚实留空**，不是缺陷，别当故障报。
 */
const puppeteer = require('puppeteer-core')

const BASE = process.env.E2E_BASE || 'http://127.0.0.1:5300/MARS-408/app/'
const CHROME = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const TCH = process.env.E2E_TEACHER || ''
const TCH_PASS = process.env.E2E_TEACHER_PASS || ''
const STU_OK = process.env.E2E_STU_MATCH || ''
const STU_OK_PASS = process.env.E2E_STU_MATCH_PASS || ''
const STU_BAD = process.env.E2E_STU_MISMATCH || ''
const STU_BAD_PASS = process.env.E2E_STU_MISMATCH_PASS || ''
const WRITE = process.env.E2E_WRITE === '1'
const sleep = ms => new Promise(r => setTimeout(r, ms))

// 控制台错误收集器必须在模块作用域：放在 IIFE 里会被其他函数引用成 ReferenceError
// （mobile_sweep.cjs 首版踩过，本脚本沿用同一约定）。
const consoleErrs = []

function attachLogs(page, net) {
  page.on('console', m => { if (m.type() === 'error') consoleErrs.push(m.text().slice(0, 160)) })
  page.on('pageerror', e => consoleErrs.push('pageerror: ' + String(e).slice(0, 160)))
  page.on('response', r => {
    if (r.status() >= 400) net.push(r.status() + ' ' + r.url().replace(BASE, '/').slice(0, 60))
  })
}

// 按可见文本点按钮（页面按钮文案随步骤变化，用文本比用 class 稳）
async function clickByText(page, texts) {
  return page.evaluate(ts => {
    const btns = Array.from(document.querySelectorAll('button')).filter(b => !b.disabled)
    for (const t of ts) {
      const hit = btns.find(b => (b.innerText || '').includes(t))
      if (hit) { hit.click(); return t }
    }
    return null
  }, texts)
}

function setInput(el, v) {
  Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(el, v)
  el.dispatchEvent(new Event('input', { bubbles: true }))
}

async function login(page, user, pass) {
  await page.goto(BASE + '#/login', { waitUntil: 'networkidle2', timeout: 60000 })
  await sleep(2000)
  await page.evaluate((u, pw, fn) => {
    const ins = Array.from(document.querySelectorAll('input')).filter(i => i.type !== 'hidden')
    const set = eval('(' + fn + ')')
    set(ins[0], u); set(ins[ins.length - 1], pw)
  }, user, pass, setInput.toString())
  await page.evaluate(() => document.querySelector('.sbtn')?.click())
  await sleep(3500)
}

// 页面顶部的操作提示（.msg）。教师端所有写操作的反馈都走它，
// 看不到它等于看不到结果——这是本脚本对"提示是否到位"的实测点。
async function readMsg(page) {
  return page.evaluate(() => {
    const el = document.querySelector('.msg')
    return el ? (el.innerText || '').trim().slice(0, 120) : ''
  })
}

async function enterTeacherPage(page) {
  await page.goto(BASE + '#/career/teacher', { waitUntil: 'networkidle2', timeout: 60000 })
  await sleep(2500)
  return page.evaluate(() => !!(document.querySelector('.teacher-career')))
}

async function createClass(page, name) {
  await page.evaluate((n, fn) => {
    const inp = document.querySelector('input[placeholder^="班级名称"]')
    if (!inp) return
    const set = eval('(' + fn + ')')
    set(inp, n)
  }, name, setInput.toString())
  await sleep(300)
  const clicked = await clickByText(page, ['创建'])
  await sleep(2500)
  return clicked
}

async function selectClass(page, name) {
  return page.evaluate(n => {
    const li = Array.from(document.querySelectorAll('.class-list li'))
      .find(x => (x.innerText || '').includes(n))
    if (!li) return false
    const btn = li.querySelector('button.link')
    if (!btn) return false
    btn.click(); return true
  }, name)
}

async function importRoster(page, text) {
  await page.evaluate(t => {
    const ta = document.querySelector('.card textarea')
    if (!ta) return
    Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set.call(ta, t)
    ta.dispatchEvent(new Event('input', { bubbles: true }))
  }, text)
  await sleep(400)
  // 按钮禁用条件是 `loading || !activeClassId`：没先选班，按钮永远灰着，
  // 点不动会误判成"导入功能坏了"。故失败时把禁用原因读出来。
  const disabled = await page.evaluate(() => {
    const b = Array.from(document.querySelectorAll('button')).find(x => (x.innerText || '').includes('导入花名册'))
    return b ? b.disabled : null
  })
  const clicked = await clickByText(page, ['导入花名册'])
  await sleep(2500)
  return { clicked, disabled }
}

async function publishTask(page, turns) {
  return page.evaluate(n => {
    const sels = Array.from(document.querySelectorAll('.task-row select'))
    // v-model 监听 change：必须显式 dispatch，只改 .value 不会触发 Vue 更新
    for (const s of sels) {
      if (s.options.length && !s.value) {
        s.value = s.options[0].value
        s.dispatchEvent(new Event('change', { bubbles: true }))
      }
    }
    const num = document.querySelector('.task-row input[type="number"]')
    if (num) {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(num, String(n))
      num.dispatchEvent(new Event('input', { bubbles: true }))
    }
    const btn = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('发布任务'))
    if (!btn || btn.disabled) return { ok: false, disabled: btn ? btn.disabled : null }
    btn.click()
    return { ok: true }
  }, turns)
}

async function readJoinCode(page) {
  return page.evaluate(() => {
    const el = document.querySelector('.join-code strong')
    return el ? (el.innerText || '').trim() : ''
  })
}

async function readRoster(page) {
  return page.evaluate(() => Array.from(document.querySelectorAll('.roster li'))
    .map(li => (li.innerText || '').replace(/\s+/g, ' ').trim()))
}

async function openDashboard(page, className) {
  const ok = await page.evaluate(n => {
    const li = Array.from(document.querySelectorAll('.class-list li'))
      .find(x => (x.innerText || '').includes(n))
    if (!li) return false
    const btn = Array.from(li.querySelectorAll('button.link')).find(b => (b.innerText || '').includes('看板'))
    if (!btn) return false
    btn.click(); return true
  }, className)
  if (!ok) return null
  // 看板第一次打开要等三个接口（dashboard + roster + feedback）
  try {
    await page.waitForFunction(() => !!document.querySelector('.card.wide table'),
      { timeout: 30000, polling: 1000 })
  } catch { /* 交给调用方判空 */ }
  await sleep(1500)
  return page.evaluate(() => {
    const table = document.querySelector('.card.wide table')
    const stats = Array.from(document.querySelectorAll('.stat')).map(s => (s.innerText || '').replace(/\s+/g, ' ').trim())
    const rows = Array.from(document.querySelectorAll('.card.wide table tbody tr')).map(tr =>
      Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').replace(/\s+/g, ' ').trim()))
    const weak = (document.querySelector('.agg-line') || {}).innerText || ''
    return {
      hasTable: !!table,
      stats,
      rows,
      weak: weak.replace(/\s+/g, ' ').trim().slice(0, 120),
      note: ((document.querySelector('.card.wide .hint') || {}).innerText || '').replace(/\s+/g, ' ').trim().slice(0, 120),
    }
  })
}

// 学生加入：单独隔离上下文，避免与教师页共用 localStorage 里的 token 串号
async function studentJoin(browser, user, pass, code, net) {
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  attachLogs(page, net)
  await page.setViewport({ width: 1440, height: 900 })
  let joinApi = null
  page.on('response', async r => {
    if (r.url().includes('/task/join')) {
      try { joinApi = await r.json() } catch { joinApi = { parseError: true } }
    }
  })
  await login(page, user, pass)
  await page.goto(BASE + '#/career/training', { waitUntil: 'networkidle2', timeout: 60000 })
  await sleep(2500)
  await page.evaluate((c, fn) => {
    const inp = document.querySelector('input.join-input')
    if (!inp) return
    const set = eval('(' + fn + ')')
    set(inp, c)
  }, code, setInput.toString())
  await sleep(500)
  const clicked = await clickByText(page, ['加入实训'])
  await sleep(3000)
  const ui = await page.evaluate(() => ({
    badge: ((document.querySelector('.join-badge') || {}).innerText || '').trim(),
    ok: ((document.querySelector('.join-ok') || {}).innerText || '').replace(/\s+/g, ' ').trim(),
    warn: ((document.querySelector('.join-warn') || {}).innerText || '').replace(/\s+/g, ' ').trim(),
  }))
  await ctx.close()
  return { clicked, ui, api: joinApi }
}

;(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
  const net = []
  const page = await browser.newPage()
  attachLogs(page, net)
  await page.setViewport({ width: 1440, height: 900 })

  await login(page, TCH, TCH_PASS)
  const inPage = await enterTeacherPage(page)
  console.log('教师登录 →', TCH, '｜进入教师端页面：', inPage ? '是' : '否（被守卫拦回或页面未渲染）')
  if (!inPage) {
    console.log('  当前 URL：', page.url())
    console.log('  页面文字片段：', (await page.evaluate(() => (document.body.innerText || '').slice(0, 160))))
  }

  const stamp = Date.now().toString().slice(-6)
  const CLS_OK = `E2E名册匹配班-${stamp}`
  const CLS_BAD = `E2E名册不匹配班-${stamp}`

  let codeOk = '', codeBad = ''
  if (WRITE) {
    // ── 班 1：名册姓名 = 学生注册姓名（正确用法）──
    console.log('\n【班 1】' + CLS_OK + '（名册姓名与学生注册姓名一致）')
    console.log('  建班：', await createClass(page, CLS_OK) ? '已点创建' : '未找到创建按钮')
    console.log('  提示：', await readMsg(page))
    await sleep(1500)
    console.log('  选中：', await selectClass(page, CLS_OK) ? '已选中' : '列表中未找到该班')
    await sleep(1200)
    const imp1 = await importRoster(page, '01 学生1\n02 学生2\n03 学生3')
    console.log('  导入花名册：', imp1.clicked ? '已点' : `未点到（按钮 disabled=${imp1.disabled}）`)
    console.log('  提示：', await readMsg(page))
    console.log('  名册：', (await readRoster(page)).join(' | '))
    const pub1 = await publishTask(page, 5)
    await sleep(2500)
    codeOk = await readJoinCode(page)
    console.log('  发布任务：', pub1.ok ? '已点' : `失败(disabled=${pub1.disabled})`, '｜任务码：', codeOk || '(未拿到)')

    // ── 班 2：名册姓名与学生注册姓名不一致（试点里极易发生）──
    console.log('\n【班 2】' + CLS_BAD + '（名册姓名与学生注册姓名不一致）')
    console.log('  建班：', await createClass(page, CLS_BAD) ? '已点创建' : '未找到创建按钮')
    await sleep(1500)
    console.log('  选中：', await selectClass(page, CLS_BAD) ? '已选中' : '列表中未找到该班')
    await sleep(1200)
    const imp2 = await importRoster(page, '01 张三\n02 李四\n03 王五')
    console.log('  导入花名册：', imp2.clicked ? '已点' : `未点到（按钮 disabled=${imp2.disabled}）`)
    console.log('  名册：', (await readRoster(page)).join(' | '))
    const pub2 = await publishTask(page, 5)
    await sleep(2500)
    codeBad = await readJoinCode(page)
    console.log('  发布任务：', pub2.ok ? '已点' : `失败(disabled=${pub2.disabled})`, '｜任务码：', codeBad || '(未拿到)')
  }

  // ── 学生加入（UI + API 双真值：页面提示与后端 matched_by 对照）──
  if (WRITE && codeOk) {
    console.log('\n【学生 A】' + STU_OK + ' 加入班 1 任务码 ' + codeOk)
    const r = await studentJoin(browser, STU_OK, STU_OK_PASS, codeOk, net)
    console.log('  点击加入：', r.clicked ? '已点' : '未找到按钮')
    console.log('  UI 徽标：', r.ui.badge, '｜按姓名匹配提示：', r.ui.ok || '(无)', '｜告警：', r.ui.warn || '(无)')
    console.log('  API 真值：', r.api
      ? `roster_bound=${r.api.roster_bound} matched_by=${r.api.bound_match || '—'} bound_name=${r.api.bound_name || '—'}`
      : '(未捕获响应)')
  }
  if (WRITE && codeBad) {
    console.log('\n【学生 B】' + STU_BAD + ' 加入班 2 任务码 ' + codeBad)
    const r = await studentJoin(browser, STU_BAD, STU_BAD_PASS, codeBad, net)
    console.log('  点击加入：', r.clicked ? '已点' : '未找到按钮')
    console.log('  UI 徽标：', r.ui.badge, '｜按姓名匹配提示：', r.ui.ok || '(无)', '｜告警：', r.ui.warn || '(无)')
    console.log('  API 真值：', r.api
      ? `roster_bound=${r.api.roster_bound} matched_by=${r.api.bound_match || '—'} bound_name=${r.api.bound_name || '—'}`
      : '(未捕获响应)')
  }

  // ── 教师视角看板：班级参与统计是否立刻反映出来 ──
  const targets = WRITE ? [CLS_OK, CLS_BAD] : (process.env.E2E_CLASS ? [process.env.E2E_CLASS] : [])
  for (const cn of targets) {
    await enterTeacherPage(page)
    await sleep(1500)
    await selectClass(page, cn)
    await sleep(1200)
    const dash = await openDashboard(page, cn)
    console.log('\n【看板】' + cn)
    if (!dash || !dash.hasTable) { console.log('  看板未渲染（.card.wide table 未出现）'); continue }
    console.log('  聚合：', dash.stats.join(' ｜ '))
    console.log('  最弱维度行：', dash.weak || '(无)')
    console.log('  备注：', dash.note || '(无)')
    for (const row of dash.rows) console.log('  学生行：', row.join(' | '))
  }

  // ── 导出（教师端两个出口：CSV / 一页纸）──
  if (targets.length) {
    const exp1 = await clickByText(page, ['导出 CSV'])
    await sleep(2000)
    const m1 = await readMsg(page)   // 两条导出共用 .msg，必须各读各的，后一条会覆盖前一条
    const exp2 = await clickByText(page, ['导出一页纸报告'])
    await sleep(4000)
    const m2 = await readMsg(page)
    console.log('\n导出 CSV：', exp1 || '(未找到/已禁用)', '｜点击后提示：', m1 || '(无反馈)')
    console.log('导出一页纸：', exp2 || '(未找到/已禁用)', '｜点击后提示：', m2 || '(无反馈)')
  }

  console.log('\n网络 4xx/5xx：', net.length ? net.join(' | ') : '无')
  console.log('控制台错误：', consoleErrs.length ? consoleErrs.slice(0, 6).join(' | ') : '无')
  await browser.close()
})().catch(e => { console.error('ERR', e.message); process.exit(1) })
