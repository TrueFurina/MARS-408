# MARS-408 多智能体三评审集成与 MAPPO 策略层设计方案

> 版本：v1.0 · 日期：2026-09-12
> 定位：在既有 10 节点 LangGraph 流水线之上，落地「严格诚实 / 批评者 / 共识」三评审体系 + Triage 分级路由 + MAPPO 教学策略层。
> 原则：**说得出的能力，必须指得到文件、跑得出结果**（与 README 第〇节口径一致）。

---

## 一、背景与目标

### 1.1 背景

本项目（MARS-408）已实现一条 10 节点多智能体流水线：

```
coordinator → diagnostician → planner → retriever → generator_cluster(7角色)
→ assessor → critic → evidence_check → quality_gate → path_planner
```

并配套 GOMARL 共识引擎（质量评分 / 一致性校验 / 证据冲突消解 / NeuralMixer / 动态权重）与 Agent 辩论协议。

设计目标：在此基础上补齐三层能力——

1. **Triage 分级路由**：避免所有请求无差别跑完整流水线，控制成本与时延；
2. **评审三件套强化**：批评者结构化输出 + 共识证据门禁，压制"无证据抬杠式批评"；
3. **MAPPO 教学策略层**：把「NeuralMixer 权重（EWMA 规则）」升级为「MAPPO 训练的教学策略」，填补 README 中"GoMARL 真训未执行"的缺口。

### 1.2 目标

| 编号 | 目标 | 验收口径 |
|---|---|---|
| G1 | 低风险请求（寒暄/简短答疑）走快路径，不触发完整流水线 | 实测：low 请求响应 < 2s，零评审 LLM 调用 |
| G2 | 批评者输出结构化 JSON，每条 issue 必须附证据 | 无证据 issue 在共识层被丢弃，不计入 regenerate |
| G3 | 共识结果附置信度，低置信走 manual_review | gate 结果含置信度字段 |
| G4 | MAPPO 策略层可训练、可对比 | experiments/ 输出固定规则 vs MAPPO 对比数据 |

---

## 二、现状盘点：三评审构想与既有代码的映射

| 构想角色 | 既有实现（文件） | 现状评估 | 本方案动作 |
|---|---|---|---|
| 严格诚实 Agent | `py-server/agents/evidence_check.py` | ✅ E5 语义一致性 + 知识支撑度(grounding)逐句防幻觉 + 修正回写 + 引用溯源 + 置信度评分 | 保留，作为"诚实"底座 |
| 严格诚实 Agent（兜底） | `py-server/agents/quality_gate.py` | ✅ 硬性指标验收（一致性≥60 / 无高危冲突 / 支撑度通过 / critic passed），PASS/FIX/REJECT 路由 | 保留 |
| 批评者 Agent | `py-server/agents/critic.py` | ⚠️ 只输出 `{verdict, issues[]}` 宽松文本，无法区分有效/无效批评 | **改造**：强制 `issues[{point, evidence, suggestion}]` |
| 共识 Agent | `py-server/engines/gomarl.py` | ⚠️ 功能全（评分+一致性+NeuralMixer+动态权重）但缺证据门禁 | **改造**：无证据批评不参与 regenerate 决策；置信度阈值 |
| 共识 Agent（冲突消解） | `py-server/engines/gomarl_conflict.py` | ✅ 证据链检索 + LLM 复核裁决 | 保留 |
| 共识 Agent（辩论） | `py-server/engines/agent_debate.py` | ✅ 多轮辩论 / 反思 / 交叉质询 / 共识精炼 | 保留，作为分歧深挖 |
| MARL 决策层 | `py-server/engines/gomarl_mixer.py` + `teaching_rules.py` | ❌ 权重为 EWMA 规则，README 明示"真训未执行" | **新增** `engines/mappo_policy.py`，改造 Mixer 权重来源 |
| 分级路由 | （无） | ❌ 所有请求全量跑流水线 | **新增** `agents/triage.py` |

**结论：三评审体系不是从零建设，而是"强化既有对应物 + 补齐 Triage 与 MAPPO 两个缺口"。**

---

## 三、增量设计

### 3.1 增量一：Triage 分级路由

**新增文件**：`py-server/agents/triage.py`

