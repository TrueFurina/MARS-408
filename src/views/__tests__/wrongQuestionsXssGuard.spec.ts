import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

// 防回归（P0 级 XSS）：WrongQuestionsView 的题目文本来自后端 API（可能由 LLM 生成，
// 不可信）。历史上它被裸用 `v-html="getQuestionText(q)"` 直接注入 HTML，存在 XSS 风险，
// 且违反项目「所有 v-html 必须净化」的统一纪律。此守护锁定：该绑定必须经 renderMarkdownSafe。
const viewSrc = readFileSync(resolve(process.cwd(), 'src/views/WrongQuestionsView.vue'), 'utf-8')

describe('WrongQuestionsView 题目文本渲染必须净化（防 XSS 回归）', () => {
  it('题目文本不得裸用 v-html 直插后端数据', () => {
    expect(viewSrc).not.toMatch(/v-html\s*=\s*"getQuestionText\(/)
  })

  it('题目文本经 renderMarkdownSafe 净化后渲染', () => {
    expect(viewSrc).toMatch(/v-html\s*=\s*"renderMarkdownSafe\(getQuestionText\(/)
  })
})
