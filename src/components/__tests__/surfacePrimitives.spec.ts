import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import GlassCard from '@/components/GlassCard.vue'
import SectionHeader from '@/components/SectionHeader.vue'

// 防回归：这两个组件为消灭 .glass-card(4 文件) 与 .engine-section-title/desc(5 文件)
// 的复制粘贴而建。GlassCard 的核心是 padding 只走 --space-N；
// SectionHeader 的核心是把原本无语义的 div 标题升级为真正的 h2/h3/h4。

describe('GlassCard 玻璃态卡片', () => {
  it('padding 走 --space 令牌，绝不产生裸值', () => {
    const w = mount(GlassCard, { props: { padding: 6 } })
    expect(w.attributes('style')).toContain('var(--space-6)')
    const style = w.attributes('style') ?? ''
    expect(style).not.toMatch(/\d+(\.\d+)?(px|rem)/)
  })

  it('默认 radius=md，可切换档位', () => {
    expect(mount(GlassCard).classes()).toContain('glass-card--radius-md')
    expect(mount(GlassCard, { props: { radius: 'lg' } }).classes()).toContain('glass-card--radius-lg')
  })

  it('hoverable / section 默认关闭，需显式开启', () => {
    const w = mount(GlassCard)
    expect(w.classes()).not.toContain('glass-card--hover')
    expect(w.classes()).not.toContain('glass-card--section')
    const on = mount(GlassCard, { props: { hoverable: true, section: true } })
    expect(on.classes()).toContain('glass-card--hover')
    expect(on.classes()).toContain('glass-card--section')
  })

  it('渲染插槽内容', () => {
    expect(mount(GlassCard, { slots: { default: '<span>内容</span>' } }).text()).toBe('内容')
  })

  it('透传 class 与 style（便于叠加业务类）', () => {
    const w = mount(GlassCard, { attrs: { class: 'engine-enter', style: 'animation-delay:0.07s' } })
    expect(w.classes()).toContain('engine-enter')
  })
})

describe('SectionHeader 区块标题', () => {
  it('默认渲染 h2 —— 修复原本用 div 导致的标题无语义', () => {
    const w = mount(SectionHeader, { props: { title: '算法引擎' } })
    expect(w.element.tagName).toBe('HEADER')
    expect(w.find('h2').exists()).toBe(true)
    expect(w.find('h2').text()).toBe('算法引擎')
  })

  it('level 可切换为 h3 / h4', () => {
    expect(mount(SectionHeader, { props: { level: 3, title: 'a' } }).find('h3').exists()).toBe(true)
    expect(mount(SectionHeader, { props: { level: 4, title: 'a' } }).find('h4').exists()).toBe(true)
    expect(mount(SectionHeader, { props: { level: 3, title: 'a' } }).find('h2').exists()).toBe(false)
  })

  it('#title 插槽可塞图标等富内容，优先级高于 title prop', () => {
    const w = mount(SectionHeader, {
      props: { title: '纯文本' },
      slots: { title: '<svg></svg>带图标' },
    })
    expect(w.find('h2').text()).toContain('带图标')
  })

  it('description 缺省时不渲染 <p>，避免空节点', () => {
    expect(mount(SectionHeader, { props: { title: 'a' } }).find('p').exists()).toBe(false)
    const w = mount(SectionHeader, { props: { title: 'a', description: '说明' } })
    expect(w.find('p').text()).toBe('说明')
  })

  it('#description 插槽可用', () => {
    const w = mount(SectionHeader, {
      props: { title: 'a' },
      slots: { description: '<strong>粗体</strong>说明' },
    })
    expect(w.find('p').text()).toContain('说明')
  })
})
