# 测试真值说明（TEST_TRUTH）

> 由收尾阶段 team-lead 落盘（qa-2 因工具权限被拒未能写入，移交 team-lead），并经 qa-2 迟到精炼实测（Windows @ de86da4，2026-10-16）校正。
> 目的：固化「测试数字」的权威来源，消除计数漂移（923/221 → 1139/0 → 1177/227 → 1178/208/3 → 1389/38/1）带来的口径混乱。

## 1. 核心结论
测试计数**不能统一为单一「权威真值」**，且必须按平台剖面区分（同一代码库的不同平台剖面，不是矛盾）：

- **本机 Windows 实测**（career-literacy @ de86da4，2026-10-16 重跑）：**1325 通过 / 208 跳过 / 1 xfailed / 0 失败 / 0 错误 / 9 未选中**；collect 总数 **1543**（=1325+208+1+9），默认集执行 **1534**（=1543−9 未选中，**≠ 通过**）。
- **CI/Linux 默认档**（10-09 快照，GitHub Actions run 37917008258）：**1389 通过 / 38 跳过 / 1 xfailed**。
- 缺口 = 172 `segv_env`（win32 torch SIGSEGV 守卫，Windows 强制跳过、CI/Linux 跑为通过）+ 36 `isolation`（全平台跳过，由 backend-test.yml `--noconftest` 覆盖）+ 29 win32-only `collect_ignore` torch 用例（Linux 才收集）。即本机通过 = CI 通过 − 172。
- **覆盖率**：本机 fresh 实测 **57.19%**（22587 stmt / 9670 missed），`--cov-fail-under=50` 过线（余量 7.19pp）。AGENTS.md:29 旧写 53.31% 已过时，应同步为 57.19%。
- 历史快照（1178/208/3、923/221、1139/0、1177/227 等）已陈旧，**仅作 git 历史记录，不可作为权威对外口径**。
- 结论：测试计数须由 `scripts/verify_metrics.py --update` 门禁锁死（CI 阻断未更新），硬编码计数一律改为动态派生。

## 2. 收尾裁决
- 动态真值须由 `scripts/verify_metrics.py --update` 门禁锁死，CI 阻断未更新。
- 快照系列仅作 git 历史记录，不可作权威。
- **硬编码计数一律改为动态派生**：移除 `tests/test_showcase_claim_invariants.py` 中的硬编码常量（1178/208/3 等），改为运行期动态统计或读取 `METRICS_CURRENT.md` 派生值。
- **e2e marker 名存实亡**：全仓 `pytest.mark.e2e` 出现 0 次，`-m e2e` 收集 0；「CI p0 档」实为 `-m p0_regression` = **67 用例**。对外材料写「默认集 1543 条 / CI p0 档 67 条」，勿提 e2e。

## 3. 各模块权威真值来源
| 模块 | 权威真值来源 | 负责人 |
|---|---|---|
| 测试计数 | 平台剖面：Windows 1325 通过 / CI 1389 通过 / collect 1543 + verify_metrics.py --update | qa-2 |
| 覆盖率 | 57.19%（-cov-fail-under=50 过线） | qa-2 |
| OpenAPI 端点 | verify_openapi_snapshot.py（237 paths / 255 ops，机器门禁） | engineer-8 |
| NeuralMixer | verify_mixer_prod.py（96 样本 / seed 20261006 / n=6） | engineer-2 |
| submission 文档数 | 53 份迁移 + 口径脚本，由 PM/engineer-6 收口 | engineer-6 |

## 4. 诚信红线（不可破）
- 任何测试/评估数字，禁止硬编码为对外常量；一律动态派生 + 门禁。
- 不得把「动态 full-run 数」与「历史快照数」混用或择优选取填入对外材料；平台剖面（Windows/CI）须如实区分，不得把 1534 默认集执行数误标为通过。
- NeuralMixer：n≠6 时形状不匹配 → 显式降级 shape_mismatch_fallback（neural_used=False），绝不把随机/均匀权重冒充神经推理（共识分对外唯一数值 7.0446 / 0.2857，stratified / 96 / n=6）。

## 5. qa-2 权限核查结论
收尾期间 qa-2 尝试落盘本文件时，`rm` / `Glob` / `Bash` / `Write` / `Edit` 全部被拒，**未误用 sudo 或暴力提权**；未能写入纯属工具权限受限，非技术阻塞。本文件由 team-lead 代落盘，并经 qa-2 精炼实测校正。
