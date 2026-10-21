/**
 * 模拟演练演示物料抓取（真浏览器截图 + 导出）。
 *
 * 对着本地环境（127.0.0.1:5300 前端 + 8002 后端）跑：
 *   1) 教师看板（桌面 + 手机两种视口）
 *   2) 学生成长页（sim_stu01，六维趋势）
 *   3) 看板 CSV 导出 + 一页纸报告（弹窗降级为下载，headless 下走 download 事件）
 *
 * 用法：
 *   NODE_PATH=<puppeteer-core node_modules> node scripts/e2e/simulation_artifacts.cjs
 *
 * 产出落 _e2e_tmp_mdhz/simulation/（gitignore 已排除该目录）。
 */
const puppeteer = require('puppeteer-core')
const fs = require('fs')
const path = require('path')

const BASE = process.env.E2E_BASE || 'http://127.0.0.1:5300/MARS-408/app/'
const CHROME = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const TCH = process.env.E2E_TEACHER || 'sim_teacher'
const TCH_PASS = process.env.E2E_TEACHER_PASS || 'SimTch#1021aa'
const STU = process.env.E2E_STU || 'sim_stu01'
const STU_PASS = process.env.E2E_STU_PASS || 'SimStu#1021aa'
const CLASS_NAME = process.env.E2E_CLASS || '信息安全1班-模拟演练'
const OUT = process.env.E2E_OUT
  ? path.resolve(process.env.E2E_OUT)
  : path.join(__dirname, '..', '..', '_e2e_tmp_mdhz', 'simulation')
const sleep = ms => new Promise(r => setTimeout(r, ms))

const consoleErrs = []

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
  // 等登录真正生效（token 落 localStorage）再返回：只睡固定时长的话，
  // 遇登录限流（10 次/分钟/IP）或慢响应时会停留在登录页，后续全部误判。
  try {
    await page.waitForFunction(
      () => !!localStorage.getItem('mangdehenzhi_token'),
      { timeout: 20000, polling: 500 })
  } catch {
    const errText = await page.evaluate(() => (document.body.innerText || '').slice(0, 120))
    throw new Error(`登录未生效（可能被限流）：${user}｜页面：${errText}`)
  }
  await sleep(1500)
}

