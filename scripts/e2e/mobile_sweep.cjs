/**
 * 移动端视口抽检：评委/指导教师大概率手机扫码访问，桌面 1440 全绿不代表手机可用。
 *
 * 用法（在仓库根）：
 *   NODE_PATH=<puppeteer-core 所在 node_modules> \
 *   E2E_USER=admin E2E_PASS=xxx \
 *   E2E_PAGES=landing,showcase,career/training \
 *   node scripts/e2e/mobile_sweep.cjs
 *
 * 判读要点：
 *   - 真信号 = OVERFLOW（整页横向溢出，scrollWidth > 视口宽）+ net 列 4xx/5xx。
 *   - 文本量只作参考：空表单页、路演落地页本就短，别当缺陷。
 *   - 输出会列出最宽的溢出元素（tag#id.class），便于直接定位到组件。
 */
const puppeteer = require('puppeteer-core')

const BASE = process.env.E2E_BASE || 'https://mangdehenzhi.app.workbuddy.host/'
const CHROME = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const U = process.env.E2E_USER || ''
const P = process.env.E2E_PASS || ''
const W = Number(process.env.E2E_VW || 390)
const H = Number(process.env.E2E_VH || 844)
const PAGES = (process.env.E2E_PAGES ||
  'landing,showcase,login,career/training,career/teacher,literacy,dashboard,profile,evidence,benchmark,achievements,settings')
  .split(',').map(s => s.trim()).filter(Boolean).map(s => s.startsWith('/') ? s : '/' + s)

const sleep = ms => new Promise(r => setTimeout(r, ms))

// 控制台错误收集器：必须是模块作用域，b_newPage 里的监听器才够得着
const consoleErrs = []

;(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
  const p = await b_newPage(browser)

  if (U && P) {
    await p.goto(BASE + '#/login', { waitUntil: 'networkidle2', timeout: 60000 })
    await sleep(2500)
    await p.evaluate((u, pw) => {
      const ins = Array.from(document.querySelectorAll('input')).filter(i => i.type !== 'hidden')
      const set = (el, v) => {
        Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(el, v)
        el.dispatchEvent(new Event('input', { bubbles: true }))
      }
      set(ins[0], u); set(ins[ins.length - 1], pw)
    }, U, P)
    await p.evaluate(() => document.querySelector('.sbtn')?.click())
    await sleep(4500)
  }

  console.log(`视口 ${W}x${H}（手机）｜页面 ${PAGES.length} 个`)
  console.log('page'.padEnd(22) + 'chars'.padEnd(7) + 'overflow'.padEnd(10) + 'net')
  console.log('-'.repeat(70))

  for (const path of PAGES) {
    const net = []
    const onr = r => { if (r.status() >= 400) net.push(r.status() + ' ' + r.url().replace(BASE, '/').slice(0, 46)) }
    p.on('response', onr)
    let errCount = consoleErrs.length

    await p.goto(BASE + '#' + path, { waitUntil: 'networkidle2', timeout: 60000 })
    await sleep(2000)

    const info = await p.evaluate(vw => {
      const de = document.documentElement
      const over = de.scrollWidth > vw + 1
      let worst = null
      if (over) {
        let maxRight = 0
        for (const el of Array.from(document.querySelectorAll('body *'))) {
          const r = el.getBoundingClientRect()
          if (r.width === 0 || r.height === 0) continue
          if (r.right > maxRight) {
            maxRight = r.right
            const id = el.id ? '#' + el.id : ''
            const cls = (el.className && typeof el.className === 'string')
              ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : ''
            worst = { sel: el.tagName.toLowerCase() + id + cls, right: Math.round(r.right), w: Math.round(r.width) }
          }
        }
      }
      const main = document.querySelector('main,.app-main,.content') || document.body
      return {
        over, scrollW: de.scrollWidth,
        worst,
        text: (main.innerText || '').trim().length,
        empty: (main.innerText || '').trim().length === 0,
      }
    }, W)

    p.off('response', onr)
    const newErrs = consoleErrs.length - errCount
    console.log(
      path.padEnd(22) +
      String(info.text).padEnd(7) +
      (info.over ? `YES ${info.scrollW}>${W}` : 'no').padEnd(10) +
      (net.join(' | ') || '-') + (newErrs ? ` | console+${newErrs}` : '')
    )
    if (info.over && info.worst) {
      console.log('    ↳ 最宽元素 ' + info.worst.sel + `  right=${info.worst.right} width=${info.worst.w}`)
    }
    if (info.empty) console.log('    ↳ 空白页（无任何文本）')
    if (newErrs > 0) {
      // 只报数量不报内容等于没法定位：去重后打印前 5 条
      const seen = new Set()
      for (let i = errCount; i < consoleErrs.length && seen.size < 5; i++) {
        const key = consoleErrs[i].slice(0, 80)
        if (seen.has(key)) continue
        seen.add(key)
        console.log('    ↳ console: ' + consoleErrs[i])
      }
    }
  }

  await browser.close()
})().catch(e => { console.error('ERR', e.message); process.exit(1) })

async function b_newPage(browser) {
  const p = await browser.newPage()
  await p.setViewport({ width: W, height: H, isMobile: true, hasTouch: true, deviceScaleFactor: 2 })
  p.on('console', m => { if (m.type() === 'error') consoleErrs.push(m.text().slice(0, 120)) })
  p.on('pageerror', e => consoleErrs.push('pageerror: ' + String(e).slice(0, 120)))
  return p
}
