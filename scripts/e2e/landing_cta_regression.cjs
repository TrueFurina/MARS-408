/**
 * landing CTA 回归（防「点啥都弹『本地运行』」复发）
 * ============================================================================
 * 守护的行为：后端在线时，落地页各 CTA 点击应直接跳转，
 *             **不得**弹出「本地运行 · 体验完整功能」说明弹窗。
 *
 * 为什么要这么测：该弹窗由「后端是否可达」的探测结果驱动，而探测是异步的 ——
 * 曾出现过「按钮刚渲染、探测未返回」的窗口期被判定为不可用，导致用户
 * 「点啥都弹窗」（实测反馈）。所以本脚本**等 CTA 一出现就立刻点**复现该竞态，
 * 而不是等网络空闲后再点（那样测不出问题）。
 *
 * 用法：node scripts/e2e/landing_cta_regression.cjs
 *      E2E_BASE=https://xxx/ 可选
 */
const puppeteer = require('puppeteer-core')

const BASE = process.env.E2E_BASE || 'https://mangdehenzhi.app.workbuddy.host/'
const CHROME = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const TARGETS = ['进入系统', '知识图谱', '技能平台', '体验对抗实训', '探索知识图谱', '立即体验']

;(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
  let bad = 0
  let hit = 0

  for (const label of TARGETS) {
    const p = await browser.newPage()
    await p.setViewport({ width: 1440, height: 900 })
    // 关键：domcontentloaded 起手，等按钮一出现立刻点（复现"手快点击"竞态）
    await p.goto(BASE + '#/landing', { waitUntil: 'domcontentloaded', timeout: 60000 })
    let found = false
    try {
      await p.waitForFunction(
        (t) => Array.from(document.querySelectorAll('button')).some((e) => (e.textContent || '').trim() === t),
        { timeout: 15000, polling: 30 },
        label,
      )
      found = true
      await p.evaluate((t) => {
        const btn = Array.from(document.querySelectorAll('button')).find((e) => (e.textContent || '').trim() === t)
        btn.click()
      }, label)
    } catch { /* 该 CTA 在当前角色下不存在 */ }

    await new Promise((r) => setTimeout(r, 1200))
    const state = await p.evaluate(() => ({
      guideOpen: !!document.querySelector('.rg-card'),
      hash: location.hash,
    }))
    const ok = !state.guideOpen
    if (!ok) bad++
    if (found) hit++
    console.log(`${ok ? 'PASS' : 'FAIL'}  「${label}」命中=${found} → 弹窗=${state.guideOpen} hash=${state.hash}`)
    await p.close()
  }

  console.log(`\n命中并点击 ${hit} 个｜${bad === 0 ? '✅ 无一弹窗' : `❌ ${bad} 个弹窗（回归）`}`)
  await browser.close()
  process.exit(bad ? 1 : 0)
})().catch((e) => { console.error('ERR', e); process.exit(1) })
