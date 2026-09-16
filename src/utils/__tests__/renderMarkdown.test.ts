import { describe, it, expect } from 'vitest'
import { renderMarkdown, sanitizeSvg } from '@/utils/markdown'

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

// 防回归：MultimodalCard 对 LLM 生成的 imageSvg 必须用 sanitizeSvg 净化后再 v-html，
// 否则 prompt injection 可注入 <script>/onload 事件造成 XSS（P0-2，2026-09-16 修复）。
describe('sanitizeSvg 净化 LLM 生成 SVG', () => {
  it('剥离 <script> 与事件处理器（防 XSS）', () => {
    const evil = '<svg><script>alert(1)</script><rect onload="alert(2)" onclick="x()"/></svg>'
    const out = sanitizeSvg(evil)
    expect(out).not.toContain('<script')
    expect(out).not.toContain('onload')
    expect(out).not.toContain('onclick')
    // 合法 SVG 图形结构应保留（注：happy-dom 的 DOMPurify 会丢弃 <svg> 根包装，
    // 这是测试环境特性；浏览器中根元素会被保留。此处验证危险内容已移除即可。）
    expect(out).toContain('<rect')
  })

  it('保留合法 SVG 图形元素', () => {
    const good = '<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="40"/></svg>'
    const out = sanitizeSvg(good)
    expect(out).toContain('<circle')
    expect(out).toContain('cx="50"')
  })

  it('空/非 SVG 输入不引入可执行内容', () => {
    expect(sanitizeSvg('')).toBe('')
    const out = sanitizeSvg('not an svg')
    expect(out).not.toContain('<script')
    expect(out).not.toContain('onload')
    expect(out).not.toContain('onclick')
  })

  it('foreignObject 这类可承载 HTML 的容器被剥离', () => {
    const evil =
      '<svg><foreignObject><body xmlns="http://www.w3.org/1999/xhtml"><script>alert(1)</script></body></foreignObject></svg>'
    const out = sanitizeSvg(evil)
    expect(out).not.toContain('<script')
    expect(out).not.toContain('foreignObject')
  })
})
