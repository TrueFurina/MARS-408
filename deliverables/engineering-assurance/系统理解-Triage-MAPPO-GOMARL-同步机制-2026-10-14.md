# 系统理解 — Triage 分级路由 / 三元评审校验壳 / MAPPO×GOMARL / 双分支同步（2026-10-14）

> 性质：**只读分析**（未改任何源码），供项目负责人审阅。对应 `plans/current.md`「系统理解任务」三项。
> 方法：以代码为唯一事实源（AGENTS.md 铁律），所有结论带 `文件:行号`；文档与代码冲突时**以代码为准并登记漂移**（见 §5）。

---

## 0. 一句话总览

```
请求 → [Triage 纯规则分级] ──low──→ quick_answer 快路径（零评审，API 层短路）
                    │
                    └──high──→ 11 节点 LangGraph 流水线
   triage → coordinator → diagnostician → planner → retriever
     → generator_cluster(7 并行) → assessor → critic
     → evidence_check → quality_gate → path_planner → END
                    （critic/gate 不通过 → 条件回环重试，额度耗尽降级通过或 REJECT）
```

编译图业务节点 **11**（含 triage）；Triage 之外的流水线本体 **10**（`agents/graph.py:99-109`、
`api/langgraph.py:48-49` 口径注释）。对外述「图」用 11，述「Triage 之后的流水线」用 10——
两种口径都正确，勿互相「修正」（AGENTS.md 同款警告）。

---

## 1. Triage 分级路由判定链

**是什么**：纯规则分类器，**零 LLM 成本、可解释、可单测**（`agents/triage.py:1-12` 设计约束）。

**判定顺序**（`classify_request`，`agents/triage.py:69-122`）：
1. 空输入 → 安全默认 **high**（:93-96）
2. 命中高风险关键词任一（讲解/练习/科目类，`_HIGH_KEYWORDS` :26-37）→ **high**（:99-103）
3. 指定了非 easy 难度或指定了课程 → 正式学习请求 → **high**（:106-111）
4. 短请求（<8 字，:50）命中低风险词（寒暄/确认，:41-47）→ **low**（:114-118）
5. 兜底：有实质内容但无明确信号 → **high**（:120-122）

**low 的短路发生在 API 层而非图内**（`api/langgraph.py:44-77`）：
- low → `agents.tutor.quick_answer` 单次答疑，**零评审**；产出仍过 `audit_output` 安全审计（:66-67）
- 快路径失败 → 回退完整流水线（`_triage_level = "high"`，:74-75），state 交图内 triage 节点复判
- high → 进 11 节点图；图内 triage 节点（`triage.py:125-154`）把 `triage_level/reason/hits` 写进
  `AgentState`（`agents/state.py:67-70`）供追溯

**诚实边界**：triage 的 docstring 预留了「供 MAPPO 策略层按分级调节评审强度（增量四预留）」
（`triage.py:129`）——这是**预留钩子，当前未接线**（见 §3 风险 R1）。

---

## 2. 三元评审校验壳

### 2.1 结构：三阶段串行壳（critic → evidence_check → quality_gate）

| 阶段 | 节点 | 职责 | 关键机制 |
|---|---|---|---|
| ① 批评者 | `critic`（`agents/critic.py:31-121`） | LLM 审阅教师文档/题库/代码/PPT | 强制 JSON 输出（:62-67）；结构化解析 point/evidence/suggestion + **valid 标记**（:146-181） |
| ② 证据校验 | `evidence_check`（`agents/evidence_check.py:1-25`） | 跨 Agent 冲突 + 知识支撑度 | 薄封装 `engines.gomarl_conflict.conflict_engine`（不重写引擎）；severity 映射 factual→high / semantic→medium / keyword→low（:47-51）；E5 余弦防幻觉（阈值 :55-57） |
| ③ 验收闸门 | `quality_gate`（`agents/quality_gate.py:82-242`） | 硬性阻断不合格产物 | fail-closed（见 2.4）；PASS→path_planner / FIX→generator_cluster / REJECT→END（:245-255） |

### 2.2 三信号与权重（`engines/review_policy.py`）

`review_signals(evidence, consensus)`（:67-90+）抽取三个归一到 0-100 的信号：

| 信号 | 来源 | 代码 |
|---|---|---|
| honest（证据/诚实） | `evidence_report.consistency_score` | :71-77 |
| critic（批评者） | `consensus.confidence_score × 100`（缺失 60） | :79-85 |
| consensus（共识） | `consensus.overall_score`，缺失按 status 映射 | :87-96 |

