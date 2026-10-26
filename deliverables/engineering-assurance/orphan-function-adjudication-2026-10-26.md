# 孤儿函数闸门裁定（T1 40 项逐项结论）—— 2026-10-26

> 工具：`scripts/audit_orphan_functions.py`（纯 stdlib AST，report-only）
> 清单：`scripts/orphan_adjudicated.json`（已裁定清单 + 已裁定基线）
> 关联：`deliverables/engineering-assurance/orphan-function-audit-2026-10-17.md`（上一轮巡检）
> 触发：T1=40 导致 `--gate` exit 1，清单悬置十天无结论 → 本轮做**裁定与治理**

## 零、一句话结论（先说清楚本轮没做什么）

**本轮一个函数都没删。** 40 项全部经 QA 逐项核完（含 `git grep` 全仓跨扩展名复核），
结论是 **0 假阳性、40 项全部为真正的零引用**。本轮做的事只有三件：

1. 把 40 项按证据分成三群（A 整模块零 import / B 已退役 CLI / C 活模块上的死方法），逐项写下裁定；
2. 给闸门补上**裁定层**（`__all__` 公开面分类 T4 + 已裁定 allowlist + 已裁定基线 + 僵尸检测 + 拒绝刷新），
   让它从「永远红的待办」变成「有裁定的准入」：存量有账可查，**新增必红且点名**；
3. 把「为什么本轮不删那 32 项」的决策理由写成本文件，留给下一阶段取舍。

**口径红线**：本文件及任何引用它的文档，都**不得**出现「已清理」「已收敛」「已删除孤儿函数」
之类的表述——本轮是裁定与治理，代码零改动（`py-server/` 生产源码一个字节没动，
`git status` 可证）。唯一的代码改动在 `scripts/` 与 `py-server/tests/` 的测试基线断言。

---

## 一、方法

- 生产面 = `py-server/` 运行时真实 import 的代码（root `.py` + `agents/api/app/app_config/db/engines/schemas/services/shared/tools/utils`），
  实测 **207 文件 / 1548 个函数定义**。
- 引用面 = 全仓任意 `.py`（生产 + 测试 + 实验 + 脚本，实测 518 文件），排除
  `.venv/archive/deploy/dist/.git/node_modules/submission/deliverables`。
- 判定链（详见 §二）：`decorated/dunder/abstract → T3`；`名字出现在字符串字面量 → T3`；
  `生产内被调用 → 排除`；`仅测试/脚本引用 → T2`；`全仓零引用 → T1`；
  再对 T1 做两层裁定：`命中 allowlist → 跳过`、`属于 __all__ 公开面 → T4`。
- 人工复核：QA 对 40 项逐条 `git grep` 全仓（不限扩展名，含 `.md`/`.yml`/`.json` 里的引用形态），
  确认无遗漏调用方。本轮结论建立在「机检给候选、人工下裁定」的分工上，不是机检直接给结论。

## 二、为什么 QA 判定 0 假阳性（判定链的三层保守）

机检要判「零引用」，必须先把所有可能的**间接**调用路径都排除掉。脚本的三层保守设计
使漏判方向被压到极小，因此「判不出来」的概率远低于「判错」：

| 层 | 判据 | 覆盖的漏判成因 | 实测规模 |
|---|---|---|---|
| 第 1 层 | `decorator_list` 非空 / 名字是 dunder / 含 `@abstractmethod`(`@abstractproperty`) | 框架入口（FastAPI 路由）、协议方法、魔术方法 | 计入 T3，T3 共 **623** 个 |
| 第 2 层 | 名字出现在**全仓 `.py` 的 identifier 形态字符串字面量**中（`dyn`） | `getattr(obj, "f")` / `importlib` / 注册表字符串分发 / 任务队列按名调度 | 同一 T3 池 |
| 第 3 层 | `called` 集合收纳 `Call`(Name/Attribute) + **任意非调用 `Attribute` 访问** + **`ast.alias`（含 `import f as g` 的两端）** | 传给回调、赋值别名、别名导入 | 生产/全仓两遍扫描 |

两条**反向**证据说明这套判据没有系统性偏差：

- 上一轮（2026-10-17）曾因漏扫 `ast.alias` 把 `try_consume` 误判为 T1（别名导入不可见），
  修复后 T2 由 858 → 37；这证明 `called` 的收纳口径是**宽**的，宁可多认引用。
