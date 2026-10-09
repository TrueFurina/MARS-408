# 前端质量机检接入门禁（2026-10-09）

> 收口质量工程链的末端：把两条前端静态扫描从「孤儿脚本」接入门禁，
> 使 CI 与本地提交都真正执行。所有改动仅涉及 `scripts/`、`.github/`、本文件，
> **未触碰 `src/` 与 `submission/`**，符合 10-28 冻结纪律。

## 接入的两道前端机检

| 脚本 | 性质 | CI（verify-structural） | 本地（pre-commit.sh） |
|------|------|------------------------|----------------------|
| `scripts/token_scan.py --baseline scripts/token_scan.baseline.json` | 设计令牌硬编码颜色**防回归** | ✅ 阻断（任一分类计数上升即 exit 1） | ✅ 阻断 |
| `scripts/a11y_scan.py` | 可访问性**硬门禁**（图标按钮可读名） | ✅ 阻断（当前 0 缺陷） | ✅ 阻断 |
| `scripts/a11y_scan.py --audit` | 可访问性**深度审计**（A/B/C/D） | ✅ 仅报告（exit 0） | 未挂（手动跑） |

### 为什么用 `--baseline` 而非 `--max-brand 0`
`token_scan` 当前扫出 src/ 含 **31 处品牌紫 + 201 处硬编码色**。冻结期禁止改 `src/`，
故不能直接卡死 `--max-brand 0`（会让 CI 红）。改用**基线防回归**：
锁定 2026-10-09 真值，任一分类（brand/known/untracked）计数**只许降不许升**；
10-28 紫族归一后跑 `--update-baseline` 把基线降到新低值。

## 当前锁定基线（`scripts/token_scan.baseline.json`）

| 分类 | 计数 | 扩展名分布 |
|------|------|-----------|
| 硬编码颜色总数 | 201 | .vue=162 / .ts=35 / .css=4 |
| ├ brand-violet（品牌紫） | 31 | 待 10-28 归一 |
| ├ known-token-eq（与令牌等价） | 57 | 应改 `var()` |
| └ untracked（未追踪） | 113 | 含 .ts Canvas/图表调色板，需人工确认 |

a11y 硬门禁：`<button>` 无可读名缺陷 **0**（PASS）。深度审计待办：A=6 / B=8 / C=9 / D=19。

## 预置但未执行的工具（10-28 窗口用）

`scripts/codemod_violet_normalize.py` —— 品牌紫归一一键工具（**dry-run 默认，当前未执行**）。
正确性约束已处理：
- 只自动改写**不透明**的 `.vue/.css` 品牌紫（24 处）→ `var(--accent-primary)`；
- **带透明度**的 `rgba(...,a)`（19 处）一律归 MANUAL，避免丢失透明度造成视觉回归，需 `color-mix` 或人工；
- `.ts/.js`（7 处）`var()` 无效，仅列出待人工提取常量。

## 冻结期（即现在）已完成 vs 待 10-28 执行

**已完成（本提交）**
- [x] `token_scan` 加 `--baseline`/`--update-baseline`，生成并提交基线 JSON
- [x] 接入 `verify-structural.yml`（CI）+ `pre-commit.sh`（本地）
- [x] `a11y_scan` 默认门禁接入 CI + 本地；`--audit` 接入 CI 报告
- [x] 预置 `codemod_violet_normalize.py`（dry-run 验证分类正确，未执行）

**待 10-28 窗口（届时放开 src/ 冻结后一键执行）**
1. `python scripts/codemod_violet_normalize.py --apply`（改写不透明 .vue/.css）
2. 人工处理 19 处带透明度 + 7 处 .ts/.js（color-mix / 提取常量）
3. `python scripts/token_scan.py --update-baseline scripts/token_scan.baseline.json`（重降基线）
4. a11y 深度审计 A 类（浮层焦点管理）成熟规则提升为硬门禁
5. 重打包提交包 zip + 同步清单数字（滞后 HEAD 90 提交、测试 1177/227/3、API 模块 43）
6. NeuralMixer 共识分 7.0446±0.2857 复核（属研究线，需服务器 + KB/KG 大文件）

## 纪律重申
- 禁止提前改 `src/`、重打包 `submission/`（10-28 前）。
- 本地门禁七道 + 树级机检（token_scan/a11y）全过方可提交。
- push 后须 `gh run list --commit <sha>` 复查 `verify-structural` 是否全绿
  （本地门禁不含其 metrics 档，历史已验证）。
