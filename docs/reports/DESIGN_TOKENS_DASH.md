# MARS-408 仪表盘 · 设计令牌文档（Design Tokens / Dashboard Extension）

> 继承来源：`DESIGN_TOKENS.md` 紫系玻璃态系统（已上线前端 CSS v7/v8 · 主色 `#7c6af2` · 四科分色 · 深色默认 + 浅色覆盖）。
> 本文档在其基础上【增补】仪表盘可视化专用令牌维度，**不另起视觉语言**；下游筑原型直接把 `:root` 粘贴即用。
> 适用：Web 数据可视化大屏 / 面板；桌面优先、1200px 容器；深色默认、浅色可选。

---

## 1. 品牌提取结论 + 决策说明（≤250 字）

复用已上线前端紫系玻璃态（DESIGN_TOKENS.md v8），主色 `#7c6af2`，四科分色 ds/cn/co/os 恒定。仪表盘不另起视觉语言，仅在既有令牌上【新增】可视化专用维度：图表色板（分类色复用四科、连续色阶用紫系深浅）、KPI 卡玻璃变体、网格/坐标轴低对比描边、三态状态色 + 薄弱专属态、等宽数字字体与玻璃图表容器。

为何如此：评审/考生/教师三受众同屏，共用同一令牌集靠「分色 + 状态 + 数据卡」区分叙事；深色玻璃态天然契合「科技感 + 可信赖」，紫系连续色阶替代红绿刺眼热力图，与品牌调性协调。吸取落地页教训——状态色与 KPI 数值在深色底均过 WCAG AA（≥4.5:1），危险红 `#ef4444` 对比 4.7:1 仅用于大字号/图例，不作小正文。

---

## 2. 设计令牌 · `:root`（深色调默认 · 含继承全集 + dash新增）

