# 代码审查示范报告 · `review_policy.py` + `db/embedder.py`

> **审查依据**：本项目《代码审查标准.md》红线速查表（§0）、反模式黑名单（§3）、分级清单（§4）；《代码审查流程.md》角色与门禁。
> **审查对象**：MARS-408 火山杯作品（`main` 分支）的核心红线锚点模块
> - `py-server/engines/review_policy.py`（993 行）—— ADR-017 评审单一真值源
> - `py-server/db/embedder.py`（275 行）—— embedding 硬约束
> **审查人**：火眼眼（代码审查专家）
> **日期**：2026-09-15
> **范围说明**：本次为"示范性审查"，聚焦两个最能暴露红线遵守情况的核心模块，验证标准是否贴合实际。后续可扩展到 `frugal_rag.py` / `gomarl.py` / 前端 view 层。

---

## 一、总体印象

这两个文件是本项目"踩坑史最密集"的区域（`review_policy.py` 顶部与多处 docstring 自述了 NaN 静默漂移、三份纪律门复刻漂移、RL 假装有效等历史事故）。**整体质量明显高于项目平均水平**，主要体现在：

1. **红线意识已内化为代码**——硬约束（`e5-base-v2/768`、单一真值源、诚信降级）不是靠注释提醒，而是写进了常量、函数边界与失败兜底。
2. **文档化即防御**——大量 docstring 如实记录"哪些历史论证已失效、哪些数字不可再宣称"，把诚信约束固化进代码可读性本身。
3. **失败路径 fail-open 设计成熟**——`torch` 缺失、`features` 非法、解析失败都安全降级到均匀权重/规则，不会阻断启动。

需要补强的是**架构层面的关注点分离**与**并发/资源副作用**，这些 CI 抓不到、但会在多进程部署或维护阶段咬人。

---

## 二、红线合规核查（对照标准 §0 红线速查表）

| 红线条款（标准 §0） | 结论 | 证据 |
|---|---|---|
| embedding 改回 MiniLM/384 会静默归零 | ✅ **合规** | `embedder.py:31-32` 写死 `EMBED_MODEL_NAME="intfloat/e5-base-v2"` / `EMBED_DIM=768`；`get_embed_dim()` 仅从 config 读并回退常量 |
| 判定语义单一真值源（ADR-017） | ✅ **合规且落实优秀** | `discipline_gate`(516) / `review_precision`(498) 为模块级唯一实现；`select_action`(829/839/842)、`evaluate_policy._apply_discipline`(964)、`decide_review_weight`(896) **全部委托调用**，无第二份复刻 |
| RL 效果一律以 `review_env_calibrated.py` 为准 | ⚠️ **边界风险**（见 🟡R1） | 合成 `ReviewEnv` 虽在 docstring 标注"论证已失效"，但仍是 `train_ppo`/`warmup_with_rules`/`evaluate_policy` 的默认环境，存在被误用的数字出口 |
| 诚信：torch 不可用不得伪造训练结果 | ✅ **合规** | `train_ppo`(674) / `warmup_with_rules`(635) 明确 `torch 不可用 → 返回 {"trained": False}`，不画曲线 |
| 禁止 `except pass` 等静默吞错 | ✅ **合规** | 所有 `except` 均 `logger.warning` 并降级，无裸 `pass` |

**结论**：核心红线零命中 🔴。这正是建立审查标准后要抓的"人审才有价值"的区域——CI 绿不等于红线合规，但这两处恰好是团队用真代价换来的合规。

---

## 三、问题清单（按优先级）

### 🔴  blockers：无

### 🟡  应当修复（suggestion）

**R1 · 合成环境仍是 RL 数字的默认出口（诚信红线边界风险）**
- 位置：`review_policy.py` 模块顶部(52-64) + `ReviewEnv` 类(238-383) + `train_ppo`(661) / `evaluate_policy`(947)
- 问题：docstring 已诚实标注"本环境（合成奖励阶梯）保留仅作历史对照；真实效果以 `review_env_calibrated.py` 为准"，但 `ReviewEnv` 仍是训练与三方案对比的默认环境。未来维护者若直接 `.mean_return` 对外宣称"RL 优于规则"，会重蹈 2026-09-14 已否证的数字事故。
- 建议：① 在模块**顶部**用醒目注释块（而非埋在函数内 298 行）写"本文件 `ReviewEnv`/`train_ppo` 仅供历史对照，**任何 RL 效果宣称必须走 `review_env_calibrated.py` 且先证同分布**"；② 或在 `evaluate_policy` 返回值加 `synthetic=True` 标记，让调用方无法无意识拿去对外。

**R2 · 关注点分离：生产决策代码与实验/training 代码同文件（torch 混入）**
- 位置：`review_policy.py` 同时含生产入口（`decide_review_weight`/`analytic_review_action`，轻量无 torch）与训练/实验（`ReviewWeightPolicy`/`train_ppo`/`warmup_with_rules`/`ReviewEnv`/`evaluate_policy`，依赖 torch）
- 问题：① 导入本模块的调用方即使只用 `analytic_review_action`，也会把整个训练体系（含 `_Actor`/`_Critic` 类定义）拉进内存映像；② 维护者难以一眼区分"哪个是生产真值、哪个是实验"。与 ADR-017"单一真值源"精神相悖——真值应被清晰隔离。
- 建议：将 `ReviewEnv` / `ReviewWeightPolicy` / `train_ppo` / `warmup_with_rules` / `evaluate_policy` 迁到 `py-server/experiments/review_train.py`（已有 `experiments/` 目录），核心模块只留 `discipline_gate` / `review_precision` / `analytic_review_action` / `decide_review_weight` / `review_state_features` / 规则函数。

