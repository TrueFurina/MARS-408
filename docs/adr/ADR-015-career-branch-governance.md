# ADR-015 — career-literacy 分支治理（双分支双身份 · 零侵入 · `career_*` 公约）

- **状态**：Accepted（记录**现有**分支与代码组织约定）
- **日期**：2026-09-14
- **决策人**：架构师（architect）
- **相关**：ADR-007（导入队列单写者）；ADR-011（三元评审权重 MAPPO 化）；`docs/MARS-408与芒得很职集成方案_v1.0.md`
- **关联代码**：`engines/career_policy.py`、`agents/career_nodes.py`、`api/career_training.py`、`db/career_store`

## 背景

同一仓库（`NetLearn/study-help-pro`）承载**两套产品身份**：

| 分支 | 身份 | 状态 |
|------|------|------|
| `main` | **MARS-408**（408 考研个性化学习，软平/软件杯线） | **冻结**（基线不动） |
| `career-literacy` | **芒得很职**（计算机学生软素养提升平台，三创赛线） | **活跃开发** |

career 线在既有 408 代码基座上生长（复用 LLM 通道、GOMARL 共识、MAPPO 网络构造等）。若缺乏明确边界，career 改动极易污染已冻结的 408 主线，造成"改一处、崩两线"。本 ADR 固化**分支治理与代码前缀公约**，把"零侵入"从口头承诺变为可验证约束。

## 决策

1. **双分支双身份**：`main` = MARS-408（冻结），`career-literacy` = 芒得很职（活跃）。两线共仓库、共 408 底座，但**变更集合互不越界**。
2. **零侵入（zero-intrusion）**：career 全部新增代码以 **`career_*` 前缀**沙箱化：
   - 策略层 `engines/career_policy.py`（P3③ 鲶鱼机制 MAPPO 化）
   - 节点层 `agents/career_nodes.py`（场景脚本 / 对抗追问）
   - 路由层 `api/career_training.py`（prefix `/career`，纯 CRUD，隔离）
   - **不改任何 408 源文件**。
3. **唯一跨边界 = 只读复用**：`engines/career_policy.py:60` 只读导入 `engines.mappo_policy._build_networks`（网络构造 helper，复用构造框架但不复用其权重）；`api/agents.py` → `agent_debate` 的调用已 **fail-open**（灰度默认关，异常退化规则版）。
4. **写路径隔离**：career 走独立 `db.career_store`，**不写 408 的 `vectordb`/`netlearn_kb`** ⇒ 不引入第二个向量库写者，ADR-007 单写者约束（`uvicorn --workers 1`）继续成立。
5. **公约**：career 侧任何新增模块、路由、table、配置项一律 `career_*` 前缀；跨边界调用只允许"只读 + 已 fail-open"。

## 证据（只读静态审计，2026-09-14）

- `agents/career_nodes.py` 对 `review_weights` / `consensus` / `quality_gate` / `gomarl` 的 grep **零匹配** ⇒ 无侧信道。
- `engines/gomarl*.py` 对 `career` / `review_policy` 的 grep **零匹配** ⇒ 新层是**单向下游消费者**，GOMARL 四文件零反向依赖。
- `api/career_training.py:17` prefix `/career`，纯 CRUD，与 408 路由隔离。
- career 端点**无 GPU/模型启动依赖**：MAPPO 懒加载、默认关、全链路 fail-open 回退规则版（可运维性 GO）。
- `config.career.use_career_mappo` 默认 `False` ⇒ 线上默认走**规则版**。

## 影响

- **变容易**：career 与 408 可并行演进、独立验收；冻结主线不被新实验污染；单写者/零侵入可被 grep 复核。
- **变困难 / 需注意**：
  - `career_policy.py:60` 依赖 `mappo_policy` 的**下划线私有 API**（`_build_networks`），属脆弱耦合——408 侧若重构该签名会断 career（**已登记技术债**，建议提为公开稳定 API 或 career 自带网络构造）。
  - 同仓库双身份对文档、CI、发布口径提出更高纪律要求（同一份 README/CLAUDE.md 需区分两线）。
- **诚实红线**：career 鲶鱼默认**规则版**（`use_career_mappo=False`）；对外若标榜为"神经网络智能"，须按 GoNoGo G1–G4 标注"v1 规则原型"，不得默认暗示已启用 MAPPO。

## 备选方案（被否决）

- **在 `main` 上直接开发 career**：会破坏 408 冻结基线、使两线变更互相污染，否决。
- **拆为独立仓库**：需重复维护 408 底座（LLM/GOMARL/MAPPO），成本高于收益，且比赛期时间窗不允许，否决（双分支双身份为折中）。
- **放开 career 直接写 408 `vectordb`**：引入第二写者、破坏 ADR-007 单写者语义，否决。
