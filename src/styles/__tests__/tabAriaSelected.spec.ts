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

  it('互斥选中控件（@click + :class 单条件 active）均有状态类 aria', () => {
    // 判据从「class 含 tab」推广到「有 @click 且 :class 单条件绑定 active/is-active」，
    // 覆盖 tab 类 23 处（ca19add）+ 一般互斥选中 26 处（faae3f5）。
    // 仍刻意不覆盖：nav 普通跳转（仅当前项才该用 aria-current）、
    // 多条件 :class（COND 提取不完整，脚本亦保守跳过）、无 @click 的纯展示高亮。
    // 注意 1：ACTIVE 不能用 /g —— 带 /g 的 test() 会记住 lastIndex，
    // 循环里复用时后续调用恒返回 false（曾导致判据失效、扫到 0 个）。
    // 注意 2：total 统计**所有**互斥选中控件（含已带 aria 的）；
    // 若只统计缺 aria 的，修完一处少一处，全部修完后计数归零、断言误报失效。
    const ACTIVE = /:class="\{\s*(?:'is-active'|active)\s*:\s*([^{}]+?)\s*\}"/
    const CLASS_OBJ = /:class="\{([^}]*)\}"/
    const offenders: string[] = []
    let total = 0
    for (const f of files) {
      const src = stripStyles(readFileSync(f, 'utf-8'))
      for (const m of src.matchAll(TAB_BUTTON)) {
        const tag = m[0]
        if (!tag.includes('@click')) continue
        if (!ACTIVE.test(tag)) continue
        total += 1
        if (STATE_ARIA.test(tag)) continue
        const cm = CLASS_OBJ.exec(tag)
        // 多条件 :class 保守跳过（COND 提取会不完整）
        if (cm && (cm[1]!.match(/['a-zA-Z_-]+\s*:/g) ?? []).length > 1) continue
        const ln = src.slice(0, m.index).split('\n').length
        offenders.push(`${relative(process.cwd(), f)}:${ln} → ${tag.trim().slice(0, 90)}`)
      }
    }
    expect(total, '应至少扫到 40 个互斥选中控件，否则判据失效').toBeGreaterThan(40)
    expect(offenders, '以下互斥选中控件缺状态 aria，读屏无法得知当前选中项').toEqual([])
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
