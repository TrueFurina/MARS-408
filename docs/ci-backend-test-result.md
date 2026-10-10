# CI Backend Test 真值抽取（自动，2026-10-10）

推送 `career-literacy` → `origin` 后触发的 CI 实测结果，用于回填交付文档的最后两项待核数字。

## run `38006205976` — Backend Test (Linux) / pytest on ubuntu-latest（head `5f8afbe`，success）

单 job，三步 pytest：

| step | 命令 | 结果 |
|---|---|---|
| 1 默认离线集 | `pytest -q --tb=short`（沿用 pyproject addopts 排除 system/requires_milvus/slow） | **1389 passed, 38 skipped, 8 deselected, 1 xfailed, 0 failed** in 363.01s |
| 2 heavy（system） | `-m "not slow and not requires_milvus"` | （独立门禁，非默认集） |
| 3 noconftest | `-o addopts="" --noconftest` | 36 passed in 0.87s（单文件覆盖率保证，非全量） |

> ⚠️ 注意：日志中最后一行 `36 passed` 是第 3 步 noconftest 子集，**不是**默认集总数。默认集真值以第 1 步 `1389 passed` 为准。

**覆盖率（step 1 报表 TOTAL 行）**：
`TOTAL  21473  8453  61%` → **代码覆盖率 61%**（门禁 `--cov-fail-under=50`，余量 11pp）。

## run `37905229979` — P0 Regression Gate (Linux)（head `eb2d256`，success）

`pytest -m "p0_regression and not system and not requires_milvus"` → **67 passed**。
静态统计 6 个 `pytestmark = p0_regression` 文件共 **29** 个 `def/async def test_` 函数（=函数数），`67` 为参数化展开后的 collected 数，二者口径一致。

## 结论：交付文档数字全部经 CI 实测背书

| 指标 | 交付文档值 | CI 实测 | 状态 |
|---|---|---|---|
| 默认集测试 | 1389 passed / 38 skipped / 1 xfailed / 0 failed | run `38006205976` step1 完全一致 | ✅ |
| 代码覆盖率 | 61% | TOTAL 21473/8453 = 61% | ✅（原写 54.96% 旧值，已修正） |
| p0 档 | 67 条 | run `37905229979` = 67 passed | ✅ |
| API / 认证覆盖率 | 244 ops / 227 paths、94.67%（231/244） | openapi() + verify_auth_coverage | ✅（早前已对齐） |
