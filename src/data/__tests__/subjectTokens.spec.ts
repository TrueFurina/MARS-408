import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  SUBJECT_COLOR_TOKENS,
  SUBJECT_COLOR_FALLBACK,
  subjectColor,
  type SubjectKey,
} from '@/data/subjectTokens'

// ─────────────────────────────────────────────────────────────────────────────
// 锁定「规范学科键 → 设计令牌」单一真值源的契约。
// 该文件是为修复 P3（ProfilePanel 用短键 ds/cn/co/os 查表，恒匹配不上、
// 配色永远走 fallback）而建的；此测试防止将来有人再把键写回短套。
//
// 额外做**交叉验证**：令牌名必须在全局 _variables.css 里真实定义，
// 否则 var(--subject-xx) 会静默解析失败，页面表现为"没有颜色"。
// ─────────────────────────────────────────────────────────────────────────────

const CSS_PATH = resolve(
  process.cwd(),
  'src/assets/styles/_variables.css',
)
const css = readFileSync(CSS_PATH, 'utf-8')

const CANONICAL_KEYS: SubjectKey[] = [
  'data_structures',
  'computer_network',
  'computer_organization',
  'operating_system',
]

describe('subjectTokens 单一真值源', () => {
  it('四个规范学科键都有令牌映射，且键名就是后端归一化输出', () => {
    expect(Object.keys(SUBJECT_COLOR_TOKENS).sort()).toEqual([...CANONICAL_KEYS].sort())
  })

  it('令牌名必须是 var(--subject-*) 形式，不得写死色值', () => {
    for (const [, token] of Object.entries(SUBJECT_COLOR_TOKENS)) {
      expect(token).toMatch(/^var\(--subject-[a-z]+\)$/)
      // 不得出现 hex/rgba 字面量（那是把令牌当常量用）
      expect(token).not.toMatch(/#[0-9a-fA-F]{3,8}|rgba?\(/i)
    }
  })

  it('兜底色存在且不是 var(--subject-*)（避免与学科令牌混淆）', () => {
    expect(SUBJECT_COLOR_FALLBACK).toBe('var(--accent-primary)')
    expect(SUBJECT_COLOR_FALLBACK).not.toMatch(/^var\(--subject-/)
  })
})

describe('令牌名与全局 CSS 变量交叉验证', () => {
  it('每个令牌名都在 _variables.css 中真实定义', () => {
    const missing: string[] = []
    for (const [key, token] of Object.entries(SUBJECT_COLOR_TOKENS)) {
      const name = token.match(/var\((--[a-z-]+)\)/)?.[1]
      expect(name, `${key} 的令牌名应可解析`).toBeTruthy()
      // 形如 "--subject-ds:" 的定义行
      if (!new RegExp(`\\${name}\\s*:`).test(css)) {
        missing.push(`${key} → ${name}`)
      }
    }
    expect(missing, '以下令牌在 CSS 中未定义，页面会静默失色').toEqual([])
  })

  it('_variables.css 中四个 --subject-* 令牌都有非空值', () => {
    for (const name of ['--subject-ds', '--subject-cn', '--subject-co', '--subject-os']) {
      const m = css.match(new RegExp(`\\${name}\\s*:\\s*([^;]+);`))
      expect(m, `${name} 应有定义`).toBeTruthy()
      expect(m![1]!.trim().length).toBeGreaterThan(0)
    }
  })
})

describe('subjectColor() 取色函数', () => {
  it('规范键返回对应令牌', () => {
    expect(subjectColor('data_structures')).toBe('var(--subject-ds)')
    expect(subjectColor('computer_network')).toBe('var(--subject-cn)')
    expect(subjectColor('computer_organization')).toBe('var(--subject-co)')
    expect(subjectColor('operating_system')).toBe('var(--subject-os)')
  })

  it('短键 ds/cn/co/os 不再被识别（P3 缺陷的回归防线）', () => {
    // 历史上 ProfilePanel 用短键查表导致恒走 fallback；
    // 本函数只认规范键，短键一律兜底，杜绝"两套键都能用"的暧昧状态
    for (const legacy of ['ds', 'cn', 'co', 'os']) {
      expect(subjectColor(legacy)).toBe(SUBJECT_COLOR_FALLBACK)
    }
  })

  it('中文名/空值/未知键一律兜底，不做静默猜测', () => {
    expect(subjectColor('数据结构')).toBe(SUBJECT_COLOR_FALLBACK)
    expect(subjectColor('')).toBe(SUBJECT_COLOR_FALLBACK)
    expect(subjectColor(null)).toBe(SUBJECT_COLOR_FALLBACK)
    expect(subjectColor(undefined)).toBe(SUBJECT_COLOR_FALLBACK)
    expect(subjectColor('unknown_subject')).toBe(SUBJECT_COLOR_FALLBACK)
  })
})
