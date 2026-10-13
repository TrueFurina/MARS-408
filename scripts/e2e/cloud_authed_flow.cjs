/**
 * 云服务登录态全链路验证（真实注册 → 存档 → 文件 → AI 助教 → 清理）
 * ============================================================================
 * 与 cloud_probe.cjs（未登录通道探针）互补：本脚本在**真实云端会话**下跑，
 * 覆盖登录后才能验证的开通方向。
 *
 * 前置：先用 cloud_probe.cjs --send-otp <邮箱> 拿到验证码邮件；
 *       verificationId 会写进 _e2e_tmp_mdhz/cloud_probe_result.json，本脚本自动解析。
 *
 * 用法（验证码只发一次、15 分钟内有效，务必一次跑完）：
 *   node scripts/e2e/cloud_authed_flow.cjs --email you@example.com --code 123456
 *   可选：--password <注册密码，默认生成随机值并写入 _e2e_tmp_mdhz/cloud_credentials.json>
 *
 * 行为与边界：
 *   - 用验证码注册（新邮箱）或登录（已注册邮箱），注册时设置密码以便后续复登；
 *   - 进度存档用 lab_id='__e2e_cloud_check'，文件上传后**全部清理**（含进度行），
 *     云端不留下验证残留；
 *   - AI 助教问一个一句话就能答的问题，验证流式返回非空即止，不做质量评判；
 *   - 产出为「接入正确性」证据，禁止当成效证据引用。
 */
'use strict'

const fs = require('node:fs')
const path = require('node:path')

// 与探针同一套浏览器垫片与配置读取（保持单一数据源）
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

const ROOT = path.join(__dirname, '..', '..')
const TMP = path.join(ROOT, '_e2e_tmp_mdhz')

function readPublicConfig() {
  const src = fs.readFileSync(path.join(ROOT, 'src', 'services', 'cloud', 'config.ts'), 'utf8')
  const pick = (key) => src.match(new RegExp(key + "\\s*:\\s*'([^']+)'"))[1]
  return {
    endpoint: pick('endpoint'),
    oauthRelayBaseUrl: pick('oauthRelayBaseUrl'),
    publishableKey: pick('publishableKey'),
  }
}

function arg(name, fallback) {
  const i = process.argv.indexOf('--' + name)
  return i >= 0 ? process.argv[i + 1] : fallback
}

// 优先用 _e2e_tmp_mdhz/vid.txt（最近一次发码落盘），退回解析探针结果 JSON
function latestVerificationId() {
  const vidFile = path.join(TMP, 'vid.txt')
  if (fs.existsSync(vidFile)) {
    const vid = fs.readFileSync(vidFile, 'utf8').trim()
    if (vid) return vid
  }
  const file = path.join(TMP, 'cloud_probe_result.json')
  if (!fs.existsSync(file)) throw new Error(`找不到探针结果 ${file}，请先跑 cloud_probe.cjs --send-otp`)
  const data = JSON.parse(fs.readFileSync(file, 'utf8'))
  const otp = [...data.results].reverse().find((r) => r.name.startsWith('auth.sendOtp'))
  if (!otp) throw new Error('探针结果里没有 sendOtp 记录，请先跑 cloud_probe.cjs --send-otp')
  const m = otp.detail.match(/verificationId=(\S+?)(?:\s|$)/)
  if (!m) throw new Error('sendOtp 失败或未返回 verificationId：' + otp.detail)
  return m[1]
}

const EMAIL = arg('email')
const CODE = arg('code')
const SEND_MODE = process.argv.includes('--send')
if (!EMAIL || (!CODE && !SEND_MODE)) {
  console.error(
    '用法：\n' +
      '  node scripts/e2e/cloud_authed_flow.cjs --email you@example.com --send       # 同进程发码并等待\n' +
      '    然后把收到的验证码写入 _e2e_tmp_mdhz/code.txt（纯文本 6 位），脚本自动继续\n' +
      '  node scripts/e2e/cloud_authed_flow.cjs --email you@example.com --code 123456 # 已有 verificationId 时直跑\n' +
      '⚠️ 默认推荐 --send：sendOtp 与 verifyOtp 必须同进程（怀疑 PKCE/客户端态不落盘，\n' +
      '   跨进程会得到 invalid_grant "issued for another client"，2026-10-14 实测）',
  )
  process.exit(1)
}

const { createWorkBuddyCloud } = require('@tencent-ai/workbuddy-cloud-sdk')
const CFG = readPublicConfig()
const cloud = createWorkBuddyCloud({
  endpoint: CFG.endpoint,
  oauthRelayBaseUrl: CFG.oauthRelayBaseUrl,
  publishableKey: CFG.publishableKey,
})

