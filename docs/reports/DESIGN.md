# MARS-408 DESIGN.md

> 基于 `src/assets/styles/main.css` (v8) 沉淀的设计系统规范 · 语义化双主题（dark 默认 / light 可选）
> AI 可读：供 Cursor / Claude Code / Google Stitch 直接消费 · 参考 Linear / Stripe 仪表盘美学

---

## 1. Visual Theme & Atmosphere

- **设计哲学**：克制深色 · 玻璃态 · 学科分色 · 微交互。去"AI 感"，追求专业教育 SaaS 的冷静与精密。
- **视觉基调**：科技感、极简、纵深克制。暗色为底，彩色仅作信号（主色紫 + 408 四科分色）。
- **核心视觉特征**：`glassmorphism`（毛玻璃模糊）、`subject-colored`（学科语义着色）、`restrained-glow`（克制发光）、`micro-interaction`（位移/缩放微动效）。
- **光影与质感**：多层 box-shadow（深色抬升 + 彩色微光）为主；玻璃态用 `backdrop-filter: blur(12px)`；无渐变填充滥用，仅 hero / 进度条 / 激活态用渐变。

---

## 2. Color Palette & Roles

### 语义层（组件只引用此层；`[data-theme="light"]` 覆盖即可双主题）

| Token | Dark (默认) | Light | 角色 |
|-------|--------------|-------|------|
| `--color-canvas` | `#080812` | `#f5f6fb` | 页面底色 |
| `--color-surface` | `rgba(255,255,255,0.03)` | `#ffffff` | 卡片/玻璃表面 |
| `--color-surface-2` | `#0f0f1a` | `#eef0f6` | 侧栏/输入框底 |
| `--color-surface-hover` | `rgba(255,255,255,0.06)` | `#e7eaf3` | 悬停表面 |
| `--color-elevated` | `#1c1c2b` | `#ffffff` | 抬升层（Select/弹层） |
| `--color-overlay` | `rgba(0,0,0,0.55)` | `rgba(15,18,40,0.32)` | 遮罩 |
| `--color-glass` | `rgba(15,15,26,0.65)` | `rgba(255,255,255,0.72)` | 玻璃态底 |
| `--color-glass-border` | `rgba(255,255,255,0.08)` | `rgba(15,18,40,0.10)` | 玻璃态边框 |
| `--color-border` | `rgba(255,255,255,0.06)` | `rgba(15,18,40,0.10)` | 默认边框 |
| `--color-border-focus` | `rgba(124,106,242,0.45)` | `rgba(124,106,242,0.50)` | 聚焦/强调边框 |
| `--color-text` | `#f8fafc` | `#1a1d2e` | 主文本 |
| `--color-text-2` | `#94a3b8` | `#525a72` | 次文本 |
| `--color-text-3` | `#7c8aa0` | `#8a92a8` | 弱文本（标签/说明） |

### 品牌色（双主题恒定）

| Token | HEX | CSS 变量 | 使用场景 |
|-------|-----|----------|----------|
| 主色 · 紫 | `#7c6af2` | `--accent` / `--accent-primary` | 主按钮 / 活跃态 / 激活边栏 |
| 辅助 · 蓝 | `#5b8bd8` | `--accent-blue` / `--accent-secondary` | 渐变收尾 / 次级信号 |
| 青 | `#06b6d4` | `--accent-cyan` / `--accent-tertiary` | 渐变中点 / 信息 |
| 琥珀 | `#f59e0b` | `--accent-warm` | 警告 / 高亮 |
| 成功 | `#22c55e` | `--accent-success` | 通过 / 正向指标 |
| 危险 | `#ef4444` | `--accent-danger` | 错误 / 删除 / 校验失败 |
| 粉 | `#f472b6` | `--accent-pink` | 强调点缀 |

### 408 四科色（恒定，语义着色用 `color-mix`）

| 科目 | HEX | 变量 | 激活态用法 |
|------|-----|------|--------------|
| 数据结构 | `#8b5cf6` | `--subject-ds` | `color-mix(in srgb, var(--subject-ds) 14%, transparent)` |
| 计网 | `#3b82f6` | `--subject-cn` | 同上 14% tint |
| 计组 | `#06b6d4` | `--subject-co` | 同上 14% tint |
| 操作系统 | `#f472b6` | `--subject-os` | 同上 14% tint |

### 阴影与发光（Dark）

