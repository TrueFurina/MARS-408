# 生产调用点审计（孤儿函数 / stub 巡检）—— 2026-10-17

> 工具：`scripts/audit_orphan_functions.py`（纯 stdlib，3.2s，report-only）
> 触发：用户「继续」指令 · 主动深审第四轮（接契约审计第三轮）
> 目的：**主动审计生产调用点，找 stub/orphan 函数与未接线能力**
> （对齐用户长期偏好：即使单测通过也补齐关键 gap；本轮回报结论 + 分级裁定，零删除）

## 一、方法

- 生产面 = `py-server/` 运行时真实 import 的代码（root `.py` + `agents/api/app/app_config/db/engines/schemas/services/shared/tools/utils`），共 **202 文件 / 1501 函数定义**。
- 引用面 = 全仓任意 `.py`（生产 + 测试 + 实验 + 脚本，483 文件），排除 `.venv/archive/deploy/dist/.git/node_modules/submission/deliverables`。
- AST 采集「被引用名」：`Call`/`Attribute`/`Name`/`alias`（含别名导入 `import x as y`）+ 字符串字面量（动态分发：`getattr`/`importlib`/注册表/装饰器）。
- 三层分类：
  - **T1 全仓零引用**（最强孤儿候选）；
  - **T2 仅测试/脚本引用**（生产零调用，信息项）；
  - **T3 入口/动态分发豁免**（装饰器 / dunder / 抽象方法 / 名字出现在字符串），不列为孤儿。
- **fail-closed**：扫描面为空 → exit 2。本工具未接入 CI 阻塞门（仅周期巡检），原因见 §三。

### 工具自身两轮缺陷修复（已实证）

1. **别名导入不可见**：首版 `collect_refs` 只扫 `Name/Attribute` 不扫 `ast.alias` ⇒ `try_consume` 被 `import ... as _bucket_try_consume` 用时误判为 T1。修复：补 `alias.name`/`alias.asname` 入引用集，重跑后 `try_consume` 移出 T1（确证其经 llm_provider.py:18 在用）。
2. **T2 分层逻辑误判**：首版把「生产有引用」的函数错归 T2（`assessor_node` 经 `agents/graph.py:105 add_node` 生产在用却进 T2）。修复：`d.name in prod_called` 直接 `continue` 排除。重跑 T2 由 858→37。

## 二、结果

- T3 入口/动态分发豁免：**603 个**（不列为孤儿）。
- **T1 全仓零引用：40 个**（见下表，已逐条人工 grep 反查）。
- T2 仅测试/脚本引用：**37 个**（含 `knowledge_graph.py` 4 个管理 CRUD：list/delete/export/import knowledge graph——对应契约审计的孤儿端点；其余为旧 agents 子函数）。

### T1 全量裁定表（40 项，全零删除零改动）

