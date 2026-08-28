# 架构与设计质量评审报告（全项目质量审计 · 维度：架构与设计）

- 评审人：高见远（Gao，架构师）
- 日期：2026-07-23
- 范围：后端 `py-server/`（FastAPI）、前端 `src/`（Vue3+Vite+TS）、前后端契约
- 原则：只读不改；发现问题仅记录，由主理人决策
- 目标判定：系统是否"前后端完好、可直接演示"

---

## 1. 架构概览

### 1.1 模块边界与分层
后端层次清晰、关注点分离良好，无"上帝文件"：

```
main.py(入口/中间件/SPA挂载/生命周期)
  └─ api/       30+ 路由模块（agents/langgraph/review/assessment/xfyun/knowledge-base/subjects/...）
       └─ agents/   10 节点 StateGraph + 独立 Agent（各自单文件）
            └─ engines/  FrugalRAG / GOMARL / quiz_engine / teaching_rules
                 └─ db/     milvus_client(抽象) / llm_provider(双通道) / redis / pg / user / skill
                      └─ shared/  auth / errors / metrics / logging / ratelimit / content_safety
                      └─ services/ import_worker(单写者) / pdf_reader / tts / video_dub / cache
```

- 依赖注入统一用 FastAPI `Depends(get_current_user)`；`main.py` 偏重（616 行）但多为装配/中间件，属 FastAPI 入口惯例，可接受。
- 工程化成熟度较高：结构化 JSON 日志、Prometheus `/metrics`、安全响应头中间件、请求体限流、SSE 流式、契约测试（`subjectMapping.test.ts`、`seedTextbooks.test.ts`）。

### 1.2 与申报书对齐度（落地核查）

| 申报书能力 | 落地位置 | 判定 | 备注 |
|---|---|---|---|
| 多智能体编排（8/9/10 节点） | `agents/graph.py` 10 个 `add_node`；`generator_cluster` 内 7 并行子 Agent | ✅ 真实存在 | 节点计数口径在代码注释间自相矛盾（见 5.P1） |
| FrugalRAG（E5+BM25+SFT+GRPO停止） | `engines/frugal_rag.py`(BM25Scorer/E5)、`frugal_rag_sft.py`、`frugal_rag_stop.py`、`db/embedder.py`(e5-base-v2 768维) | ✅ 组件齐 | Reranker 离线禁用→精排降级（演示隐患，见 4-风险4） |
| GOMARL（加权投票+Kappa+NeuralMixer+证据冲突消解） | `engines/gomarl.py`、`gomarl_mixer.py`、`gomarl_conflict.py` | ✅ 高对齐 | 加权投票/一致性/NeuralMixer/动态权重均实现 |
| 8 维动态学生画像 | `src/stores/studyStore.ts`(8基础+5扩展) + 后端 profile 链路 | ✅ | — |
| AI 知识图谱生成器 | `agents/knowledge_graph.py`、`db/graph_db.py`、`/knowledge-graph` | ✅ | — |
| 向量库 Milvus 抽象（Lite InMemory 兜底） | `db/milvus_client.py`；`main.py:125-136` 优先 Milvus 失败回退 InMemory | ✅ 高对齐 | 抽象层设计良好 |
| LLM 双通道（星火X2主→DeepSeek兜底） | `db/llm_provider.py`（信号量7+限流退避 11202/11203+fallback） | ✅ 高对齐 | — |
| 讯飞 10 项能力 | `api/xfyun.py`（tti/图片理解/聚合搜索/ppt/数字人/纠错/公文校对/合规/角色模拟/简历） | ✅ | — |

**对齐度小结**：核心算法与中间件均"真实落地"，非纯 PPT 口径。主要扣分项：① 节点计数 8/9/10 自相矛盾；② 离线环境 Reranker 禁用使"重排"卖点演示不达标；③ 种子教材与真实 RAG 源脱节（见 2、4）。

### 1.3 明显坏味道
1. **后端两套相互矛盾的 group 映射**（严重，见 3）。
2. 根目录散落 `_deep_qa_test*.py`、`_qa_endpoint_test.py`、`archive/scratch_debug/*` 等调试脚本（卫生问题，非演示风险）。
3. `/knowledge-base` 前端 33KB 重复种子数据（见 2）。

---

## 2. 四修复架构评审