- 本轮实测踩到一个反向案例：把字符串 `"agent_reflection"` 写进 `py-server/tests/` 的测试夹具后，
  该函数立刻被 `dyn` 判为 T3、从 T1 消失（allowlist 命中数 6→5）。说明「字符串字面量」
  这层判据**极其敏感**——它甚至会把测试里的字面量也算作调用证据。

**刻意不加的东西（已评估，别再提议）**：

- **「动态路由 / getattr 反射豁免」**：上面第 2 层 `dyn` 已经覆盖这类成因——任何以字符串形式
  出现的函数名都会脱罪。再加一层「疑似反射就豁免」只会**增加假阴性**，把真孤儿洗白。
  该结论已写进 `scripts/audit_orphan_functions.py` 的模块 docstring，避免后人重复提议。
- **`__all__` 跨模块 `from m import *` 追踪**：任一条 star-import 就能让整模块脱罪，
  公开面被无限放大。T4 只认**同文件模块级** `__all__`。

## 三、三群归类表（40 项逐项裁定）

裁定值说明：`T4` = `__all__` 公开导出面；`keep` = 人工裁定保留；
`planned-use` = 已排期接入；`defer-delete` = 本轮不删、登记待后续阶段处置。

### A 群：`py-server/db/graph_db.py` 整模块零 import（15 项）

| # | 函数名 | 文件:行 | 裁定 | 关键证据 | 本轮处置 | 删除风险 |
|---|---|---|---|---|---|---|
| 1 | `get_graph_db` | `db/graph_db.py:20` | defer-delete | 模块级单例工厂；整模块零 import（`plans/current.md:264` 同一结论） | 保留，登记基线 | 删它等于先拆模块入口，后续上卷无落点 |
| 2 | `get_dependents` | `db/graph_db.py:50` | defer-delete | 基类 `GraphDB(:43)` 接口声明（`raise NotImplementedError`） | 保留，登记基线 | 同上 |
| 3 | `get_learning_path` | `db/graph_db.py:54` | defer-delete | 基类接口声明 | 保留，登记基线 | 同上 |
| 4 | `search_by_keyword` | `db/graph_db.py:58` | defer-delete | 基类接口声明 | 保留，登记基线 | 同上 |
| 5 | `get_all_topics` | `db/graph_db.py:62` | defer-delete | 基类接口声明 | 保留，登记基线 | 同上 |
| 6 | `_topic_id_to_name` | `db/graph_db.py:99` | defer-delete | `MemoryGraphDB(:71)` 私有 helper，模块内亦零调用（实现走 `_topic_id_to_group:181`） | 保留，登记基线 | 低（私有），但要与模块同批删才不残留半成品 |
| 7 | `get_dependents` | `db/graph_db.py:112` | defer-delete | `MemoryGraphDB` 内存 DAG 实现 | 保留，登记基线 | 见 §六 |
| 8 | `get_learning_path` | `db/graph_db.py:120` | defer-delete | `MemoryGraphDB` 实现 | 保留，登记基线 | 见 §六 |
| 9 | `search_by_keyword` | `db/graph_db.py:147` | defer-delete | `MemoryGraphDB` 实现 | 保留，登记基线 | 低 |
| 10 | `get_all_topics` | `db/graph_db.py:154` | defer-delete | `MemoryGraphDB` 实现 | 保留，登记基线 | 低 |
| 11 | `get_dependents` | `db/graph_db.py:220` | defer-delete | `Neo4jGraphDB(:192)` Cypher 实现（本机亦无 Neo4j） | 保留，登记基线 | 低 |
| 12 | `get_learning_path` | `db/graph_db.py:229` | defer-delete | `Neo4jGraphDB` 实现 | 保留，登记基线 | 低 |
| 13 | `search_by_keyword` | `db/graph_db.py:252` | defer-delete | `Neo4jGraphDB` 实现 | 保留，登记基线 | 低 |
| 14 | `get_all_topics` | `db/graph_db.py:262` | defer-delete | `Neo4jGraphDB` 实现 | 保留，登记基线 | 低 |
| 15 | `import_from_kg_dag` | `db/graph_db.py:281` | defer-delete | `Neo4jGraphDB` 的 `kg_dag → Neo4j` 灌库入口（`from shared.kg_dag import GROUP_PREREQS`） | 保留，登记基线 | 它是「章级 DAG 落图」的现成搬运口 |