```css
--shadow-sm:   0 1px 2px rgba(0,0,0,0.30);
--shadow-md:   0 4px 12px rgba(0,0,0,0.35);
--shadow-lg:   0 8px 24px rgba(0,0,0,0.40);
--shadow-xl:   0 16px 40px rgba(0,0,0,0.45);
--shadow-card:         0 2px 8px rgba(0,0,0,0.25), 0 0 1px rgba(255,255,255,0.06);
--shadow-card-hover:   0 8px 24px rgba(0,0,0,0.35), 0 0 20px rgba(124,106,242,0.08);
--glow-primary: 0 0 20px rgba(124,106,242,0.15), 0 0 40px rgba(124,106,242,0.08);
```

---

## 3. Typography Rules

- **Font Family**：`-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif`；等宽 `'SF Mono', 'Fira Code', 'Consolas', monospace`（代码/数值）。
- **设计哲学**：中文用系统字体栈零加载；层级靠**字号 + 字重（500/600/700）+ 负字距**建立，不依赖颜色。数字/指标用 700 + `-0.5px` 收紧。

| 层级 | Size | Weight | Line Height | Letter Spacing | 用途 |
|------|------|--------|-------------|----------------|------|
| Display Hero | 32px | 700 | 1.1 | -0.8px | 首页 hero 标题 |
| H1 | 24px | 700 | 1.2 | -0.5px | 页面主标题 |
| H2 / Section | 20px | 700 | 1.3 | -0.3px | `.section-title` |
| H3 / Card | 16px | 600 | 1.4 | 0 | `.card-title` |
| Body | 14px | 400 | 1.6 | 0 | 正文 |
| Body Strong | 14px | 500 | 1.6 | 0 | 标签/强调 |
| Caption | 13px | 400 | 1.5 | 0 | 次文本 |
| Nano / Label | 12px | 500 | 1.4 | 0.2px | 徽章/说明 |

---

## 4. Component Stylings

### Buttons（标准系统 `.btn` + 变体；历史 `.engine-btn` / `.rag-btn` 已对齐）

```css
.btn { display:inline-flex; align-items:center; justify-content:center; gap:8px;
  font-size:14px; font-weight:600; line-height:1; padding:10px 20px;
  border-radius:var(--radius-md); border:1px solid transparent; cursor:pointer;
  transition:var(--transition); }
.btn-primary { background:var(--gradient-primary); color:#fff; }
.btn-primary:hover { opacity:0.92; transform:translateY(-1px);
  box-shadow:0 8px 20px rgba(124,106,242,0.25); }
.btn-secondary { background:var(--color-surface-hover); color:var(--color-text); border-color:var(--color-border); }
.btn-secondary:hover { background:var(--color-surface-2); border-color:var(--color-border-focus); }
.btn-ghost { background:transparent; color:var(--color-text-2); }
.btn-ghost:hover { background:var(--color-surface-hover); color:var(--color-text); }
.btn-soft { background:var(--accent-primary-10); color:var(--accent-primary); }
.btn-danger { background:rgba(239,68,68,0.10); color:var(--accent-danger); }
.btn-sm { padding:7px 14px; font-size:13px; border-radius:var(--radius-sm); }
.btn-lg { padding:13px 28px; font-size:15px; }
.btn-block { width:100%; }
.btn:disabled { opacity:0.5; cursor:not-allowed; transform:none !important; }
```

### Cards

```css
.card, .stat-card, .glass-card {
  padding:20px; border-radius:var(--radius-lg);
  background:var(--color-surface); border:1px solid var(--color-border);
  box-shadow:var(--shadow-card);
}
.card:hover, .stat-card:hover {
  border-color:transparent; transform:scale(1.02);
  box-shadow:var(--shadow-card-hover), 0 0 0 1px rgba(124,106,242,0.15);
}
```

### Inputs

```css
.rag-select, .answer-input, .conv-search-input {
  background:var(--bg-input); border:1px solid var(--color-border);
  border-radius:var(--radius-md); padding:10px 14px; color:var(--color-text);
  font-size:14px; transition:var(--transition);
}
.rag-select:focus, .answer-input:focus {
  border-color:var(--border-focus);
  box-shadow:0 0 0 3px var(--accent-primary-10);
}
::placeholder { color:var(--color-text-3); }
```

### Navigation（侧栏 `.nav-item`）

```css
.nav-item { display:flex; align-items:center; gap:12px; padding:11px 12px;
  border-radius:var(--radius-sm); color:var(--color-text-2); font-size:14px; font-weight:500; }
.nav-item:hover { background:var(--color-surface-hover); color:var(--color-text); }
.nav-item.active { background:var(--accent-primary-10); color:var(--accent-primary); }
.nav-item.active::before { content:''; position:absolute; left:0; top:50%; transform:translateY(-50%);
  width:3px; height:18px; border-radius:0 3px 3px 0;
  background:var(--gradient-primary); box-shadow:0 0 8px rgba(124,106,242,0.40); }
/* 学科色激活：.nav-item.active.nav-subject-0/1/2/3 → 对应 --subject-* */
```

