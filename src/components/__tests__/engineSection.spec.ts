import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import EngineSection from '@/components/EngineSection.vue'

// 防回归：EngineSection 收敛了 .engine-section/.engine-section-title/.engine-tag/.engine-desc
// 在 5 个文件的整组复制。核心契约：标题用真正 h2，tag/desc 条件渲染，正文走插槽。

describe('EngineSection 算法引擎区块', () => {
  it('标题渲染为真正的 h2（而非无语义 div）', () => {
    const w = mount(EngineSection, { props: { title: 'GoMARL 共识引擎' } })
    expect(w.find('h2').text()).toContain('GoMARL 共识引擎')
  })

  it('tag / desc 缺省时不渲染对应节点', () => {
    const w = mount(EngineSection, { props: { title: 'A' } })
    expect(w.find('.engine-tag').exists()).toBe(false)
    expect(w.find('p').exists()).toBe(false)
  })

  it('tag 与 desc 传入时渲染', () => {
    const w = mount(EngineSection, {
      props: { title: 'A', tag: '实时状态', desc: '说明文字' },
    })
    expect(w.find('.engine-tag').text()).toBe('实时状态')
    expect(w.find('p').text()).toBe('说明文字')
  })

  it('icon 插槽渲染在标题内', () => {
    const w = mount(EngineSection, {
      props: { title: 'A' },
      slots: { icon: '<svg></svg>' },
    })
    expect(w.find('.engine-icon svg').exists()).toBe(true)
  })

  it('iconAccent 控制图标是否用强调色（默认不用）', () => {
    expect(mount(EngineSection, { props: { title: 'A' } }).find('.engine-icon--accent').exists()).toBe(false)
    expect(
      mount(EngineSection, { props: { title: 'A', iconAccent: true } }).find('.engine-icon--accent').exists(),
    ).toBe(true)
  })

  it('正文走默认插槽', () => {
    const w = mount(EngineSection, {
      props: { title: 'A' },
      slots: { default: '<div class="result">结果</div>' },
    })
    expect(w.find('.result').text()).toBe('结果')
  })

  it('外层是玻璃态卡片（padding 走 --space-6 令牌，无裸值）', () => {
    const w = mount(EngineSection, { props: { title: 'A' } })
    const style = w.find('.glass-card').attributes('style') ?? ''
    expect(style).toContain('var(--space-6)')
    expect(style).not.toMatch(/\d+(\.\d+)?(px|rem)/)
  })
})
