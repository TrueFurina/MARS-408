# ADR-017 — 评审单一真值源（`discipline_gate` / `review_precision` 收敛）

- **状态**：Accepted（已收敛，测试守护）
- **日期**：2026-09-14
- **决策人**：架构师（architect）
- **相关**：ADR-011（三元评审权重 MAPPO 化）；`docs/三元评审权重MAPPO-环境根因与真实效果报告-2026-09-14.md` §6；`docs/INVALID-ARTIFACTS.md`
- **关联代码**：`engines/review_policy.py`（`discipline_gate` / `review_precision`）；`tests/test_review_single_source.py`

## 背景

评审纪律规则（"skip 连发 ≥2 必须拦截"）与精准判定（"正确放行优质产物"）这两条**判定语义**，历史上在代码库中存在**多份互不引用的复制**，并已实际造成"静默漂移"事故：

`discipline_gate` 一度存在 **3 份**复制：
- (a) `review_policy.ReviewWeightPolicy.select_action` 内的闭包 `_block_skip`
- (b) `review_policy.evaluate_policy` 内的闭包 `_apply_discipline`
- (c) `engines/review_env_calibrated.py` 的模块级 `discipline_gate`（**逐字复刻**）

`review_precision` 的判定也曾被评测脚本按旧量纲**复刻**成 `thr = 75.0 if idx==4 else 60.0`（0–100 时代产物）；量纲改 0–1 后复刻体**恒判 False** ⇒ 精准率四臂全 0，而**所有单测仍绿**。

后果：生产侧修 (a) 的差一（`skip_streak >= LIMIT` → `>= LIMIT−1`）时，(b)(c) 不会跟着改。已付代价：角色 C 的评测脚本因绕开护栏而报出 `discipline_ok=False / max_skip_streak=2` 的**假警报**，把"脚本口径错误"误诊为"策略违规"。

**根因**：判定语义以"复制粘贴"的方式扩散，而"对拍测试"（断言两份实现行为一致）只能**事后**发现漂移。

## 决策

1. **唯一真值实现**：`discipline_gate`（`engines/review_policy.py:516-537`）与 `review_precision`（`engines/review_policy.py:498-513`）各自**只允许一份实现**，统一落在 `engines/review_policy.py`。
2. **其余调用点一律委托**：**6 处**调用点（校准环境 `engines/review_env_calibrated.py:151`、影子探针 `engines/review_shadow_probe.py:117`、诊断脚本与测试等）只**调用**唯一实现，**禁止本地重定义**。
   - 生产 `select_action`（`review_policy.py:829/839/842`）与 `evaluate_policy`（`review_policy.py:964`）同样委托模块级函数，不再保留内联闭包。
3. **守护 = 函数对象同一性断言（非对拍）**：`tests/test_review_single_source.py`（**49 例**）以 `is` 断言"调用点指向**同一函数对象**"——对同一性、量纲、分项自洽三类不变量做硬断言。任何变异体（在 calibrated/probe 里重新 `def` 一份实现）会让用例**失败**，从而让漂移**根本无法发生**（事前防复发）。

## 影响

- **变容易**：修一处即全链路生效；纠正"差一"类语义只需改唯一实现；审计时可 grep 复核"无第二份定义"。
- **变困难 / 需注意**：新增评测/诊断脚本**必须**走同一实现——"新增诊断脚本必须与探针同口径"已上升为本项目**硬纪律**（根因报告 §6.1 自述重犯）。
- **反脆弱价值**：把"对拍"（事后）升级为"同一性断言"（事前），是本项目"只读 + 仅追加"诚实治理在测试层的体现。

## 备选方案（被否决）

- **保留多份复制 + 对拍测试**：只能**事后**发现漂移，且已实际漏检（精准率全 0 而单测全绿），否决。
- **仅靠 code review 约束**：无法在 CI 层自动拦截复发，否决。
- **把判定逻辑内联在调用点**：正是漂移成因，否决。