### 2.1 /showcase 白屏修复
- **代码**：`main.py:587-606`。把 `dist/showcase` 挂为 `StaticFiles`；并在 `spa_fallback` 中间件对 `status_code in (307,404)` 的 GET（排除 `/api/` 与 `/showcase/` 子路径）回退 `index.html`，让 Vue Router 接管 `/showcase`。
- **评价**：功能可用、注释清晰、有 `not request.url.path.startswith("/showcase/")` 护栏避免递归。
- **风险**：
  1. blanket `404 → index.html` 会**掩盖真实 404**（缺失的 JS chunk / 静态资源会被当 HTML 返回，资源型故障更难定位；favicon/robots 等也返回 HTML）。
  2. `307` 特判本质是补偿"StaticFiles 挂载路径与 Vue 路由同名冲突"的补丁，根因（路径重名）未根治。
  3. `/showcase` 仅在 `dist/showcase` 存在时挂载，否则纯靠 SPA fallback，依赖前端构建产物齐全。
- **更优解**：把展示原型挂到非 Vue 路由前缀（如 `/static/showcase`）由 `ShowcaseView` 用 iframe 引用；或 `StaticFiles(html=True)` 消除 307；或 `spa_fallback` 仅对"无扩展名路径"回退。
- **结论**：演示可行，属可接受技术债。

### 2.2 /knowledge-base 无教材修复
- **代码**：`src/data/seedTextbooks.ts`（33KB，4 本 408 种子教材）；`KnowledgeBaseView.vue:9` 初始即 `SEED_TEXTBOOK_LIST`，仅当后端 `/knowledge-base/textbooks` 返回非空才替换；而 `py-server/data/textbooks/` **为空** → 永远用种子。
- **评价**：保证页面非空、演示不尴尬。
- **风险**：
  1. 种子教材是**前端伪造数据**，不在向量库/RAG 中；"问选中"走 `FrugalRAG over vector_db`（`api/knowledge_base.py:131`），不查这些种子教材——展示内容与真实检索源不一致，对评委有**诚实性风险**。
  2. 33KB 重复数据放在前端，与后端 `pdf_reader` 结构对齐但维护双份。
  3. 生产必须有真实 PDF 导入，否则"知识库"为空壳。
- **更优解**：后端提供统一内置 seed 教材 API（同一份数据），前端仅做空态兜底并明确标注"演示样例"。
- **结论**：演示可用，但属演示性补丁。

### 2.3 /review 科目统计修复
- **代码**：`ReviewView.vue:20-55`，用 `SUBJECT_TO_COURSE`（由 `COURSE_MAP` 生成）把后端按**章节级 key** 聚合的 `by_subject` 合并到 408 四科，用 `COURSE_MAP` 固定顺序输出；含"未识别 key"兜底行。后端 `api/review.py:139-173` 仍按 `quiz_history.subject`（章节级 key）聚合。
- **评价**：实现正确，且有契约测试 `subjectMapping.test.ts` 守护"单一真源"。
- **风险/讨论**：
  1. **四科聚合放在前端**——聚合本应是后端职责（单一事实源应在后端）；当前两边各有一套映射（前端 `COURSE_MAP` + 后端 `kg_dag`/`SUBJECT_NAMES`），任一方变动易漂移。
  2. 依赖 `quiz_history` 存的 `subject` 为章节级 key（`SUBJECT_TO_COURSE` 能命中）；若某处存了课程级 key（如 `data_structures`），前端 `|| s.subject` 兜底会显示原始英文 key，出现丑陋行。
  3. 后端 `SUBJECT_NAMES` 与前端 `COURSE_MAP.name` 是两份中文名。
- **建议**：后端按"章节→课程"聚合后返回四科，或后端暴露统一 `subject→course` 枚举供前端消费。
- **结论**：当前演示正确，架构上聚合位置可优化。

### 2.4 P0 重构（品牌/守卫/版本号）
- **代码**：`App.vue` 品牌已改 "MARS-408"（`App.vue:168,218` 等多处）；`router/index.ts:206-232` 守卫改为 **meta 驱动**（`requiresRole`/`public`/`profileRequired`），`beforeEach` 无硬编码 path——比硬编码更优、可维护、可扩展。
- **评价**：品牌与守卫达标。
- **问题**：`package.json` `"version": "0.0.0"` **仍未修复**（声称"版本号修复"未落地；`name` 已品牌化为 `mars-408-agent`）。`activeKey` 仍有较长 if/else 链（`App.vue:133-150`）但属展示层，无关紧要。
- **结论**：品牌与守卫达标，版本号遗漏（小项，见 5.P1）。

