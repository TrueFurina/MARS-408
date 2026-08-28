# MARS-408 知识图谱页 · 页面级设计令牌（增补于 DESIGN_TOKENS.md 之上）

> 本页仅补页面级令牌；所有基础语义变量（画布/表面/文本/品牌色/间距/圆角/阴影）一律 `var()` 复用 `DESIGN_TOKENS.md`，不重定义。

## §1 四科色（复用既有，确认 + 别名）
既有 `--subject-ds/cn/co/os` 已存在，直接复用。为契合本页命名，增设 `--subject-data/net/org/os` 别名映射：

| 页面别名 | 映射既有 | HEX | 科目 |
|---|---|---|---|
| `--subject-data` | `--subject-ds` | #8b5cf6 | 数据结构 |
| `--subject-net`  | `--subject-cn` | #3b82f6 | 计网 |
| `--subject-org`  | `--subject-co` | #06b6d4 | 计组 |
| `--subject-os`   | `--subject-os` | #f472b6 | 操作系统 |

四色恒定（深浅同值），互为区分、彼此对比 ≥4.5:1，可用 `color-mix 14%` 着色簇背景。

## §2 掌握度三档节点色（新增）
学情页未定义 `--mastery-*`，本页新增（低红/中琥珀/高绿，深浅各值；节点为大面积图形，与画布 ≥3:1 达标）：

| Token | Dark | Light | 档位 |
|---|---|---|---|
| `--mastery-low`  | #ef4444 | #dc2626 | 薄弱 |
| `--mastery-mid`  | #f59e0b | #b45309 | 一般 |
| `--mastery-high` | #22c55e | #15803d | 扎实 |

## §3 边类型色（新增）
| Token | Dark | Light | 线型 | 语义 |
|---|---|---|---|---|
| `--edge-prereq`  | #7c6af2 | #6b5cdb | 实线 | 先修依赖（accent 强调） |
| `--edge-related` | #475569 | #94a3b8 | 虚线 | 关联（装饰·低对比） |

## §4 节点尺寸与描边（新增）
- `--kg-node-base: 44px`（最小节点直径，兼触达目标）；重要性缩放用 `calc(var(--kg-node-base) * k)`，k∈[0.8,1.6]。
- 簇描边 = 对应 `--subject-*`（data/net/org/os）；节点填充 = `--mastery-*`。
- 低掌握度加 `--urgent` 描边环（= `--mastery-low`），提示优先补强链。

## §5 a11y 约定
- 图谱 SVG 节点填充一律走 `var()`，禁裸 hex。
- 图例文字用 `--color-text-2`；容器 `role="img"` + `<title>` + `aria-label`。
- 文本替代：四科→知识点清单表（含掌握度），保证读屏/移动降级可读。
- 边 `aria-hidden`（装饰），图例另述「先修=实线紫 / 关联=虚线灰」含义。

> 本页全走 var()：复用 DESIGN_TOKENS.md 既有 `--subject-ds/cn/co/os`、`--color-text-2`、`--accent-*`（红/琥珀/绿/紫）；新增 `--subject-data/net/org/os` 别名、`--mastery-*`、`--edge-*`、`--kg-node-base`、`--urgent`，均不重定义基础令牌。
