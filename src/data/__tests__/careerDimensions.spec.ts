import { describe, expect, it } from 'vitest'
import {
  CAREER_DIM_ORDER, careerDimRows, careerMissingDimText, careerPartialMissingDimText,
  isDemoClassName,
} from '@/data/careerDimensions'

describe('careerDimRows', () => {
  it('固定按 canonical 六维展开，缺失维度标 covered=false 而不是整列消失', () => {
    const rows = careerDimRows({ expression: 4, stress: 3 })
    expect(rows.map(r => r.key)).toEqual([...CAREER_DIM_ORDER])
    expect(rows).toHaveLength(6)
    const covered = rows.filter(r => r.covered).map(r => r.key)
    expect(covered).toEqual(['expression', 'stress'])
    // 缺失维度的 value 必须是 undefined（不是 0），否则会被读成「这维得了 0 分」
    expect(rows.find(r => r.key === 'presentation')?.value).toBeUndefined()
  })

  it('空/缺省入参按「六维全未覆盖」处理，不抛错', () => {
    expect(careerDimRows(null)).toHaveLength(6)
    expect(careerDimRows(undefined).every(r => !r.covered)).toBe(true)
    expect(careerDimRows({})).toHaveLength(6)
  })

  it('中文标签取自 CAREER_DIM_LABEL', () => {
    const rows = careerDimRows({ presentation: 5 })
    expect(rows.find(r => r.key === 'presentation')?.label).toBe('技术汇报')
  })
})

describe('careerMissingDimText', () => {
  it('缺失维度合并成「本场景未覆盖：…」，按 canonical 顺序列出', () => {
    const text = careerMissingDimText({ expression: 4, stress: 3, decompose: 2, collab: 3 })
    expect(text).toBe('本场景未覆盖：技术汇报、问题解决')
  })

  it('六维全有分时返回空串（调用方不渲染灰字）', () => {
    const full = Object.fromEntries(CAREER_DIM_ORDER.map(d => [d, 4]))
    expect(careerMissingDimText(full)).toBe('')
  })
})

describe('careerPartialMissingDimText', () => {
  it('完全无分返回空串，让调用方显示「—」而不是六维全未覆盖', () => {
    expect(careerPartialMissingDimText({})).toBe('')
    expect(careerPartialMissingDimText(null)).toBe('')
  })

  it('已有部分分数时列出缺失维度', () => {
    expect(careerPartialMissingDimText({ expression: 4 })).toBe(
      '本场景未覆盖：抗压应变、方案拆解、协作沟通、技术汇报、问题解决',
    )
  })
})

describe('isDemoClassName', () => {
  it('识别演示样例班（名称含「演示」）', () => {
    expect(isDemoClassName('演示样例班（非真实学生数据）')).toBe(true)
  })

  it('真实班不误杀', () => {
    expect(isDemoClassName('24信安1班')).toBe(false)
    expect(isDemoClassName('')).toBe(false)
    expect(isDemoClassName(null)).toBe(false)
  })
})