**A 群不删的额外理由（外文档已锁）**：
`deliverables/408-kg/架构设计-408知识图谱导入.md:150,151,328,574` 把 `MemoryGraphDB`
明确列为「未来考点级→章级上卷」的适配口，并写明**本期不改 `graph_db.py`**。
本轮删它会与该方案的既定边界冲突。

### B 群：已退役 CLI 的批量导入入口（2 项）

| # | 函数名 | 文件:行 | 裁定 | 关键证据 | 本轮处置 | 删除风险 |
|---|---|---|---|---|---|---|
| 16 | `import_all` | `import_pdfs.py:318` | defer-delete | 模块 `__main__` 已改成分发到 `tools/import_client.py` 并打印 DEPRECATED，故无调用路径 | 保留，登记基线 | **只能删函数不能删模块** |
| 17 | `import_all` | `import_docling.py:61` | defer-delete | 同上 | 保留，登记基线 | **只能删函数不能删模块** |

**B 群的硬约束**：`py-server/services/import_worker.py:329,367,368,393` **仍在 import 这两个模块**
的 `SCANNED_PDFS` / `convert_with_docling` / `semantic_chunk` / `detect_subject` / `process_file`
（其中 `:364-366` 的注释本身就在解释这个依赖）。所以拆模块的收益必须由 `import_worker`
的收敛一起做，单独删 `import_all` 只是剪掉一个叶子，不改变模块仍被依赖的事实。

### C 群：活模块 / 活类上的死方法（23 项）

其中 **15 项无争议建议删（本轮不删）**、**6 项裁定保留（进 allowlist）**、**2 项属 `__all__` 公开面（T4）**。

#### C-1 无争议建议删、本轮不删（15 项）

| # | 函数名 | 文件:行 | 裁定 | 关键证据 | 本轮处置 | 删除风险 |
|---|---|---|---|---|---|---|
| 18 | `generate_full_media_package` | `agents/media_generator.py:236` | defer-delete | 聚合打包函数（图+音+视一把梭）从未接线，调用方走分步接口 | 保留，登记基线 | 媒体特性回归时无现成聚合入口 |
| 19 | `execute_skill` | `agents/skill_agent.py:204` | defer-delete | 技能执行已统一走 `skill_plugin_runtime` | 保留，登记基线 | 低 |
| 20 | `get_llm_config` | `config.py:284` | defer-delete | 冗余 helper；真实通道经 `_apply_env_overrides` + `config["llm_provider"]` 直读 | 保留，登记基线 | 低 |
| 21 | `init_db` | `db/__init__.py:10` | defer-delete | NetLearn 时代 bootstrap 残留；且**不在 `__all__` 内**（非公开面）；career 分支靠 `ensure_tables()` 惰性建表 | 保留，登记基线 | 低，但要确认无部署脚本调用 |
| 22 | `cache_llm_response` | `db/redis_client.py:136` | defer-delete | LLM 响应缓存写入 helper 未接线 | 保留，登记基线 | 低 |
| 23 | `get_cached_llm_response` | `db/redis_client.py:140` | defer-delete | 同上（读取侧） | 保留，登记基线 | 低 |
| 24 | `get_agent_weights` | `db/redis_client.py:150` | defer-delete | 多智能体权重读取 helper 未接线 | 保留，登记基线 | 低 |
| 25 | `list_usage_logs` | `db/skill_store.py:615` | defer-delete | usage 日志查询未暴露端点（对应契约审计的孤儿端点之一，管理面） | 保留，登记基线 | 端点一旦补上就要现成查询函数 |
| 26 | `clear_cache` | `engines/frugal_rag.py:647` | defer-delete | 缓存惰性，无需显式清理 | 保留，登记基线 | 低 |
| 27 | `get_recommended_questions` | `engines/quiz_engine.py:636` | defer-delete | 推荐函数未接到端点（孤儿端点之一） | 保留，登记基线 | 同上，端点补齐时要用 |
| 28 | `get_exam_weight` | `engines/teaching_rules.py:330` | defer-delete | 规则引擎直接读配置，本读取函数未用 | 保留，登记基线 | 低 |
| 29 | `get_difficulty` | `engines/teaching_rules.py:337` | defer-delete | 同上 | 保留，登记基线 | 低 |
| 30 | `cache_stats` | `services/cache.py:89` | defer-delete | 缓存装饰器在用，本统计函数未接 | 保留，登记基线 | 低，但运维排障会想看 |
| 31 | `generate_scene_audio` | `services/video_generator.py:677` | defer-delete | 低层未接线（视频特性部分停用，03 演示视频上锁） | 保留，登记基线 | 特性解冻即需 |
| 32 | `generate_video_from_topic` | `services/video_generator.py:793` | defer-delete | 同上 | 保留，登记基线 | 特性解冻即需 |