**R3 · 模块级单例 `_get_shared_policy` 无并发保护**
- 位置：`review_policy.py:919-934`
- 问题：修改全局 `_SHARED_POLICY` 未加锁。多线程并发首次调用可能创建并加载两次模型（420MB），虽最终只保留一个引用，但双初始化浪费资源且 `_torch.load` 可能竞态。
- 建议：用 `threading.Lock` 保护单例创建（double-checked locking 或锁内赋值）。

**R4 · `is_available()` 触发重资源加载（420MB 模型）**
- 位置：`embedder.py:269-275`
- 问题：`is_available()` 直接调用 `_get_e5_model()`，后者会实际 `SentenceTransformer(model_name)` 加载 420MB 模型到内存。**探针函数应有"零副作用"语义**——若健康检查/状态接口频繁调用，会无谓占用 1.5GB 级内存与启动时间。
- 建议：`is_available()` 改为检查依赖与配置就绪（`sentence_transformers` 是否 import 成功 + 模型路径是否存在），真正加载延迟到 `embed_batch` 首次调用。

### 💭  nice to have（nit）

- **N1** `embedder.py:96` `np.load(..., allow_pickle=True)`：本地可信缓存可接受，但建议在加载前校验文件属主/路径，避免被替换为恶意 `.npz` 时执行 pickle 负载。
- **N2** `embedder.py:52` 内存上限 `_CACHE_MAX=500000` × 768×4B ≈ **1.5GB** 峰值。建议改用 LRU 或把上限降到与语料规模匹配（2113 条真实语料远小于此），避免大内存机器上静默涨到 OOM。
- **N3** `review_policy.py` 权重表示混用：常量 `REVIEW_WEIGHTS` 用 tuple，而 `UNIFORM_WEIGHTS` 用 dict；`_weights_of` 负责 tuple→dict 转换。可统一为 dataclass 或全 dict，降低心智负担。
- **N4** `train_ppo` 返回的 `improved` 字段已在 docstring(806-809) 明确"不可靠、不得单独作为证据"，但仍默认返回。建议标记 `@deprecated` 或默认不返回，只保留 `improved_deterministic`。
- **N5** `review_reward` 成本归一化分母 `2000`(217) 与 `ACTION_TOKENS` 实际量级(800–1000)不匹配（cost 分量永远 ≤0.5），若非有意为之，建议对齐量纲。

---

## 四、亮点（应当保持并推广）

- 👍 **`_features_valid` 显式拦截 NaN/Inf**（177-188）：文档点明"NaN 进入线性层不抛异常、会静默产出任意权重"，这是用事故换来的防御，建议列为标准 §3 反模式黑名单新条款（"未在 NN 输入入口拦截非有限值"）。
- 👍 **缓存的模型名失效保护**（`embedder.py:103-108`）：模型切换自动失效旧缓存，避免维度错配——正是 memory 里"embedding 改回 MiniLM 会静默归零"的针对性防御。
- 👍 **纪律门单一真值源的 docstring 自述**（526-532）：把"三份复制曾静默漂移、导致假警报误诊"写进代码，是项目级知识沉淀的范例。
- 👍 **`review_reward` 强制分项透视、禁止外部复刻公式**（211-213）：直接封堵了"脚本复刻阈值导致精准率恒为 0 而单测全绿"的历史事故。

---

## 五、标准自检：本次审查暴露《代码审查标准.md》需补强的点

示范审查的目的之一是验证标准是否贴合实际。以下条款建议补入标准：

1. **§0 红线速查表新增**：「合成/训练环境（`ReviewEnv` 类）禁止作为对外效果宣称的数据源；RL 效果数字必须来自 `review_env_calibrated.py` 且先证同分布」。本次 R1 证明该边界必须显式成红线，而非仅埋在 docstring。
2. **§0/§4 新增架构红线**：「生产决策代码不得与实验/训练代码（torch 重依赖）同文件；单一真值源函数必须被清晰隔离」。对应 R2。
3. **§3 反模式黑名单新增**：「模块级单例/全局可变状态（如 `_SHARED_POLICY`、缓存 dict）无并发保护」——对应 R3。
4. **§3 反模式黑名单新增**：「探针/可用性函数（`is_available` 类）触发重资源加载（如加载 420MB 模型）」——对应 R4。
5. **§3 反模式黑名单新增**（来自本次 👍）：「未在神经网络输入入口显式拦截 NaN/Inf/维度不符」。

---

## 六、下一步建议

1. **优先处理 R1**（诚信边界）：在 `review_policy.py` 顶部加醒目"合成环境禁用"注释块——零代码改动、零风险，却堵住最大的数字事故复发口。
2. **R3/R4** 是低风险小改，可随下次相关 PR 一并修。
3. **R2** 拆分是一次性重构，建议单独开 PR（不混进功能改动），并补测试守护"生产入口不触发 torch 重加载"。
4. **标准补强**（第五节 5 条）建议直接并入《代码审查标准.md》——示范审查已证明这些条款源于真实痛点，不是空想。

> 如需，我可以把本报告落到 `docs/代码审查示范-ReviewPolicy.md` 并提交到 `main`（火山杯线），同时把第五节 5 条补进《代码审查标准.md》。是否要我执行落盘？