合成公式（ADR-011）：`effective = s_honest + (weighted − uniform)`，均匀权重 (1/3,1/3,1/3) 时
`effective == s_honest`（= 现状，**偏移 0，行为零变化**）——这是灰度安全契约（`review_policy.py:48`、
`quality_gate.py:46-49`）。

### 2.3 权重来源优先级（`quality_gate.py:52-79`）

```
state["review_weights"]（上游显式注入）
  > MAPPO 在线决策（仅当 config.use_review_mappo() = True，config.py:319-321 默认 False）
  > None → 均匀权重（现状）
```

ADR-011 决策：**生产默认 = 解析式最优**（`RULE_MODE="analytic"`，`review_policy.py:474`），
RL（MAPPO）被重新定位为**兜底**而非「更强」；任何异常 → 均匀权重（fail-open）。
接入点两处：**插入点 B** = quality_gate（只换判定输入，PASS/FIX/REJECT 门不动）；
**插入点 A** = `engines/agent_debate.py:145-171`（2-agent 冲突 regenerate 路径的内容预算分配）。

### 2.4 两层「证据门禁」与 fail-closed 转向

1. **Critic 证据门禁**（`critic.py:83-93`）：verdict=flagged/regenerate 但全部 issue 无 evidence
   → 降级 passed，无证据批评记入 `filtered_issues`——**无证据批评不能触发重生成**。
2. **Quality Gate fail-closed**（`quality_gate.py:204-240`）：执行异常 → 显式 `degraded` +
   路由 fix/reject，**绝不谎报「质检通过」**。代码注释明载原 fail-open 会违反诚实红线故已改。
   ⚠️ 但 CLAUDE.md:74 仍写「Quality Gate 是 fail-open」——**文档陈旧，以代码为准**（见 §5-D1）。

另注意 Critic 自身的 LLM 异常仍是 passed（`critic.py:113-119`，防误杀）——即「评审器挂掉」放行、
「闸门挂掉」阻断，两层语义不同，勿混为一谈。

---

## 3. MAPPO 教学策略层 × GOMARL 共识引擎

### 3.1 两条 MAPPO 线（互不共享权重）

| | 408 教学策略层 | career 鲶鱼策略层 |
|---|---|---|
| 文件 | `engines/mappo_policy.py`（CTDE：Actor-Critic+GAE+PPO clip，:286/:471） | `engines/career_policy.py` |
| 开关 | `config.gomarl.use_mappo_policy`（config.py:170 = **True，已激活**） | `config.career.use_career_mappo`（默认 **False**） |
| 写入点 | `coordinator.py:65-71` → `state["policy_action"]` | `agents/career_nodes.py:221`（对抗模式决策） |
| 无 torch/未训练时 | 自动降级规则动作（source=rules，fail-open） | 诚实降级规则版（career_policy.py:330） |
| 唯一共享代码 | `mappo_policy._build_networks` 被 career_policy.py:61 只读导入 | ← 同一处 |

**跨线耦合 = ADR-015 登记的技术债**：career 依赖 408 侧**下划线私有 API** `_build_networks`，
408 若重构该签名会断 career（ADR-015「影响」节）。

### 3.2 GOMARL 四件（共识的是「评分/证据/权重」，不是动作选择）

```
gomarl.py（共识决策编排：LLM 1-10 评分 + 规则降级 → passed/regenerate/manual_review）
  ├─ gomarl_conflict.py（三级冲突检测：单Agent事实 → 跨Agent矛盾 → E5 语义分歧）
  ├─ gomarl_mixer.py（NeuralMixer 神经加权 + 动态权重 EWMA）
  └─ gomarl_bridge.py（零 import 方 = 死代码，仅 logger 与 references 文档命中）
```

### 3.3 MAPPO 与 GOMARL 的三个真实接入点

| # | 位置 | 数据形态 | 开关状态 |
|---|---|---|---|
| 1 | `gomarl_mixer.py:886-900`（`_compute_dynamic_weights` 尾部） | `student_profile` → `{agent: 乘子}` → 命中 key 相乘并重新归一化；异常 fail-open 保持规则权重 | `use_mappo_policy=True`（**已激活**） |
| 2 | `quality_gate.py:52-79`（插入点 B，三元评审权重） | features → `decide_review_weight` → 三信号权重 | `use_review_mappo` 默认 **False**（灰度关） |
| 3 | `agent_debate.py:145-171`（插入点 A，内容预算分配） | 权重 → 精炼注意力/内容预算，仅 2-agent regenerate 路径 | 同 #2 |

未训练时 `agent_weight_adjust` 返回的是**规则导出的乘子**（mappo_policy.py:396/:406）——
即接入点 1 名义「MAPPO 调权重」，无模型时实为规则调权重。

### 3.4 诚实状态（对外口径红线，ADR-011「三位一体」）

