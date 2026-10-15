/**
 * 线上多页质量抽检（quality sweep）
 * ============================================================================
 * 目的：对已部署站点做一次「页面级」体检 —— 渲染内容量 / 控制台异常 /
 *       网络失败(4xx-5xx) / 图片裂图，输出一张表，一眼看出哪个页面坏了。
 *
 * 用法：
 *   E2E_USER=<账号> E2E_PASS=<密码> node scripts/e2e/quality_sweep.cjs
 *   E2E_BASE=https://xxx/ 可选（默认发布域）
 *   E2E_PAGES=/a,/b         可选（默认下面这组常用页）
 *
 * 说明：账号从环境变量读，脚本内不落任何凭据。
 */
const puppeteer = require('puppeteer-core')

const BASE = process.env.E2E_BASE || 'https://mangdehenzhi.app.workbuddy.host/'
const U = process.env.E2E_USER || ''
const P = process.env.E2E_PASS || ''
const PAGES = (process.env.E2E_PAGES || '/kaoyan,/achievements,/profile,/career/training,/memory,/engine,/code-lab,/cloud-lab,/design-system').split(',')
const CHROME = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'

async function login(p) {
  if (!U || !P) return false
  await p.goto(BASE + '#/login', { waitUntil: 'networkidle2', timeout: 60000 })
  await new Promise((r) => setTimeout(r, 2500))
  await p.evaluate((u, pw) => {
    const ins = Array.from(document.querySelectorAll('input')).filter((i) => i.type !== 'hidden')
    const set = (el, v) => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(el, v)
      el.dispatchEvent(new Event('input', { bubbles: true }))
    }
    set(ins[0], u)
    set(ins[ins.length - 1], pw)
  }, U, P)
  await p.evaluate(() => document.querySelector('.sbtn')?.click())
  await new Promise((r) => setTimeout(r, 4500))
  return true
}

;(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
  const p = await browser.newPage()
  await p.setViewport({ width: 1440, height: 900 })

  let pageErrs = []
  let netFails = []
  p.on('pageerror', (e) => pageErrs.push(String(e.message).slice(0, 110)))
  p.on('response', (r) => {
    if (r.status() >= 400) netFails.push(r.status() + ' ' + r.url().replace(BASE, '/').slice(0, 70))
  })

  const logged = await login(p)
  if (logged) console.log('登录后落点:', await p.evaluate(() => location.hash))
  else console.log('（未提供 E2E_USER/E2E_PASS，仅抽检公开页）')

  const rows = []
  for (const path of PAGES) {
    pageErrs = []
    netFails = []
    await p.goto(BASE + '#' + path, { waitUntil: 'networkidle2', timeout: 60000 })
    await new Promise((r) => setTimeout(r, 2200))
    const d = await p.evaluate(() => {
      const main = document.querySelector('main,.app-main,.content') || document.body
      return {
        text: main.innerText.trim().length,
        imgs: document.querySelectorAll('img').length,
        broken: Array.from(document.querySelectorAll('img')).filter((i) => !i.complete || i.naturalWidth === 0).length,
        svgs: document.querySelectorAll('svg').length,
      }
    })
    rows.push({ path, ...d, errs: pageErrs.length, net: [...new Set(netFails)].slice(0, 2) })
  }

  console.log('\n' + '路径'.padEnd(22) + '文本  图/裂  svg  异常  网络')
  let bad = 0
  for (const r of rows) {
    const problems = r.errs > 0 || r.broken > 0 || r.net.length > 0 || r.text < 150
    if (problems) bad++
    console.log(
      r.path.padEnd(20) + String(r.text).padStart(5) + String(r.imgs + '/' + r.broken).padStart(7) +
      String(r.svgs).padStart(6) + String(r.errs).padStart(5) + '  ' + (r.net.join(',') || '-') +
      (problems ? '  <-- 需关注' : ''),
    )
  }
  console.log(`\n抽检 ${rows.length} 页，需关注 ${bad} 页`)
  await browser.close()
  process.exit(bad ? 1 : 0)
})().catch((e) => { console.error('ERR', e); process.exit(1) })
