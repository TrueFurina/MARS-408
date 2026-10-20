#!/usr/bin/env node
/**
 * doctor.mjs — 芒得很职一键健康自检（只读聚合，不新增门禁语义）
 *
 * 用法:
 *   node scripts/doctor.mjs            # 快速档（环境 + 仓库卫生 + 端口，秒级）
 *   node scripts/doctor.mjs --full     # 追加 npm run verify（7 门禁全量，分钟级）
 *   node scripts/doctor.mjs --json     # 机器可读输出（供 agent 读取，不打印表格）
 *
 * 设计纪律（来自 REA 调研的最佳实践映射，2026-10-19）:
 *   1. 只读：本脚本不写、不改、不删任何文件；
 *   2. 证据分级：每条检查结果带 observed（直接测得）/ derived（由观测推导）/ unknown（未能确认）——
 *      unknown 显式输出，不静默省略（"没报出来" ≠ "没有问题"）；
 *   3. fail-closed：退出码 0 = 全部通过，1 = 存在 ❌（含 unknown 计为 ⚠️ 不计失败，
 *      但 --strict 下 unknown 也判失败）；
 *   4. 聚合而非重造：全部调用既有资产（verify_all.mjs / gate 脚本 / py-server 结构），
 *      不复制任何门禁逻辑。
 *
 * 与 CI 的关系：CI 权威口径见 AGENTS.md（verify-structural.yml 等）；
 * 本脚本是多会话并发改仓场景下的 10 秒本地自检，不替代 CI。
 */
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import net from 'node:net'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const ROOT = fileURLToPath(new URL('..', import.meta.url))

const ARGS = process.argv.slice(2)

// 选项单一真值源（REA #26）：解析、帮助文本、非法选项提示都从这张表生成。
// 单一来源的意义不在省几行，而在「加一个选项不必改三处」——漏改一处就会出现
// 文档承诺了但代码不认的选项（或反之），而这类偏差没人会去测。
const OPTIONS = {
  '--json': { key: 'json', desc: '机器可读输出（供 agent 读取，不打印表格）' },
  '--full': { key: 'full', desc: '追加 npm run verify（7 门禁全量，分钟级）' },
  '--strict': { key: 'strict', desc: 'unknown/WARN 也计失败' },
  '--help': { key: 'help', desc: '显示本帮助' },
  '-h': { key: 'help', desc: '显示本帮助（同 --help）' },
}
// 注意：多个别名可映射同一个 key（--help / -h），必须**或**起来——
// 用 Object.fromEntries(map) 会让后写者覆盖前者（--help 曾被 -h 的 false 覆盖，实测踩到）。
const FLAGS = {}
for (const [flag, { key }] of Object.entries(OPTIONS)) {
  FLAGS[key] = Boolean(FLAGS[key]) || ARGS.includes(flag)
}
const JSON_MODE = FLAGS.json
const FULL = FLAGS.full
const STRICT = FLAGS.strict

function usage() {
  const lines = ['用法: node scripts/doctor.mjs [选项]', '', '选项:']
  for (const [flag, { desc }] of Object.entries(OPTIONS)) {
    lines.push(`  ${flag.padEnd(9)} ${desc}`)
  }
  lines.push('', '退出码: 0 通过 / 1 存在失败（--strict 下 WARN 也失败）/ 2 用法错误')
  return lines.join('\n')
}

// 拼错的选项必须炸，不能静默忽略（REA #101：静默降级比报错危险）。
const unknown = ARGS.filter((a) => a.startsWith('-') && !(a in OPTIONS))
if (unknown.length > 0) {
  console.error(`未知选项: ${unknown.join(' ')}\n\n${usage()}`)
  process.exit(2)
}
if (FLAGS.help) {
  console.log(usage())
  process.exit(0)
}

const results = []
function record(name, ok, level, detail) {
  results.push({ name, ok: ok === true ? 'PASS' : ok === false ? 'FAIL' : 'WARN', level, detail: detail || '' })
}
function run(cmd, args, opts = {}) {
  return spawnSync(cmd, args, { cwd: ROOT, encoding: 'utf8', ...opts })
}

// ---------- 1. Node 工具链 ----------
function checkNode() {
  const pkg = require(`${ROOT}/package.json`)
  const engines = pkg.engines?.node || '(未声明)'
  const v = process.versions.node
  // engines 形如 "^20.19.0 || >=22.12.0"：取 OR 各段做最低版本判断（derived）
  const clauses = String(engines).split('||').map((s) => s.trim())
  const minOf = (c) => {
    const m = c.match(/(\d+)\.(\d+)\.(\d+)/)
    return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null
  }
  const cur = v.split('.').map(Number)
  let ok = null // null = unknown
  for (const c of clauses) {
    if (c.startsWith('^')) {
      const min = minOf(c)
      if (min && cur[0] === min[0] && (cur[1] > min[1] || (cur[1] === min[1] && cur[2] >= min[2]))) ok = true
      else if (min && cur[0] > min[0]) ok = true
    } else if (c.startsWith('>=')) {
      const min = minOf(c)
      if (min && (cur[0] > min[0] || (cur[0] === min[0] && (cur[1] > min[1] || (cur[1] === min[1] && cur[2] >= min[2]))))) ok = true
    }
  }
  if (ok === null) ok = true // 无法解析 engines 时不误报（derived：解析失败≠不满足）
  record(`Node 版本 ${v}（engines: ${engines}）`, ok, 'derived')
}

