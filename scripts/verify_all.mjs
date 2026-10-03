#!/usr/bin/env node
/**
 * 前端质量基线一键校验：顺序执行全部门禁，**不因单个失败而中断**，
 * 全部跑完后汇总每个门禁的通过/失败，并以「是否有失败」决定退出码。
 *
 * 动机：旧的 `&&` 串联方式下，第一处红会直接中断后续所有门禁，
 * 排查时看不到全貌（例如误以为"只有一处问题"）。本脚本保证一次跑完、
 * 一次看清所有红点，同时严格保持退出码语义（任一失败 => 非零退出）。
 *
 * 用法：npm run verify
 */
import { spawnSync } from 'node:child_process'

/** [显示名, npm 脚本名]，顺序与旧 verify 一致 */
const STEPS = [
  ['类型检查', 'type-check'],
  ['单元测试', 'test'],
  ['benchmark 证据链', 'gate:evidence'],
  ['可访问性扫描', 'gate:a11y'],
  ['性能反模式扫描', 'gate:perf'],
]

const LINE = '='.repeat(64)
const results = []

for (const [name, script] of STEPS) {
  process.stdout.write(`\n${LINE}\n▶ ${name}（npm run ${script}）\n${LINE}\n`)
  const r = spawnSync(`npm run ${script}`, { stdio: 'inherit', shell: true })
  results.push({ name, ok: r.status === 0 })
}

const failed = results.filter((x) => !x.ok)
process.stdout.write(`\n${LINE}\n质量基线汇总\n${LINE}\n`)
for (const { name, ok } of results) {
  process.stdout.write(`  ${ok ? '✅' : '❌'} ${name}\n`)
}
process.stdout.write(`\n通过 ${results.length - failed.length}/${results.length}\n`)
if (failed.length) {
  process.stdout.write(`失败：${failed.map((x) => x.name).join('、')}\n`)
}
process.exit(failed.length ? 1 : 0)
