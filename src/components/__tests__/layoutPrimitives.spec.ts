import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Stack from '@/components/Stack.vue'
import TagList from '@/components/TagList.vue'

// 防回归：Stack / TagList 是为了消灭 5 文件 × 2 种重复 flex 布局而建的 L2 组件。
// 它们最核心的契约是 **gap 只走 --space-N 令牌** —— 一旦允许裸值流入，
// 之前收敛掉的 28 组复制粘贴会以新的形式长回来。

describe('Stack 堆叠容器', () => {
  it('默认纵向堆叠，gap 走 --space-3 令牌', () => {
    const w = mount(Stack)
    expect(w.classes()).toContain('stack--column')
    expect(w.attributes('style')).toContain('var(--space-3)')
  })

  it('gap 档位数字映射为对应 space 令牌，绝不产生裸值', () => {
    expect(mount(Stack, { props: { gap: 1 } }).attributes('style')).toContain('var(--space-1)')
    expect(mount(Stack, { props: { gap: 6 } }).attributes('style')).toContain('var(--space-6)')
    const style = mount(Stack, { props: { gap: 4 } }).attributes('style') ?? ''
    expect(style).not.toMatch(/\d+(\.\d+)?(px|rem)/)
  })

  it('direction / align / justify / wrap 映射为对应类名', () => {
    const w = mount(Stack, {
      props: { direction: 'row', align: 'center', justify: 'between', wrap: true },
    })
    expect(w.classes()).toContain('stack--row')
    expect(w.classes()).toContain('stack--align-center')
    expect(w.classes()).toContain('stack--justify-between')
    expect(w.classes()).toContain('stack--wrap')
  })

  it('默认不换行（wrap 必须显式开启）', () => {
    expect(mount(Stack).classes()).not.toContain('stack--wrap')
  })

  it('渲染插槽内容', () => {
    expect(mount(Stack, { slots: { default: '<span>A</span>' } }).text()).toBe('A')
  })

  it('透传 aria 属性到根元素', () => {
    const w = mount(Stack, { attrs: { 'aria-label': '薄弱知识点列表' } })
    expect(w.attributes('aria-label')).toBe('薄弱知识点列表')
  })
})

describe('TagList 标签列表', () => {
  it('可换行且 gap 走令牌，不产生裸值', () => {
    const w = mount(TagList, { slots: { default: '<span>a</span>' } })
    expect(w.classes()).toContain('tag-list')
    const style = w.attributes('style') ?? ''
    expect(style).toContain('var(--space-2)')
    expect(style).not.toMatch(/\d+(\.\d+)?(px|rem)/)
  })

  it('gap 档位可配置', () => {
    const w = mount(TagList, { props: { gap: 1 }, slots: { default: '<span>a</span>' } })
    expect(w.attributes('style')).toContain('var(--space-1)')
  })

  it('list 模式渲染为 ul/li，利于读屏', () => {
    const w = mount(TagList, {
      slots: { default: '<span>数据结构</span><span>计组</span>' },
    })
    expect(w.element.tagName).toBe('UL')
    expect(w.findAll('li')).toHaveLength(2)
    expect(w.text()).toContain('数据结构')
  })

  it('group 模式渲染为 div + role=group', () => {
    const w = mount(TagList, {
      props: { as: 'group' },
      slots: { default: '<span>a</span>' },
    })
    expect(w.element.tagName).toBe('DIV')
    expect(w.attributes('role')).toBe('group')
  })

  it('label 作为整组标签的无障碍名称', () => {
    const w = mount(TagList, {
      props: { label: '涉及知识点' },
      slots: { default: '<span>a</span>' },
    })
    expect(w.attributes('aria-label')).toBe('涉及知识点')
  })
})