### Badges / Tags（双主题自适应，勿硬编码 rgba）

```css
.tag-purple { background:color-mix(in srgb, var(--subject-ds) 14%, transparent); color:var(--subject-ds); }
.tag-green  { background:color-mix(in srgb, var(--accent-success) 14%, transparent); color:var(--accent-success); }
.tag-primary{ background:var(--accent-primary-10); color:var(--accent-primary); }
/* 同构：.tag-blue/.tag-cyan/.tag-pink/.tag-warm → --subject-cn/co/os + --accent-warm */
```

### Modals / Drawers（`.panel-overlay` + 滑出面板）

```css
.panel-overlay { position:fixed; inset:0; background:var(--bg-overlay);
  z-index:900; opacity:0; pointer-events:none; transition:var(--transition-slow);
  backdrop-filter:blur(4px); }
.panel-overlay.open { opacity:1; pointer-events:auto; }
.profile-panel { position:fixed; top:0; right:0; bottom:0; width:400px; max-width:90vw;
  z-index:950; transform:translateX(100%); transition:transform var(--duration-slow) cubic-bezier(0.4,0,0.2,1);
  background:var(--glass-bg); backdrop-filter:blur(var(--glass-blur-heavy));
  border-left:1px solid var(--glass-border); box-shadow:var(--shadow-xl); }
.profile-panel.open { transform:translateX(0); }
```

---

## 5. Layout Principles

- **Spacing System**：基数 **4px**（实际组件多用 8/12/16/20/24 的 4 倍数）。建议新增 `--space-1`(4) ~ `--space-8`(32) 变量。
- **Grid System**：`.grid-4 { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; }`；平板(≤1024) → 2 列；小屏(≤480) → 1 列。
- **Container**：`.page-section { padding:24px 32px; max-width:1200px; margin:0 auto; }`。
- **App Shell**：左侧栏 `--sidebar-width:220px`（折叠 72px）+ 主区；移动端隐藏侧栏，顶栏(64px) + 底栏(64px) 接管。
- **留白哲学**：卡片内距 20px，区块间距 16-24px，列表项间距 4-12px。纵深靠阴影而非粗边框——边框保持 0.06-0.10 低存在感。

---

## 6. Depth & Elevation

- **Shadow System**（Dark → Light，见 §2 表格；Light 用 `rgba(15,18,40,x)` 柔和阴影替代深色投影）。
- **Surface Layers**：`--color-canvas`（底）→ `--color-surface-2`（侧栏/输入）→ `--color-elevated`（弹层）→ `--color-overlay`（遮罩）。
- **Z-index Scale**：sidebar `100` · conv-panel `300` · panel-overlay `900` · profile-panel `950` · tooltip `1000`。
- **Backdrop Effects**：玻璃态 `backdrop-filter: blur(var(--glass-blur))`（12px 标准 / 20px 重）；遮罩 `blur(4px)`。

---

## 7. Do's and Don'ts

**Do's**
1. 组件只引用语义层 `--color-*` / `--accent-*` / `--subject-*` 变量，禁止硬编码 `rgba`/`hex`（双主题会崩）。
2. 新按钮统一用 `.btn` + 变体（`.btn-primary` / `.btn-secondary` / `.btn-ghost` / `.btn-soft` / `.btn-danger`），勿新增散落按钮类。
3. 学科/状态着色用 `color-mix(in srgb, VAR 14%, transparent)`，自动适配明暗。
4. 圆角统一走 `--radius-*` 刻度（xs6 / sm10 / md14 / lg18 / xl24 / full）。
5. 层级用 `--shadow-*` 刻度，勿手写 box-shadow 散落值。
6. 间距优先 4 倍数（8/12/16/20/24）；卡片内距固定 20px。
7. 图标用 `currentColor` + `lucide-vue-next`，尺寸 18-22px，随文本色变化。

**Don'ts**
1. 勿直接写 `rgba(255,255,255,0.06)` 这类值到组件——改用 `--color-border` 等语义变量。
2. 勿新增 `.xxx-btn` 散落按钮类（历史 `.engine-btn`/`.rag-btn` 已对齐 `.btn`，新代码禁用）。
3. 勿用 `transform:scale()` 做卡片 hover 跳动感过强——当前 1.02 已是上限。
4. 勿在浅色主题下使用强发光 `box-shadow` 彩色投影——Light 已降级为柔和 `rgba(15,18,40,x)`。
5. 勿把主色 `#7c6af2` 用于大面填充（仅按钮/激活态/细线），大面积用 surface 层级。
6. 勿在中文字体栈里写非系统字体（零加载依赖是核心约束）。
7. 勿用 `!important` 覆盖（除 `.btn:disabled` 必要场景）；冲突请调整 specificity。

