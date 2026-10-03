# 评测产物状态清单（口径审计）

> 本文件由角色 B 于 2026-09-14 新增，**只增不删**。目的：把"哪些产物还能引用、哪些
> 字段已失效、失效原因是什么"写成可审计的事实，避免后来者把已作废的读数当结论使用。
>
> 判定方式：只读扫描全部 `experiments/results/*.json`，按 `meta/config` 里的
> **训练预算（episodes / batch → n_updates）**、**训练环境（legacy / calibrated）**、
> **是否施加纪律护栏**、**指标量纲**四项交叉核对，不凭记忆。
>
> 生成方式：`scripts/audit_eval_artifacts.py`（只读，不修改任何数据文件）。

---

## 0. 一句话

三个独立的**口径事故**污染了 2026-09-14 的评审权重（MAPPO）评测产物，必须区分对待：
**(A)** 训练预算被静默饿死（只传 `episodes`、`batch` 语义变更）→ 读数作废；
**(B)** 精准率量纲漂移（consistency 0-100→0-1，脚本硬编码阈值 60/75）→ 该指标恒为 0；
**(C)** 评测脚本未施加纪律护栏 → 报出 `discipline_ok=False` 假警报。

---

## 1. 有效产物（可引用）

| 文件 | 预算 | 关键读数 | 说明 |
|---|---|---|---|
| `review_shadow_summary_20260914_164556.json` | 3000ep/48 → **63 次更新** | shadow **69.896**、Δ规则 **+0.948** | 角色 B 第 8 轮主证据 |
| `review_shadow_summary_20260914_163552.json` | 同上 | 同上（逐位一致） | 同配置重复跑，用于验证确定性 |
| `review_shadow_summary_20260914_163933.json` | 同上 | 同上（逐位一致） | 同上 |
| `review_shadow_summary_20260914_171403.json` | 10000ep → **209 次更新** | shadow **69.999**、Δ规则 **+1.051** | 更大预算，当前最强 |
| `review_shadow_summary_20260914_172149.json` | 同上 | 同上（逐位一致） | 同配置重复跑 |
| `sweep_shadow_budget_20260914_163451.json` | 5/25/63/200 次四档 | 68.445 / 68.964 / 69.896 / 69.480 | **预算→结论**单调性的唯一真值源 |
| `sweep_shadow_budget_20260914_163817.json` | 留出集（data_seed 777777、种子 11/123/2027） | 63 次 → Δ规则 **+1.005** | 留出集复现 |
| `experiments/results/mappo_reachability_verify.json` | — | 合成环境三档验收 | 合成环境结论（不可外推） |
| `experiments/results/review_mappo_stage2_wrapup.json` | 2/25/63 次三档 + 统一护栏 | 6.9313 / 8.1580 / **11.3835** | 阶段2 收尾取证（角色 B） |

---

## 2. 字段级失效（文件保留，但指定字段不可引用）

### `sweep_shadow_budget_20260914_162837.json`

- **失效字段**：`baselines.rule = 69.966`
- **原因**：该次运行的独立基线段**未施加纪律护栏**，规则臂靠 skip 省成本而虚高。
- **修正值**：`69.948`（见 `163451`，同一脚本修复后重跑；两文件的 `results` 段逐位一致，
  说明**只有 baselines 段错**，各预算档的 shadow 读数仍有效）。
- **修正方式**：`sweep_shadow_budget.py` 已改为复用生产 `discipline_gate`。

---

## 3. 整体作废（预算被静默饿死，读数无意义）

`d55387e` 把 `train_ppo` 改为批处理（新增默认 `batch_episodes=48`）后，**只传 `episodes`
不传 `batch_episodes`** 的调用方，实际梯度更新次数暴跌（例：`episodes=200` → 5 次）。
以下产物即该口径产物：

