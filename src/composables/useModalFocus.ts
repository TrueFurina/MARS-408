import { ref, nextTick, onBeforeUnmount, type Ref } from 'vue'

/**
 * 模态浮层焦点管理（WCAG 2.4.3 焦点顺序 / 2.1.1 键盘）。
 * 打开：记录触发元素（opener）→ 焦点移入容器（容器需 tabindex="-1"）；
 * Tab / Shift+Tab：在容器内可聚焦元素间循环，不外泄到背景；
 * 关闭 / 卸载：焦点归还 opener，用户不会"丢焦点"到 body。
 *
 * 纯原生实现，无第三方依赖；键盘事件由调用方模板/监听器转发 trapTab。
 */
const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function useModalFocus(container: Ref<HTMLElement | null>) {
  const opener = ref<HTMLElement | null>(null)

  /** 浮层打开时调用：记录 opener 并把焦点移入容器 */
  async function activate(): Promise<void> {
    opener.value = (document.activeElement as HTMLElement | null) ?? null
    await nextTick()
    container.value?.focus()
  }

  /** 浮层关闭时调用：焦点归还 opener（无 opener 时不动作） */
  function deactivate(): void {
    opener.value?.focus()
    opener.value = null
  }

  /**
   * Tab 圈闭：在 keydown 处理器里调用。
   * 容器内无焦点在册时先把焦点给首个可聚焦元素； Shift+Tab 于首元素→末元素、
   * Tab 于末元素→首元素，形成循环。
   */
  function trapTab(e: KeyboardEvent): void {
    const root = container.value
    if (!root) return
    const nodes = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
      .filter((n) => n.offsetParent !== null || n === document.activeElement)
    if (nodes.length === 0) {
      e.preventDefault()
      root.focus()
      return
    }
    const first = nodes[0]
    const last = nodes[nodes.length - 1]
    const current = document.activeElement as HTMLElement | null
    if (first && last) {
      if (!current || !root.contains(current)) {
        e.preventDefault()
        first.focus()
      } else if (e.shiftKey && current === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && current === last) {
        e.preventDefault()
        first.focus()
      }
    }
  }

  // 组件被直接销毁（如路由切换）时兜底归还，避免焦点丢到 body
  onBeforeUnmount(deactivate)

  return { activate, deactivate, trapTab }
}
