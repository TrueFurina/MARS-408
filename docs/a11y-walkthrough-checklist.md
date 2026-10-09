# 前端可访问性走查清单（a11y Walkthrough Checklist）

> 生成日期：2026-10-09 · 状态：冻结期审计（仅物料/文档，不改 `src/`）
> 配套工具：`scripts/a11y_scan.py`（硬门禁 + `--audit` 咨询级审计）
> 适用分支：`career-literacy` · 国创赛「可访问性」证据页数据源

---

## 0. 门禁与审计分级

| 档位 | 命令 | 退出码 | 是否阻断 CI | 说明 |
|------|------|--------|-------------|------|
| 硬门禁 | `python scripts/a11y_scan.py` | 发现按钮无可读名→1，否则 0 | ✅ 阻断 | 图标按钮缺 `aria-label`/`title` |
| 硬门禁+链接 | `... --strict` | 同上，增查 `<a>` 空文本 | ✅ 阻断 | 同上 |
| 深度审计 | `... --audit` | **恒为 0**（report-only） | ❌ 不阻断 | 下列 4 类咨询级检测 |

**设计原则**：硬门禁窄而精确（宁可漏报不误报），当前 `src/**/*.vue` **0 缺陷**、`[PASS]`。
深度审计为**静态初筛**，可能含误报（如全局守卫或运行时处理），需人工走查确认；待 10-28 窗口后可将成熟规则提升为硬门禁。

---

## 1. 审计实测结果（2026-10-09 实跑）

| 类别 | 命中数 | WCAG 条款 | 含义 |
|------|--------|-----------|------|
| **A** 浮层/沙箱焦点管理 | **6** | 2.4.3 焦点顺序 | 模态/沙箱打开后焦点未 trapped，Esc 未必能关 |
| **B** 流式输出 `aria-live` | **8** | 4.1.3 状态消息 | LLM 流式增量对读屏不可感知 |
| **C** 自定义可点击键盘可达 | **9** | 2.1.1 键盘 | `role="button"` / `<div @click>` 仅鼠标可达 |
| **D** `prefers-reduced-motion` 守卫 | **19** | 2.3.3 动画交互 | 含 `@keyframes`/`animation` 但无减弱动画守卫 |

> 注：`SandboxView.vue` 因文件内已含焦点信号被 A 类**正确排除**（非漏报）；`EmptyState`/`ErrorBoundary`/`ExperimentEvidenceView` 已含 `aria-live`，故不计入 B 类。

---

## 2. 逐类走查明细与修复指引

### A 类 — 浮层 / 沙箱焦点管理（WCAG 2.4.3）· 6 项

| 文件 | 疑点 | 修复建议 |
|------|------|----------|
| `components/MultimodalCard.vue` | 浮层无 focus-trap / `.focus()` | 打开时把焦点移入浮层首个可聚焦元素，关闭时归还触发元素 |
| `components/PdfReader.vue` | 同上 | 同上；PDF 阅读器需支持方向键翻页 + 焦点可见 |
| `components/ToastNotification.vue` | 同上 | Toast 若是可交互的需可聚焦；纯提示用 `role="status"` 即可 |
| `components/VideoPlayer.vue` | 同上 | 播放器控件需可 Tab 到达 + 焦点环可见 |
| `views/CodeLabView.vue` | WASM 沙箱（C 编译 playground） | 沙箱打开后焦点应进入编辑器/终端；Esc 关闭 |
| `views/LandingView.vue` | 含 `<teleport>` 浮层 | teleport 内容需独立管理焦点 |

**通用修复模板**：
```vue
<template>
  <div role="dialog" aria-modal="true" aria-label="标题" @keydown.esc="close" ref="dialog">
    <!-- 内容 -->
  </div>
</template>
<script setup>
import { onMounted, ref, nextTick } from 'vue'
const dialog = ref(null)
const prevFocus = ref(null)
onMounted(async () => {
  prevFocus.value = document.activeElement
  await nextTick()
  dialog.value?.querySelector('[autofocus],button,a,input,select,textarea')?.focus()
})
function close() { /* ... */; prevFocus.value?.focus() }
</script>
```
> 或引入轻量 `focus-trap` 库（注意 WASM Worker 内不可用，须在宿主 DOM 侧处理）。

### B 类 — 流式输出 `aria-live`（WCAG 4.1.3）· 8 项