---

## 3. 前后端契约

### 3.1 科目/分组映射一致性
- **前端**：`studyStore.ts` `COURSE_MAP` = 27 章节 key → 4 课程（`computer_network` 7 / `data_structures` 8 / `computer_organization` 7 / `operating_system` 5）；`SUBJECT_TO_COURSE` 由之反向生成（27 key）。
- **后端存在两套 group 映射**：
  - `agents/kg_dag.py:21-34` `SUBJECT_GROUP_MAP`（31 key，线性 1-26：计网1-7 / 数据结构8-14 / 计组15-20 / OS22-26），其文件头自封"metadata.group 的单一真源"。
  - `api/subjects.py:31-44` `group_map`（计网13-19 / 数据结构8-14 / 计组15-21 / OS22-26）—— 用于 `/knowledge-graph` 节点过滤。
- **判定**：
  - **课程级分组（章节→四科）**：前端 27 key ⊆ 后端 `kg_dag` 31 key，且两者章节→课程归类一致 → **PASS**。
  - **group 编号层面**：两套后端映射**相互矛盾（FAIL）**，证据：
    - 计网：`kg_dag=1-7` vs `subjects.py=13-19`（差 +12）。
    - 计组：`kg_dag` 内部 `co_isa=16 / co_cpu=18 / co_bus=19 / co_io=20`；`subjects.py=18 / 19 / 20 / 21`（整体 +1~+2 漂移）。且 `kg_dag` 注释/ `SUBJECT_GROUP_SPAN` 称"计组 15-21（7组）"，实际仅用 15-20（6组），**group 21 被 `subjects.py` 占用**——`kg_dag` 自封"单一真源"却被直接违背。
    - 数据结构、OS 两套映射一致。
- **结论**：课程分组映射 **PASS**（前端↔后端 `kg_dag` 一致）；但**后端内部 group 编号漂移 = FAIL**（真实不一致），属潜伏正确性地雷。前端因只用课程分组、不依赖 group 编号，当前演示不受影响。
- **漂移风险：高**。两份映射各自硬编码、无共享源；若未来跨功能关联 path-planner group 与 KG group（如高亮学习路径节点），将错位。

### 3.2 API 字段对齐（抽查）
| 端点 | 前端期望 | 后端返回 | 结果 |
|---|---|---|---|
| `/review/summary` | `{total_questions,total_wrong,overall_accuracy,by_subject,weak_topics,recommendation}` | `ReviewSummaryResponse` 完全一致 | ✅ PASS |
| `/subjects` | `{subjects, knowledge_graph}` | `{subjects:SEED_SUBJECTS, knowledge_graph:KNOWLEDGE_GRAPH}` | ✅ PASS |
| `/xfyun/image-understand` | `data.text` | `{"text":...,"source":...}` | ✅ PASS |
| `/tutor/enhanced-answer` | `{answer, svg_diagram, video_script}` | result 字典（answer 经 audit_output 确认；svg/video 来自 tutor 服务） | ✅ 基本 PASS（建议演示前跑一次确认三字段非空） |
| 错误契约 | `body?.detail \|\| body?.error?.message` | dev `{detail}` / prod `{error:{code,message}}` | ✅ PASS |

- 前端 SSE 解析（`studyStore.sendMessageStream`）仅处理已知 `type`（reasoning/tool_call/tool_result/content/error），未知事件类型容错忽略，与 `langgraph.py` 多类型推送兼容良好。

---

## 4. 演示风险登记（按影响排序）