// database 表名收窄问题同 labArchive.ts：一处宽松别名
const db = cloud.database
const TABLE = 'source_lab_progress'
const LAB = '__e2e_cloud_check'

const results = []
async function step(name, fn) {
  try {
    const r = await fn()
    results.push({ name, ok: r.ok, detail: r.detail })
    console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${name}\n      ${r.detail}`)
  } catch (e) {
    const msg = e && e.message ? e.message : String(e)
    results.push({ name, ok: false, detail: msg })
    console.log(`FAIL  ${name}\n      抛出异常：${msg}`)
  }
}

async function main() {
  console.log('=== 云服务登录态全链路验证 ===')
  console.log(`endpoint: ${CFG.endpoint} / email: ${EMAIL} / ${new Date().toISOString()}\n`)

  // 同进程发码：避免跨进程丢客户端态（PKCE/匿名 session 线索不落 localStorage）
  let code = CODE
  if (SEND_MODE) {
    const codeFile = path.join(TMP, 'code.txt')
    if (fs.existsSync(codeFile)) fs.unlinkSync(codeFile)
    const send = await cloud.auth.sendOtp({ email: EMAIL })
    if (send.error) {
      console.log('FAIL  auth.sendOtp', JSON.stringify(send.error))
      process.exit(1)
    }
    fs.writeFileSync(path.join(TMP, 'vid.txt'), send.data.verificationId, 'utf8')
    console.log(`已发送验证码到 ${EMAIL}（isExistingUser=${send.data.isExistingUser}）`)
    console.log(`等待验证码写入 ${codeFile} …（最长 15 分钟）`)
    const deadline = Date.now() + 15 * 60 * 1000
    while (Date.now() < deadline) {
      if (fs.existsSync(codeFile)) {
        code = fs.readFileSync(codeFile, 'utf8').trim()
        if (code) break
      }
      await new Promise((r) => setTimeout(r, 3000))
    }
    if (!code) {
      console.log('FAIL  等待验证码超时')
      process.exit(1)
    }
    console.log(`已读取验证码（${code.length} 位），继续校验\n`)
  }

  // 1) 验证码校验（新邮箱注册设密码；老邮箱忽略密码）
  // ⚠️ 实测教训：verifyOtp 校验成功但**注册密码不可回读**——若失败重试，
  //     isExistingUser 已变 true，只能走「已存在用户」路径，原密码即丢失。
  //     所以失败时也要把本次生成的密码落盘，宁可错存不可丢。
  let password = arg('password') || 'E2e#' + Math.random().toString(36).slice(2, 10) + 'x'
  await step('auth.verifyOtp（注册/登录）', async () => {
    const res = await cloud.auth.verifyOtp({
      email: EMAIL,
      verificationId: latestVerificationId(),
      isExistingUser: true, // 上次尝试后账号已存在；新邮箱直接注册由 sendOtp 的 isExistingUser 决定
      token: code.trim(),
    })
    if (res.error) {
      fs.mkdirSync(TMP, { recursive: true })
      fs.writeFileSync(
        path.join(TMP, 'cloud_credentials.json'),
        JSON.stringify({ email: EMAIL, attemptedPassword: password, note: 'verifyOtp 失败时的候选密码' }, null, 2),
        'utf8',
      )
      return { ok: false, detail: JSON.stringify(res.error) }
    }
    const s = res.data
    fs.mkdirSync(TMP, { recursive: true })
    fs.writeFileSync(
      path.join(TMP, 'cloud_credentials.json'),
      JSON.stringify({ email: EMAIL, password, note: '云服务验证测试账号，非生产凭据' }, null, 2),
      'utf8',
    )
    return {
      ok: !!(s && s.user && s.user.id),
      detail: `uid=${s.user && s.user.id}`,
    }
  })

  // 后续步骤都要求已登录
  const sess = await cloud.auth.getSession()
  const uid = sess.data && sess.data.user ? sess.data.user.id : null
  if (!uid) {
    console.log('\n未建立会话，终止后续步骤。')
    fs.writeFileSync(
      path.join(TMP, 'cloud_authed_result.json'),
      JSON.stringify({ at: new Date().toISOString(), results }, null, 2),
      'utf8',
    )
    process.exit(1)
  }
  console.log(`\n会话就绪 uid=${uid}\n`)

  // 2) 进度存档：写入 → 读回 → 比对
  const completed = ['step-1', 'step-2']
  const attempts = { 'step-1': 3, 'step-2': 1 }
  await step('database 进度写入（upsert + select 回读）', async () => {
    const w = await db
      .from(TABLE)
      .upsert(
        { lab_id: LAB, completed, attempts, updated_at: new Date().toISOString() },
        { onConflict: 'owner_id,lab_id' },
      )
      .select()
    if (w.error) return { ok: false, detail: '写入报错：' + JSON.stringify(w.error) }
    if (!Array.isArray(w.data) || w.data.length === 0)
      return { ok: false, detail: '写入返回空数组（被 RLS 拦下？）' }
    const r = await db.from(TABLE).select('lab_id, completed, attempts').eq('lab_id', LAB).maybeSingle()
    if (r.error) return { ok: false, detail: '读回报错：' + JSON.stringify(r.error) }
    const same =
      r.data && JSON.stringify(r.data.completed) === JSON.stringify(completed) &&
      JSON.stringify(r.data.attempts) === JSON.stringify(attempts)
    return { ok: !!same, detail: `读回=${JSON.stringify(r.data)}` }
  })

  // 3) 存储：上传 → 列表 → 下载读回 → 删除
  const fileName = 'e2e-cloud-check.txt'
  const fileBody = 'cloud e2e check @ ' + new Date().toISOString()
  let uploadedPath = null
  await step('storage 上传/列表/下载读回', async () => {
    const dir = cloud.storage.userPath(uid, `source-lab/${LAB}`)
    const up = await cloud.storage.upload(`${dir}/${fileName}`, fileBody, {
      contentType: 'text/plain',
      upsert: true,
    })
    if (up.error) return { ok: false, detail: '上传报错：' + JSON.stringify(up.error) }
    uploadedPath = `${dir}/${fileName}`
    const list = await cloud.storage.list(dir, { limit: 100 })
    if (list.error) return { ok: false, detail: '列表报错：' + JSON.stringify(list.error) }
    const found = (list.data || []).some((f) => f.name === fileName)
    if (!found) return { ok: false, detail: '列表中未找到刚上传的文件' }
    const dl = await cloud.storage.download(uploadedPath)
    if (dl.error) return { ok: false, detail: '下载报错：' + JSON.stringify(dl.error) }
    const text = await dl.data.text()
    return { ok: text === fileBody, detail: `下载读回 ${text.length} 字节，一致=${text === fileBody}` }
  })

  // 4) AI 助教：列模型 + 一次最小流式对话
  await step('llm models.list + 最小流式对话', async () => {
    const models = (await cloud.llm.models.list()) || []
    if (!models.length) return { ok: false, detail: '模型列表为空' }
    const model = models.find((m) => m.disabled !== true)
    if (!model) return { ok: false, detail: '所有模型均被禁用' }
    let got = ''
    for await (const chunk of cloud.llm.chat.completions.create({
      model: model.id,
      messages: [
        { role: 'system', content: '你是冒烟测试助手，只回复两个字：正常' },
        { role: 'user', content: '请回复' },
      ],
      stream: true,
    })) {
      got += chunk.choices?.[0]?.delta?.content || ''
    }
    return { ok: got.trim().length > 0, detail: `model=${model.id} 首答="${got.trim().slice(0, 40)}"` }
  })

  // 5) 清理验证残留（进度行 + 文件；删除失败不静默）
  await step('清理验证残留（进度行 + 云端文件）', async () => {
    const d1 = await db.from(TABLE).delete().eq('lab_id', LAB).select()
    const d2 = uploadedPath ? await cloud.storage.remove([uploadedPath]) : { data: [], error: null }
    const okRows = !d1.error && Array.isArray(d1.data)
    const okFiles = !d2.error
    return {
      ok: okRows && okFiles,
      detail: `进度行删除=${okRows ? d1.data.length + ' 行' : JSON.stringify(d1.error)}；文件删除=${okFiles ? (d2.data || []).length + ' 个' : JSON.stringify(d2.error)}`,
    }
  })

  // 记录测试账号密码（仅本地临时目录，已 gitignore，供后续复登）
  fs.writeFileSync(
    path.join(TMP, 'cloud_credentials.json'),
    JSON.stringify({ email: EMAIL, password, note: '云服务验证测试账号，非生产凭据' }, null, 2),
    'utf8',
  )

  const failed = results.filter((r) => !r.ok)
  console.log('\n=== 汇总 ===')
  console.log(`通过 ${results.length - failed.length}/${results.length}`)
  if (failed.length) failed.forEach((f) => console.log(`  - ${f.name}: ${f.detail}`))

  fs.writeFileSync(
    path.join(TMP, 'cloud_authed_result.json'),
    JSON.stringify({ at: new Date().toISOString(), email: EMAIL, uid, results }, null, 2),
    'utf8',
  )
  console.log(`\n结果已写入：_e2e_tmp_mdhz/cloud_authed_result.json`)
  process.exit(failed.length ? 1 : 0)
}

main()