#### C-2 `__all__` 公开导出面（2 项，判 T4）

| # | 函数名 | 文件:行 | 裁定 | 关键证据 | 本轮处置 | 删除风险 |
|---|---|---|---|---|---|---|
| 33 | `aretrieve` | `engines/algorithm_factory.py:99` | **T4** | 宿主 `RealRetrieverStub` **在 `algorithm_factory.py:219` 的 `__all__` 里明列** | 改判 T4，不进 T1 | 属对外承诺的异步对称接口 |
| 34 | `aevaluate` | `engines/algorithm_factory.py:119` | **T4** | 宿主 `RealConsensusStub` 在 `__all__:220` 明列 | 改判 T4，不进 T1 | 同上 |

**为什么这 2 项不该出现在「孤儿候选」里**：两个 stub 类被写进模块 `__all__`，是模块对外的
**公开面承诺**；`aretrieve`/`aevaluate` 是与 `retrieve`/`evaluate` 成对提供的**异步对称接口**
（真版检索/共识将在 T2/T3 落地，当前 `raise NotImplementedError` 是 fail-closed 设计）。
零内部调用方的原因是「真版还没实现」，不是「这接口没人要」。把它列进孤儿清单，
会诱导后来者删掉对外承诺的对称接口——这正是上一轮把它误列为 T1 的代价。
机检层面：方法没有 `@abstractmethod` 装饰器，所以躲过了第 1 层；名字也没出现在字符串里，
躲过了第 2 层；于是落进 T1。T4 分类就是为这一形态补的。

#### C-3 人工裁定保留（6 项，进 allowlist）

| # | 函数名 | 文件:行 | 裁定 | 关键证据 | 本轮处置 | 删除风险 |
|---|---|---|---|---|---|---|
| 35 | `agent_reflection` | `engines/agent_debate.py:427` | **keep** | 宿主 `AgentDebate` 活跃：`:659` 模块级单例 + `api/agents.py:144` 调 `debate` | 进 allowlist，跳过 T1 | 删掉会拆掉「反思→交叉质询→共识」三段协议的一半 |
| 36 | `cross_examine` | `engines/agent_debate.py:486` | **keep** | 同上，与 `agent_reflection` 成对 | 进 allowlist，跳过 T1 | 破坏协议对称性 |
| 37 | `invalidate_cache` | `engines/skill_plugin_runtime.py:334` | **planned-use** | 当前靠进程重启/TTL 过期；skill 热加载一接线就必须有显式失效路径 | 进 allowlist，跳过 T1 | 届时重写成本高于保留；接线上线后本条应改为删除 |
| 38 | `override` | `shared/container.py:74` | **keep** | docstring 自陈「测试用：替换依赖实例」；`git grep -nE '\.override\('` 全仓 **0 命中** | 进 allowlist，跳过 T1 | 删掉后所有依赖注入测试无法打桩 |
| 39 | `run_semantic_check` | `shared/semantic_guard.py:226` | **keep** | 是 `should_run_semantic_check` + `classify_intent` 的组合编排层；生产为省一次分支直接调原子函数 | 进 allowlist，跳过 T1 | 删掉后失去对外可读的语义入口 |
| 40 | `sanitize_input` | `utils/safety.py:116` | **keep** | 安全域 helper；函数体对注入关键词只 `logger.info` 不剥离，真实防护由 `filter_sensitive`（生产在用）+ `ANTI_INJECTION_INSTRUCTION` 覆盖 | 进 allowlist，跳过 T1 | **删它容易被误读为「安全网被拆」**，进而复制一份更弱的实现 |

第 38 项值得单独说明：「零调用」不等于「死代码」。`override` 的调用方是**未来的测试**，
不是当前的生产代码——机检看不到「为测试而保留的注入口」这一维度，只能靠人工裁定补上。