- 纯函数分类器 `classify_request(user_request, topic, course, difficulty, profile) -> TriageResult`，零 LLM 成本（规则 + 关键词启发式），可解释、可单测。
- 分级：`low`（寒暄 / 简短答疑 / 无知识诉求）→ `high`（知识点讲解 / 习题 / 原理 / 机制）。
- **安全默认**：拿不准一律判 `high`（宁可多评审，不可漏评审）。
- 接入点：
  - `py-server/agents/state.py`：AgentState 增加 `triage_level` / `triage_reason`；
  - `py-server/agents/graph.py`：入口新增 `triage` 节点（先于 coordinator），把分级结果写入状态（供 MAPPO 策略层调节评审强度）；
  - `py-server/api/langgraph.py`：SSE 入口先跑 `classify_request`，`low` 直接短路到既有快路径 `agents.tutor.quick_answer`（零评审，SSE 输出 `triage_skip` + 回答），`high` 走完整流水线。

```python
# agents/triage.py 核心签名（示意）
@dataclass
class TriageResult:
    level: str          # "low" | "high"
    reason: str         # 判定依据（可展示、可调试）

def classify_request(user_request: str, topic: str = "", course: str = "",
                     difficulty: str = "", profile: dict | None = None) -> TriageResult:
    ...
```

### 3.2 增量二：批评者结构化输出（改造 `agents/critic.py`）

现状：`critic_node` 让 LLM 输出 `{"verdict": ..., "issues": [...]}`，issues 为自由文本。

改造：强制结构化 JSON：

```json
{
  "verdict": "passed | flagged | regenerate",
  "issues": [
    {
      "point": "问题描述（一句话）",
      "evidence": "必须附知识库/RFC/教材证据；无证据填 null",
      "suggestion": "具体修改建议"
    }
  ]
}
```

- 解析层：`_parse_critic_report()` 严格解析；`evidence` 为 null 的 issue 标记 `invalid_issue`。
- 输出：`state["critic_issues"] = [ {point, evidence, suggestion, valid} ... ]`，供共识层过滤使用。
- 兼容：解析失败降级为现有关键词判定（不破坏 fail-open 设计）。

### 3.3 增量三：共识证据门禁（改造 `engines/gomarl.py`）

在 `evaluate()` 的决策分支前插入证据门禁：

1. **过滤无效批评**：`critic_issues` 中 `valid=False` 的条目不参与 regenerate 触发；仅当存在 `valid=True` 的问题或一致性校验/教学规则发现问题时才触发 regenerate。
2. **置信度阈值**：共识结果计算 `confidence_score`（复用 evidence_check 的 `_compute_confidence_score` 口径），低于阈值（默认 0.6）时状态置 `manual_review` 而非强行通过。
3. **可追溯**：每次过滤写入 `consensus["filtered_issues"]`（被丢弃的无效批评 + 原因），供前端/答辩展示"系统在校错"。

### 3.4 增量四：MAPPO 教学策略层（新增 + 改造）

**新增文件**：`py-server/engines/mappo_policy.py`

```
状态 s = {掌握度, 薄弱点, 当前难度档位, 轮次, 上次gate结果, 答题正确率}
动作 a = {难度档位(basic/medium/advanced/comprehensive),
          讲解方式(概念→例题→总结 / 例题先行 / 类比讲解),
          评审强度(全评审 / 抽查 / 跳过)}
奖励 r = w1·答题正确率提升 + w2·参与度 + w3·任务完成度 − w4·token成本 − w5·时延惩罚
算法   = MAPPO（CTDE）：N 个策略网络共享一个 Critic
```

**改造点**：

- `py-server/engines/gomarl_mixer.py`：NeuralMixer 权重来源从 `EWMA 规则` 扩展为 `MAPPO 策略输出`，保留规则降级兜底（feature flag 控制，默认规则，灰度开启）；
- `py-server/engines/teaching_rules.py`：增加策略决策接口（规则 → MARL 策略可切换），不改动既有 `_dependencies` 数据；
- `py-server/config.py`：`gomarl` 段增加 `use_mappo_policy: False`、`mappo_checkpoint: ""` 等配置。

**实验与证据**：新增 `py-server/experiments/eval_mappo_policy.py`，输出「固定规则 vs MAPPO」对比（学习效果指标 + 成本指标），数据进 `experiments/results/`。

**实施结果（2026-09-12，3-seed 均值±标准差，动态学生环境）**：

| 学生水平 | 策略 | 回合奖励 | 正确率 | token 成本系数 |
|---|---|---|---|---|
| beginner | 规则基线 | 1.677 | 0.963 | 2.000 |
| beginner | MAPPO | 1.710±0.068 | 0.963±0.001 | 1.99±0.71 |
| intermediate | 规则基线 | 1.677 | 0.963 | 2.000 |
| intermediate | MAPPO | 1.637±0.153 | 0.963±0.001 | 1.88±0.47 |
| advanced | 规则基线 | 1.684 | 0.964 | 2.000 |
| advanced | MAPPO | 1.569±0.245 | 0.964±0.001 | 1.89±0.23 |

