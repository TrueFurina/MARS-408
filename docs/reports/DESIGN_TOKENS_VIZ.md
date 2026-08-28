# MARS-408 智能体协作可视化页 · 页面级设计令牌（补充）

继承 `DESIGN_TOKENS.md` 全部基础语义变量（`--accent*`/`--color-*`/`--space-*`/`--fs-*`/`--radius-*`/`--shadow-*`/`--glow-*`），本页仅新增下列页面级令牌，全走 var()，不重定义基础令牌。

## §1 Agent 节点语义色（Deep / Light 各一值，色相分散）

| 变量 | 角色（层） | Deep | Light |
|------|-----------|------|-------|
| `--agent-coord` | 全局协调（编排） | `#7c6af2` | `#6d5deb` |
| `--agent-plan` | 路径规划·高亮（编排） | `#c4b5fd` | `#7c6af2` |
| `--agent-diag` | 学情诊断（认知·数构） | `#8b5cf6` | `#7c3aed` |
| `--agent-gen` | 资源生成集群（生成·计网） | `#3b82f6` | `#2563eb` |
| `--agent-retrieve` | 检索优化（检索·计组） | `#06b6d4` | `#0891b2` |
| `--agent-eval` | 评估反馈（校验·OS） | `#f472b6` | `#db2777` |
| `--agent-quality` | 质量校验（校验·OS） | `#ec4899` | `#be185d` |

编排层紫系（coord/plan 取明度差区分）、认知层数构紫、生成层计网蓝、检索层计组青、校验层 OS 粉；eval/quality 同族明度差区分。

## §2 流/边色（深浅各值，相互区分）

| 变量 | 含义 | 线型 | Deep | Light |
|------|------|------|------|-------|
| `--flow-data` | 数据流 | 实线蓝 | `#60a5fa` | `#2563eb` |
| `--flow-control` | 控制/编排流 | 虚线紫 | `#a78bfa` | `#7c6af2` |
| `--flow-consensus` | 共识/加权投票流 | 加粗青 | `#22d3ee` | `#0891b2` |

## §3 共识机制可视化色

- `--nm-mix-from` / `--nm-mix-to`：NeuralMixer 融合渐变起止（紫→青，表多源信号融合）。Deep `#a78bfa`→`#22d3ee`；Light `#7c6af2`→`#0891b2`。
- `--conflict-detected`：冲突检出（warn/红）。Deep `#f87171`；Light `#dc2626`。
- `--conflict-resolved`：冲突消解裁决（ok/绿）。Deep `#4ade80`；Light `#16a34a`。

## §4 a11y 约定

- SVG 节点填充/描边用 `var(--agent-*)`（禁裸 hex）；节点色对 `--color-canvas` 的描边/填充满足 AA（≥4.5:1 大字/图形）。
- 图例文字用 `--color-text-2`；色块承载 `--agent-*` 语义色。
- 容器 `role="img"` + 内嵌 `<title>` + `aria-label`，并附文本替代（节点清单表）。
- 连线 `aria-hidden`（装饰），含义统一在图例说明。

本页全部页面级令牌均经 `var()` 引用 `DESIGN_TOKENS.md` 的基础语义变量，未新定义任何基础令牌，双主题（dark/light）自动连续。
