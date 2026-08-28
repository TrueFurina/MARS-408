# MARS-408 落地页 · 设计令牌文档（Design Tokens / brand-spec）

> 主路径：品牌提取协议（brand-extraction）。来源 = 已上线前端 `src/assets/styles/_variables.css` + `main.css`（标注 v7）+ 仓库 `DESIGN.md`（文档化 v8）。
> 落地页（Phase 2 → Phase 3 筑原型）直接复用本 `:root` 语义令牌，保证与已上线前端视觉连续。
> 下文 `:root` 为深色调默认（landing 默认深色），附 `[data-theme="light"]` 覆盖以保持双主题连续。

---

## 1. 品牌提取结论 + 决策说明（≤300 字）

已上线前端采用「CSS v7/v8 玻璃态发光」系统，**主色为紫 `#7c6af2`**（注意：需求摘要写「科技蓝主色」为误述，蓝 `#5b8bd8` 仅出现在紫→蓝渐变收尾），配 408 四科分色与克制发光。落地页直接复用该 `:root` 语义令牌，确保视觉连续。

决策：延续深色玻璃态为默认；为落地页新增大屏 Hero 字号阶梯、4/8 间距刻度、组件级令牌与 sticky 导航层级；动效维持 0.2s 克制过渡。三重战线（考生 / 评审 / 教师）通过 408 分色标签与数据卡片区分叙事，不另起视觉语言。

---

