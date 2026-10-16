# 测试真值说明（TEST_TRUTH）

> 由收尾阶段 team-lead 落盘（qa-2 因工具权限被拒未能写入，移交 team-lead），并经 qa-2 多次实测与最终裁定（2026-10-16）校正。
> 目的：固化「测试数字」的权威来源，消除计数漂移（923/221 → 1139/0 → 1177/227 → 1178/208/3 → 1389/38/1）带来的口径混乱。

## 1. 核心结论（权威口径以 SSOT 为准）
**权威对外口径 = CI 全量回归 `1389 通过 / 38 跳过 / 1 xfailed / 0 失败`（1436 collected）**，依据项目 SSOT `docs/METRICS_CURRENT.md:79-81` 明文裁定："测试数不在上表……其真值以 CI 全量回归为准（见 AGENTS.md）。标注来源时点：1389 通过 / 38 跳过 / 1 xfail（2026-10-09 CI run 37917008258）；套件已增长，须由下一次 CI 全量回归刷新。"

三层校准（同代码库、不同平台剖面，非矛盾）：
| 数字 | 性质 | 地位 |
|---|---|---|
| 1178/208/3（10-06 Windows） | 本机 Windows 剖面 | ❌ 已被 SSOT 订正为「标记剖面错位，非当前真值」 |
| 1543 collected（docs/TEST_TRUTH.md / 本机 Windows 重跑） | 可独立复现的 collect 总数 | ⚠️ 1543 total 可复现（1325+208+1+9）；但 passed 随平台而异（Windows 1325 / CI 1389），**不能硬编码为 passed** |
| **1389/38/1（CI run 37917008258）** | CI/Linux 全量回归 | ✅ **SSOT 指定对外权威口径** |

- **本机 Windows 实测**（career-literacy @ de86da4，2026-10-16 重跑）：**1325 通过 / 208 跳过 / 1 xfailed / 0 失败 / 0 错误 / 9 未选中**；collect **1543**（=1325+208+1+9），默认集执行 **1534**（=1543−9 未选中，**≠ 通过**）。
- **CI/Linux 默认档**（10-09 快照）：**1389 通过 / 38 跳过 / 1 xfailed**（1436 collected）。缺口 = 172 `segv_env` + 36 `isolation` + 29 win32-only，系平台剖面差异。
- **覆盖率**：本机 fresh 实测 **57.19%**（22587 stmt / 9670 missed），`--cov-fail-under=50` 过线（余量 7.19pp）。AGENTS.md:29 旧写 53.31% 已过时，应同步为 57.19%。
- 历史快照（1178/208/3、923/221、1139/0、1177/227 等）已陈旧，**仅作 git 历史记录，不可作权威对外口径**。

## 2. 收尾裁决（机制）
- **测试计数不进 `verify_metrics.py` 表**：SSOT 明确"测试数不在上表"，其真值以 CI 全量回归为准（指向 CI run id + 下一次 CI 刷新）。`verify_metrics.py` 仅锁死**工程规模指标**（API 236/254 路径/操作、49 views 等），不锁测试数。
- 快照系列仅作 git 历史记录，不可作权威。
- **硬编码计数一律改为动态派生**：移除 `tests/test_showcase_claim_invariants.py` 中的硬编码常量（1178/208/3 等），改为读取 CI 口径或动态统计。
- **e2e marker 名存实亡**：全仓 `pytest.mark.e2e` 出现 0 次；「CI p0 档」实为 `-m p0_regression` = **67 用例**。对外材料写「默认集 1543 条 / CI p0 档 67 条」，勿提 e2e。

## 3. 各模块权威真值来源
| 模块 | 权威真值来源 | 负责人 |
|---|---|---|
| 测试计数 | **CI 全量回归 1389 通过/38 跳过/1 xfail（run 37917008258）**，SSOT METRICS_CURRENT.md:79-81 | qa-2 / SSOT |
| 覆盖率 | 57.19%（-cov-fail-under=50 过线） | qa-2 |
| 工程规模（API/views 等） | verify_metrics.py --update 机检 | qa-2 |
| OpenAPI 端点 | verify_openapi_snapshot.py（237 paths / 255 ops，机器门禁） | engineer-8 |
| NeuralMixer | verify_mixer_prod.py（96 样本 / seed 20261006 / n=6） | engineer-2 |
| submission 文档数 | 53 份迁移 + 口径脚本，由 PM/engineer-6 收口 | engineer-6 |

## 4. 诚信红线（不可破）
- 任何测试/评估数字，禁止硬编码为对外常量；测试数以 CI run 时点指针为准，不得把 1543 默认集执行数误标为通过、不得把 Windows 1325 冒充 CI 1389。
- 不得把「动态 full-run 数」与「历史快照数」混用或择优选取填入对外材料。
- NeuralMixer：n≠6 时形状不匹配 → 显式降级 shape_mismatch_fallback（neural_used=False），绝不把随机/均匀权重冒充神经推理（共识分对外唯一数值 7.0446 / 0.2857，stratified / 96 / n=6）。

## 5. 收尾待决（P1/P2）
- **P1（必须，否则留 gap）**：当前 HEAD 的 1543 collected 已比 10-09 的 1436 多 7 条 → 1389/38/1 微陈旧。收尾动作：在 de86da4 跑一次 CI 全量回归 → 用新数回填 `METRICS_CURRENT.md:81` + `AGENTS.md:11/33` + `README:83/263` → 转 ✅。该动作依赖 CI（GitHub Actions），非本地可独立完成。
- **P2（格式锁 + 数字同步）**：
  - 认证覆盖率漂移：SSOT 记 **94.88%（245 端点/232 受保护/13 公开）**，10-06 实测 94.65%（243/230/13，API 面增 2 端点）；README/AGENTS 若仍写 94.65% 即陈旧，应同步 94.88%。
  - submission 文档数 sign-off：实质数（教学 DAG 86/82、seed KG 643/639、StateGraph 11、讯飞 10）已实测为真；commit `243fd3c` 已重同步 10 份 docx，但 zero-residual-drift 正式签核待 engineer-6/PM 回执。

## 6. qa-2 权限核查结论
收尾期间 qa-2 尝试落盘本文件时，`rm` / `Glob` / `Bash` / `Write` / `Edit` 全部被拒，**未误用 sudo 或暴力提权**；未能写入纯属工具权限受限，非技术阻塞。本文件由 team-lead 代落盘，并经 qa-2 多轮实测与最终裁定校正。