| 文件 | 说明 |
|------|------|
| `components/ChatInput.vue` | 输入框状态/发送反馈 |
| `views/ChatView.vue` | **核心**：LLM 逐字流式回复区无 `aria-live`，读屏用户收不到增量 |
| `views/DashboardView.vue` | 含流式/增量内容 |
| `views/DesignUpgradeView.vue` | 含流式内容 |
| `views/EngineView.vue` | 引擎状态流式 |
| `views/ResourceView.vue` | 资源加载流式 |
| `views/ShowcaseView.vue` | 展示流 |
| `views/SkillDetailView.vue` | 技能详情流式 |

**修复建议**（ChatView 为最高优先）：
```vue
<!-- 流式回复容器 -->
<div aria-live="polite" aria-atomic="false" role="log">
  <!-- 增量渲染的 Markdown / 文本 -->
</div>
```
> `aria-live="polite"` 不抢读屏焦点；对纯日志用 `role="log"`；高频流式建议节流播报，避免刷屏。

### C 类 — 自定义可点击键盘可达（WCAG 2.1.1）· 9 项

| 文件 | 说明 |
|------|------|
| `components/MoreMenu.vue` | 更多菜单触发 |
| `components/ProfilePanel.vue` | 资料面板项 |
| `components/VideoPlayer.vue` | 播放器自定义控件 |
| `views/CreatorDashboardView.vue` | 创作者面板 |
| `views/DesignSystemView.vue` | 设计系统演示（自身即反例） |
| `views/DesignUpgradeView.vue` | 升级页 |
| `views/LandingView.vue` | 落地页 |
| `views/PracticeView.vue` | 练习页 |
| `views/SkillStudioView.vue` | 技能工作室 |

**修复建议**：`role="button"` 的元素补 `@keydown.enter/@keydown.space` + `tabindex="0"`；`<div @click>` 改用 `<button>` 或至少补齐键盘等价事件。

### D 类 — `prefers-reduced-motion` 守卫（WCAG 2.3.3）· 19 项

> 含 `@keyframes`/`animation` 的组件，应在全局或本文件提供减弱动画守卫。已有 8 处文件级守卫（如 `App.vue` 外的全局规则可能覆盖部分），需逐文件确认。

**最高优先（动画明显、用户必见）**：
`VideoPlayer.vue`、`KnowledgeGraphView.vue`、`LangGraphFlow.vue`、`GOMARLPanel.vue`、`LoginView.vue`、`LandingView.vue`、`ChatView.vue`、`TcpHandshakeAnimation`（动画组件）等。

**修复建议**（全局统一最省事，推荐放在 `assets/styles/` 全局层）：
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
}
```
> 若已有全局守卫，D 类多数可标记为「已覆盖」；逐项确认即可，无需逐文件改。

---

## 3. 人工走查勾选表（评审用）

| # | 检查项 | WCAG | 状态 | 备注 |
|---|--------|------|------|------|
| 1 | 所有图标按钮有 `aria-label`/`title` | 4.1.2 | ✅ 已门禁保证 | 硬门禁 0 缺陷 |
| 2 | 模态/沙箱打开后焦点 trapped，Esc 可关 | 2.4.3 | ⬜ 待走查 A 类 6 项 | |
| 3 | LLM 流式输出声明 `aria-live` | 4.1.3 | ⬜ 待走查 B 类 8 项 | ChatView 优先 |
| 4 | 自定义可点击元素键盘可达 | 2.1.1 | ⬜ 待走查 C 类 9 项 | |
| 5 | 动画组件提供 reduced-motion 守卫 | 2.3.3 | ⬜ 待走查 D 类 19 项 | 先确认全局守卫覆盖 |
| 6 | 颜色对比度（玻璃拟态深底）达标 AA | 1.4.3 | ⬜ 待用 axe/Lighthouse 实测 | 见设计令牌报告 |
| 7 | 表单标签与输入关联 | 1.3.1 | ⬜ 待走查 | |
| 8 | 图片/图标有 `alt` 或 `role="img"`+`aria-label` | 1.1.1 | ⬜ 待走查 | |

---

## 4. 冻结期处置建议

- **现在（10-28 前）**：本清单与 `scripts/a11y_scan.py --audit` 已就位，可作为国创赛「可访问性」证据页的**过程证据**；不改动 `src/`。
- **10-28 窗口**：将 A/B/C 中确认的真实缺口并入修复；D 类优先落地**全局** reduced-motion 守卫（一处覆盖多数）。
- **提升为硬门禁**：A 类（浮层焦点）误报率低、价值高，可率先提升为 `exit 1`；B/C 先保留咨询级直至修复完成。
