/**
 * 学生端实训全流程（真浏览器，不是只打 API）。
 *
 * 验证的是「人在页面上操作时」链路是否成立：加入任务 → 逐轮作答 →
 * 看到"报告生成中"轮询提示 → 报告页出六维分数。
 * API 层全流程由 public_pilot_api.cjs 覆盖，本脚本专测前端轮询 UI——
 * 终评已异步化（后台 asyncio task），前端必须轮询才拿得到报告；
 * 只验证 API 200 无法证明这段 UI 真的能用。
 *
 * 用法（仓库根）：
 *   NODE_PATH=<puppeteer-core 所在 node_modules> \
 *   E2E_USER=pilot_student E2E_PASS=xxx E2E_JOIN_CODE=22632D \
 *   node scripts/e2e/student_training_ui.cjs
 *
 * 判读：终点是 report 区出现六维分数；中途 net 列出现 5xx/504 才是真故障
 *（终评走后台任务，慢是预期的，504 不是）。
 */
const puppeteer = require('puppeteer-core')

const BASE = process.env.E2E_BASE || 'https://mangdehenzhi.app.workbuddy.host/'
const CHROME = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const U = process.env.E2E_USER || ''
const P = process.env.E2E_PASS || ''
const CODE = process.env.E2E_JOIN_CODE || '22632D'
const TURNS = Number(process.env.E2E_TURNS || 5)
const sleep = ms => new Promise(r => setTimeout(r, ms))

const consoleErrs = []

// 按可见文本点按钮（页面按钮文案会随步骤变化，用文本比用 class 稳）
function clickByText(page, texts) {
  return page.evaluate(ts => {
    const btns = Array.from(document.querySelectorAll('button')).filter(b => !b.disabled)
    for (const t of ts) {
      const hit = btns.find(b => (b.innerText || '').includes(t))
      if (hit) { hit.click(); return t }
    }
    return null
  }, texts)
}

async function typeAnswer(page, text) {
  await page.evaluate(t => {
    const ta = document.querySelector('textarea.answer-input')
    if (!ta) return
    Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set.call(ta, t)
    ta.dispatchEvent(new Event('input', { bubbles: true }))
  }, text)
}

const ANSWERS = [
  '我的选题是多智能体强化学习驱动的共识机制优化。理由是现有 PBFT 在节点规模上升时通信开销呈平方增长，实际部署到 16 节点就明显掉吞吐。',
  '方法上采用分阶段共识：候选提名、加权投票、提交确认三阶段，用历史行为形成的信用权重替代全量广播，每轮只与高信用节点通信。',
  '主要风险是信用权重本身可能被恶意节点通过长期小额作恶来操纵。我准备用身份锚定加三阶段防护，把单点影响限制在局部。',
  '实验设计是与基线 PBFT 对比，在 4、8、16 节点三种规模下测吞吐和延迟，另外做 20% 恶意节点注入，观察吞吐量衰减幅度。',
  '预期贡献是把通信复杂度从平方级降到近似线性，并且在 16 节点规模下保持吞吐不下降，同时恶意节点场景下衰减控制在可接受范围。',
]