---

## 四、闸门改造：从「永远红的待办」到「有裁定的准入」

### 4.1 新增的分类与清单

| 机制 | 位置 | 作用 | 是否参与红绿 |
|---|---|---|---|
| **T4 `__all__` 公开导出面** | 脚本内 `collect_module_exports()` + `export_hit()` | 收集每个生产模块**模块级 `__all__`** 的导出名（支持 `=`/`+=`/`.extend()`/`.append()` 四种形态）。命中规则：① 顶层函数名在 `__all__`；② 方法的**任一宿主类名**在 `__all__` | **否**（单列统计） |
| **已裁定 allowlist** | `scripts/orphan_adjudicated.json` → `adjudicated[]`，verdict ∈ `keep` / `planned-use` | 人工裁定保留的项从 T1 跳过 | **否**（跳过计数打印） |
| **已裁定基线** | 同文件 `baseline.t1` + `defer-delete` 条目推导的名册 | 32 项「本轮不删」的存量登记。**T1 中出现名册未登记的项 = 新增零引用函数 → exit 1 并点名** | **是** |
| **僵尸检测** | 脚本内 `defined_func_names()` | `keep`/`planned-use` 条目指向的函数在文件中已不存在 → exit 1（与 `--gate` 无关）；`defer-delete` 项消失则只打印「建议人工收紧基线」 | **是**（僵尸） |
| **拒绝刷新** | `REFRESH_ARGS` 白名单 | `--update` / `--update-baseline` / `--bless` 等一律 **exit 2** | — |
| **`__all__` 僵尸对照** | 脚本内对照打印 | `__all__` 导出的名字在本模块内找不到定义（拼错/已删）时点名，实测 `19 个模块 / 172 个导出名 / 0 个僵尸` | 否（仅报告） |

### 4.2 退出码（改造后）

| 码 | 条件 |
|---|---|
| `0` | 无新增未登记孤儿、无僵尸条目 |
| `1` | `--gate`：T1 存在名册未登记项；或存在 allowlist 僵尸条目（清单与代码不一致，与 `--gate` 无关） |
| `2` | 扫描面为空 / 已裁定清单缺失或 JSON 坏 / 字段缺 / verdict 不在枚举 / 重复 `(file,name,line)` / `baseline.t1` 与 `defer-delete` 条目数不符 / 显式传入刷新参数 |

### 4.3 与原始指令的一处**刻意偏差**（必须记录）

原始指令同时要求三条：① `--gate` → **exit 0**；② 输出里 **T1 显示 32**；
③ 「不要改 `--gate` 的既有语义定义（T1 非空即 exit 1）」。
**这三条在数学上无法同时成立**：T1 非空（32）与「非空即 exit 1」推出 exit 1，与 ① 矛盾。

本轮按**目的**（「让闸门从永远红的待办变成有裁定的准入」）与验收项 ① 取了解法：
**红绿判据改为「T1 中是否存在已裁定基线名册未登记的项」**——存量的 32 项有账可查不阻断，
任何**新增**零引用函数立刻转红并点名。这样 ①②③ 中保留了 ①②，把 ③ 的「非空即红」
升级为「未裁定即红」：`--gate` 仍由 T1 驱动、仍是准入闸，且不再存在
「删 1 个 + 加 1 个 = 计数不变因而漏网」的漏洞（名册按 `(file, name)` + 出现次数比对）。

如果主理人认为应严格保留 ③（宁可闸门继续常红），回退方式是：把 `baseline.t1` 设为 0 并清空
`defer-delete` 条目——脚本与裁定文档均无需改动。

### 4.4 副作用：测试基线断言必须同步

`py-server/tests/test_orphan_function_audit.py` 原本硬断言 `"最强孤儿候选，40 个"`（防新孤儿爬入的
基线快照）。裁定口径变化后该断言必然失败，本轮把它更新为 `32`，并**加固**为五条断言
（T1 32 / T4 2 / allowlist 6 / 台账 40 / 僵尸 0），另补 4 条 fail-closed 单测
（清单缺失、JSON 坏、verdict 不在枚举、基线自相矛盾 → 均 exit 2）。实测 **9 passed**
（**时点锚：`a10ee76`**；这是**本闸门自测子集**的通过数，**不是** CI 默认档 1737 的口径；
后续增删断言须同步本句——否则这个数会静默变旧且无人知晓）。
这是测试快照随口径更新，不是「为了让实现通过而改测试」——新增断言比原断言更严。