| # | 位置 | 函数 | 模块状态 | 判定 |
|---|------|------|---------|------|
| 1–14 | `db/graph_db.py` | `get_graph_db`/`get_dependents`/`get_learning_path`/`search_by_keyword`/`get_all_topics`/`_topic_id_to_name`/`import_from_kg_dag`（后者×1 + 接口×4 + 实现×4 共 14） | **整个模块零 import** | **完全死亡模块**：NetLearn 时代 Neo4j 风格 KG 存储；career 分支 KG 已由 `agents/knowledge_graph.py`(实体抽取+SQLite) + `api/knowledge_graph.py` 取代。保留（红线 + B2 先例） |
| 15–17 | `db/redis_client.py` | `cache_llm_response`/`get_cached_llm_response`/`get_agent_weights` | 模块在用 | LLM 响应缓存 helper 未接线；LLM 调用层无缓存需求已验证可用，非 bug。保留 |
| 18–19 | `engines/agent_debate.py` | `agent_reflection`/`cross_examine` | 模块在用 | 辩论引擎可选节点，未接入 `graph.py` workflow（特性未启用）。保留 |
| 20–21 | `engines/algorithm_factory.py` | `aretrieve`/`aevaluate` | 模块在用 | 抽象接口方法（real 分支 `raise NotImplementedError`，fail-closed 设计，测试引用）；T3 误入 T1（无 `@abstractmethod` 装饰器致漏判），合规 |
| 22 | `engines/frugal_rag.py` | `clear_cache` | 模块在用 | 缓存惰性，无需显式清理。保留 |
| 23 | `engines/quiz_engine.py` | `get_recommended_questions` | 模块在用 | 推荐函数未接到端点（对应契约审计 84 孤儿端点之一）。保留 |
| 24–25 | `engines/teaching_rules.py` | `get_exam_weight`/`get_difficulty` | 模块在用 | 规则引擎直接读配置，这 2 读取函数未用。保留 |
| 26 | `agents/media_generator.py` | `generate_full_media_package` | 模块在用 | 聚合打包函数未接线。保留 |
| 27 | `agents/skill_agent.py` | `execute_skill` | 模块在用 | 技能经 `skill_plugin_runtime` 走，此路径未用。保留 |
| 28 | `db/skill_store.py` | `list_usage_logs` | 模块在用 | usage 日志查询未暴露端点（管理面，对应孤儿端点）。保留 |
| 29 | `services/cache.py` | `cache_stats` | 模块在用 | 缓存装饰器在用，`cache_stats` 监控函数未接。保留 |
| 30–31 | `services/video_generator.py` | `generate_scene_audio`/`generate_video_from_topic` | 模块在用 | 低层函数未接线（视频特性部分停用，03 演示视频上锁）。保留 |
| 32 | `shared/container.py` | `override` | 模块在用 | DI 容器运行时覆盖（测试注入用），生产零调用。保留 |
| 33 | `shared/semantic_guard.py` | `run_semantic_check` | 模块在用 | 高层 async wrapper；下层 `should_run_semantic_check`+`classify_intent` 已在 `llm_provider.py:369` 生产在用。冗余 wrapper，非缺口。保留 |
| 34 | `utils/safety.py` | `sanitize_input` | 模块在用 | **仅记录不剥离**（函数体内对注入关键词只 `logger.info`）；注入防护已由 `filter_sensitive`（生产在用）+ `ANTI_INJECTION_INSTRUCTION`（附加到系统提示）覆盖。**非安全缺口，废弃 guard**。保留 |
| 35 | `config.py` | `get_llm_config` | 模块在用 | 冗余未用 helper；真实 LLM 通道经 env-override（`_apply_env_overrides`）+ `config["llm_provider"]` 直接读取（已证可用，见拼图①）。保留 |
| 36 | `db/__init__.py` | `init_db` | 模块在用（实例） | NetLearn 时代 bootstrap 残留；career 分支表结构经 `career_store.ensure_tables()`/`ability_store.ensure_tables()`（`CREATE TABLE IF NOT EXISTS` 惰性建表）创建，已证可用。保留 |
| 37–38 | `import_pdfs.py:318` / `import_docling.py:61` | `import_all` | 运维脚本 | CLI 入口（`__main__`/外部调用），模块级函数无静态引用，符合预期。保留 |
| — | `shared/token_bucket.py` | `try_consume` | — | **首版误判已修复**：经 `llm_provider.py:18 from ... import try_consume as _bucket_try_consume` 在用。移出 T1 |

## 三、关键结论

1. **无安全缺口**：逐条交叉核对死集中 `sanitize_input`↔`filter_sensitive`+`ANTI_INJECTION_INSTRUCTION`、`run_semantic_check`↔`should_run_semantic_check`+`classify_intent` ⇒ 没有任何孤儿函数是「某必需控制的唯一实现」。注入/语义防护在产线均已落地。
2. **无真实 LLM 通道 bug**：`get_llm_config` 是冗余 helper，env-override 直读路径已证可用（拼图① 四通道回退链实证）。
3. **DB 启动路径健康**：`init_db` 死，但 `ensure_tables()`（IF NOT EXISTS 惰性建表）在 career/ability store 生产在用，表结构与运行时一致（demos/测试已证）。
4. **`db/graph_db.py` 是本轮唯一「整模块死亡」项**：NetLearn 时代 KG 存储，迁移到 career 的 `knowledge_graph.py` 后整模块无人 import。保留不删（红线 + B2「legacy 保留」先例）。
5. **其余 39 项 = 可选特性未接线 / 冗余 helper / 测试注入点 / 运维 CLI**，均非 bug，全部保留。

## 四、与「补齐关键 gap」的关系

用户长期偏好「主动审计生产调用点找 stub/orphan，即使单测通过也补齐关键 gap」。本轮巡检结果：**未发现关键 gap**——所有孤儿函数要么是 (a) 被替代实现覆盖（sanitize_input/run_semantic_check/get_llm_config/init_db），(b) 可选特性节点未启用（agent_debate/media_generator/video 部分），或 (c) 测试/运维专用（override/import_all）。**这与 SecAutoMind 的 `CreateInstance/GetAccess` 未调用属不同性质**：彼处是「生产代码本该有人调用却没接」（真实功能缺口）；此处是「历史/可选代码自然沉淀」，功能由其他路径完整提供。**诚实地不粉饰为缺口**。

## 五、本工具是否进 CI 门禁

**不进 CI 阻塞门**（与契约审计的 B 类同处理）：T1=40 全为「已裁定保留」项，若 gate 非空会逼出删端点的违规通过方式（违反红线）。作为**周期巡检脚本**运行即可；若未来要做回归守护，应建「T1 仅允许缩减的基线快照」而非布尔阻断。
