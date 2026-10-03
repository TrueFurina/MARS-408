import { describe, it, expect } from 'vitest'
import { renderMarkdown } from '@/utils/markdown'

// 防回归：renderMarkdown 是对话/资源内容渲染的唯一真相源。
// 必须正确渲染标题/粗体/代码块，且未闭合代码块自动补全。
describe('renderMarkdown 渲染', () => {
  it('渲染标题与粗体/斜体', () => {
    const html = renderMarkdown('# 标题\n\n**粗体** 和 *斜体*')
    expect(html).toContain('<h1>标题</h1>')
    expect(html).toContain('<strong>粗体</strong>')
    expect(html).toContain('<em>斜体</em>')
  })

  it('渲染代码块并带复制按钮', () => {
    const html = renderMarkdown('```python\nprint("hi")\n```')
    expect(html).toContain('code-block-wrapper')
    expect(html).toContain('data-action="copy"')
    expect(html).toContain('hljs')
    expect(html).toContain('print')
  })

  it('未闭合代码块自动补全（防 markdown 解析错乱）', () => {
    const html = renderMarkdown('```python\nprint(1)')
    // 补全后应能渲染出代码块而不是原始文本
    expect(html).toContain('code-block-wrapper')
    expect(html).toContain('print')
  })

  it('空字符串安全返回', () => {
    expect(renderMarkdown('')).toBe('')
  })
})