## 2. 设计令牌 · `:root`（深色调默认 · 可直接粘贴进原生 HTML）

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
  --accent:              #7c6af2;   /* 主色 · 紫（非科技蓝；蓝仅出现在渐变收尾） */
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

  /* ============ 间距（4/8 基准 · 落地页新增刻度） ============ */
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
  --space-24: 96px;   /* 落地页区块竖向节律 */

  /* ============ 排版（中文系统字体栈 · 零加载） ============ */
  --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  --font-mono: 'SF Mono', 'Fira Code', 'Consolas', 'Cascadia Code', monospace;
  --fs-nano:    12px;   /* 徽章 / 说明 */
  --fs-caption: 13px;   /* 次文本 */
  --fs-body:    14px;   /* 正文基准（沿用 App） */
  --fs-body-lg: 16px;
  --fs-h3:      18px;   /* 卡片标题（落地页略放大） */
  --fs-h2:      24px;   /* 区块标题 */
  --fs-h1:      32px;
  --fs-display: 40px;
  --fs-hero:    clamp(40px, 6vw, 64px);   /* 大屏 Hero 标题（落地页新增） */
  --fs-hero-sub:clamp(16px, 2vw, 20px);   /* Hero 副标题 */
  --lh-tight: 1.1;
  --lh-snug:  1.2;
  --lh-normal:1.6;
  --ls-tight: -0.8px;   /* Hero 负字距 */
  --ls-snug:  -0.5px;
  --ls-normal:0;
  --fw-regular: 400;
  --fw-medium:  500;
  --fw-semibold:600;
  --fw-bold:    700;

  /* ============ 层级 / Elevation（落地页 viewport 层） ============ */
  --z-base: 1;
  --z-sticky-nav: 100;   /* 顶部吸顶导航 */
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
  --btn-radius-pill: var(--radius-full);   /* Hero CTA 用胶囊 */
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
  --card-padding: 24px;     /* 落地页略大于 App 的 20px，留呼吸感 */
  --card-shadow: var(--shadow-card);
  --card-hover-shadow: var(--shadow-card-hover);
  --card-hover-transform: scale(1.02);   /* 上限，勿超（见 Don'ts） */
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
}
```

### 浅色主题覆盖（与已上线前端一致，可选启用）

```css
[data-theme="light"] {
  --color-canvas:        #f5f6fb;
  --color-surface:       #ffffff;
  --color-surface-2:     #eef0f6;
  --color-surface-hover: #e7eaf3;
  --color-elevated:      #ffffff;
  --color-overlay:       rgba(15,18,40,0.32);
  --color-glass:         rgba(255,255,255,0.72);
  --color-glass-hover:   rgba(255,255,255,0.88);
  --color-glass-border:  rgba(15,18,40,0.10);
  --color-border:        rgba(15,18,40,0.10);
  --color-border-light:  rgba(15,18,40,0.06);
  --color-border-focus:  rgba(124,106,242,0.50);
  --color-border-glow:   rgba(124,106,242,0.22);
  --color-text:          #1a1d2e;
  --color-text-2:        #525a72;
  --color-text-3:        #8a92a8;
  --color-text-invert:   #ffffff;
  --bg-input:            rgba(15,18,40,0.04);
  --accent-primary-10:   rgba(124,106,242,0.08);
  --accent-primary-20:   rgba(124,106,242,0.14);
  --accent-primary-30:   rgba(124,106,242,0.20);
  --glow-primary:        0 0 18px rgba(124,106,242,0.10), 0 0 36px rgba(124,106,242,0.05);
  --glow-primary-strong: 0 0 18px rgba(124,106,242,0.18), 0 0 48px rgba(124,106,242,0.09);
  --glow-secondary:      0 0 18px rgba(91,139,216,0.10), 0 0 36px rgba(91,139,216,0.05);
  --glow-success:        0 0 18px rgba(34,197,94,0.10);
  --shadow-sm:        0 1px 2px rgba(15,18,40,0.06);
  --shadow-md:        0 4px 12px rgba(15,18,40,0.08);
  --shadow-lg:        0 8px 24px rgba(15,18,40,0.10);
  --shadow-xl:        0 16px 40px rgba(15,18,40,0.14);
  --shadow-card:      0 1px 3px rgba(15,18,40,0.06), 0 0 1px rgba(15,18,40,0.04);
  --shadow-card-hover:0 8px 24px rgba(15,18,40,0.10), 0 0 18px rgba(124,106,242,0.06);
  --shadow-glow:      0 4px 16px rgba(124,106,242,0.08);
}
```

### 可选动效片段（Hero 轻动效 / hover 用，复制即用）

```css
@keyframes fade-up { from { opacity:0; transform:translateY(12px); } to { opacity:1; transform:translateY(0); } }
@keyframes fade-in { from { opacity:0; } to { opacity:1; } }
@keyframes scale-in { from { opacity:0; transform:scale(.95); } to { opacity:1; transform:scale(1); } }
@keyframes pulse-glow {
  0%,100% { box-shadow: var(--glow-primary); }
  50%     { box-shadow: var(--glow-primary-strong); }
}
@keyframes gradient-shift { 0% { background-position:0% 50%; } 50% { background-position:100% 50%; } 100% { background-position:0% 50%; } }
```

---

## 3. 设计决策说明草稿（给主理人评审）

**为什么延续 CSS v7/v8 玻璃态发光**
- 需求摘要明确要求「与已上线前端一致」，而 `DESIGN.md` 已沉淀为 AI 可读的语义令牌系统（`:root` 语义层 + 别名层 + 品牌色层 + 学科色层），复用成本最低、风险最低。
- 该系统的「克制深色 + 玻璃态 + 紫主色 + 408 四科分色 + 微交互」恰好命中需求摘要的 Tone：科技感（玻璃/发光）、可信赖（线性/Stripe 仪表盘美学、零浮夸）、教育温度（学科分色带来的人文秩序感）。

**为落地页做的克制增强（不破坏连续）**
1. 字号阶梯新增大屏 `Hero`（clamp 40–64px）与区块标题 24px，解决单页首屏缺「门面感」。
2. 补齐 4/8 基准间距刻度 `--space-1…24`，统一区块竖向节律 `--section-gap:96px`。
3. 抽离组件级令牌（按钮/卡片/徽章/导航/分隔线），让筑原型不再散写值。
4. 新增 viewport 层级 `--z-sticky-nav` 等，支撑吸顶导航与分区叠加。
5. 卡片内距 20→24px、玻璃 blur 维持 12px，hover 缩放封顶 1.02——「增强」但不「变调」。

**与三战线叙事的呼应**
- 考生视角：Hero 痛点+收益 → 用 `--gradient-hero` 柔光 + `--fs-hero` 大标题建立冲击力；核心能力用四色 `--subject-*` 标签映射 408 科目。
- 评审视角：系统架构/技术亮点/学情可视化 → 用 `--card` 玻璃卡 + `--stat-*` 数据卡（数值 30px/700 + 负字距）呈现技术深度与指标可信度。
- 教师视角：教改/赛事社会价值 → 用 `--accent-warm`/`--accent-success` 状态色与 `--gradient-progress` 四色进度条表达成果与成长。
- 三者共用同一令牌集，仅靠「分色标签 + 数据卡 + 状态色」区分，避免视觉分裂。

---

## 4. 互补设计系统增强建议（非主选 · 仅借鉴）

1. **Raycast**（玻璃态 + 发光 + 紫系同族）：借鉴其「命令栏渐变光晕 / 窗口质感打磨」手法，强化落地页 Hero 区发光层次（如按钮 hover 叠加 `pulse-glow`），提升精致度而不加大面积色彩——与「克制发光」原则同向。
2. **Vercel**（极简高对比排版纪律）：借鉴其 Geist 式排版克制与文本高对比，约束落地页正文层级，抵消发光可能带来的「轻飘感」，强化「专业不冰冷、可信赖」。

> 二者均为增强参考，主选仍是既有 CSS v7/v8 品牌系统，不引入新主色或新视觉语言。

---

## 5. WCAG 备注（深色默认）

- 主文本 `#f8fafc` / 次文本 `#94a3b8` / 弱文本 `#7c8aa0` 在画布 `#080812` 上对比度均 ≥ 4.5:1（AA 通过）。
- 强调紫 `--accent-primary #7c6af2` 仅用于 UI、链接、激活态与大字号；**勿作正文色**（深底对比约 4:1，仅满足大字/UI）。
- 主按钮白字配紫→蓝渐变（平均明度足够），CTA 文字建议 ≥ 15px / 600 字重以稳过 AA。
- 学科标签用 `color-mix(in srgb, var(--subject-x) 14%, transparent)` 着色背景 + 该科原色文字，深浅主题自动适配。