① 解析式最优是生产默认；② RL 只在解析式失效场景兜底；③ **career 鲶鱼 MAPPO 是当前唯一有
真实增益数据的 RL 环节**（3-seed 真训 reward 全超规则版，ADR-011 证据表）。
「用 RL 在线调权超越一切基线」的常见叙事在本项目**不成立**——这是实测后的订正，勿回退。

---

## 4. main → career-literacy 单向同步机制

**治理**（ADR-015，Accepted 2026-09-14）：
- 双分支双身份：`main` = 408 考研（冻结基线），`career-literacy` = 软素养实训（活跃）
- 零侵入：career 全部新增代码 `career_*` 前缀（`engines/career_policy.py`、`agents/career_nodes.py`、
  `api/career_training.py` prefix `/career`、`db/career_store` 独立写路径）
- 唯一跨边界 = **只读复用**（`career_policy.py:60` 导入 `_build_networks`；`api/agents.py` →
  `agent_debate` 调用已 fail-open）
- 合并方向：**只允许 main → career-literacy 单向同步底座 bugfix**（改造方案 :485）；
  竞赛期不反向合并

**机制实证**（git 历史）：同步 = 定期 `git merge origin/main`，近次 6 个 merge 提交
`7f7893f / 305dec7 / 7aa1e75 / ec12856 / 2beed79 / e2c396c`（commit message 均为
"Merge remote-tracking branch 'origin/main' into career-literacy"）。
remote 两个：`origin`（GitHub TrueFurina/MARS-408）+ `mangdehenzhi`（本地副本，CLAUDE.md:178）。

**防双向漂移的操作要点**：career 侧提交只 push `origin career-literacy`；main 侧修 bug 后
merge 过来；任何「把 career 功能合回 main」的动议须走 ADR 评估（竞赛期禁止）。

---

## 5. 本次核查发现的漂移与风险清单

| # | 类型 | 事实 | 证据 | 建议 |
|---|---|---|---|---|
| D1 | 🔴 文档漂移 | CLAUDE.md:74 称「Quality Gate 是 fail-open」；代码早已 fail-closed（异常 → degraded + fix/reject） | `quality_gate.py:204-240` 注释明载改因 | 改 CLAUDE.md:74 |
| D2 | 🟠 文档漂移 | CLAUDE.md:179 称 main 冻结于 `8065295`；实际 main HEAD 已到 `d21cd72`（对象库损坏恢复提交） | `git log main -1` | 更新分支矩阵 |
| D3 | 🟢 文档漂移 | CLAUDE.md:101「种子 1883 chunks + 200 题」；实际 2015 + 230 | `verify_seed_data_split.py` 机验输出 | 顺手改 |
| R1 | 🟠 预留未接线 | triage docstring 预留「MAPPO 按分级调节评审强度」（增量四），当前 `policy_action` 无下游消费者——决策只进 state 供追溯，不改变产物 | `triage.py:129`；全目录 grep `policy_action` 仅 coordinator 写入 + smoke/test 断言 | 要么接线要么删钩子，勿留中间态 |
| R2 | 🟡 死代码 | `engines/gomarl_bridge.py` 零 import 方 | 全仓 grep 仅命中自身 logger:17 与一份 references 文档 | 归档或补调用方 |
| R3 | 🟡 脆弱耦合 | career 依赖 408 私有 API `_build_networks` | ADR-015「影响」节已登记 | 提为公开稳定 API |
| R4 | 🟡 环境约束 | `models/` 权重被 gitignore（mixer :37-38 自述）⇒ CI 环境神经推理必然降级；`mappo_policy.pt` 仅本机存在 | ADR-011 环境报告 | 对外演示须备降级口径 |

---

## 6. 给负责人的三句话

1. **判定链是「低成本前置 + 三层评审壳」**：Triage 纯规则把寒暄短路掉（零评审），
   高风险进 11 节点图过 critic→evidence_check→quality_gate 三阶段；三信号均匀权重下
   行为与旧版逐字一致，MAPPO 调权重全部走灰度 flag（两个默认关、一个已激活但无模型时即规则）。
2. **MAPPO 与 GOMARL 不是两套独立系统也不是一层**：三个真实接入点（mixer 动态权重已激活 /
   gate 评审权重灰度 / debate 内容预算灰度），共识对象是评分与证据取舍，动作选择归 MAPPO。
3. **同步机制 = 单向 merge + 前缀隔离**，历史清白（6 个 merge 提交可查）；主要风险不在机制而在
   文档陈旧（D1-D3）与两个「名义神经、实为规则」的降级路径——对外口径必须按 ADR-011 三位一体叙事。
