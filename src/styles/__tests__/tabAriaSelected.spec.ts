import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { resolve, relative } from 'node:path'

// ─────────────────────────────────────────────────────────────────────────────
// 源码门禁：tab 类切换按钮必须带**状态类** aria。
//
// 背景：可访问性排查发现 67 处「切换态控件缺状态 aria」——它们只有 aria-label
// （表达名字）而没有 aria-pressed / aria-selected / aria-current 等（表达状态），
// 读屏用户听到的是「对比 按钮」而非「对比 已选中」，无从得知当前在哪一档。
//
// 范围收敛（与内联动效门禁同一思路，只查真缺口）：
//   本次只覆盖 **tab 类按钮**（class 含 tab 且 :class 绑定 active / is-active），
//   因为它们语义最明确（互斥选中），且 `:class` 的条件就是「是否选中」，
//   可零逻辑改动地复用到 :aria-selected。
//   其余切换态控件（导航项→aria-current、折叠→aria-expanded、菜单开关→
//   aria-pressed）语义各异，需逐处判断，留作后续，避免批量加错。
//
// 历史：2026-10-18 一次性给 23 处补了 :aria-selected（复用 :class 条件）；
//   本门禁防回归。
// ─────────────────────────────────────────────────────────────────────────────

const SRC = resolve(process.cwd(), 'src')
// 状态类 aria 属性名（表达选中/展开/按压等状态，而非仅名字）
const STATE_PROPS = ['pressed', 'selected', 'current', 'expanded', 'checked', 'busy']
const STATE_ARIA = new RegExp('aria-(?:' + STATE_PROPS.join('|') + ')')

/** <button ...> 开标签，且 class 含 tab */
const TAB_BUTTON = /<button\b[^>]*>/g

function walk(dir: string, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = resolve(dir, name)
    if (statSync(p).isDirectory()) {
      if (name === '__tests__' || name === 'node_modules') continue
      walk(p, acc)
    } else if (name.endsWith('.vue')) {
      acc.push(p)
    }
  }
  return acc
}

function stripStyles(src: string): string {
  return src.replace(/<style[^>]*>[\s\S]*?<\/style>/g, '')
}

describe('tab 类切换按钮必须带状态类 aria', () => {
  const files = walk(SRC)

  it('扫描到足够多的 .vue 文件（防 walk 失效空扫通过）', () => {
    expect(files.length).toBeGreaterThan(20)
  })

  it('class 含 tab 的 button 均有 aria-pressed/selected/current/expanded', () => {
    const offenders: string[] = []
    let checked = 0
    for (const f of files) {
      const src = stripStyles(readFileSync(f, 'utf-8'))
      for (const m of src.matchAll(TAB_BUTTON)) {
        const tag = m[0]
        if (!/class="[^"]*\btab\b[^"]*"/.test(tag)) continue
        checked += 1
        if (!STATE_ARIA.test(tag)) {
          const ln = src.slice(0, m.index).split('\n').length
          offenders.push(`${relative(process.cwd(), f)}:${ln} → ${tag.trim().slice(0, 90)}`)
        }
      }
    }
    expect(checked, '应至少扫到若干 tab 按钮，否则判据失效').toBeGreaterThan(15)
    expect(offenders, '以下 tab 按钮缺状态 aria，读屏无法得知当前选中档').toEqual([])
  })

  it('aria-selected 的条件与 :class 的 active 条件一致（不是硬编码 false）', () => {
    // 抽样三处代表性写法：=== 比较、取反、v-for 成员比较
    const probes: Array<[string, RegExp]> = [
      ['src/components/KnowledgeGraph.vue', /aria-selected="detailTab === 'info'"/],
      ['src/views/PracticeView.vue', /aria-selected="!showStepQuiz"/],
      ['src/views/ResourceView.vue', /aria-selected="activeTab === tab\.key"/],
    ]
    for (const [rel, re] of probes) {
      const src = stripStyles(readFileSync(resolve(process.cwd(), rel), 'utf-8'))
      expect(src, `${rel} 应含与 :class 条件一致的 aria-selected`).toMatch(re)
    }
  })
})
