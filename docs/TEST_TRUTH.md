# 测试真值说明（TEST_TRUTH）

> 由收尾阶段 team-lead 落盘（qa-2 因工具权限被拒未能写入，移交 team-lead）。
> 目的：固化「测试数字」的权威来源，消除计数漂移（1178/208/3 → 1389/38/1 → 1534/1543）带来的口径混乱。

## 1. 核心结论
测试计数**不能统一为单一「权威真值」**。原因：
- clean full-run 结果（当前 1534 passed / 1543 total / 73 待定）是**动态真值**，随文件新增/修改而演化，是唯一可信的「当下真值」，但必须靠门禁锁死。
- 历史快照（1178/208/3）已陈旧，**仅作 git 历史记录，不可作为权威对外口径**。
- 两者是「动态真值 vs 过时快照」的冲突，不是可仲裁为单一常量的真值。

## 2. 收尾裁决
- 动态真值须由 `scripts/verify_metrics.py --update` 门禁锁死，CI 阻断未更新。
- 快照系列仅作 git 历史记录，不可作权威。
- **硬编码计数一律改为动态派生**：移除 `tests/test_showcase_claim_invariants.py` 中的硬编码常量（1178/208/3 等），改为运行期动态统计或读取 `METRICS_CURRENT.md` 派生值。

## 3. 各模块权威真值来源
| 模块 | 权威真值来源 | 负责人 |
|---|---|---|
| 测试计数 | clean full-run + verify_metrics.py --update | qa-2 |
| OpenAPI 端点 | verify_openapi_snapshot.py（237 paths / 255 ops，机器门禁） | engineer-8 |
| NeuralMixer | verify_mixer_prod.py（96 样本 / seed 20261006 / n=6） | engineer-2 |
| submission 文档数 | 53 份迁移 + 口径脚本，由 PM/engineer-6 收口 | engineer-6 |

## 4. 诚信红线（不可破）
- 任何测试/评估数字，禁止硬编码为对外常量；一律动态派生 + 门禁。
- 不得把「动态 full-run 数」与「历史快照数」混用或择优选取填入对外材料。
- NeuralMixer：n≠6 时形状不匹配 → 显式降级 shape_mismatch_fallback（neural_used=False），绝不把随机/均匀权重冒充神经推理（共识分对外唯一数值 7.0446 / 0.2857，stratified / 96 / n=6）。

## 5. qa-2 权限核查结论
收尾期间 qa-2 尝试落盘本文件时，`rm` / `Glob` / `Bash` / `Write` / `Edit` 全部被拒，**未误用 sudo 或暴力提权**；未能写入纯属工具权限受限，非技术阻塞。本文件由 team-lead 代落盘。
