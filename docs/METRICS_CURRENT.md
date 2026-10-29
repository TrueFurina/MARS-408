# 当前指标真值（Single Source of Truth）

> **本文件是 benchmark 指标的单一真值源（SSOT）。**
> 任何"活文档"（证据页、overview、战略规划、演示稿）引用 benchmark 数字时，**必须与此处一致**，
> 或显式注明所引产物版本。禁止在文档里手写/记忆式抄数。
>
> 本文件所有数字由 `py-server/experiments/results/benchmark_2026-09-18.json` 直接提取，可用
> `python scripts/scan_stale_calibration.py --verify-ssot` 复核。

## 真值产物（唯一权威来源）

| 字段 | 值 |
| --- | --- |
| 产物文件 | `py-server/experiments/results/benchmark_2026-09-18.json` |
| sha256（前16位） | `3ffae12147dc2a8b`（完整值见真产物文件，校验脚本只比前 16 位） |
| 大小 | 261558 字节 |
| 生成时间 | 2026-09-18 00:52 |
| 查询数 | 28（实验1）/ 30×3 重复（实验2） |
| KB chunks | 2122（2026-09-18 实验时点口径；当前种子库已扩至 2015 chunks + 230 题，见 CLAUDE.md 数据层） |
| 随机种子 | 20260719 |
| 模型/KB | e5-base-v2（768）· netlearn_kb（2122 chunk，2026-09-18 实验时点口径） |

## 实验1 — FrugalRAG vs 全量检索（28 查询）

| 指标 | FrugalRAG | 全量 | 变化 |
| --- | --- | --- | --- |
| Recall@5 | 0.8214（82.14%） | 0.7500（75.00%） | **+0.0714（+7.14pp）** |
| Precision@5 | 0.6857（68.57%） | 0.5286（52.86%） | +0.1571（+15.71pp） |
| 平均延迟 | 574.36 ms | 2.70 ms | **≈213× 代价** |
| Token | — | — | **−11.99%（未降反增）** |

> 说明：延迟与 token 均为**代价侧**，FrugalRAG 赢在检索质量（recall/precision/MRR），代价是延迟与 token。
> 诚实呈现，禁止删改"如实说明"块。

## 实验2 — NeuralMixer vs 加权投票（30 题×3 重复）

| 指标 | NeuralMixer | 加权投票 | 变化 |
| --- | --- | --- | --- |
| 准确率 | 0.8889（88.89%） | 0.7667（76.67%） | **+0.1222（+12.22pp）** |
| Cohen's κ（对真值） | 0.8512 | — | — |
| Cohen's κ（投票对真值） | — | 0.6884 | — |

> 实验2 在 09-17 复现中**逐位一致**（0.8889 / 0.7667 / +12.2pp / κ 0.8512），属确定性可复现结论。

## 已作废的旧口径（禁止再出现在活文档）

以下为历史产物口径，**仅允许出现在注明产物版本的对比列或时点留档（审计/溯源）中**：

| 旧值 | 来源 | 现状 |
| --- | --- | --- |
| Recall@5 +10.7pp / 78.6% vs 67.9% | `benchmark_2026-08-17.json` | 被 09-18 的 +7.14pp / 82.14% vs 75.00% 取代 |
| 延迟 108.2 vs 5.4ms（≈20×） | `benchmark_2026-08-17.json` | 被 09-18 的 574.36 vs 2.70ms（≈213×）取代 |
| Token −0.14% | `benchmark_2026-07-19.json` | 被 09-18 的 −11.99% 取代 |
| NeuralMixer 83.3% / κ 0.776 | `benchmark_2026-08-17.json` 复现前 | 被 09-18 的 88.89% / κ 0.8512 取代 |

## 工程规模指标（视图 / 代码量 / API 规模）

> 本节同样属**活文档真值**，由 `python scripts/verify_metrics.py` 机检：
> 重算当前值与下表比对，任何一项不一致即 `exit 1`（已接入 CI）。
> 改动代码后跑 `python scripts/verify_metrics.py --update` 同步。
>
> 此前 README 的这些数字多次漂移（views 45→46、后端文件 414→374、API 端点约240→244），
> 根因是"手抄数字、无机检"。**引用前请先跑校验脚本，不要凭记忆抄数。**

<!-- METRICS_TABLE_START -->
| 指标 | 真值 | 口径（可复现） |
| --- | --- | --- |
| 前端 views（页面级组件） | 49 | `git ls-files 'src/views/*.vue'` 计数 |
| 前端 .vue 总数 | 88 | `git ls-files 'src/*.vue' 'src/**/*.vue' | sort -u` 计数（含顶层 App.vue；勿单用 `src/**/*.vue`，git 的 `**` 不匹配顶层文件，会漏 1） |
| 前端 .ts 总数 | 77 | `git ls-files 'src/*.ts' 'src/**/*.ts' | sort -u` 计数（含顶层 main.ts；勿单用 `src/**/*.ts`，git 的 `**` 不匹配顶层文件，会漏 1） |
| 前端代码行数（.vue+.ts） | 57942 | git 跟踪的 `.vue` + `.ts` 全部行数 |
| 后端 Python 文件数 | 388 | `git ls-files 'py-server/**/*.py'` 计数 |
| 后端代码行数 | 92882 | git 跟踪的 `.py` 全部行数 |
| API 路由模块数 | 42 | `git ls-files 'py-server/api/*.py'` 去 `__init__.py` |
| API 路径数（/api） | 243 | `py-server/openapi.json` 中 `/api` 路径数 |
| API 操作数（/api，method 级） | 261 | `py-server/openapi.json` 中 `/api` 操作数（method 级） |
<!-- METRICS_TABLE_END -->

> **测试数不在上表**：passed / skipped / xfail 需真正跑一遍 pytest，耗时且依赖环境，
> 其真值以 CI 全量回归为准（见 `AGENTS.md` 复核记录）。标注来源时点：
> **1524 通过 / 38 跳过 / 1 xfail / 0 失败（2026-10-17 CI run 38938041036）** → **已更新（2026-10-18）：1654 通过 / 38 跳过 / 1 xfail / 0 失败（CI run 39101268904，head 3bae4b9，Backend Test Linux 默认档；约 1702 collected，`addopts` deselect 9。1524→1654 增量 = 教师端三方向新测试。旧 1389/38/1 为 2026-10-09 run 37917008258，已作废）** → **已更新（2026-10-20）：1693 通过 / 38 跳过 / 1 xfail / 0 失败（CI run 39467891052，head 22a7469，Backend Test Linux 默认档，384.74s；约 1741 collected。1654→1693 增量 = 教师端看板口径 + 错误文案分类 + 四组运行时契约测试）** → **已更新（2026-10-21）：1737 通过 / 38 跳过 / 1 xfail / 0 失败（CI run 39681618692，head 2ba7e6b，Backend Test Linux 默认档，266.31s；约 1785 collected。1693→1737 增量 = SAGE 分级提示功能新增 44 条测试）**。
>
> **认证覆盖率**同理由独立脚本产出：`py-server/scripts/verify_auth_coverage.py`
> （当前 total=261 / protected=248 / public=13 / coverage=**95.02%** / unregistered=0）。

## 漂移防护

- 活文档若再出现上表"旧值"，`npm run gate:calibration` 在 CI 中直接红，定位到文件:行。
- 新产物生成后：更新本文件 + 重跑 `python scripts/scan_stale_calibration.py --verify-ssot` 确认一致。