| # | 风险 | 影响 | 触发条件 | 现有兜底 | 建议 |
|---|---|---|---|---|---|
| 1 | LLM 凭证/配额耗尽（DeepSeek/讯飞） | 高 | 无凭证（进 demo 模式仅返样例）或星火限流 11202/11203 | 双通道主→兜底、信号量(7)+退避、单节点 120s 超时降级、demo 模式内置样例 | 演示前确认双通道凭证；固定演示账号；关键链路预跑+录屏兜底 |
| 2 | 单进程锁误用（ADR-007 须 `--workers 1`） | 中 | `UVICORN_WORKERS>1` | lifespan 显式 assert 拒绝启动 | 演示脚本锁定 `--workers 1` |
| 3 | 冷启动慢（E5 加载+种子向量+教材导入队列） | 中 | vectordb_data 无缓存/首次 | HF 离线避免 90s 重试、E5 磁盘缓存、仅 count<500 导教材 | 演示机提前预热一次，保留 `e5_embed_cache` |
| 4 | 离线 Reranker 禁用 → "FrugalRAG 个性化重排"实际未运行 | 中（诚实性/精度） | 本机无外网 | 无重排直接截断 top_k | 需演示重排卖点则提供联网/预置模型环境；否则材料改"重排模型离线降级" |
| 5 | /knowledge-base 种子教材与 RAG 脱节 | 中（诚实性） | data/textbooks 空、问的内容不在 vector_db | 搜索后端无果回退种子教材关键词；ask 走 FrugalRAG | 演示避开"基于真实教材出处"话术，或预导真实 PDF |
| 6 | SPA fallback 掩盖 404 | 低 | 构建产物缺文件 | 无（设计如此） | 演示前 `npm run build` 产物完整校验 |
| 7 | 讯飞 10 能力网络依赖（tti/数字人/ppt 等） | 中（加分项） | 无网/超配额 | 异常捕获返友好提示；`dist/showcase` 已存 .pptx/html 原型 | 演示前逐项验证可用能力，准备静态成品兜底 |
| 8 | group 映射漂移（kg_dag vs subjects.py） | 低（当前各功能自洽） | 未来改动任一处 | 各功能用各自一致映射 | 合并为单一真源（见 5.P0） |

---

## 5. 技术债

### P0（赛后必清；演示暂无碍但涉正确性）
- **[一致性] 后端两套 group 映射矛盾**（`kg_dag.SUBJECT_GROUP_MAP` 与 `api/subjects.py` group_map：计网 +12 偏移、计组 +1~+2 漂移、group21 归属不一；`kg_dag` 自封"单一真源"却被违反）。→ 合并为唯一真源（放 `kg_dag` 或新建 `subjects_enum` 模块），`subjects.py`/前端统一引用。**演示影响：无**（各功能自洽），但属潜伏正确性 bug。

### P1（演示影响中等，建议赛前处理）
- **[诚实性] FrugalRAG Reranker 离线禁用**（`bge-reranker-base` 加载失败即永久禁用）→ 申报书"个性化重排"在离线演示未生效。材料/话术需对齐或提供联网演示环境。
- **[诚实性] /knowledge-base 前端 33KB 种子教材非真实 RAG 数据**；展示与检索源不一致。建议后端统一内置 seed 教材并标注"演示样例"。
- **[文档一致性] 节点计数 8/9/10 自相矛盾**（申报书/main.py/langgraph.py）。统一为"10 节点（9 职能 + quality_gate）/7 并行资源 agent"。
- **[P0 遗漏] `package.json` version 仍为 `0.0.0`**，声称"版本号修复"未落地（`name` 已品牌化）。建议设为正式语义版本。
- **[契约] 四科聚合后端 vs 前端分裂**（`api/review.py` 章节级 + 前端 `COURSE_MAP`）；后端应提供统一 `subject→course` 枚举或聚合接口。

### P2（卫生/可维护）
- **[重复数据]** 前端 `seedTextbooks.ts` 与后端 `pdf_reader` 结构双份；`SUBJECT_NAMES`（后端）与 `COURSE_MAP.name`（前端）两份中文名。
- **[代码卫生]** 根目录散落 `_deep_qa_test*.py`、`_qa_endpoint_test.py`、`archive/scratch_debug/*` 等调试脚本；建议移入 `tests/` 或清理。
- **[SPA]** `spa_fallback` 全量 `404→index.html` 可改为"无扩展名路径才回退"，减少掩盖。
- **[启动]** 教材自动导入依赖 `import_worker` 后台队列，`count>=500` 不重复；建议在状态页显示教材数，便于演示自检。

---

## 6. 架构健康评分

- **总分：79 / 100**
- **一句话结论**：分层清晰、核心算法（GOMARL / FrugalRAG / E5 / 双通道 LLM / Milvus 抽象）真实落地、四修复演示可用；但存在"后端双 group 映射互相矛盾""离线重排与种子教材的真实性缺口""节点计数/版本号口径不一"三类需赛后清理的一致性/诚实性技术债——**整体已达"前后端完好、可直接演示"水平，演示前建议完成第 4 节风险 1/3/4/7 的预检与兜底准备。**