| 文件 | 名义预算 | 实际更新 | 失效读数 |
|---|---|---|---|
| `review_shadow_summary_20260914_161319.json` | 200ep | 极少（未落盘 n_updates） | Δ规则 −0.503 |
| `review_shadow_summary_20260914_161556.json` | 200ep | **5 次** | shadow 68.445、Δ规则 −0.503 |
| `review_shadow_summary_20260914_161635.json` | 200ep | **5 次** | 同上（与 161556 逐位相同） |
| `review_shadow_summary_20260914_161821.json` | 200ep（legacy 训练环境） | **5 次** | shadow 68.487、Δ规则 −0.460 |

**替代产物**：`164556`（63 次更新，shadow 69.896）或 `172149`（209 次，shadow 69.999）。

> ⚠️ 特别提醒：`161556` / `161635` 的 **Δ规则 −0.503** 曾被用作"RL 在真实特征空间
> 输给规则"的证据。该结论**已撤回** —— 它测的是"没训够"，不是"方法不行"。

---

## 4. 口径过时（数字本身有效，但不得当作现状）

| 文件 | 过时项 | 处置 |
|---|---|---|
| `review_mappo_eval_20260914.json` | ① `ppo_episodes=60`（=**2 次**更新）② `precision_rate` 全 0（量纲漂移）③ 未施纪律护栏 | 保留为历史；**再引用须换用修复后脚本重跑** |
| `review_mappo_ablation_20260914.json` | 同上（且仅 1 seed） | 同上 |
| `review_action_dist_20260914.json` | `ppo_episodes=60`（旧口径） | 同上 |
| `review_shadow_summary_20260914_144351.json` | 针对**旧代码**的塌缩基线（`shadow_action_dist={'3':240}` 全部塌缩到 balanced、Δ均匀 −0.025） | 作为"修复前对照"有效；**不得描述为现状** |
| `review_shadow_summary_20260914_161259.json` | legacy 训练环境 + 旧代码 | 同上 |

---

## 5. 有效对照（有诊断价值，但不是结论）

| 文件 | 价值 |
|---|---|
| `review_shadow_summary_20260914_163519.json` | **legacy 训练 + calibrated 评测** → shadow 67.259、Δ规则 −1.689。证明"训练分布必须与评测分布一致"，否则再大预算也学不到迁移增益 |
| `review_shadow_summary_20260914_164229.json` | 同上（shadow 67.22、Δ规则 −1.728），且 `shadow_action_dist` 明显偏斜到 action 1 |
| `review_shadow_summary_20260914_161534.json` | 单 seed（`shadow_seeds=[7]`）诊断跑，Δ规则恰为 `0.0` ⇒ 该次 shadow 未训练成功、退化为规则等价；**扩 seed 后不成立** |

---

## 6. 仍未解决（需 CTO / 角色 C 决策）

1. **`precision` 分项零判别力**：奖励权重 `0.35`（第二大项），但在有效动作集 `{0,1,2,3}` 上
   该分量恒为 `+0.35`（`review_precision` 对任何非 skip 动作恒 True）⇒ 不参与 argmax。
   已由 `eval_review_mappo.py` 的 `reward_term_audit` 显式落盘并告警。
   **处置边界：属环境设计变更，需 CTO 书面背书；禁止以"让 RL 赢"为目的调权重。**
2. **`discipline` 分项恒不激活**：权重 `0.10`，仅在 `skip_streak ≥ SKIP_STREAK_LIMIT` 时非零，
   而 `discipline_gate` 的设计目标正是让该界线永不被跨过 ⇒ 护栏生效时恒为 0。
   属**设计使然**（违规才激活型惩罚），非失效，但须写清楚以免误读。
3. **环境内自造最优**：`gate` 分项（唯一有判别力的项）在本环境中由**环境作者写死的档位
   判据**决定 ⇒ RL 的"赢"只等价于"更常命中该判据"，**不是教学增益**。
   唯一出路是把评测换到真实评审 trace 上（见 `experiments/eval_review_mappo_real.py`）。