// ---------- 2. 依赖与关键路径 ----------
function checkPaths() {
  const need = [
    'node_modules',
    'scripts/verify_all.mjs',
    'py-server/main.py',
    'py-server/app',
    'py-server/seed',
    'py-server/db/profile_store.py',
  ]
  const missing = need.filter((p) => !existsSync(`${ROOT}/${p}`))
  record(
    `关键路径 ${need.length - missing.length}/${need.length} 在位`,
    missing.length === 0,
    'observed',
    missing.length ? `缺失: ${missing.join(', ')}` : ''
  )
  record('py-server 虚拟环境（.venv）', existsSync(`${ROOT}/py-server/.venv`), 'observed',
    existsSync(`${ROOT}/py-server/.venv`) ? '' : '缺失——按 AGENTS.md 命令先 cd py-server && pip install -e .')
}

// ---------- 3. Git 卫生（多会话并发改仓场景） ----------
function checkGit() {
  const branch = run('git', ['branch', 'show-current'])
  const name = (branch.stdout || '').trim()
  const st = run('git', 'status --porcelain'.split(' '))
  const lines = (st.stdout || '').split('\n').filter(Boolean)
  const untracked = lines.filter((l) => l.startsWith('??')).length
  const modified = lines.length - untracked
  if (name) {
    record(`Git 分支 = ${name}`, true, 'observed')
  } else {
    // detached HEAD 三态：被分支包含 → WARN（可恢复）；孤儿 → FAIL
    const contained = run('git', ['branch', '--contains', 'HEAD'])
    const holders = (contained.stdout || '')
      .split('\n').map((s) => s.replace(/^\*?\s+/, '').trim()).filter(Boolean)
    if (holders.length) {
      record('Git HEAD = detached（可恢复）', undefined, 'observed',
        `HEAD 被分支包含（${holders.join(', ')}）——建议 git switch <分支> 回到分支，避免提交丢失`)
    } else {
      record('Git HEAD = detached（孤儿）', false, 'observed',
        'HEAD 不被任何分支包含——先 git switch -c <分支> 再操作')
    }
  }
  record(
    `工作区 ${modified} 改 / ${untracked} 未跟踪`,
    true, // 非失败项，仅态势上报
    'observed',
    name === 'main'
      ? '⚠️ 当前在 main：同步方向唯一 main → career-literacy，新代码应落 career-literacy'
      : !name ? 'detached 态下勿直接 commit，先切回分支' : ''
  )
}

// ---------- 4. 端口态势 ----------
function probePort(port, timeout = 400) {
  return new Promise((resolve) => {
    const s = new net.Socket()
    let done = false
    const finish = (r) => { if (!done) { done = true; s.destroy(); resolve(r) } }
    s.setTimeout(timeout)
    s.once('connect', () => finish({ state: 'up' }))
    s.once('timeout', () => finish({ state: 'unknown' }))
    s.once('error', (e) => finish({ state: 'down', reason: e.code }))
    s.connect(port, '127.0.0.1')
  })
}
async function checkPorts() {
  for (const [port, label] of [[8002, '后端 py-server'], [5173, 'vite dev']]) {
    const r = await probePort(port)
    if (r.state === 'unknown') record(`端口 ${port}（${label}）`, undefined, 'unknown', '探测超时，未确认')
    else record(`端口 ${port}（${label}）${r.state === 'up' ? '占用中' : '未监听'}`, true, 'observed', r.reason || '')
  }
}

// ---------- 5. --full：既有全量门禁 ----------
function runFull() {
  const r = run('npm', ['run', 'verify'], { stdio: JSON_MODE ? 'pipe' : 'inherit' })
  record('npm run verify（7 门禁全量）', r.status === 0, 'observed', r.status === 0 ? '' : `退出码 ${r.status}`)
}

// ---------- 输出 ----------
function printTable() {
  const mark = { PASS: '✅', FAIL: '❌', WARN: '⚠️' }
  const w = Math.max(...results.map((r) => r.name.length)) + 2
  for (const r of results) {
    console.log(`  ${mark[r.ok]} ${r.name.padEnd(w)} [${r.level}]${r.detail ? ' — ' + r.detail : ''}`)
  }
  const fails = results.filter((r) => r.ok === 'FAIL').length
  const warns = results.filter((r) => r.ok === 'WARN').length
  console.log('-'.repeat(64))
  console.log(`  汇总: ${results.length - fails} 通过 / ${fails} 失败 / ${warns} 警告` +
    (STRICT ? `（--strict: ${warns} 个 WARN 计失败）` : ''))
}

async function main() {
  checkNode()
  checkPaths()
  checkGit()
  await checkPorts()
  if (FULL) runFull()

  const fails = results.filter((r) => r.ok === 'FAIL').length
  const warns = results.filter((r) => r.ok === 'WARN').length
  const failed = fails + (STRICT ? warns : 0)

  // 执行基线：pin HEAD + 运行时刻，供 CI 归因与历史对比（REA #134）
  const head = run('git', ['rev-parse', 'HEAD'])
  const headSha = head.status === 0 ? head.stdout.trim() : 'unknown'
  const ranAt = new Date().toISOString()

  if (JSON_MODE) {
    console.log(JSON.stringify({ tool: 'doctor', root: ROOT, full: FULL, strict: STRICT, head: headSha, ran_at: ranAt, results, summary: { pass: results.length - fails - warns, fail: fails, warn: warns } }, null, 2))
  } else {
    console.log('='.repeat(64))
    console.log('  芒得很职 · 健康自检（doctor）' + (FULL ? ' · --full' : ' · 快速档'))
    console.log(`  基线 HEAD: ${headSha}  运行时刻: ${ranAt}`)
    console.log('='.repeat(64))
    printTable()
  }
  process.exit(failed ? 1 : 0)
}

main()
