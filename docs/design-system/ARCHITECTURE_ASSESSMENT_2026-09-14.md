# MARS-408 设计系统架构评估与优化路线图

> 评估角色：设计系统架构师（DesignMdArchitect）｜日期：2026-09-14
> 范围：`src/assets/styles/**`（令牌 / 全局 CSS）+ `docs/**` 设计文档 + `design-system/**` 治理资产 + CI 门禁
> 方法：只读侦察（文件读取 + grep 量化 + 门禁实跑），不修改任何受检文件
> 结论一句话：**骨架健康（4 层 SSOT + 漂移门禁 + 双主题），但有一条架构级硬伤——文档与代码彻底失联；门禁只覆盖 showcase HTML，看不到文档与组件层，漂移对 CI 完全隐形。**

---

## 0. 结论速览（TL;DR）

| 维度 | 评分 | 说明 |
|------|------|------|
| 令牌架构（分层/命名/双主题） | 🟢 良好 | 原语→语义→别名三层清晰，116 语义令牌，双主题覆盖完整 |
| 代码 SSOT 唯一性 | 🟢 良好 | `_variables.css` 语义层为唯一可改源，`var()` 别名链解耦 72 组件 |
| 全局 CSS 模块化 | 🟢 良好 | `main.css` 已拆为 `_variables` / `_layout` / `_components` 三文件 @import |
| **文档一致性** | 🔴 **严重** | **生产已 v10「砚·Ink&Clay」（陶土），全部规范文档仍写 v7/v8（AI 紫）** |
| 治理/门禁覆盖 | 🟠 不足 | 漂移门禁只管 showcase HTML；**无 stylelint**，"禁止裸值"红线无自动执行 |
| 结构纯粹性 | 🟡 一般 | 令牌文件混装组件类；`.skeleton` 双定义；`--text-*` 命名二义 |
| 仓库卫生 | 🟡 一般 | `.bak` 入库、`__pycache__` 落盘、3 份 cleanup 脚本 |

---

## 1. 现状：架构长什么样（as-is）

```
┌─ 令牌层 (SSOT) ────────────────────────────────────────────────┐
│  src/assets/styles/_variables.css   v10「砚·Ink&Clay」857 行     │
│   §1 主题无关原语(~116)  §2 深色语义(~150)  §3 浅色语义(~118)    │
│   §4 兼容别名(~78)  §5 关键帧  §6 状态基类  §7 降级规则          │
└───────────────┬────────────────────────────────────────────────┘
                │ @import
┌─ 全局 CSS 层 ─▼────────────────────────────────────────────────┐
│  main.css(入口+重置) → _layout.css(壳+断点) → _components.css   │
└───────────────┬────────────────────────────────────────────────┘
                │ var(--…)
┌─ 组件层 ──────▼────────────────────────────────────────────────┐
│  src/**/*.vue  <style scoped>  只引用 --color-*/--subject-*      │
└────────────────────────────────────────────────────────────────┘

┌─ 文档层（应派生于 SSOT）───────────────────────────────────────┐
│  docs/design-system/SSOT.md          ✅ 契约(正确,2026-07-13)    │
│  docs/reports/DESIGN.md              🔴 v8 紫  自称"唯一真相源"  │
│  docs/design-system/DESIGN_SYSTEM_v2.md 🔴 v2 紫 自称"权威参考"  │
│  docs/reports/DESIGN_TOKENS{,_DASH,_KG,_VIZ}.md 🔴 4 份 v7 紫    │
└────────────────────────────────────────────────────────────────┘

┌─ 治理/门禁 ────────────────────────────────────────────────────┐
│  design-system/check_tokens.py  → 只比对 showcase HTML 内联:root │
│  .github/workflows/ci.yml:350  design-token-drift job（绿）      │
│  ESLint（.vue/.js/.ts）  无 stylelint  → CSS 层无自动门禁        │
└────────────────────────────────────────────────────────────────┘
```

**现状数据（实跑/实测）：**
- `check_tokens.py` 实跑 → **零漂移 EXIT=0**（canonical 116 令牌，12 个 showcase 消费者全对齐）。
- 全仓 grep `砚|CE8256|Ink & Clay|v10` 于 `docs/` → **0 命中**（v10 无任何文档）。
- grep `7c6af2`（旧 AI 紫）于 `docs/` → **13 个文件命中**（见 §2.1）。

---

## 2. 问题清单（按严重度排序）

### 🔴 P0 — 文档与代码彻底失联（架构级硬伤）

**事实**：`_variables.css` 已于 2026-09-12（commit `b4ea778`「四支柱大改」）升级为 **v10「砚 · Ink & Clay」**——主色从 AI 紫 `#7c6af2` 改为**陶土 Clay `#CE8256`**，画布 `#080812`→`#0E1217`，**删除全部彩色发光**（glow 令牌退化为中性投影）。但**所有规范文档一字未改**，仍在描述旧紫系统。

