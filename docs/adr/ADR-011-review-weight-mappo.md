# ADR-011 — 三元评审权重 MAPPO 化（解析式默认 + RL 兜底）

- **状态**：Accepted（已落进生产，灰度默认关；记录**现有实现**）
- **日期**：2026-09-14
- **决策人**：架构师（architect）
- **相关**：`docs/CTO-芒得很职三元评审权重MAPPO化攻坚令-2026-09-14.md`；`docs/三元评审权重MAPPO-环境根因与真实效果报告-2026-09-14.md`；`docs/CTO-深度验收结论与三项派单令-2026-09-14.md` §4；ADR-017（评审单一真值源）；ADR-015（career 线）
- **关联代码**：`engines/review_policy.py`（`RULE_MODE`/`analytic_review_action`/`decide_review_weight`）；`agents/quality_gate.py`（插入点 B）；`engines/agent_debate.py`（插入点 A）；`config.use_review_mappo()`

## 背景

多智能体评审链（诚实 / 批评 / 共识三路 GOMARL 信号）产生三个可归一到 0–100 的评分信号 `(s_honest, s_critic, s_consensus)`。原实现以**均匀权重**（1/3,1/3,1/3）合成"有效一致性分"：

```
weighted = w_h·s_h + w_c·s_c + w_k·s_k
uniform  = (s_h + s_c + s_k) / 3
effective = s_h + (weighted − uniform)
```

均匀权重时 `weighted == uniform` ⇒ `effective == s_h`（即现状）。是否应引入**在线学习**来按上下文动态调整三元权重，是本次攻坚的核心问题。

企业/学术常见叙事是"用 RL（MAPPO）在线调权，超越一切基线"。本 ADR 记录**实测后的真实结论**：在可解析的目标口径下，最优权重是**解析解**，RL 的价值被重新定位为**兜底**而非"更强"。

## 决策

1. **生产默认 = 解析式**：`RULE_MODE = "analytic"`（`review_policy.py:474`）。当灰度开关打开且 `evidence`/`consensus` 均可用时，由 `analytic_review_action(evidence, consensus)`（`review_policy.py:477-495`）按生产打分定义**直接算出四档有效分取最大**，得解析最优档位（0..3）。零训练、可解释、可审计。
2. **RL = 兜底（fail-open）**：解析式不可用的场景（`evidence`/`consensus` 字段缺失、目标函数非 effective、强噪声）回退策略路径——MAPPO 在线决策或规则档（`decide_review_weight`，`review_policy.py:874-913`）。任何异常 → 均匀权重。
3. **灰度契约（默认关）**：`config.use_review_mappo()` 默认 `False`（`config.py:302-304`）。关闭时权重恒为均匀 ⇒ `effective` 逐字等于原 `consistency_score`，**偏移 0，行为零变化**。
4. **接入方式为干净下游插入**（不改判定逻辑）：
   - **插入点 B**（`agents/quality_gate.py:136-163` `_resolve_review_weights` + `202-218` 加权应用）：只换"判定输入"，PASS/FIX/REJECT 门不动；缺失/非法/均匀 → `weighted_consistency_score` 返回 `(s_h, False)`，零偏移。
   - **插入点 A**（`engines/agent_debate.py:145-171` `resolve_debate_review_weights` + `114-142` `review_content_budgets`）：按权重分配精炼注意力/内容预算，仅 2-agent 冲突 `regenerate` 路径生效（`api/agents.py:147-162`）；权重缺失/非法/均匀 → 预算等于历史基线（不变式 I1/I2）。

## 三位一体叙事（对外统一口径）

> **① 解析式最优**：在可解析的 effective 口径下，评审权重存在**解析最优解**，已作为生产默认。
> **② RL 兜底复杂场景**：解析式失效场景（字段缺失 / 目标非 effective / 强噪声）由 MAPPO 在线决策兜底，fail-open 降级。
> **③ career 线 RL 真实增益**：鲶鱼对抗模式在真实特征空间由 MAPPO 学习，3-seed 真训 reward 全超规则版——**这是当前唯一有真实增益数据的 RL 环节**（详见 ADR-015）。

