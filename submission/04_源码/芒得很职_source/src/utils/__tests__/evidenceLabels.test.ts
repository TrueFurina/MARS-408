import { describe, it, expect } from 'vitest'
import {
  TYPE_LABEL, SEVERITY_COLOR, SEVERITY_LABEL,
  DISPOSITION_LABEL, DISPOSITION_COLOR, AGENT_LABEL,
} from '@/utils/evidence'

// 防回归：evidence 标签映射是 Agent 冲突检测展示的唯一真相源。
// 映射缺失时前端会直出英文 key（type/semantic 等），可读性差。
describe('evidence 冲突检测标签映射', () => {
  it('冲突类型 TYPE_LABEL 覆盖全部 3 类且中文正确', () => {
    expect(TYPE_LABEL).toMatchObject({
      semantic: '语义',
      factual: '事实',
      keyword: '关键词',
    })
    expect(Object.keys(TYPE_LABEL).length).toBe(3)
  })

  it('严重度 SEVERITY_LABEL 覆盖 high/medium/low', () => {
    expect(SEVERITY_LABEL).toMatchObject({
      high: '高危',
      medium: '中危',
      low: '低危',
    })
    // 每个严重度都有配色（防渲染时 undefined 样式）
    for (const k of Object.keys(SEVERITY_LABEL)) {
      expect(SEVERITY_COLOR[k]).toBeTruthy()
    }
  })

  it('处置类型 DISPOSITION_LABEL 覆盖 3 类且配色齐全', () => {
    expect(DISPOSITION_LABEL).toMatchObject({
      adopt: '采纳',
      reject: '否决',
      human_review: '人工复核',
    })
    for (const k of Object.keys(DISPOSITION_LABEL)) {
      expect(DISPOSITION_COLOR[k]).toBeTruthy()
    }
  })

  it('Agent 名 AGENT_LABEL 覆盖全部 7 个协作 Agent', () => {
    expect(Object.keys(AGENT_LABEL).length).toBeGreaterThanOrEqual(7)
    expect(AGENT_LABEL.teacher).toBe('讲解文档')
    expect(AGENT_LABEL.quiz).toBe('题库')
    expect(AGENT_LABEL.mindmap).toBe('思维导图')
  })

  it('所有映射值不含空串（防英文 key 直出）', () => {
    const maps = [TYPE_LABEL, SEVERITY_LABEL, DISPOSITION_LABEL, AGENT_LABEL]
    for (const m of maps) {
      for (const [k, v] of Object.entries(m)) {
        expect(v.trim(), `映射 ${k} 不应为空`).toBeTruthy()
        expect(v).not.toBe(k) // 值不应等于 key（说明未映射）
      }
    }
  })
})
