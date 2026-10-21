# CI Backend Test 真值抽取（自动，2026-10-21 复核）

推送 `career-literacy` → `origin` 后触发的 CI 实测结果，用于回填交付文档的最后两项待核数字。
**只有本节第一段是当前权威；以下历史段落均为其时点真值，引用前必须核对 run id。**

## run `39467891052` — Backend Test (Linux) / pytest on ubuntu-latest（head `22a7469`，success，2026-10-20）

**当前权威值**：教师端看板口径 + 错误文案分类（M01）+ 四组运行时契约测试并入后的全量回归。

| step | 命令 | 结果 |
|---|---|---|
| 1 默认离线集 | `pytest -q --tb=short` | **1693 passed, 38 skipped, 9 deselected, 1 xfailed, 0 failed** in 384.74s |

> collected = 1693+38+9+1 = **1741**（约值口径，与 TEST_TRUTH 一致）；运行项 = 1693+38+1 = **1732**。
> 1654→1693 增量 = 教师端看板口径 + 错误文案分类（M01）+ 四组运行时契约测试（2026-10-20 并入）。
> 同步更新的活副本：`AGENTS.md:11/33`、`docs/METRICS_CURRENT.md`、`docs/TEST_TRUTH.md`、
> `README.md`、`README_EN.md`、`src/views/ShowcaseView.vue`、`site/` 与 `website/` 落地页
> （后者由 `scripts/check_landing_sync.py` 机检守护）、`submission/00` + 配套文档、两份 pptx 与 4 份 docx 实体。

**覆盖率（step 1 报表 TOTAL 行）**：
`TOTAL  22554  8439  63%` → **CI 口径覆盖率 63%**（门禁 `--cov-fail-under=50`，余量 13pp）。
⚠️ 口径分野：`TEST_TRUTH.md` 另记**本机 fresh 57.19%**（22587 stmt / 9670 missed，2026-10-16 实测）——
两者是不同平台剖面（CI/Linux 与 Windows 跳过项不同），对外引用必须带口径，不得混用。

## 历史段落（以下数字为其 run 时点真值，已被上节取代）

### run `39101268904`（head `3bae4b9`，2026-10-18，success）
默认档 **1654 passed / 38 skipped / 9 deselected / 1 xfailed / 0 failed**（1702 collected）——已被 1693 取代。

### run `38942815598`（head `46b41b5`，2026-10-17，success）
默认档 **1524 passed / 38 skipped / 9 deselected / 1 xfailed / 0 failed** in 376.46s。
与 run `38938041036` 完全一致（两 commit 之间未触测试文件）。

### run `38938041036`（head `dc18dd2`，2026-10-17，success）

| step | 命令 | 结果 |
|---|---|---|
| 1 默认离线集 | `pytest -q --tb=short` | **1524 passed, 38 skipped, 9 deselected, 1 xfailed, 0 failed** in 377.60s |
| 2 heavy（system） | `-m "not slow and not requires_milvus"` | （独立门禁，非默认集） |
| 3 noconftest | `-o addopts="" --noconftest` | 36 passed in 0.88s（单文件覆盖率保证，非全量） |

> ⚠️ 注意：第 3 步的 `36 passed` 不是默认集总数。collected = 1524+38+9+1 = 1572。
> 覆盖率（step 1 TOTAL）：`TOTAL 22108 8522 61%` → 61%（门禁 50，余量 11pp）。

### run `38006205976`（head `5f8afbe`，success）

| step | 命令 | 结果 |
|---|---|---|
| 1 默认离线集 | `pytest -q --tb=short` | **1389 passed, 38 skipped, 8 deselected, 1 xfailed, 0 failed** in 363.01s |
| 2 heavy（system） | `-m "not slow and not requires_milvus"` | （独立门禁，非默认集） |
| 3 noconftest | `-o addopts="" --noconftest` | 36 passed in 0.87s |

> 覆盖率（step 1 TOTAL）：`TOTAL 21473 8453 61%` → 61%。

### run `37905229979` — P0 Regression Gate (Linux)（head `eb2d256`，success）

`pytest -m "p0_regression and not system and not requires_milvus"` → **67 passed**。
静态统计 6 个 `pytestmark = p0_regression` 文件共 29 个测试函数（函数数），67 为参数化展开后的 collected 数，口径一致。

## 结论：交付文档数字全部经 CI 实测背书（2026-10-21 复核）

| 指标 | 交付文档值 | CI 实测 | 状态 |
|---|---|---|---|
| 默认集测试 | 1693 passed / 38 skipped / 1 xfailed / 0 failed | run `39467891052` step1 完全一致 | ✅ |
| 代码覆盖率 | CI 63%；本机 fresh 57.19%（TEST_TRUTH 口径） | TOTAL 22554/8439 = 63%（run `39467891052`） | ✅（带口径引用） |
| p0 档 | 67 条 | run `37905229979` = 67 passed | ✅ |
| API / 认证覆盖率 | 261 ops / 243 paths（/api 口径，全量 262/244）、**95.02%（248/261）** | `openapi.json` 实测 + `verify_auth_coverage.py`（2026-10-21 复算，unregistered=0） | ✅ |