## 证据（均落盘、CTO 独立复现）

| 方案 | capture（主集） | capture（泛化集） | 加噪 ±3% |
|---|---|---|---|
| 原级联规则 `rule_old` | 39.1% | 33.1% | 33.1% |
| 折进阈值的二分支 `rule_new` | 54.8% | 50.1% | 50.1% |
| RL（h=32, ep=10000, 3 seed） | — | 56.1% | — |
| **解析式 `analytic`** | **100.0%** | **100.0%** | **99.8%** |

- 来源：`experiments/diag_state_extend.py` + `accept_review.py`（独立泛化集 seed=313131）；CTO 独立跑 `accept_review.py` 得 capture **100%/100%/99.8%** → PASS（`docs/CTO-深度验收结论与三项派单令-2026-09-14.md` §1.1 判据 4）。
- `analytic` 与 oracle 动作**逐位一致**，且与打分函数 argmax **恒等**（守护测试 `test_analytic_is_identity_with_scoring_argmax`，变异验证可杀死错误实现）。
- **RL 上界被封闭**：`analytic` 在 effective 口径下 = oracle ⇒ 任何学习方案都无法超过解析式。RL 收敛带 55–61% 与单特征阈值上限 60.2% 重合 ⇒ 天花板在**信息层**（`s_c`/`s_k` 不在 12 维状态里），不因加大算力而提升。
- career 线：`career_catfish_mappo_eval_20260914.json`（RTX 5080）3-seed `mappo reward` 全超 `rule`（rule −0.0172/−0.0159/−0.0158 vs mappo −0.0113/−0.0129/−0.0102）；证据密度 0.41→0.55；纪律违规 0。

## 诚实边界（必须在一切对外引用中保留）

1. **仅证"effective 口径下最优可解析"，不等于"真实教学增益"**。`effective` 仍是**代理指标**；解析式的 100% 是该目标函数下的恒等式结果，真实收益取决于 `effective` 是否忠实代理教学质量——需接入真实评审日志回放复算（当前属合成/半合成结论）。
2. **career 六维均分 +0.02 属噪声级，不得对外称"提升"**；可对外仅为奖励超规则（3-seed）、证据密度提升（+27% 量级）、纪律违规 0，且须注明"合成环境（卡住型学生模拟），真实增益待 P5 试点"。
3. **绝对增益为暂定值**：头寸绝对值依赖样本生成器"s_h/s_c/s_k 相互独立"的假设；相对排序（解析式 > 折阈值规则 > RL > 现状）比绝对值稳健。
4. RL 在 effective 口径下**不构成"更强"卖点**；其正当性仅在兜底与探索更优目标。

## 影响

- **变容易**：评审调权有了可审计、零训练、理论最优的默认路径；灰度开关单点真值（`config.use_review_mappo()`），默认关时对既有链路零影响。
- **变困难 / 需注意**：`analytic` 需 `evidence`/`consensus` 同时传入——**插入点 A（辩论侧）当前仅传 `use_mappo=True` 未传两者，解析式分支不可达、落到 RL/规则路径**（已知偏差，见 `engines/agent_debate.py:164`）。即"点 A 仅走 RL，解析式仅点 B 可达"。
- **需重新审视**：任何"MAPPO 在线调权超一切"的旧叙事**作废**（可证伪的假话）；对外统一改为上述三位一体。

## 备选方案（被否决）

- **对外宣称"RL 调权超一切"**：与"解析式占满头寸"实测矛盾，属声称 > 证据，否决。
- **为"提升 effective"继续投入 RL 算力**：上界已被解析式封闭（§证据），性价比为负，否决；RL 仅保留兜底/探索定位。
- **默认开启灰度**：违反"行为零变化"上线纪律，且 `analytic` 需上游字段就绪，否决（保持默认关）。