;(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
  const page = await browser.newPage()
  await page.setViewport({ width: 1440, height: 900 })
  page.on('console', m => { if (m.type() === 'error') consoleErrs.push(m.text().slice(0, 140)) })
  page.on('pageerror', e => consoleErrs.push('pageerror: ' + String(e).slice(0, 140)))

  const net = []
  page.on('response', r => {
    if (r.status() >= 400) net.push(r.status() + ' ' + r.url().replace(BASE, '/').slice(0, 50))
  })

  // ── 登录 ──
  await page.goto(BASE + '#/login', { waitUntil: 'networkidle2', timeout: 60000 })
  await sleep(2500)
  await page.evaluate((u, pw) => {
    const ins = Array.from(document.querySelectorAll('input')).filter(i => i.type !== 'hidden')
    const set = (el, v) => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(el, v)
      el.dispatchEvent(new Event('input', { bubbles: true }))
    }
    set(ins[0], u); set(ins[ins.length - 1], pw)
  }, U, P)
  await page.evaluate(() => document.querySelector('.sbtn')?.click())
  await sleep(4500)
  console.log('登录 →', U)

  // ── 进实训页 ──
  await page.goto(BASE + '#/career/training', { waitUntil: 'networkidle2', timeout: 60000 })
  await sleep(3000)

  // 知情同意（若存在）
  const consent = await clickByText(page, ['同意并继续'])
  if (consent) { console.log('知情同意：已点「同意并继续」'); await sleep(2500) }

  // ── 加入教师任务 ──
  await page.evaluate(code => {
    const inp = document.querySelector('input.join-input')
    if (!inp) return
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(inp, code)
    inp.dispatchEvent(new Event('input', { bubbles: true }))
  }, CODE)
  await sleep(600)
  const joined = await clickByText(page, ['加入实训'])
  console.log('加入任务码', CODE, '→', joined ? '已点' : '未找到按钮（可能已加入）')
  await sleep(3500)

  // 加入后的提示（名册匹配情况）
  const joinInfo = await page.evaluate(() => {
    const el = document.querySelector('.join-badge')
    if (!el) return null
    const warn = document.querySelector('.join-warn')
    return { badge: el.innerText.trim(), warn: warn ? warn.innerText.trim() : '' }
  })
  if (joinInfo) console.log('  加入状态：', joinInfo.badge, joinInfo.warn ? '| ' + joinInfo.warn : '')

  // ── 推进到对话页 ──
  // 页面是三段式：select(选情景) → briefing(情景介绍) → battle(对话)，
  // 每段各有一个按钮（select 上是「开始…」，briefing 上是「进入对抗 →」）。
  // 首版只点一次就以为进去了，结果停在 briefing，后续全误判成"输入框消失"。
  // 故改为循环推进：每轮按当前页面存在的按钮文案点一次，直到 textarea 出现。
  let entered = false
  for (let attempt = 1; attempt <= 4 && !entered; attempt++) {
    const clicked = await clickByText(page, ['进入对抗', '开始实训', '开始对抗', '开始'])
    console.log(`推进 ${attempt}: 点击「${clicked || '(无可点按钮)'}」`)
    if (!clicked) break
    let w = 0
    while (w < 30000) {
      await sleep(2000); w += 2000
      entered = await page.evaluate(() => !!document.querySelector('textarea.answer-input'))
      if (entered) break
    }
  }
  if (!entered) {
    const btns = await page.evaluate(() => Array.from(document.querySelectorAll('button'))
      .map(b => (b.innerText || '').trim()).filter(Boolean).slice(0, 8))
    console.log('  !! 未能进入对话页，当前按钮：', btns.join(' / '))
  } else {
    console.log('已进入对话页（battle）')
  }

  // ── 逐轮作答 ──
  let sawPending = false
  for (let i = 0; i < TURNS; i++) {
    const hasInput = await page.evaluate(() => !!document.querySelector('textarea.answer-input'))
    if (!hasInput) { console.log(`  第 ${i + 1} 轮：输入框已消失（实训已结束）`); break }

    // 顺序很重要：必须先填答案，再等按钮可用。
    // 按钮的禁用条件是 `busy || !answerInput.trim()`——先等的话答案为空，
    // 条件恒真，会一直等到超时（第三版就卡死在这，报"150s 未恢复可用"）。
    await typeAnswer(page, ANSWERS[i % ANSWERS.length])
    await sleep(400)

    // 填完答案后，剩下的等待只是「等上一轮 LLM 生成完，busy 解除」
    let ready = true
    try {
      await page.waitForFunction(() => {
        const b = Array.from(document.querySelectorAll('button'))
          .find(x => (x.innerText || '').includes('提交作答'))
        return b && !b.disabled
      }, { timeout: 150000, polling: 1000 })
    } catch { ready = false }
    if (!ready) { console.log(`  第 ${i + 1} 轮：提交按钮 150s 未恢复可用，中止`); break }
    const t0 = Date.now()
    const clicked = await clickByText(page, ['提交作答', '发送', '提交'])
    if (!clicked) { console.log(`  第 ${i + 1} 轮：未找到提交按钮`); break }

    // 等轮次真正推进（页面顶部有「第 N/5 轮」）或进入报告态
    let advanced = false
    try {
      // 注意两点：
      // 1) 回调在浏览器里执行，外部变量必须显式作参数传入，否则 ReferenceError；
      // 2) 页面顶部「第 N/5 轮」是**已作答轮数**，进入对话时为「第 0/5 轮」，
      //    所以提交第 i+1 轮后应等到「第 i+1/5 轮」，不是 i+2（第三版多数了一轮）。
      //    最后一轮提交后不会再到下一轮，而是直接进入报告态，故并列「评估报告生成中」。
      await page.waitForFunction((n, total) => {
        const t = document.body.innerText || ''
        return t.includes(`第 ${n}/${total} 轮`) || t.includes('评估报告生成中')
      }, { timeout: 150000, polling: 1500 }, i + 1, TURNS)
      advanced = true
    } catch { /* 超时交给下面统一判定 */ }

    const st = await page.evaluate(() => ({
      pending: (document.querySelector('.bubble.interviewer.typing') || {}).innerText || '',
      students: document.querySelectorAll('.bubble.student').length,
      turnText: (document.body.innerText.match(/第\s*\d+\/\d+\s*轮/) || [''])[0],
    }))
    if (st.pending.includes('评估报告')) sawPending = true
    console.log(`  第 ${i + 1} 轮提交 用时 ${((Date.now() - t0) / 1000).toFixed(1)}s`
      + `｜推进=${advanced ? '是' : '否'}｜${st.turnText}｜学生气泡 ${st.students} 个`
      + (st.pending ? '｜' + st.pending.slice(0, 36) : ''))
    if (!advanced && !st.pending.includes('评估报告')) break
  }

  console.log()
  console.log('轮询提示是否出现过（"评估报告生成中"）:', sawPending ? '是' : '否')

  // ── 等报告真正渲染 ──
  // 判定用报告页专属 DOM（.overall-score），不能用文本关键字：页面正文里
  // 「命中 2 个维度证据」也含"维度"，用文本匹配会在 4s 就误判成报告已到、
  // 其实终评还在后台跑（第五版踩过）。
  // 逐 5s 采样这期间的页面反馈：终评要跑 1–2 分钟，若这段时间页面一直显示
  // 「对手正在思考下一个问题…」，用户得到的就是**错误反馈**（实际在生成报告），
  // 近两分钟会以为还在追问。这是体验问题，必须实测而不能只等结果。
  const states = new Set()
  const samples = []
  let got = false
  const tRep = Date.now()
  while (Date.now() - tRep < 220000) {
    const s = await page.evaluate(() => {
      const el = document.querySelector('.bubble.interviewer.typing')
      const btn = Array.from(document.querySelectorAll('button'))
        .find(b => (b.innerText || '').includes('处理中'))
      return {
        typing: el ? (el.innerText || '').trim().slice(0, 40) : '',
        btn: btn ? (btn.innerText || '').trim() : '',
        hasReport: !!document.querySelector('.overall-score'),
      }
    })
    if (s.typing) states.add(s.typing)
    if (s.btn) states.add('按钮:' + s.btn)
    samples.push(`${((Date.now() - tRep) / 1000).toFixed(0)}s:${(s.typing || s.btn || '无提示').slice(0, 24)}`)
    if (s.hasReport) { got = true; break }
    await sleep(5000)
  }
  console.log(`等报告 ${((Date.now() - tRep) / 1000).toFixed(0)}s → ${got ? '已渲染' : '未渲染（超时）'}`)
  console.log('等待期间出现过的页面提示：', states.size ? Array.from(states).join(' ｜ ') : '（无）')
  console.log('采样：', samples.slice(0, 6).join(' → '))

  if (got) {
    // 顺便把验收口径搬进脚本：.src-tag 直接暴露 assessment_source
    const rep = await page.evaluate(() => ({
      overall: (document.querySelector('.overall-score') || {}).innerText || '',
      src: (document.querySelector('.src-tag') || {}).innerText || '',
      summary: ((document.querySelector('.report-summary') || {}).innerText || '').slice(0, 120),
      dims: Array.from(document.querySelectorAll('.dim-row')).map(r => ({
        name: (r.querySelector('.dim-name') || {}).innerText || '',
        score: (r.querySelector('.dim-score') || {}).innerText || '',
        rationale: ((r.querySelector('.dim-rationale') || {}).innerText || '').slice(0, 60),
      })),
    }))
    console.log(`=== 报告：综合 ${rep.overall} / 5 ｜ 评估来源标签 = ${rep.src}（AI评估=真模型，规则评估=兜底）`)
    console.log('    摘要:', rep.summary)
    for (const d of rep.dims) {
      console.log(`    ${d.name.padEnd(8)} ${d.score}  ${d.rationale}`)
    }
    console.log('    六维条目数 =', rep.dims.length)
  }
  console.log('网络 4xx/5xx:', net.length ? net.join(' | ') : '无')
  console.log('控制台错误:', consoleErrs.length ? consoleErrs.slice(0, 5).join(' | ') : '无')

  await browser.close()
})().catch(e => { console.error('ERR', e.message); process.exit(1) })