;(async () => {
  fs.mkdirSync(OUT, { recursive: true })
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })

  // ── 1) 教师看板（桌面）──
  const page = await browser.newPage()
  page.on('console', m => { if (m.type() === 'error') consoleErrs.push(m.text().slice(0, 140)) })
  page.on('pageerror', e => consoleErrs.push('pageerror: ' + String(e).slice(0, 140)))
  await page.setViewport({ width: 1440, height: 900 })
  await login(page, TCH, TCH_PASS)
  await page.goto(BASE + '#/career/teacher', { waitUntil: 'networkidle2', timeout: 60000 })
  await sleep(2500)
  // 选中模拟班
  await page.evaluate(n => {
    const li = Array.from(document.querySelectorAll('.class-list li'))
      .find(x => (x.innerText || '').includes(n))
    li?.querySelector('button.link')?.click()
  }, CLASS_NAME)
  await sleep(1500)
  // 点「看板」
  await page.evaluate(n => {
    const li = Array.from(document.querySelectorAll('.class-list li'))
      .find(x => (x.innerText || '').includes(n))
    if (!li) throw new Error('班级列表未渲染或未找到目标班：' + n)
    const btn = Array.from(li.querySelectorAll('button.link')).find(b => (b.innerText || '').includes('看板'))
    if (!btn) throw new Error('未找到该班的「看板」按钮')
    btn.click()
  }, CLASS_NAME)
  try {
    await page.waitForFunction(() => !!document.querySelector('.card.wide table'),
      { timeout: 30000, polling: 1000 })
  } catch { /* 下面统一判 */ }
  await sleep(2000)
  const dashInfo = await page.evaluate(() => ({
    stats: Array.from(document.querySelectorAll('.stat')).map(s => (s.innerText || '').replace(/\s+/g, ' ').trim()),
    rows: document.querySelectorAll('.card.wide table tbody tr').length,
    hasAgg: !!document.querySelector('.agg'),
  }))
  console.log('看板聚合：', dashInfo.stats.join(' ｜ '))
  console.log('学生表行数：', dashInfo.rows, '｜聚合区：', dashInfo.hasAgg ? '在' : '缺')
  // fullPage 在本应用不生效（内容在内部滚动容器，文档本身只有一屏高）——
  // 实测截图只有 1440x900、看板区没进去。改用「抬高视口 + 视口截图」。
  await page.setViewport({ width: 1440, height: 2100 })
  await sleep(1500)
  await page.screenshot({ path: path.join(OUT, 'dashboard_desktop.png') })
  // 看板本体（.card.wide）用元素截图：47 行名册把卡片推到很下方，
  // 视口截图（再高也有限）装不全，元素截图与滚动位置无关。
  const dashCard = await page.$('.card.wide')
  if (dashCard) {
    await dashCard.screenshot({ path: path.join(OUT, 'dashboard_card.png') })
    console.log('看板卡片元素截图：已存')
  }

  // ── 2) 教师看板（手机视口）──
  const mp = await browser.newPage()
  await mp.setViewport({ width: 390, height: 844 })
  await login(mp, TCH, TCH_PASS)
  await mp.goto(BASE + '#/career/teacher', { waitUntil: 'networkidle2', timeout: 60000 })
  await sleep(2500)
  await mp.evaluate(n => {
    const li = Array.from(document.querySelectorAll('.class-list li'))
      .find(x => (x.innerText || '').includes(n))
    const btn = Array.from(li.querySelectorAll('button.link')).find(b => (b.innerText || '').includes('看板'))
    btn?.click()
  }, CLASS_NAME)
  await sleep(4000)
  await mp.screenshot({ path: path.join(OUT, 'dashboard_mobile.png'), fullPage: true })
  await mp.close()

  // ── 3) 导出：CSV（download 事件）+ 一页纸（弹窗被拦 ⇒ 降级下载）──
  const dlDir = path.join(OUT, 'downloads')
  fs.mkdirSync(dlDir, { recursive: true })
  const client = await page.target().createCDPSession()
  await client.send('Page.setDownloadBehavior', { behavior: 'allow', downloadPath: dlDir })

  const csvBtn = await page.evaluate(() => {
    const b = Array.from(document.querySelectorAll('button')).find(x => (x.innerText || '').includes('导出 CSV'))
    if (b) { b.click(); return true }
    return false
  })
  await sleep(2500)
  const msgAfterCsv = await page.evaluate(() => (document.querySelector('.msg') || {}).innerText || '')
  console.log('CSV 导出：', csvBtn ? '已点' : '未找到', '｜提示：', msgAfterCsv.trim().slice(0, 60))

  const pdfBtn = await page.evaluate(() => {
    const b = Array.from(document.querySelectorAll('button')).find(x => (x.innerText || '').includes('导出一页纸报告'))
    if (b) { b.click(); return true }
    return false
  })
  await sleep(5000)
  const msgAfterPdf = await page.evaluate(() => (document.querySelector('.msg') || {}).innerText || '')
  console.log('一页纸导出：', pdfBtn ? '已点' : '未找到', '｜提示：', msgAfterPdf.trim().slice(0, 60))
  const downloads = fs.existsSync(dlDir) ? fs.readdirSync(dlDir) : []
  console.log('下载目录文件：', downloads.length ? downloads.join(' | ') : '（无）')

  // ── 4) 学生成长页（sim_stu01）──
  // 🔴 必须用独立 BrowserContext：同 context 的新 page 会共享 localStorage 里的
  // 教师 token，成长页渲染的是教师身份（教师 0 场次）——本项目踩过两次的坑。
  const sctx = await browser.createBrowserContext()
  const sp = await sctx.newPage()
  await sp.setViewport({ width: 1440, height: 900 })
  await login(sp, STU, STU_PASS)
  await sp.goto(BASE + '#/career/growth', { waitUntil: 'networkidle2', timeout: 60000 })
  await sleep(3500)
  const growth = await sp.evaluate(() => (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 240))
  const who = await sp.evaluate(() => {
    const m = (document.body.innerText || '').match(/模拟学生\d+|学生\d+|模拟教师/)
    return m ? m[0] : '(未识别)'
  })
  console.log('成长页身份：', who)
  console.log('成长页片段：', growth)
  await sp.setViewport({ width: 1440, height: 1600 })
  await sleep(1200)
  await sp.screenshot({ path: path.join(OUT, 'student_growth.png') })
  await sctx.close()

  console.log('控制台错误：', consoleErrs.length ? consoleErrs.slice(0, 5).join(' | ') : '无')
  console.log('产物目录：', OUT)
  await browser.close()
})().catch(e => { console.error('ERR', e.stack || e.message); process.exit(1) })