---

## 8. Responsive Behavior

| Breakpoint | 范围 | 行为 |
|-----------|------|------|
| Desktop | > 1024px | 侧栏(220px)常驻 + 顶栏隐藏 + 底栏隐藏 |
| Tablet | ≤ 1024px | 网格 4→2 列 |
| Mobile | ≤ 768px | 侧栏隐藏；顶栏(64px) + 底栏(64px) 接管；`.page-section` padding 收窄至 20/16 |
| Small | ≤ 480px | 网格 4→1 列；hero 标题 32→22px；输入区内距收窄 |

- **Touch Targets**：导航项 / 按钮最小高度 ≥ 44px（`.nav-item` 11+11+文本 ≈ 44；`.topbar-btn` 40px 略小，移动可放宽）。
- **折叠策略**：桌面侧栏 → 移动转顶栏汉堡 + 底栏 5 项 tab；对话历史桌面内联 → 移动全屏滑出(`width:100vw`)。
- **Font Scaling**：移动端 stat-value 30→24px、greeting 32→22px；其余层级保持，靠容器 padding 收窄适配。
- **主题跟随**：`[data-theme="light"]` 覆盖语义层；初始化 `localStorage > matchMedia(prefers-color-scheme) > dark`。

---

## 9. Agent Prompt Guide

### Quick Reference
MARS-408 设计系统 = 克制深色玻璃态 + 紫色主色(#7c6af2) + 408 四科分色(#8b5cf6/#3b82f6/#06b6d4/#f472b6)。**唯一真相源**：`src/assets/styles/main.css` 的 `--color-*` 语义变量。组件只引用变量，双主题(`:root` dark / `[data-theme="light"]`)自动适配。标准按钮 `.btn`，卡片 `.card`/`.glass-card`，标签 `.tag-*`，模态 `.panel-overlay`。

### Component Prompts（可直接复制给 AI 代理）
```
1. 生成一个主操作按钮：class="btn btn-primary"，文字"开始学习"，左侧加 lucide 'play' 图标，圆角用 --radius-md。
2. 生成一个资源卡片：外层 .card（padding 20px，radius-lg），内含 .card-header（标题+链接）、正文、底部 .tag-cyan 学科标签。
3. 生成一个学科筛选标签组：用 .tag-purple/.tag-blue/.tag-cyan/.tag-pink 表示数据结构/计网/计组/操作系统，背景用 color-mix 14% tint。
4. 生成一个错误提示条：class="engine-error"（红底 rgba(239,68,68,0.08) + 红边 + #fca5a5 文字），含关闭按钮。
5. 生成一个右侧滑出抽屉：结构 .panel-overlay(遮罩 blur4px) + .profile-panel(玻璃态 blur20px, 宽 400px, slide-in transform)，激活加 .open。
6. 生成一个统计卡片网格：父 .grid-4（4列 gap16），子 .stat-card（顶部 3px 渐变条 + 图标 + 数值 30px/700 + 变化标签）。
```

### Iteration Guide
1. **先读变量**：生成任何组件前，先读 `main.css` 的 `:root` 与 `[data-theme="light"]`，只引用已定义的 `--color-*`/`--accent-*`/`--radius-*`/`--shadow-*`。
2. **禁止裸值**：若提示里写 `background:#7c6af2`，改为 `background:var(--accent-primary)`——否则浅色主题下断裂。
3. **双主题自检**：每生成一个组件，脑内渲染一次 light 主题（白底），确认对比度与边框可见。
4. **按钮走标准**：新按钮一律 `.btn` 变体；除非改历史视图，否则不写 `.new-btn` 类。
5. **标签走 color-mix**：学科/状态标签用 `color-mix(in srgb, var(--subject-x) 14%, transparent)`，勿写死 `rgba`。
6. **圆角刻度**：卡片 lg(18) / 按钮 md(14) / 小元素 sm(10) / 胶囊 full——勿用 12px 等非刻度值。
7. **阴影刻度**：优先 `--shadow-card` / `--shadow-md`，手写投影仅限特殊 hover（如 `--shadow-card-hover`）。
8. **间距 4 倍数**：padding/margin 用 8/12/16/20/24；避免 10/14/18 等奇数（除必要对齐）。
9. **图标 currentColor**：SVG 用 `stroke="currentColor"`，尺寸 18-22px，颜色随父文本变量。
10. **响应式收口**：新网格默认 4 列，补 `@media (max-width:1024px){...2列}` 与 `480px{...1列}` 规则，对齐现有断点。
```
