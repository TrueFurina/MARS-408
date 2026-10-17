import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/**
 * 掌握度地图的颜色令牌门禁（源码级静态断言）
 *
 * 背景：设计师审计（gstack/qa-design-mastery-map-2026-10-18.md）判定该视图
 * 「颜色维度达标」——零硬编码色、全部走 --mastery-* / --seq-* / --color-* 令牌。
 * 但达标只存在于当时的源码快照，缺少持续守护，后续改动很容易重新写回 hex。
 *
 * 本文件把「零硬编码色」从一次性审计升级为可执行门禁：
 *   1. 源码（含 <style>）不得出现 hex 色值或 rgb()/rgba() 字面量
 *   2. 不得出现仅供 canvas 使用的 resolveToken 取色包装函数
 *      （本视图没有任何 canvas 绘图，TIER_TOKEN/heatToken 直接交给 CSS 即可；
 *        历史上 tierColorResolved(0) 被当作「常量主色」误用，heatColorResolved
 *        则从头到尾没有调用方 —— 两者都以硬编码 fallback 的形式藏了色值）
 */
const viewPath = resolve(process.cwd(), 'src/views/MasteryMapView.vue')
const viewSrc = readFileSync(viewPath, 'utf-8')

// 去掉注释后再扫描，避免注释里的示例色值造成误报
const codeOnly = viewSrc
  .replace(/<!--[\s\S]*?-->/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/(^|[^:])\/\/.*$/gm, '$1')

describe('MasteryMapView 颜色令牌门禁', () => {
  it('源码（含 style）不含 hex 色值字面量', () => {
    const hexes = codeOnly.match(/#[0-9a-fA-F]{3,8}\b/g) || []
    expect(hexes).toEqual([])
  })

  it('源码（含 style）不含 rgb()/rgba() 字面量', () => {
    const rgbs = codeOnly.match(/\brgba?\s*\(/g) || []
    expect(rgbs).toEqual([])
  })

  it('不存在仅供 canvas 的 resolveToken 取色包装（本视图无 canvas）', () => {
    expect(codeOnly).not.toContain('resolveToken')
    expect(codeOnly).not.toContain('ColorResolved')
  })

  it('档位配色统一来自 TIER_TOKEN 的 CSS 变量', () => {
    // 四档令牌齐备，且以 var(--mastery-*) 形式交给样式层
    ;['high', 'mid', 'low', 'none'].forEach((tier) => {
      expect(viewSrc).toContain(`${tier}: 'var(--mastery-${tier})'`)
    })
  })
})