| # | 文件 | 漂移证据（file:line） | 危害 |
|---|------|----------------------|------|
| 1 | `docs/reports/DESIGN.md` | L3「基于 main.css (v8)」；L41「主色 · 紫 `#7c6af2`」；L67 `glow-primary` 彩色发光；L71 说"唯一真相源 main.css" | 🔴 自称 SSOT 却是错的 → AI 代理照它生成紫色 UI |
| 2 | `docs/design-system/DESIGN_SYSTEM_v2.md` | L4「**本文件是所有 UI 开发的权威参考**」；L13/L47 主色紫；L72 发光 | 🔴 明示为权威 → 误导性最强 |
| 3 | `docs/reports/DESIGN_TOKENS.md` | L49 `--accent:#7c6af2`；L78 紫→蓝渐变；L199 `--transition:all 0.2s`（已废弃写法） | 🔴 落地页原型生成规范失真 |
| 4 | `docs/reports/DESIGN_TOKENS_DASH.md` | 5 处旧紫 | 🟠 仪表盘原型失真 |
| 5 | `docs/reports/DESIGN_TOKENS_VIZ.md` | 4 处旧紫 | 🟠 可视化原型失真 |
| 6 | `docs/reports/DESIGN_TOKENS_KG.md` | 1 处旧紫 | 🟡 图谱原型失真 |
| 7 | `src/assets/styles/_variables.css.bak` | 349 行旧紫版本，**被 git 跟踪** | 🟡 陈旧备份入库，易被误读为"备选真相源" |

**根因链**：v10 只改代码 → `check_tokens.py` 只校验 showcase HTML（`check_tokens.py:30-33`）→ 文档从未纳入门禁 → 漂移对 CI **完全隐形**（门禁一路绿）。**这是"文档即 SSOT"治理模型的根本漏洞：谁不被校验，谁就必然漂移。**

**冲突放大**：同时存在 **3 份互斥的"真值源"声明**——`DESIGN.md` 说"唯一真相源是 main.css"、`DESIGN_SYSTEM_v2.md` 说"本文件是权威参考"、`SSOT.md` 说"真值源是 _variables.css"。三者指向不同，读者/AI 无所适从。

---

### 🟠 P1 — 治理覆盖缺口（防漂移机制只护住一角）

| # | 问题 | 证据 | 后果 |
|---|------|------|------|
| 1 | **无 stylelint** | `package.json` scripts 只有 eslint/prettier/vitest；无 stylelint 依赖 | SSOT 铁律 2「组件禁止裸 hex/rgba」**无任何自动执行**，仅靠人工 grep |
| 2 | **漂移门禁范围过窄** | `check_tokens.py:30-33` 消费者仅 `public/showcase` + `design-system`（.html） | 文档(`.md`)、`.vue`、`_layout/_components.css` **全在盲区** |
| 3 | **ESLint 不覆盖 CSS** | `lint: "eslint . --ext .vue,.js,.ts,.tsx"` | `<style>` 段与 `.css` 文件的裸值无人把关 |
| 4 | **原生 CSS 仍有裸值残留** | `_layout.css` hex=2/rgba=7；`_components.css` hex=11/rgba=13 | 部分属合理（断点/rgba 叠加），部分疑为漂移，无门禁无法区分 |

> 判据：门禁覆盖率矩阵（§4）显示——**4 个层里只有"showcase HTML"1 层有自动化守护**。

---

### 🟡 P2 — 结构纯粹性与命名（可维护性）

| # | 问题 | 证据 | 建议 |
|---|------|------|------|
| 1 | **令牌文件混装组件类** | `_variables.css:784` `.skeleton`、`:798` `.stream-caret` 定义在"变量"文件内 | 基类应移入 `_components.css`，令牌文件只留变量 |
| 2 | **`.skeleton` 双定义（死代码）** | `main.css:62`（radius-lg + `shimmer`）与 `_variables.css:784`（radius-sm + `mars-shimmer`）同选择器 | `_variables.css` 那份被覆盖成死代码，去重 |
| 3 | **`--text-*` 命名二义** | §1.2 `--text-2xs…6xl` 是**字号**；§4.4 `--text-primary/secondary/muted` 是**颜色**别名 | 同前缀两种语义，阅读/自动补全易错；建议字号改 `--fs-*` |
| 4 | **兼容别名层偏重** | §4 有 78 条别名（95 条指向语义层） | 属"72 组件零改动"过渡债；应有迁移清零路线，否则永久沉积 |

---

### 🟢 P3 — 仓库卫生

| # | 问题 | 证据 |
|---|------|------|
| 1 | `.bak` 入库 | `git ls-files` 含 `src/assets/styles/_variables.css.bak` |
| 2 | `__pycache__` 落盘 | `docs/design-system/__pycache__/*.pyc` 存在于工作树 |
| 3 | 3 份 cleanup 脚本冗余 | `docs/design-system/cleanup_tokens{,_2,_3}.py` |
| 4 | 死代码已注释留存 | `main.css:57-59` 记录已删的 `pulse-glow`/`gradient-shift`（合理，但说明清理靠人工） |