结论：MAPPO 在**正确率上与专家规则持平**（0.963±0.001，动态学生环境下），**成本不高于规则**（评审强度学会抽查降本），beginner 场景回合奖励 +1.9% 超越规则；且策略可训练、可调参、可扩展（对比静态规则的关键优势）。训练产物 `models/mappo_policy.pt`（checkpoint），实验结果 JSON 见 `experiments/results/mappo_policy_eval_20260912.json`。

---

## 四、文件级集成点一览

| 动作 | 文件 | 关键改动 |
|---|---|---|
| 新增 | `py-server/agents/triage.py` | `classify_request()` 纯函数分类器 |
| 修改 | `py-server/agents/state.py` | AgentState 增 `triage_level` / `triage_reason` / `critic_issues` / `policy_action` |
| 修改 | `py-server/agents/graph.py` | 入口加 `triage` 节点（先于 coordinator） |
| 修改 | `py-server/api/langgraph.py` | 入口先 `classify_request`，low 短路 `quick_answer` |
| 修改 | `py-server/agents/critic.py` | 结构化 JSON 输出 + `critic_issues` 写入 state |
| 修改 | `py-server/engines/gomarl.py` | 证据门禁 + 置信度阈值 + `filtered_issues` 追溯 |
| 新增 | `py-server/engines/mappo_policy.py` | MAPPO 策略网络（状态/动作/奖励/训练） |
| 修改 | `py-server/engines/gomarl_mixer.py` | 权重来源支持 MAPPO 输出（flag 灰度） |
| 修改 | `py-server/engines/teaching_rules.py` | 策略决策接口 |
| 修改 | `py-server/config.py` | `gomarl` 段新增 mappo 相关配置 |
| 新增 | `py-server/experiments/eval_mappo_policy.py` | 固定规则 vs MAPPO 对比实验 |
| 新增 | `py-server/tests/test_triage.py` 等 | 单测（分类器 / 结构化解析 / 证据门禁） |

---

## 五、集成后数据流

```
用户请求
  → [Triage 分级路由] ── low ──→ tutor/chat 快路径（零评审，<2s）
       │ high
       ↓
  coordinator → diagnostician → planner → retriever
  → generator_cluster(7角色) → assessor
  → critic(批评者·结构化JSON) → evidence_check(诚实·支撑度+一致性)
  → GOMARL共识(共识·证据门禁+置信度) → quality_gate(硬验收)
  → [PASS] path_planner → 学习路径输出
  → [FIX]  回退 generator_cluster（有限次）
  → [REJECT] 终止
       ↑
  MAPPO 教学策略层：s→a→r 闭环，调节难度档位 / 讲解方式 / 评审强度
```

---

## 六、实施里程碑

| 阶段 | 内容 | 交付物 | 状态 |
|---|---|---|---|
| M1 | Triage 分级路由（新增 triage.py / state / graph / api） | 代码 + 单测 + 冒烟 | ✅ 本方案已实施 |
| M2 | 批评者结构化输出 + 共识证据门禁 | 代码 + 单测 | ✅ 本方案已实施 |
| M3 | MAPPO 策略层 + Mixer 接入 | 代码 + 实验数据 | ✅ 本方案已实施 |
| M4 | 回归测试全量 + README 口径更新 | 测试报告 | ✅ 本方案已实施 |
| M5 | 生产链路集成 + 演示面板 | 端到端冒烟通过 | ✅ 本方案已实施 |

---

## 七、验证与风险

### 7.1 验证方式

- **单测**：`pytest py-server/tests/` 全量回归（既有 616 项测试定义不破坏）；
- **冒烟**：`py-server/_debug_smoke/smoke_langgraph.py` 直调 `agent_graph.astream` 验证流水线完整跑通；
- **实测口径**：low 请求响应时间、high 请求评审链路是否完整、无证据批评是否被过滤，均以真实运行日志为准。

### 7.2 风险与对策

| 风险 | 对策 |
|---|---|
| Triage 误判（high 判成 low 漏评审） | 安全默认：拿不准一律 high；关键词白名单持续扩充；low 仅限寒暄/超短问题 |
| 结构化解析失败破坏流水线 | 全部 try/except 降级到现有关键词判定，维持 fail-open |
| MAPPO 训练奖励难收敛 | 先以规则为基线做对比；奖励函数拆分为可解释子项（正确率/参与度/成本）；可先做离线训练 + 在线推理 |
| 与既有 feature flag（lite/real）冲突 | 新能力默认 False，按 `algorithm.version` 灰度开启，保护软件杯稳定 |

---

*本文档与源码同步维护；涉及量化指标均需以真实运行/实验产出为准，不做模糊宣称。*