### 4.5 守卫自身曾失效的两个缺陷（2026-10-26 实测踩到，已修，留档）

这两条比功能本身更值钱，因为它们都是**「看似有守卫、实际没生效」**的形态，且都不会
在正常使用路径上暴露——只有给守卫自己写测试才会撞出来。已同步写进
`scripts/audit_orphan_functions.py` 的模块 docstring，改动者动到相关代码前请先读那一节。

| # | 缺陷 | 为什么会静默失效 | 处置 |
|---|---|---|---|
| ① | `rel()` 跨盘符抛 `ValueError`（Windows：pytest 的 tmp_path 在 `C:`、仓库在 `E:`，`os.path.relpath` 跨盘符必抛） | 它崩在 `_fail()` **格式化报错文案的路径上**，于是「已裁定清单坏了」这条 fail-closed 报错被一条**完全无关的 traceback** 顶掉——fail-closed 静默失效 | 兜底：失败时回退绝对路径。**守卫报错路径本身必须有单测**（新增的 4 条 fail-closed 用例即为此存在） |
| ② | 测试夹具写真实函数名，把该函数字符串喂进 `dyn` 判据，**当场把它从 T1 抹掉**（实测 allowlist 命中 6→5） | 引用面覆盖全仓 `.py`（含 `py-server/tests/`），所以「测试里**提到**某函数名」= 「看起来有调用方」 | 夹具一律用中性名（见测试文件 `_valid_entry` docstring）。这条也是 §二「不需要再补反射豁免」的反向证据 |

---

## 五、变异测试实证（五项，全部双向还原）

| # | 变异 | 预期 | 实测 |
|---|---|---|---|
| ① | 删掉 allowlist 里 `agent_reflection` 那条 | exit 1 且点名该项 | ✅ exit 1；台账 `T1 33 + T4 2 + allowlist 5`；stderr 点名 `py-server/engines/agent_debate.py:427 agent_reflection`；还原后 exit 0 |
| ② | 把该条 `name` 改成 `agent_reflection_XXX` | exit 1 报僵尸 | ✅ exit 1；`🔴 僵尸裁定条目：py-server/engines/agent_debate.py:427 agent_reflection_XXX（verdict=keep，该文件已无同名函数定义 …）`；还原后 exit 0 |
| ③ | JSON 写坏（去掉结尾 `}`） | exit 2，不得静默放行 | ✅ exit 2；`🔴 已裁定清单 JSON 解析失败：scripts/orphan_adjudicated.json 第 356 行第 1 列（Expecting ',' delimiter）→ 人工修好再跑，禁止静默当空清单`；另测「删中间一个括号」亦 exit 2；还原后 exit 0 |
| ④ | 显式传 `--update` | 拒绝 | ✅ exit 2；`🔴 本脚本不提供刷新入口（--update）：… 照 token_scan「拒绝刷新基线」口径——禁止用一次运行把当前状态洗白` |
| ⑤ | 从 `algorithm_factory.py` 的 `__all__` 摘掉 `RealRetrieverStub` | `aretrieve` 从 T4 掉回 T1 且闸门转红 | ✅ exit 1；`T4 … 1 个`、`T1 … 33 个`、台账 `T1 33 + T4 1 + allowlist 6`；stderr 点名 `py-server/engines/algorithm_factory.py:99 aretrieve`；`git checkout` 还原后 exit 0 |

复现命令：

```bash
python scripts/audit_orphan_functions.py --gate      # 基线 → exit 0
py-server/.venv/Scripts/python.exe -m pytest py-server/tests/test_orphan_function_audit.py -q
python scripts/verify_metrics.py                     # 9 项全部与真值一致 → exit 0
```

本轮实测基线输出尾部：

