import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Skeleton from '@/components/Skeleton.vue'
import EmptyState from '@/components/EmptyState.vue'

// 防回归：这两个组件是全库复用最广的基础设施（Skeleton 12 处 / EmptyState 15 处），
// 它们的 a11y 契约一旦被改坏，会同时影响十几个页面且不易察觉。
// 本文件是前端第一批组件测试（此前 7 个测试全在 utils/，组件测试为 0）。

describe('Skeleton 骨架屏 · a11y 契约', () => {
  it('单块变体：暴露 role=status + aria-busy，供读屏播报加载中', () => {
    const w = mount(Skeleton, { props: { variant: 'card' } })
    const root = w.get('.skeleton')
    expect(root.attributes('role')).toBe('status')
    expect(root.attributes('aria-busy')).toBe('true')
  })

  it('aria-label 默认「加载中」，且可被 label prop 覆盖', () => {
    expect(mount(Skeleton).get('.skeleton').attributes('aria-label')).toBe('加载中')
    expect(
      mount(Skeleton, { props: { label: '正在生成题目' } }).get('.skeleton').attributes('aria-label'),
    ).toBe('正在生成题目')
  })

  it('variant 映射为 skeleton-{variant} 类名', () => {
    expect(mount(Skeleton, { props: { variant: 'chart' } }).get('.skeleton').classes()).toContain(
      'skeleton-chart',
    )
  })

  it('多行文本：渲染 count 个条，且末行收窄到 60%', () => {
    const w = mount(Skeleton, { props: { variant: 'text', count: 3 } })
    const bars = w.findAll('.skeleton-text')
    expect(bars).toHaveLength(3)
    expect(bars[0].attributes('style')).toContain('100%')
    expect(bars[2].attributes('style')).toContain('60%')
  })

  it('count=1 时不走 stack 分支（避免多余嵌套）', () => {
    const w = mount(Skeleton, { props: { variant: 'text', count: 1 } })
    expect(w.find('.skeleton-stack').exists()).toBe(false)
  })
})

describe('EmptyState 空状态 · a11y 契约', () => {
  it('暴露 role=status + aria-live=polite，数据到达时读屏可感知', () => {
    const root = mount(EmptyState).get('.nl-empty')
    expect(root.attributes('role')).toBe('status')
    expect(root.attributes('aria-live')).toBe('polite')
  })

  it('title 默认「暂无数据」，可被覆盖；description 缺省时不渲染', () => {
    expect(mount(EmptyState).get('.nl-empty-title').text()).toBe('暂无数据')
    expect(
      mount(EmptyState, { props: { title: '还没有错题' } }).get('.nl-empty-title').text(),
    ).toBe('还没有错题')
    expect(mount(EmptyState).find('.nl-empty-desc').exists()).toBe(false)
  })

  it('传入 description 时渲染描述文案', () => {
    const w = mount(EmptyState, { props: { description: '先去做一套练习吧' } })
    expect(w.get('.nl-empty-desc').text()).toBe('先去做一套练习吧')
  })

  it('action 插槽：未传时不渲染容器，传入时渲染', () => {
    expect(mount(EmptyState).find('.nl-empty-actions').exists()).toBe(false)
    const w = mount(EmptyState, { slots: { action: '<button>去练习</button>' } })
    expect(w.get('.nl-empty-actions').text()).toBe('去练习')
  })

  it('accent 默认取品牌主色令牌，而非硬编码色值', () => {
    // 设计系统铁律：组件只引语义令牌，禁止裸 hex
    const w = mount(EmptyState, { props: { icon: '<svg></svg>' } })
    const style = w.get('.nl-empty-icon').attributes('style') ?? ''
    expect(style).toContain('var(--accent-primary)')
    expect(style).not.toMatch(/#[0-9a-fA-F]{3,8}/)
  })
})
