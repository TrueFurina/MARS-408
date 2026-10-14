import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { useModalFocus } from './useModalFocus'

/** 测试宿主：把 composable 挂在真实 DOM 上（onBeforeUnmount 需组件上下文） */
const Harness = defineComponent({
  props: { withButtons: { type: Boolean, default: true } },
  setup(_props) {
    const box = ref<HTMLElement | null>(null)
    // 直接返回 API：vm 上天然带类型，无需 expose + 泛型断言
    return { box, ...useModalFocus(box) }
  },
  render() {
    return h(
      'div',
      { ref: 'box', tabindex: '-1', id: 'mf-modal' },
      this.withButtons
        ? [
            h('button', { id: 'mf-first' }, '第一个'),
            h('button', { id: 'mf-last' }, '最后一个'),
          ]
        : [h('span', '无按钮')]
    )
  },
})

function mountModal(withButtons = true) {
  return mount(Harness, { props: { withButtons }, attachTo: document.body })
}

function tabEvent(shiftKey = false): KeyboardEvent {
  return new KeyboardEvent('keydown', {
    key: 'Tab',
    shiftKey,
    bubbles: true,
    cancelable: true,
  })
}

describe('useModalFocus', () => {
  let opener: HTMLButtonElement

  beforeEach(() => {
    document.body.innerHTML = ''
    opener = document.createElement('button')
    // ⚠️ id 勿用 'opener'：happy-dom 会把元素 id 注册为 window 具名属性，
    // 而 window.opener 是只读 getter ⇒ 元素挂载即 TypeError（happy-dom 缺陷，非本实现问题）
    opener.id = 'mf-opener'
    opener.textContent = '打开'
    document.body.appendChild(opener)
  })

  it('activate：记录 opener 并把焦点移入容器', async () => {
    const w = mountModal()
    opener.focus()
    expect(document.activeElement).toBe(opener)
    await w.vm.activate()
    expect(document.activeElement).toBe(w.get('#mf-modal').element)
    w.unmount()
  })

  it('deactivate：焦点归还 opener（不丢焦点到 body）', async () => {
    const w = mountModal()
    opener.focus()
    await w.vm.activate()
    w.vm.deactivate()
    expect(document.activeElement).toBe(opener)
    w.unmount()
  })

  it('deactivate：无 opener（从未 activate）时不抛错', () => {
    const w = mountModal()
    expect(() => w.vm.deactivate()).not.toThrow()
    w.unmount()
  })

  it('trapTab：Tab 于末元素 → 循环回首元素（焦点不外泄）', async () => {
    const w = mountModal()
    const first = w.get('#mf-first').element as HTMLElement
    const last = w.get('#mf-last').element as HTMLElement
    await w.vm.activate()
    last.focus()
    const e = tabEvent(false)
    w.vm.trapTab(e)
    expect(document.activeElement).toBe(first)
    expect(e.defaultPrevented).toBe(true)
    w.unmount()
  })

  it('trapTab：Shift+Tab 于首元素 → 循环到末元素', async () => {
    const w = mountModal()
    const first = w.get('#mf-first').element as HTMLElement
    const last = w.get('#mf-last').element as HTMLElement
    await w.vm.activate()
    first.focus()
    const e = tabEvent(true)
    w.vm.trapTab(e)
    expect(document.activeElement).toBe(last)
    expect(e.defaultPrevented).toBe(true)
    w.unmount()
  })

  it('trapTab：焦点尚在容器外 → 先交给首个可聚焦元素', async () => {
    const w = mountModal()
    const first = w.get('#mf-first').element as HTMLElement
    await w.vm.activate()
    opener.focus()
    const e = tabEvent(false)
    w.vm.trapTab(e)
    expect(document.activeElement).toBe(first)
    expect(e.defaultPrevented).toBe(true)
    w.unmount()
  })

  it('trapTab：容器内无可聚焦元素 → 阻止默认并把焦点留在容器', async () => {
    const w = mountModal(false)
    const modal = w.get('#mf-modal').element as HTMLElement
    await w.vm.activate()
    const e = tabEvent(false)
    w.vm.trapTab(e)
    expect(e.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(modal)
    w.unmount()
  })

  it('trapTab：容器 ref 尚未就绪（null）时不抛错', () => {
    // 未挂载时不触发 onBeforeUnmount 警告路径，仅验证空 ref 安全
    const box = ref<HTMLElement | null>(null)
    const fn = () => {
      // 直接在无组件上下文调用：Vue 会 warn 但不应抛错——trapTab 必须先判空
      const { trapTab } = useModalFocus(box)
      trapTab(tabEvent())
    }
    expect(() => fn()).not.toThrow()
  })

  it('onBeforeUnmount 兜底：组件被销毁时归还焦点', async () => {
    const w = mountModal()
    opener.focus()
    await w.vm.activate()
    expect(document.activeElement).not.toBe(opener)
    w.unmount()
    expect(document.activeElement).toBe(opener)
  })
})