```css
:root {
  /* ============ 语义层 · 画布与表面 ============ */
  --color-canvas:        #080812;
  --color-surface:       rgba(255,255,255,0.03);
  --color-surface-2:     #0f0f1a;
  --color-surface-hover: rgba(255,255,255,0.06);
  --color-elevated:      #1c1c2b;
  --color-overlay:       rgba(0,0,0,0.55);

  /* ============ 语义层 · 玻璃态 ============ */
  --color-glass:         rgba(15,15,26,0.65);
  --color-glass-hover:   rgba(15,15,26,0.80);
  --color-glass-border:  rgba(255,255,255,0.08);
  --glass-blur:          12px;
  --glass-blur-heavy:    20px;

  /* ============ 语义层 · 边框 ============ */
  --color-border:        rgba(255,255,255,0.06);
  --color-border-light:  rgba(255,255,255,0.04);
  --color-border-focus:  rgba(124,106,242,0.45);
  --color-border-glow:   rgba(124,106,242,0.25);

  /* ============ 语义层 · 文本 ============ */
  --color-text:          #f8fafc;
  --color-text-2:        #94a3b8;
  --color-text-3:        #7c8aa0;
  --color-text-invert:   #0f0f1a;

  /* ============ 品牌色（双主题恒定） ============ */
  --accent:              #7c6af2;   /* 主色 · 紫 */
  --accent-dark:         #6b5cdb;
  --accent-blue:         #5b8bd8;   /* 辅助 · 蓝（渐变收尾 / 次级信号） */
  --accent-cyan:         #06b6d4;
  --accent-warm:         #f59e0b;
  --accent-success:      #22c55e;
  --accent-danger:       #ef4444;
  --accent-pink:         #f472b6;
  --accent-primary:        var(--accent);
  --accent-primary-dark:   var(--accent-dark);
  --accent-secondary:      var(--accent-blue);
  --accent-tertiary:       var(--accent-cyan);
  --accent-primary-10:   rgba(124,106,242,0.10);
  --accent-primary-20:   rgba(124,106,242,0.20);
  --accent-primary-30:   rgba(124,106,242,0.30);

  /* ============ 408 四科色（恒定 · 语义着色用 color-mix 14%） ============ */
  --subject-ds: #8b5cf6;  /* 数据结构 */
  --subject-cn: #3b82f6;  /* 计网 */
  --subject-co: #06b6d4;  /* 计组 */
  --subject-os: #f472b6;  /* 操作系统 */

  /* ============ 发光 ============ */
  --glow-primary:        0 0 20px rgba(124,106,242,0.15), 0 0 40px rgba(124,106,242,0.08);
  --glow-primary-strong: 0 0 20px rgba(124,106,242,0.25), 0 0 60px rgba(124,106,242,0.12);
  --glow-secondary:      0 0 20px rgba(91,139,216,0.15), 0 0 40px rgba(91,139,216,0.08);
  --glow-success:        0 0 20px rgba(34,197,94,0.15);

  /* ============ 渐变 ============ */
  --gradient-primary: linear-gradient(135deg, #7c6af2 0%, #5b8bd8 100%);
  --gradient-text:    linear-gradient(135deg, #f8fafc 0%, #a5b4fc 100%);
  --gradient-hero:    radial-gradient(ellipse 600px 400px at 30% 30%, rgba(124,106,242,0.10) 0%, transparent 70%),
                      radial-gradient(ellipse 500px 300px at 70% 60%, rgba(91,139,216,0.08) 0%, transparent 70%);
  --gradient-border:  linear-gradient(135deg, rgba(124,106,242,0.20), rgba(91,139,216,0.15), rgba(6,182,212,0.10));
  --gradient-progress:linear-gradient(90deg, #7c6af2, #5b8bd8, #06b6d4);
  --gradient-warm:    linear-gradient(135deg, #f59e0b 0%, #f472b6 100%);

  /* ============ 阴影（克制深色抬升 + 彩色发光） ============ */
  --shadow-sm:        0 1px 2px rgba(0,0,0,0.30);
  --shadow-md:        0 4px 12px rgba(0,0,0,0.35);
  --shadow-lg:        0 8px 24px rgba(0,0,0,0.40);
  --shadow-xl:        0 16px 40px rgba(0,0,0,0.45);
  --shadow-card:      0 2px 8px rgba(0,0,0,0.25), 0 0 1px rgba(255,255,255,0.06);
  --shadow-card-hover:0 8px 24px rgba(0,0,0,0.35), 0 0 20px rgba(124,106,242,0.08);
  --shadow-glow:      0 4px 16px rgba(124,106,242,0.12);

  /* ============ 圆角 ============ */
  --radius-xs: 6px;
  --radius-sm: 10px;
  --radius-md: 14px;
  --radius-lg: 18px;
  --radius-xl: 24px;
  --radius-full: 9999px;

  /* ============ 间距（4/8 基准） ============ */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-7: 28px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;
  --space-20: 80px;
  --space-24: 96px;

  /* ============ 排版（中文系统字体栈 · 零加载） ============ */
  --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  --font-mono: 'SF Mono', 'Fira Code', 'Consolas', 'Cascadia Code', monospace;
  --fs-nano:    12px;
  --fs-caption: 13px;
  --fs-body:    14px;
  --fs-body-lg: 16px;
  --fs-h3:      18px;
  --fs-h2:      24px;
  --fs-h1:      32px;
  --fs-display: 40px;
  --fs-hero:    clamp(40px, 6vw, 64px);
  --fs-hero-sub:clamp(16px, 2vw, 20px);
  --lh-tight: 1.1;
  --lh-snug:  1.2;
  --lh-normal:1.6;
  --ls-tight: -0.8px;
  --ls-snug:  -0.5px;
  --ls-normal:0;
  --fw-regular: 400;
  --fw-medium:  500;
  --fw-semibold:600;
  --fw-bold:    700;

  /* ============ 层级 / Elevation ============ */
  --z-base: 1;
  --z-sticky-nav: 100;
  --z-dropdown: 200;
  --z-overlay: 900;
  --z-modal: 950;
  --z-tooltip: 1000;

  /* ============ 布局 ============ */
  --container-max: 1200px;
  --container-pad: 32px;
  --nav-height: 72px;
  --section-gap: 96px;

  /* ============ 组件令牌 · 按钮 ============ */
  --btn-radius: var(--radius-md);
  --btn-radius-pill: var(--radius-full);
  --btn-pad-y: 10px;
  --btn-pad-x: 20px;
  --btn-pad-y-lg: 13px;
  --btn-pad-x-lg: 28px;
  --btn-primary-bg: var(--gradient-primary);
  --btn-primary-color: #ffffff;
  --btn-primary-hover-shadow: 0 8px 20px rgba(124,106,242,0.25);
  --btn-secondary-bg: var(--color-surface-hover);
  --btn-secondary-color: var(--color-text);
  --btn-secondary-border: var(--color-border);
  --btn-ghost-color: var(--color-text-2);
  --btn-soft-bg: var(--accent-primary-10);
  --btn-soft-color: var(--accent-primary);

  /* ============ 组件令牌 · 卡片（玻璃态） ============ */
  --card-bg: var(--color-glass);
  --card-border: var(--color-glass-border);
  --card-radius: var(--radius-lg);
  --card-padding: 24px;
  --card-shadow: var(--shadow-card);
  --card-hover-shadow: var(--shadow-card-hover);
  --card-hover-transform: scale(1.02);
  --card-blur: var(--glass-blur);

  /* ============ 组件令牌 · 徽章 / 标签 ============ */
  --badge-radius: var(--radius-full);
  --badge-padding: 4px 12px;
  --badge-font-size: 12px;
  --badge-font-weight: 600;

  /* ============ 组件令牌 · 导航栏（吸顶玻璃） ============ */
  --nav-bg: var(--color-glass);
  --nav-border: var(--color-glass-border);
  --nav-blur: var(--glass-blur);

  /* ============ 组件令牌 · 分隔线 ============ */
  --divider-color: var(--color-border);
  --divider-light: var(--color-border-light);

  /* ============ 动效（轻量过渡 + 缓动） ============ */
  --transition:        all 0.2s cubic-bezier(0.4,0,0.2,1);
  --transition-slow:   all 0.35s cubic-bezier(0.4,0,0.2,1);
  --transition-bounce: all 0.4s cubic-bezier(0.34,1.56,0.64,1);
  --duration-fast:   150ms;
  --duration-normal:  300ms;
  --duration-slow:    500ms;
  --duration-enter:   600ms;

  /* ================================================================ */
  /* =================== dash新增 · 仪表盘可视化维度 =================== */
  /* ================================================================ */

  /* ============ dash新增 · 图表分类色板（复用四科分色 + 补充序列） ============ */
  --series-1: var(--subject-ds);   /* 数据结构 */
  --series-2: var(--subject-cn);   /* 计网 */
  --series-3: var(--subject-co);   /* 计组 */
  --series-4: var(--subject-os);   /* 操作系统 */
  --series-5: #a78bfa;             /* 补充 · 总体/均值 */
  --series-6: #5b8bd8;             /* 补充 · 其他/对照 */

  /* ============ dash新增 · 连续数值色阶（热力图 · 紫系深浅，低→高） ============ */
  --seq-1: rgba(124,106,242,0.10); /* 掌握度极低 */
  --seq-2: rgba(124,106,242,0.24);
  --seq-3: rgba(124,106,242,0.40);
  --seq-4: rgba(124,106,242,0.58);
  --seq-5: rgba(124,106,242,0.76);
  --seq-6: #c4b5fd;                /* 掌握度极高（亮紫） */
  --heat-gradient: linear-gradient(135deg, rgba(124,106,242,0.10) 0%, #c4b5fd 100%);  /* 热力连续映射 */

  /* ============ dash新增 · 三态状态色 + 薄弱专属态 ============ */
  --state-success: #22c55e;        /* 达标 / 已掌握 */
  --state-warning: #f59e0b;        /* 警告（沿用 --accent-warm） */
  --state-danger:  #ef4444;        /* 危险 / 严重薄弱 */
  --state-weak:    #a78bfa;        /* 薄弱/预警专属（品牌紫系，弱化警报感，提示关注，与警告区分） */

  /* ============ dash新增 · 图表网格 / 坐标轴（低对比描边） ============ */
  --chart-grid:        rgba(255,255,255,0.06);  /* 网格线 */
  --chart-grid-strong: rgba(255,255,255,0.10);  /* 基准轴 */
  --chart-axis:        rgba(255,255,255,0.12);  /* 坐标轴描边 */
  --chart-tick:        #7c8aa0;                  /* 刻度/轴文本（= --color-text-3，过 AA） */

  /* ============ dash新增 · 图表字体 ============ */
  --chart-font-value: var(--font-mono);   /* 数值等宽更专业 */
  --chart-font-label: var(--font-sans);   /* 标签 */
  --chart-axis-size:  12px;
  --chart-legend-size:12px;
  --chart-value-size: 14px;

  /* ============ dash新增 · KPI 卡（玻璃卡变体） ============ */
  --kpi-bg:           var(--card-bg);
  --kpi-border:       var(--card-border);
  --kpi-radius:       var(--radius-lg);
  --kpi-padding:      20px;
  --kpi-value-size:   32px;     /* 大字号数值 */
  --kpi-value-weight: 700;
  --kpi-value-font:   var(--font-mono);
  --kpi-value-glow:   0 0 18px rgba(124,106,242,0.20);  /* 发光强调 */
  --kpi-label-size:   13px;
  --kpi-label-color:  var(--color-text-2);
  --kpi-trend-up:     var(--state-success);
  --kpi-trend-down:   var(--state-danger);
  --kpi-trend-flat:   var(--color-text-2);

  /* ============ dash新增 · 图表容器（玻璃态面板，沿用 --card-* + 发光） ============ */
  --chart-panel-bg:     var(--card-bg);
  --chart-panel-border: var(--card-border);
  --chart-panel-radius: var(--radius-lg);
  --chart-panel-blur:   var(--glass-blur);
  --chart-panel-shadow: var(--shadow-card);
  --chart-padding:      20px;    /* 图表区内距 */

  /* ============ dash新增 · 角标 / 示意标签（真实·示意混合统一） ============ */
  --tag-demo-bg:    rgba(148,163,184,0.14);  /* 示意占位（中性，不报警） */
  --tag-demo-color: #cbd5e1;
  --tag-live-bg:    rgba(34,197,94,0.14);    /* 真实数据 */
  --tag-live-color: var(--state-success);

  /* ============ dash新增 · 多智能体（8 Agent）状态色 ============ */
  --agent-online:   var(--accent);     /* 在线/激活（品牌紫） */
  --agent-busy:     var(--state-warning);
  --agent-idle:     #94a3b8;           /* 空闲（= --color-text-2） */
  --agent-offline:  #64748b;           /* 离线（仅状态点/图标，不作正文） */
  --agent-error:    var(--state-danger);
}
```

