import { marked } from 'marked'
import hljs from 'highlight.js/lib/core'
import DOMPurify from 'dompurify'

// ── katex 延迟加载（仅当文本包含 LaTeX 公式时加载） ──
let _katexLoaded = false
async function ensureKatex() {
  if (_katexLoaded) return
  // 动态导入 katex CSS
  await import('katex/dist/katex.min.css')
  const { default: markedKatex } = await import('@sigodenjs/marked-katex-extension')
  marked.use(markedKatex({
    throwOnError: false,
    inlineTolerantNoSpace: true,
  }))
  _katexLoaded = true
}

function hasLatex(text: string): boolean {
  return /\$\$[\s\S]*?\$\$|\$[^\s$][^$]*\$|\\\\\(|\\\\\[/.test(text)
}

// 按需注册 highlight.js 语言（仅注册 408 考研场景高频使用的语言）
import python from 'highlight.js/lib/languages/python'
import c from 'highlight.js/lib/languages/c'
import cpp from 'highlight.js/lib/languages/cpp'
import java from 'highlight.js/lib/languages/java'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import xml from 'highlight.js/lib/languages/xml'
import sql from 'highlight.js/lib/languages/sql'
import yaml from 'highlight.js/lib/languages/yaml'
import markdown from 'highlight.js/lib/languages/markdown'
import go from 'highlight.js/lib/languages/go'
import rust from 'highlight.js/lib/languages/rust'
import plaintext from 'highlight.js/lib/languages/plaintext'

hljs.registerLanguage('python', python)
hljs.registerLanguage('c', c)
hljs.registerLanguage('cpp', cpp)
hljs.registerLanguage('java', java)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('sh', bash)
hljs.registerLanguage('json', json)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('yml', yaml)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('md', markdown)
hljs.registerLanguage('go', go)
hljs.registerLanguage('rust', rust)
hljs.registerLanguage('plaintext', plaintext)
hljs.registerLanguage('text', plaintext)

marked.setOptions({
  breaks: true,
  gfm: true,
  async: false,
})

// 自定义图片渲染器（缩放）
const imageRenderer = new marked.Renderer()
imageRenderer.image = function (token: any) {
  const src = token.href || ''
  const alt = token.text || ''
  return `<img src="${src}" alt="${alt}" style="max-width:100%;height:auto;border-radius:8px;margin:8px 0;" />`
}

export function renderMarkdown(text: string): string {
  // 检查是否包含 LaTeX，按需加载 katex
  if (hasLatex(text)) {
    ensureKatex().catch(() => {})
  }
  // 补全未闭合代码块
  const backtickCount = (text.match(/```/g) || []).length
  const safeText = backtickCount % 2 !== 0 ? text + '\n```' : text

  // 提取代码块
  const blocks: { code: string; lang: string; highlighted: string }[] = []
  const processed = safeText.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const idx = blocks.length
    const langName = lang || 'code'
    let highlighted = ''
    try {
      highlighted = hljs.highlight(code.trim(), lang ? { language: lang } : { language: 'plaintext' }).value
    } catch {
      highlighted = escapeHtml(code.trim())
    }
    blocks.push({ code: code.trim(), lang: langName, highlighted })
    return `%%CODEBLOCK_${idx}%%`
  })


  let html = ''
  try {
    const result = marked.parse(processed, { renderer: imageRenderer })
    html = typeof result === 'string' ? result : ''
  } catch {
    html = processed.replace(/\n/g, '<br>')
  }

  // 恢复代码块
  html = html.replace(/%%CODEBLOCK_(\d+)%%/g, (_, idx) => {
    const block = blocks[parseInt(idx)]
    if (!block) return ''
    const codeAttr = block.code.replace(/"/g, '&quot;').replace(/'/g, '&#39;')
    return `
<div class="code-block-wrapper">
  <div class="code-block-header">
    <span class="code-lang">${block.lang}</span>
    <div class="code-block-actions">
      <button class="code-action-btn" data-action="copy" data-code="${codeAttr}" title="复制代码">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
      </button>
      <button class="code-action-btn" data-action="download" data-code="${codeAttr}" data-lang="${block.lang}" title="下载代码">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
      </button>
    </div>
  </div>
  <pre><code class="hljs">${block.highlighted}</code></pre>
</div>`
  })

  return html
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

/**
 * DOMPurify sanitized markdown rendering.
 * Use this for all v-html bindings to prevent XSS attacks.
 */
export function renderMarkdownSafe(text: string): string {
  const html = renderMarkdown(text)
  return DOMPurify.sanitize(html, {
    ADD_TAGS: ['math', 'katex'],
    ALLOWED_ATTR: [
      'data-action', 'data-code', 'data-lang', 'class', 'id',
    ],
  })
}

/**
 * Sanitize SVG markup for safe inline rendering (功能④多模态导师答疑).
 *
 * ⚠️ 两层防御（defense-in-depth），原因各有：
 *
 * 1) DOMPurify 的 `USE_PROFILES:{ svg:true }` 会**放行** SVG 上下文中的 `<script>` 与
 *    `on*` 事件处理器（SVG 规范允许内联脚本，这是 DOMPurify 的已知行为，并非「默认已剥离」）。
 *    因此必须显式 FORBID 它们，否则净化形同虚设、LLM 生成的 SVG 可直接 XSS。
 *
 * 2) 实测发现：在 happy-dom 测试环境下 DOMPurify 行为不可靠——它会剥离 `<svg>` 根元素，
 *    却保留其内部的 `<script>`/`onload`/`onclick`（详见 tests/ 回归用例）。因此**仅依赖
 *    DOMPurify 无法在测试环境给出可信的净化保证**。
 *
 * 故先以「与运行环境无关」的针对性正则预清洗掉所有已知可执行载体（<script>、on* 事件、
 * 可承载 HTML 的 <foreignObject>、javascript: 协议 URI），再交给 DOMPurify 做 SVG 结构校验。
 * 两层叠加：浏览器中由 DOMPurify 兜底，测试环境（happy-dom）中由正则保证安全。
 */
const SVG_FORBIDDEN_TAGS = ['script', 'foreignObject']
const SVG_FORBIDDEN_ATTR = [
  'onload', 'onunload', 'onclick', 'ondblclick', 'onmousedown', 'onmouseup',
  'onmouseover', 'onmousemove', 'onmouseout', 'onfocus', 'onblur', 'onchange',
  'onsubmit', 'onreset', 'onkeydown', 'onkeyup', 'onkeypress', 'oninput',
  'oncontextmenu', 'onwheel', 'onerror', 'onabort', 'onanimationstart',
  'onanimationend', 'ontransitionend',
]

/**
 * 运行环境无关的预清洗：剥离 SVG 中所有已知可执行载体。
 * 只针对明确的危险模式，不破坏合法 SVG 图形属性（如 opacity、font-size 等均不匹配 on[a-z]+=）。
 */
function stripSvgExecutableVectors(input: string): string {
  let s = input
  // 1) <script>...</script> 及自闭合/空 <script .../>
  s = s.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
  s = s.replace(/<script\b[^>]*\/?>/gi, '')
  // 2) 所有 on* 事件处理器属性（双引号 / 单引号 / 无引号三种写法）
  s = s.replace(/\s+on[a-z]+\s*=\s*"[^"]*"/gi, '')
  s = s.replace(/\s+on[a-z]+\s*=\s*'[^']*'/gi, '')
  s = s.replace(/\s+on[a-z]+\s*=\s*[^\s>]+/gi, '')
  // 3) 可承载 HTML/脚本的 foreignObject 容器（含全部子节点）
  s = s.replace(/<foreignObject\b[^>]*>[\s\S]*?<\/foreignObject>/gi, '')
  s = s.replace(/<foreignObject\b[^>]*\/?>/gi, '')
  // 4) javascript: 协议 URI（点击执行）
  s = s.replace(/\s+(?:xlink:href|href)\s*=\s*"javascript:[^"]*"/gi, '')
  s = s.replace(/\s+(?:xlink:href|href)\s*=\s*'javascript:[^']*'/gi, '')
  return s
}

export function sanitizeSvg(svg: string): string {
  if (!svg || typeof svg !== 'string') return ''
  const preCleaned = stripSvgExecutableVectors(svg)
  return DOMPurify.sanitize(preCleaned, {
    USE_PROFILES: { svg: true, svgFilters: true },
    FORBID_TAGS: SVG_FORBIDDEN_TAGS,
    FORBID_ATTR: SVG_FORBIDDEN_ATTR,
  })
}