```
裁定台账：零引用候选 40 个 = T1 32 + T4 公开面 2 + allowlist 跳过 6
已裁定清单对照（非红绿，仅报告）：
  · allowlist 僵尸条目 0 项（函数已不存在却仍被裁定保留 → 红）；已消解 0 项（已有调用方/已挪位 → 建议人工清理条目）
  · 基线名册 24 个键 / 32 项：仍在 T1 32 项，已消解 0 项（其中 0 项函数已不在源文件中 = 真删除，其余为已接线/被判 T3 → 均建议人工收紧基线）
__all__ 对照（非红绿，仅报告）：生产面 19 个模块声明 __all__ / 172 个导出名，其中 0 个在本模块内找不到同名定义

🟢 [orphan] --gate：T1 32 项全部在已裁定基线内（无新增未裁定孤儿），allowlist 无僵尸 → 放行
```

> 注：名册「24 个键 / 32 项」的差异是刻意的——`graph_db.py` 里 `get_dependents`、
> `get_learning_path`、`search_by_keyword`、`get_all_topics` 各有「基类接口 + 内存实现 + Neo4j 实现」
> 三处同名定义，按 `(file, name)` 归并成 4 个键、按出现次数计 12 项。比对用「键 + 次数」，
> 因此同名多实现不会互相顶替而漏掉新增。

---

## 六、决策记录：为什么本轮不删那 32 项

**收益侧**（删了能得到什么）：少 32 段未接线的代码、闸门数字更好看。
**风险侧**（删了会付出什么）：

1. **A 群（15 项）与外文档既定边界冲突**——`deliverables/408-kg/架构设计-408知识图谱导入.md`
   已把 `MemoryGraphDB` 定为「考点级→章级上卷」的适配口并写明本期不改 `graph_db.py`。
   现在删，等于替下一阶段做了一个它明确表示要自己做的决定。
2. **B 群（2 项）删不干净**——`import_worker.py` 仍 import 这两个模块的其他符号，
   只删 `import_all` 不改变「模块仍被依赖」的事实，收益被高估。
3. **C 群（15 项）里有 4 项不是纯死码**——`list_usage_logs`、`get_recommended_questions`
   对应契约审计点出的**孤儿端点**：端点补齐时它们是现成实现；`generate_scene_audio` /
   `generate_video_from_topic` 是「03 演示视频上锁」期间被冻结的低层能力，特性解冻即需。
4. **不可逆性为零，但“急着做”的收益也为零**——删函数可由 Git 历史随时还原
   （这正是「可随时还原」被列为不删的理由之一：既然随时能删，就不必在本轮
   这个以「治理闸门」为目标的任务里顺手做掉）。
5. **本轮的目标是把闸门变成可信的准入机制**，一旦同时删代码，就无法区分
   「闸门转绿是因为治理生效」还是「闸门转绿是因为函数被删了」——会污染下一阶段的判断基线。

**留给下一阶段的取舍**（不是本轮的承诺）：

- A 群：随 408-KG 上卷方案一并处置（删整模块或整体重写，不要零星删）；
- B 群：与 `import_worker.py` 的收敛同批做（彻底移除退役 CLI 的依赖面）；
- C 群 15 项：可随时删，但 `list_usage_logs` / `get_recommended_questions` /
  `generate_scene_audio` / `generate_video_from_topic` 这 4 项应先确认对应端点/特性
  是「永久不做」还是「暂缓」——若是暂缓，删了要重写。

**收敛信号**：删除后 `scripts/orphan_adjudicated.json` 里对应的 `defer-delete` 条目必须同步人工删除，
脚本会打印「已消解 N 项 → 建议人工收紧基线」；`baseline.t1` 必须同步下调
（否则脚本 exit 2：基线自相矛盾）。这条纪律让「删代码」和「改台账」必须成对发生。

---

## 七、诚实口径声明

- **本轮零删除**：`py-server/` 生产源码一个字节没动；`git status` 在本轮提交前只显示
  `scripts/audit_orphan_functions.py`（改）、`scripts/orphan_adjudicated.json`（新增）、
  `py-server/tests/test_orphan_function_audit.py`（测试基线断言随口径更新）。
- 本文件**不是**「孤儿已清理报告」。T1 仍是 32 项，只是**每一项都有裁定、有理由、有证据位置**。
- 闸门转绿的含义是「**没有新增未裁定的零引用函数**」，**不是**「没有零引用函数」。
  任何引用本文件的文档若把 green 读成后者，即为误读。
- 本轮新增的 `keep` 6 项不等于「永久豁免」：`invalidate_cache`（planned-use）接线上线后
  应改为删除并同步台账；其余 5 项若后续被证明无用，同样走「删函数 + 删条目」成对流程。