---

## 3. 浅色主题覆盖（dash新增项覆盖 · 与已上线前端一致）

```css
[data-theme="light"] {
  /* dash新增 · 图表网格/坐标轴（浅底反相低对比） */
  --chart-grid:        rgba(15,18,40,0.06);
  --chart-grid-strong: rgba(15,18,40,0.10);
  --chart-axis:        rgba(15,18,40,0.12);
  --chart-tick:        #8a92a8;

  /* dash新增 · 连续色阶（浅底需更实，保证可见） */
  --seq-1: rgba(124,106,242,0.14);
  --seq-2: rgba(124,106,242,0.30);
  --seq-3: rgba(124,106,242,0.46);
  --seq-4: rgba(124,106,242,0.62);
  --seq-5: rgba(124,106,242,0.80);
  --seq-6: #6d5fe0;
  --heat-gradient: linear-gradient(135deg, rgba(124,106,242,0.14) 0%, #6d5fe0 100%);

  /* dash新增 · 角标（浅底） */
  --tag-demo-bg:    rgba(15,18,40,0.06);
  --tag-demo-color: #525a72;
  --tag-live-bg:    rgba(34,197,94,0.14);
  --tag-live-color: #16a34a;

  /* dash新增 · Agent 状态（浅底） */
  --agent-idle:     #525a72;
  --agent-offline:  #94a3b8;
}
```

