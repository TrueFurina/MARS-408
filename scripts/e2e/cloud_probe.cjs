/**
 * 云服务通道探针（Node 直连，不经浏览器）
 * ============================================================================
 * 目的：在「能不能收到邮箱验证码」之外，先把云通道本身验掉 ——
 *   endpoint 是否可达、publishableKey 是否被服务端接受、
 *   LLM 网关是否可列举模型、未登录时行级安全（RLS）是否真的拦住写入。
 *
 * 这两类验证都不需要登录态，因此可以在收不到验证码的情况下独立得出结论。
 *
 * 用法：
 *   node scripts/e2e/cloud_probe.cjs                # 只跑「不发送邮件」的探测
 *   node scripts/e2e/cloud_probe.cjs --send-otp you@example.com
 *                                                    # 额外真发一封验证码（会真实发信）
 *
 * 退出码：0 = 全部按预期；1 = 出现预期外结果。
 *
 * ⚠️ 本脚本的产出是「通道可用性」证据，**不是成效证据**，禁止当成效引用。
 */

'use strict'

const fs = require('node:fs')
const path = require('node:path')

// ── 最小浏览器环境垫片 ────────────────────────────────────────────────────
// SDK 会话持久化用了 localStorage，Node 里没有；这里给一个内存实现，
// 顺便保证「每次运行都是干净会话」，不受上一次残留影响。
const store = new Map()
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => void store.set(k, String(v)),
  removeItem: (k) => void store.delete(k),
  clear: () => store.clear(),
  key: (i) => Array.from(store.keys())[i] ?? null,
  get length() {
    return store.size
  },
}
globalThis.document = {}

// ── 配置从单一数据源读取，避免与前端漂移 ──────────────────────────────────
const CONFIG_FILE = path.join(__dirname, '..', '..', 'src', 'services', 'cloud', 'config.ts')

function readPublicConfig() {
  const src = fs.readFileSync(CONFIG_FILE, 'utf8')
  const pick = (key) => {
    const m = src.match(new RegExp(key + "\\s*:\\s*'([^']+)'"))
    if (!m) throw new Error(`publicConfig 缺少字段：${key}（检查 ${CONFIG_FILE}）`)
    return m[1]
  }
  return {
    resourceId: pick('resourceId'),
    endpoint: pick('endpoint'),
    oauthRelayBaseUrl: pick('oauthRelayBaseUrl'),
    publishableKey: pick('publishableKey'),
  }
}

const CFG = readPublicConfig()
const { createWorkBuddyCloud } = require('@tencent-ai/workbuddy-cloud-sdk')
const cloud = createWorkBuddyCloud({
  endpoint: CFG.endpoint,
  oauthRelayBaseUrl: CFG.oauthRelayBaseUrl,
  publishableKey: CFG.publishableKey,
})

// ── 结果记录 ─────────────────────────────────────────────────────────────
const results = []
function record(name, ok, detail) {
  results.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}\n      ${detail}`)
}

async function step(name, fn) {
  try {
    const r = await fn()
    record(name, r.ok, r.detail)
    return r
  } catch (e) {
    record(name, false, `抛出异常：${e && e.message ? e.message : e}`)
    return null
  }
}

const fmt = (v) => {
  try {
    return JSON.stringify(v)
  } catch {
    return String(v)
  }
}

async function main() {
  const sendOtpTo = process.argv.includes('--send-otp')
    ? process.argv[process.argv.indexOf('--send-otp') + 1]
    : null

  console.log('=== 云服务通道探针 ===')
  console.log(`resourceId : ${CFG.resourceId}`)
  console.log(`endpoint   : ${CFG.endpoint}`)
  console.log(`publishable: ${CFG.publishableKey.slice(0, 14)}…（已脱敏）`)
  console.log(`时间       : ${new Date().toISOString()}\n`)

  // 1) 会话读取：未登录应返回空会话，且「不是」报错
  await step('auth.getSession（未登录应为空且无 error）', async () => {
    const res = await cloud.auth.getSession()
    if (res.error) {
      const code = res.error.code || res.error.kind || ''
      // 未登录若被报成 unauthenticated，也说明通道是通的、只是没身份
      return {
        ok: code === 'unauthenticated',
        detail: `error=${fmt({ code, message: res.error.message })}`,
      }
    }
    return { ok: res.data === null, detail: `session=${fmt(res.data)}` }
  })

  // 2) LLM 网关：能否列举模型（不需要登录态）
  await step('llm.models.list（列出可用模型）', async () => {
    const models = await cloud.llm.models.list()
    const list = models || []
    const ids = list.slice(0, 8).map((m) => m.id)
    return {
      ok: true,
      detail: `共 ${list.length} 个模型：${ids.join(', ') || '（空）'}`,
    }
  })

  // 3) 数据库未登录写入：RLS 必须拦住（这是安全边界，不是功能失败）
  await step('database 未登录写入（应被 RLS 拦住）', async () => {
    const res = await cloud.database
      .from('source_lab_progress')
      .insert({ lab_id: '__probe_' + Date.now(), completed: [], attempts: {} })
      .select()
    if (res.error) {
      return {
        ok: true,
        detail: `已拒绝：${fmt({ code: res.error.code, message: res.error.message })}`,
      }
    }
    const rows = res.data || []
    return {
      ok: rows.length === 0,
      detail: rows.length === 0 ? '已拒绝（返回空数组，无 error）' : `⚠️ 竟然写入成功：${fmt(rows)}`,
    }
  })

  // 4) 数据库未登录读取：应只能拿到空集或报错
  await step('database 未登录读取（应拿不到他人数据）', async () => {
    const res = await cloud.database.from('source_lab_progress').select('lab_id')
    if (res.error) {
      return { ok: true, detail: `已拒绝：${fmt({ code: res.error.code, message: res.error.message })}` }
    }
    const rows = res.data || []
    return { ok: rows.length === 0, detail: `返回 ${rows.length} 行（预期 0 行）` }
  })

  // 5) 可选：真发一封验证码（会真实发信，默认关闭）
  if (sendOtpTo) {
    await step(`auth.sendOtp → ${sendOtpTo}`, async () => {
      const res = await cloud.auth.sendOtp({ email: sendOtpTo })
      if (res.error) {
        return { ok: false, detail: `发送失败：${fmt(res.error)}` }
      }
      const d = res.data || {}
      return {
        ok: Boolean(d.verificationId),
        detail: `verificationId=${d.verificationId || '（无）'} isExistingUser=${d.isExistingUser}`,
      }
    })
  } else {
    console.log('SKIP  auth.sendOtp（未传 --send-otp，避免真实发信）\n')
  }

  // ── 汇总 ───────────────────────────────────────────────────────────────
  const failed = results.filter((r) => !r.ok)
  console.log('\n=== 汇总 ===')
  console.log(`通过 ${results.length - failed.length}/${results.length}`)
  if (failed.length) {
    console.log('未通过项：')
    failed.forEach((f) => console.log(`  - ${f.name}: ${f.detail}`))
  }

  const outFile = path.join(__dirname, '..', '..', '_e2e_tmp_mdhz', 'cloud_probe_result.json')
  fs.mkdirSync(path.dirname(outFile), { recursive: true })
  fs.writeFileSync(
    outFile,
    JSON.stringify({ at: new Date().toISOString(), endpoint: CFG.endpoint, results }, null, 2),
    'utf8',
  )
  console.log(`\n结果已写入：${path.relative(process.cwd(), outFile)}`)

  process.exit(failed.length ? 1 : 0)
}

main()