---

## 3. 优化路线图（分优先级 · 可直接执行）

### 🔴 P0 — 文档收口（最高优先，必须先做）
1. **重写 `DESIGN.md` 到 v10**：以 `_variables.css` 的 `:root` 为唯一输入，机械重新生成色板/字号/组件/阴影表（陶土 `#CE8256`、零发光、`--space-*`、agent/chart/seq 令牌），并把 §9 Quick Reference 的"唯一真相源"改为 `_variables.css`。
2. **冻结旧文档**：在 `DESIGN_SYSTEM_v2.md`、`DESIGN_TOKENS*.md` 顶部加醒目横幅「⚠ 本文档描述的 v7/v8 紫系统已于 2026-09-12 被 v10「砚·Ink&Clay」取代；技术细节以 `_variables.css` 为准，本文仅存档」。
3. **新增 v10 叙事规范**：写一份 `DESIGN_SYSTEM_v10.md`（或并入重写的 DESIGN.md），记录陶土主色选择理由、零发光决策、阅读优先哲学（这些已在 `_variables.css:1-40` 注释里，提炼即可）。
4. **SSOT 命名消歧**：让 3 份"真值源"声明收敛为 1 份——保留 `SSOT.md` 为唯一治理契约，其余降级为"消费者"。

### 🟠 P1 — 扩展门禁（让漂移无法隐形）
1. **引入 stylelint**（`stylelint-config-standard` + 自定义 `color-no-hex`/`declaration-property-value-disallowed-list`），对 `src/**/*.vue` 的 `<style>` 与 `src/assets/styles/*.css`（除 `_variables.css`）禁裸 hex/rgba；接入 `ci.yml` 的 `lint-build` job。
2. **升级 `check_tokens.py` 为"全消费者"检测器**：新增两个消费者类型——(a) markdown 中的色值代码块（正则提取 `#hex` 与 `_variables.css` 交叉核对）；(b) `.vue`/`_components.css` 裸值扫描（白名单例外：Canvas 调色板、SVG `currentColor`）。
3. **把"文档禁止引用已变更令牌值"纳入 P0 门禁**：文档里出现与 canonical 不符的旧 hex → 阻断。（这条能直接捕获本次这类事故。）

### 🟡 P2 — 结构重构
1. 把 `.skeleton` / `.stream-caret` 从 `_variables.css` 移入 `_components.css`；删除 `_variables.css` 中的重复 `.skeleton`。
2. 字号令牌 `--text-*` → `--fs-*` 重命名（保留 `--text-*` 旧名做别名过渡），消除与颜色别名的前缀二义。
3. 制定兼容别名清除计划：统计 §4 各别名的真实引用数，零引用的直接删，有引用的排期迁移（可脚本化）。

### 🟢 P3 — 卫生
1. 将 `_variables.css.bak` 移出 git（`git rm --cached`，磁盘保留，遵守只读红线）。
2. `.gitignore` 补 `**/__pycache__/`、`*.pyc`。
3. `cleanup_tokens*.py` 合并为 1 份或归档到 `archive/`。

---

## 4. 门禁覆盖率矩阵（现状 vs 目标）

| 层 | 代表文件 | 文档 | 对齐 v10 | 自动化门禁 | 目标 |
|----|----------|------|----------|------------|------|
| 令牌 SSOT | `_variables.css` | 内嵌注释 | ✅ | 无（自身即源） | 保持 |
| 全局 CSS | `main.css`/`_layout`/`_components` | ❌ | ✅（main） | ❌ | **+stylelint** |
| 组件 `.vue` | `src/**/*.vue` | ❌ | 部分 | ❌（仅人工 grep） | **+stylelint** |
| Showcase HTML | `public/showcase/*.html` | — | ✅ | ✅ `check_tokens.py` | 保持 |
| **Prose 文档** | `DESIGN*.md` | ✅（但是旧的） | 🔴 **否** | ❌ | **P0 重写 + P1 门禁** |

> 一句话：**4 个层里只有 1 个层有自动守护**；文档层既没有门禁、内容还全错——这正是漂移能"静默存活"的结构原因。

---

## 5. 建议下一步（择一即可开工）

- **A（推荐·P0）**：立即重写 `DESIGN.md` 到 v10 + 给旧文档加冻结横幅——**消除"AI 照旧文档生成错 UI"的现实威胁**。
- **B（P1）**：引入 stylelint + 升级漂移门禁为全消费者检测器——把"零漂移"从人工承诺变成 CI 硬约束。
- **C（P2/P3）**：结构重构 + 卫生清理（去重 `.skeleton`、移基类、清 `.bak`）。

> 红线声明：本评估为**只读侦察**，未修改 `_variables.css` 或任何受检文件；`.bak`/`__pycache__` 等卫生项**建议**清理，未擅自删除。