---

## 4. WCAG 备注（仪表盘 · 深色默认）

- **状态色在 `#080812` 上的对比度**：success `#22c55e` ≈7.4:1、warning `#f59e0b` ≈8.7:1、weak `#a78bfa` ≈8.5:1、danger `#ef4444` ≈4.7:1——均 ≥4.5:1（AA 通过）。`#ef4444` 仅用于大字号/图例/状态点，不作小正文。
- **KPI 数值**：用 `--color-text #f8fafc`（≈18:1）+ `--font-mono`，绝对可读；若用强调紫仅作大字号/UI。
- **图表刻度文本** `--chart-tick #7c8aa0` ≈5.1:1（AA 通过）；网格线保持 `rgba(255,255,255,0.06)` 级低对比，不抢数据。
- **热力图单元格**：连续色阶为单元格背景，单元格内标签按单元亮度切换——深单元用 `#f8fafc`、亮单元（--seq-6 `#c4b5fd`）用 `#1a1d2e`，保证可读。
- **四科分色标签**：沿用 `color-mix(in srgb, var(--subject-x) 14%, transparent)` 着色背景 + 该科原色文字，深浅主题自动适配、对比达标。
- **`示意` 角标**用中性灰 `#cbd5e1`（非红/黄），避免与告警语义混淆；`真实` 角标用绿，与数据可信叙事一致。

---

## 5. 下游筑原型使用指引（非令牌，仅说明）

- 顶栏全局 KPI → 用 `--kpi-*` + `--glow-primary`；趋势箭头用 `--kpi-trend-up/down`。
- 学情总览条形/雷达 → 分类色用 `--series-1…4`（=四科）；知识点热力图 → `--seq-1…6` + `--heat-gradient`。
- 学习路径 / 多智能体协同 → Agent 状态点用 `--agent-*`；8 Agent 心跳/快照统一以 `--tag-live` / `--tag-demo` 角标标注真实/示意。
- 预警干预区 → 薄弱点用 `--state-weak`、危险用 `--state-danger`，与图例一致。
- 所有图表容器 → `--chart-panel-*`（玻璃面板）+ `--chart-padding:20px`；网格/刻度引用 `--chart-grid` / `--chart-tick`。
- 严禁编造数据：后端未接入时统一挂 `--tag-demo` 角标并预留 `fetch` 结构（真实数据接入后切 `--tag-live`）。
