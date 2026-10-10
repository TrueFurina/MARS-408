/**
 * 运行时主题令牌解析工具
 * ----------------------------------------------------------------
 * 设计系统的颜色唯一真值源是 _variables.css 的语义层变量（--color-* / --subject-* /
 * --accent-* 等）。DOM/CSS 上下文直接用 var(--token) 即可跟随主题，无需本工具。
 *
 * 但 canvas / SVG 绘制上下文（ctx.fillStyle、ctx.strokeStyle、SVG stop-color 属性）
 * 无法解析 CSS 变量，必须先把变量当前实际值取出来。本工具用 getComputedStyle 读取
 * :root 上的变量值并提供缓存，供 canvas 组件在绘制时取用，从而让 canvas 绘制的颜色
 * 也对齐 SSOT（而非写死 hex/rgba）。
 *
 * 注意：
 * - 颜色在 initGraph/draw 时按当前主题解析一次并缓存；若运行时切换主题，调用
 *   clearTokenCache() 后重绘即可取到新主题色（见 App.vue 主题切换）。
 * - 本工具仅用于 canvas/SVG 这类无法写 var() 的上下文；DOM 内联 style 应直接写
 *   'var(--token)'，更省事且天然跟随主题。
 */

let cache: Record<string, string> = {}

function rootEl(): HTMLElement | null {
  if (typeof document === 'undefined') return null
  return document.documentElement
}

/**
 * 读取 CSS 变量当前实际值（带缓存）。fallback 用于无 DOM / 变量未定义场景。
 * 入参可写 'var(--x)' 形式（如直接喂 masteryColor() 的返回值），会自动提取变量名。
 */
export function resolveToken(name: string, fallback = ''): string {
  const key = name.startsWith('var(')
    ? name.slice(4, -1).trim()
    : name.startsWith('--')
      ? name
      : name // 已是裸值（如 #7c6af2）直接作为缓存键
  if (cache[key] !== undefined) return cache[key]
  const el = rootEl()
  if (!el || typeof getComputedStyle === 'undefined') return fallback
  const value = getComputedStyle(el).getPropertyValue(key).trim()
  const resolved = value || fallback
  cache[key] = resolved
  return resolved
}

/**
 * 把 hex / rgb(a) 字符串转成带 alpha 的 rgba()，用于 canvas 半透明绘制。
 * 非法输入原样返回，避免绘制异常。
 */
export function withAlpha(color: string, alpha: number): string {
  const c = color.trim()
  const rgbMatch = c.match(/rgba?\(([^)]+)\)/)
  if (rgbMatch) {
    const inner = rgbMatch[1] ?? ''
    const parts = inner.split(/[,\s/]+/).filter(Boolean)
    const [r = '0', g = '0', b = '0'] = parts
    return `rgba(${r}, ${g}, ${b}, ${alpha})`
  }
  const hex = c.replace('#', '')
  const full = hex.length === 3 ? hex.split('').map(x => x + x).join('') : hex
  if (full.length < 6) return c
  const r = parseInt(full.slice(0, 2), 16)
  const g = parseInt(full.slice(2, 4), 16)
  const b = parseInt(full.slice(4, 6), 16)
  if ([r, g, b].some(Number.isNaN)) return c
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

/**
 * 主题切换 / 变量热更新时清空缓存，使下一次绘制重新读取当前主题色。
 */
export function clearTokenCache(): void {
  cache = {}
}
