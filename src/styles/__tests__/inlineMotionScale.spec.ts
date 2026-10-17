import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { resolve, relative } from 'node:path'

// ─────────────────────────────────────────────────────────────────────────────
// 源码门禁：模板内联 style 的动效时长必须走 --motion-scale 总闸。
//
// 为什么只查「内联」而不查 CSS：
//   CSS 里的 animation/transition 死时长已被 _components.css:296 的全局兜底覆盖：
//     @media (prefers-reduced-motion:reduce){ *,*::before,*::after{
//       animation-duration:0.001ms!important; transition-duration:0.001ms!important; …}}
//   该 !important 规则优先级最高，CSS 选择器里的死时长一律会被压掉。
//   而**内联 style 的特异性同样高于普通选择器**，且本项目没有对内联动效写
//   !important 覆盖 —— 所以内联死时长是唯一真正绕过 reduced-motion 的缺口。
//   （历史缺口见 EvidenceCheckPanel、LearningPathView、ResourceView 三个组件。）
//
// 另一个差异化点：--motion-scale 在 pointer:coarse 时降到 0.7（触屏降级），
// 只有显式引用该变量的动效才会跟着降级。
// ─────────────────────────────────────────────────────────────────────────────

const SRC = resolve(process.cwd(), 'src')

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

/** 去掉 <style> 块与注释，只留模板 + <script>（内联动效在这里） */
function stripStylesAndComments(src: string): string {
  return src
    .replace(/<style[^>]*>[\s\S]*?<\/style>/g, '')
    .replace(/\{\*[\s\S]*?\*\}/g, '')
    .replace(/<!--[\s\S]*?-->/g, '')
}

/** 抓 transition/animation 简写里带死时长（数字+ms/s）且未引用 motion-scale 的 */
const INLINE_MOTION =
  /(?:transition|animation)\s*:\s*['"`]([^'"`]*)[`'"`]/g

describe('内联动效必须走 --motion-scale 总闸', () => {
  const files = walk(SRC)

  it('扫描到足够多的 .vue 文件（防止 walk 失效导致空扫通过）', () => {
    expect(files.length).toBeGreaterThan(20)
  })

  it('模板/脚本内联 style 中不存在写死时长的 transition/animation', () => {
    const offenders: string[] = []
    for (const f of files) {
      const src = stripStylesAndComments(readFileSync(f, 'utf-8'))
      for (const m of src.matchAll(INLINE_MOTION)) {
        const seg = m[1]
        const hasDeadDuration = /\b\d+(?:\.\d+)?m?s\b/.test(seg)
        const usesMasterSwitch = seg.includes('motion-scale') ||
                                  seg.includes('var(--duration-')
        if (hasDeadDuration && !usesMasterSwitch) {
          const ln = src.slice(0, m.index).split('\n').length
          offenders.push(`${relative(process.cwd(), f)}:${ln} → ${seg.trim().slice(0, 80)}`)
        }
      }
    }
    expect(offenders, '以下内联动效写死时长，reduced-motion 管不到（内联无 !important 覆盖）')
      .toEqual([])
  })

  it('已知的三处历史缺口确实已走 calc(X * var(--motion-scale))', () => {
    const probes: Array<[string, string]> = [
      ['src/components/EvidenceCheckPanel.vue', 'stroke-dashoffset'],
      ['src/views/LearningPathView.vue', 'transform'],
      ['src/views/ResourceView.vue', 'transform'],
    ]
    for (const [rel, prop] of probes) {
      const src = stripStylesAndComments(readFileSync(resolve(process.cwd(), rel), 'utf-8'))
      const hit = [...src.matchAll(INLINE_MOTION)].find((m) => m[1].includes(prop))
      expect(hit, `${rel} 应含 ${prop} 的内联 transition`).toBeTruthy()
      expect(hit![1]).toContain('var(--motion-scale)')
    }
  })
})
