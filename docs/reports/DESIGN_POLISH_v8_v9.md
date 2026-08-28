# 竞赛级 UI 精修令牌规范（v8→v9 polish）

> 消费对象：原型构建师 · 真相源：`src/assets/styles/_variables.css` · 组件：`src/components/`
> 原则：在现有 v8 玻璃态发光系统（语义变量 `--color-*`/`--accent-*`/`--subject-*` + 双主题）之上做特等奖级抛光，只补强、统一、修裸值，不破坏语义体系。

## 1. 精修总纲
定位：**在现有 v8 之上做特等奖级抛光，不重建、不破坏现有语义变量体系**。所有新增令牌复用现有命名风格（`--accent-*`/`--color-*`/刻度 `--radius-*`/`--shadow-*`），双主题（`[data-theme="light"]`）自动跟随。

## 2. 新增/补强令牌清单
```css
/* 流式输出 */
--cursor-color: var(--accent-primary);          /* 打字光标色 */
--cursor-blink: 1.1s;                            /* blink 节奏 */
--thinking-bg: color-mix(in srgb, var(--accent-primary) 8%, var(--color-surface)); /* 思考气泡底 */
--stream-fade: 200ms;                            /* 逐字渐显 duration */

/* 微交互节奏（复用已有 --duration-fast150 / --duration-normal300 / --duration-slow500） */
--ease-standard: cubic-bezier(0.4,0,0.2,1);
--ease-out:      cubic-bezier(0.16,1,0.3,1);
--ease-bounce:   cubic-bezier(0.34,1.56,0.64,1);

/* 可达性 */
--focus-ring: 0 0 0 3px var(--accent-primary-20);          /* 统一 focus 环 */
--hover-glow-cap: var(--shadow-card-hover);                /* glass hover 发光上限（克制度约束） */
```
**AA 对比度**：正文 `--text-primary`（暗 #f8fafc / 亮 #1a1d2e）配 `--color-canvas` 已达 7:1；次级 `--text-secondary`（亮 #525a72 配白底 ≈4.8:1）仅作次文本，勿作正文。

## 3. 流式输出语言规范（评委第一眼）
全局唯一流式呈现语言，三件套：
- **思考气泡**：`background:var(--thinking-bg); border:1px solid var(--color-border); border-radius:var(--radius-md); padding:12px 16px;` 内含三点跳动 `dot`（`background:var(--accent-primary)`）。
- **打字机光标**：`display:inline-block; width:2px; height:1.1em; background:var(--cursor-color); margin-left:2px; animation:blink var(--cursor-blink) step-end infinite;` `@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}`。
- **逐字渐显**：`.stream-char{display:inline-block; opacity:0; transform:translateY(.3em); animation:charIn var(--stream-fade) var(--ease-out) forwards}` `@keyframes charIn{to{opacity:1; transform:none}}`。
- **长任务三阶段态**：排队中（Spinner + 文案「排队中」）→ 生成中（光标流式 + `RingProgress` 描边 `var(--gradient-progress)`、track `var(--color-border)`）→ 已完成（淡出气泡，常显内容）。文案统一：排队中 / 正在生成 / 已完成。

## 4. Markdown 渲染排版规范
全部用语义 token，禁裸值：
- 标题：h1/h2/h3 行高 1.2/1.3/1.4，下距 12/10/8px。
- 代码块：`background:var(--color-surface-2); border:1px solid var(--color-border); border-radius:var(--radius-sm);` 语言标签 `--text-muted`；滚动条 `var(--color-border)`。
- 行内代码：`background:var(--accent-primary-10); color:var(--accent-primary); border-radius:var(--radius-xs); padding:2px 6px;`。
- 表格：斑马纹 `tr:nth-child(even){background:var(--color-surface-hover)}`，边框 `var(--color-border)`。
- 引用：`border-left:3px solid var(--accent-primary); background:var(--accent-primary-10); padding:8px 12px; border-radius:var(--radius-sm);`。
- 链接 `color:var(--accent-primary)`；分割线 `border-top:1px solid var(--color-border)`；列表标记 `var(--accent-primary)`。

## 5. 多模态卡片统一容器规范
`MultimodalCard` 为唯一多模态容器。外壳：`border-radius:var(--radius-lg); box-shadow:var(--shadow-card); padding:20px; border:1px solid var(--color-border); background:var(--color-surface)`。子类型（图文/语音/视频/代码/思维导图）共用此壳，顶部 3px 类型色条（图文 `--subject-ds`、计网 `--subject-cn`、计组 `--subject-co`、OS `--subject-os`、语音 `--accent-tertiary`）。

**修复现有硬编码（MultimodalCard.vue 第 94/95/171/202 行 `rgba(99,102,241,x)` —— #6366f1 ≠ 品牌 #7c6af2，浅色白底必断且色相偏差）**：
```css
.mm-image-section, .mm-audio-section {
  background: color-mix(in srgb, var(--accent-primary) 8%, var(--color-surface));
  border: 1px solid color-mix(in srgb, var(--accent-primary) 16%, transparent);
  border-radius: var(--radius-md);
  padding: 16px;
}
.mm-spinner { border: 2px solid var(--accent-primary-20); border-top-color: var(--accent-primary); }
.mm-speak-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 12px var(--accent-primary-20); }
```

## 6. 三件套兜底规范
- **Skeleton**：`background:linear-gradient(90deg, var(--color-surface) 25%, var(--color-surface-hover) 37%, var(--color-surface) 63%); background-size:400% 100%; animation:shimmer 1.4s ease infinite;` `@keyframes shimmer{0%{background-position:100% 0}100%{background-position:-100% 0}}`（防白屏）。
- **EmptyState**：插画（svg，亮主题 opacity .35）+ `.card-title` 标题 + `--text-secondary` 描述 + `.btn.btn-soft` 动作。
- **ErrorBoundary**：`.error-bar{background:var(--accent-danger-10); border:1px solid var(--accent-danger-20); color:var(--text-danger); border-radius:var(--radius-md); padding:12px 16px;}`。
- 触发：每屏（Chat/Resource/Dashboard/LearningPath/Knowledge）加载/空/错至少覆盖其一。

## 7. 双主题自检清单
① MultimodalCard 的 4 处 `rgba(99,102,241,x)` 改 `color-mix`/`var(--accent-primary-*)`，否则浅色断裂且色偏。② 引用/行内代码/标签 tint 一律 `color-mix`，自动适配明暗。③ focus 环 `--focus-ring` 两主题均可见。④ `--text-secondary` 仅次文本，正文用 `--text-primary` 保 AA。⑤ hover 发光不超 `--hover-glow-cap`，浅色禁强彩光（已降级 `rgba(15,18,40,x)`）。

## 8. Anti-Slop / 特等奖红线
1. 禁裸 `rgba/hex`（含 #6366f1 近似品牌色亦违规），一律语义变量。
2. 禁卡片 hover `scale>1.02`（现有 1.02 即上限）。
3. 禁主色大面填充（仅按钮/激活态/细线）。
4. 禁 emoji 当图标主角（用 `lucide-vue-next` + `currentColor`）。
5. 禁白屏无兜底（每屏 Skeleton/EmptyState/ErrorBoundary 三选一）。
6. 禁流式输出无统一光标/思考气泡（防闪烁白屏感）。
7. 禁 MD 裸样式、禁各屏流式语言不一致。
