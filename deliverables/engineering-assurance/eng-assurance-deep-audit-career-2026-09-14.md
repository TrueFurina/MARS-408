# 工程保障深度审计 · career-literacy 当前真实状态（2026-09-14）

**日期**：2026-09-14
**工作流**：工作流 1（综合代码审查）＋ 工作流 5（技术债评估）联合 · 超级深度摸底后全队并行审计
**参与成员**：Cody（代码审查）· Archi（架构）· Rex（SRE）· Tessa（测试）· Docu（文档）
**审计方式**：只读静态审计 + 实际 `git status` / 实际跑测试；不修改任何文件，所见即仓库实时状态。

---

## 📌 TL;DR（执行摘要）

- **整体结论**：career-literacy 主线（三元评审权重 MAPPO 化 + 鲶鱼 MAPPO 化）**实现真实、可复算、治理诚实**，具备演示上线条件；但存在"声称已修实际未修"的 2 处真实异步阻塞，以及一批文档事实漂移/ADR 治理缺口。
- **严重度分布**：🔴 严重 2 项 / 🟠 高 4 项 / 🟡 中 14 项 / 🟢 低（已验证良好）多项。
- **阻塞 / 非阻塞**：**无演示级硬阻塞**；2 处 🔴 为事件循环冻结风险（TTS/PPT 异步路径），建议在演示前修复。
- **最大亮点（经独立核验）**：解析式 `analytic_review_action` 真按加权恒等式算四档有效分（非查表/硬编码）；单一真值源 `discipline_gate`/`review_precision` 收敛成立（49 例守护）；career `EVIDENCE_DENSITY_DEFAULT=0.3` 与三路播种齐全；filelock no-op 已修为 `blocking=True`；工作树实测**干净**；判据 A 实跑 capture 100%/100%/99.8% PASS。

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| 整体评级 | 🟡 有条件通过（主线可信，需清 2 处真阻塞 + 文档漂移） |
| 阻塞项数量 | 0 硬阻塞 / 2 处 🔴 事件循环冻结风险（演示前建议修） |
| 关键行动项 | 12 条（P0×2 / P1×5 / P2×5） |
| 建议下一步 | 派发第二波"修复波"：Cody 修 2 阻塞 + Docu 订正 CLAUDE.md/README + Archi 补 ADR + Rex 补 Runbook career 绿线 + Tessa 补 CI 门禁 |

---

## 🔍 审查发现（按严重度排序，已去重合并）

| # | 严重度 | 类别 | 文件:行 | 问题描述 | 建议修复 | 来源 |
|---|--------|------|---------|----------|----------|------|
| 1 | 🔴 | 异步(声称不符) | `api/multimodal.py:109` | python-pptx 阻塞未修：异步端点直接同步调 `build_pptx`，未 `to_thread`；与 `generator_cluster.py:132` 已修路径不一致，违反 CLAUDE.md"已修复"措辞 | 改为 `await asyncio.get_running_loop().run_in_executor(None, build_pptx, ...)` | Cody F13 |
| 2 | 🔴 | 异步(声称不符) | `tts_service.py:238,244` → `api/tts.py:65` | MeloTTS 阻塞未修：`synthesize` 直接同步调 `melo_synthesize`（数秒级），未 `to_thread`；xfyun 分支已 `await`，melo 分支漏 | 改为 `await asyncio.to_thread(melo_synthesize, text, language)` | Cody F9 |
| 3 | 🟠 | 可观测性 | `shared/metrics.py:117-131` | P2 `http_request_duration_seconds_p95/p99` 显式 gauge **未落地**（仅 `_bucket` 直方图）；Runbook `findstr p95` 无匹配 | 按 `DEMO_OBSERVABILITY.md §1` 补 p95/p99 gauge，或改盯盘读直方图 | Rex C11 |
| 4 | 🟠 | 演示就绪 | `DEMO_RUNBOOK.md` / `DEMO_GONOGO.md` | 全文无 `/api/career` 冒烟步骤，无 career 功能级绿线；"演示 career 功能"流程上未被显式放行 | 加 career 冒烟：① `GET /api/career/scenarios` 列表 ② demo 账号 `POST /api/career/session/start` 建会话 ③ 教师端 `/api/career/classes` 角色校验 | Rex E17/E18 |
| 5 | 🟠 | 文档事实错误 | `CLAUDE.md:161` | 仍写"branch `master`、无 upstream"——实为 `career-literacy` + `origin`/`mars408` 已配置且跟踪 upstream；两处均错，误导贡献者 | 改为 career-literacy + 已存在 origin/mars408 且跟踪 | Docu #6 |
| 6 | 🟠 | 架构治理 | `docs/adr/`（仅 008/009/010） | 本次新增 review/MAPPO/career 架构**未进 ADR 治理**；architect 起草的 ADR-011/015/017 未见落盘，仅存于 CTO 攻坚令/B-*.md 报告 | 立 ADR-011（review 权重）、ADR-015/017（career/catfish），ADR-007/008 提 Accepted | Archi #7 |
| 7 | 🟡 | 接线偏差 | `agent_debate.py:164` | 插入点 A 解析式不可达：仅传 `use_mappo=True` 未传 evidence/consensus → `decide_review_weight` 解析式分支（需两者）被跳过，落到 RL 路径 | 文档明确"点A仅走 RL，解析式仅点B可达"；或确认辩论侧可补传 evidence/consensus | Cody F16 |
| 8 | 🟡 | 正确性 | `frugal_rag.py:640` | `clear_cache` 用 `redis_client._client.keys(...)`：访问私有 `_client` + KEYS 阻塞型反模式 | 改用 `scan_iter` 并经公开封装，勿碰 `_client` | Cody F17 |
| 9 | 🟡 | 安全/约定 | `shared/prompt_guard.py:22-40` | CLAUDE.md 称"单一 verb-gated 正则"，实际 9 条规则含无动词规则（jailbreak/system:/developer mode），会误伤良性安全/OS 学术提问 | 文档与代码对齐；无动词规则加最小上下文约束 | Cody F18 |
| 10 | 🟡 | 约定 | `agents/ppt_builder.py:120,132` | `except Exception: pass` 静默吞错（字体 fallback），违反 CLAUDE.md 禁止条款 | 至少 `logger.debug` 或收窄为 `(AttributeError, KeyError)` | Cody F19 |
| 11 | 🟡 | 发布卫生 | `py-server/guardian.bat:26` | 启动行无 `--workers` 也无 `WEB_CONCURRENCY=1`；Runbook/GoNoGo"已固化 --workers 1"未落地。当前靠 main.py fail-fast 兜底（安全但不可实测验证） | 加 `--workers 1` 并 `set "WEB_CONCURRENCY=1"` 纵深防御 | Rex B9 |
| 12 | 🟡 | 可观测性 | `shared/metrics.py` | P2 `vector_db_backend` / `import_queue_depth` gauge 未实现（D-obs 计划未落地）；career 不依赖二者，影响有限 | 演示可补；优先级低 | Rex C12/C13 |
| 13 | 🟡 | 文档事实错误 | `CLAUDE.md:142` | "FastAPI 0.115.0" 过时；实测 `0.141.1`；其下"全量 pytest 报错"绕过说明需复核 | 改 0.141.1 并核 pytest 绕过说明是否仍成立 | Docu #7 |
| 14 | 🟡 | 文档自相矛盾 | `README.md:50 vs :56 vs :113` | 行50"E5 已本地化启用"与行56"BM25-only 规划中"/行113"当前 BM25-only 降级"矛盾；实测 `_degraded` 仅异常兜底，默认主路径为向量检索 | 行56/113 改为"向量检索主路径（E5 已本地化；异常时 BM25-only 降级）" | Docu #8 |
| 15 | 🟡 | 文档漂移 | `README.md:45/160/224 vs :174`；`README_EN.md`；`submission/开发说明书:408` | 向量条数 2122 vs 2113；API 数 170+ vs 196+ vs 实测~236；测试数 616 vs 843 多处漂移 | 统一向量 2122、API ~236、测试 843 | Docu #9/10/11 |
| 16 | 🟡 | 文档误述 | `docs/派单执行回执-2026-09-14.md:49` | 误称"README 无 career/MAPPO 内容"——README 实含第十一节 career + M3/M5 MAPPO 段 | 更正为"README 符合纪律，无需新增三位一体专节" | Docu #5 |
| 17 | 🟡 | 文档债 | `docs/demo/三评审MAPPO演示面板.html:176` | "全量回归 592 passed" 过时（现 843） | 更新为 843 | Docu #12 |
| 18 | 🟡 | 测试门禁 | `experiments/accept_review.py` | 判据 A（解析式 capture ≥95%）是验证接线的关键卡，却只在本地手动跑 + 落盘 JSON，**CI 无自动断言**；恒等式回归只靠人工发现 | 加轻量 pytest 包装断言 `analytic_capture_* ≥ 95%` 与 `PASS=True` | Tessa 缺口#1 |
| 19 | 🟡 | 测试覆盖 | `agents/career_nodes.py:111-133,266-269` | `build_scenario_script` / `generate_adversary_question` 的 LLM 失败兜底（非 JSON→种子/兜底）无专门单测 | 加 mock-LLM-返回非JSON→断言返回兜底对象 | Tessa 缺口#2 |
| 20 | 🟡 | 测试标记 | `tests/test_career_policy_baseline.py` 等 | 两个新测试文件无 `p0_regression`/`import_queue` 标记，仅随通用 `backend-tests` 跑，无独立门禁隔离 | 给基线门测试加 `@pytest.mark.p0_regression` | Tessa 缺口#3 |
| 21 | 🟡 | 架构维护脚枪 | `scripts/wire_review_weight_*.py` | 用字符串锚点补丁直接改源文件，且调用签名已与落地代码 drift（`decide_review_weight(feats, use_mappo=True)` 不带 evidence/consensus）；重跑 `--apply` 会二次插入损坏 | 归档/删除；一次性脚本移入 `experiments/archive` | Archi #8 |
| 22 | 🟡 | 架构耦合 | `career_policy.py:60,287-289` | career 只读导入 `mappo_policy._build_networks`（下划线私有）构造网络；私有 API 依赖脆弱，408 侧重构该签名会断 career | 提为公开稳定 API，或 career 自带网络构造 | Archi #10 |
| 23 | 🟡 | 文档债 | `CTO-芒得很职P3鲶鱼MAPPO化设计-2026-09-12.md:42` | 奖励命名含"六维均分…提升"字样（纪律前旧稿，未对外） | 加注"该+0.02 属噪声级，不得对外称提升" | Docu #3 |
| 24 | 🟢 | 架构 | `quality_gate.py:136-163` / `agent_debate.py:145-171` | 新权重层干净下游插入：点B 只换判定输入、点A 仅 regenerate 路径；fail-open + 灰度默认关；均匀权重偏移为 0 | 保持；演示前再确认 config 两开关 false | Archi #1-3 |
| 25 | 🟢 | 耦合 | `engines/gomarl*.py` | 新层只**读** GOMARL 产出 consensus/evidence，gomarl* 四文件零反向依赖 → 单向下游消费者 | 禁止 review_policy/career 回写 gomarl | Archi #4 |
| 26 | 🟢 | 零侵入 | `career_*.py` / `api/career_training.py:17` | career 全 `career_*` 沙箱；唯一跨边界是 `api/agents.py→agent_debate`（已 fail-open）；未改任何 408 源文件 | 保持 | Archi #5 |
| 27 | 🟢 | 单写者 | `import_worker.py:127` / `main.py:262-278,720` | filelock no-op 已修为 `blocking=True, timeout=2` 真阻塞；与 main.py env/CLI fail-fast 形成三重兜底；career 走独立 `db.career_store` 不碰 vectordb | 建议 ADR-007 提 Accepted 并补记 filelock 强化 | Archi #6 |
| 28 | 🟢 | 测试真实性 | `test_review_single_source.py`(49) / `test_career_policy_baseline.py`(9) | 单一真值源身份同一性 + CTO 基线三门均**实跑覆盖**（Tessa 实测 58 passed / 0 error）；accept_review 判据 A 实跑 capture 100/100/99.8% PASS | 保持 | Tessa #1-10 |
| 29 | 🟢 | 发布卫生 | `git status`（实测） | 工作树**干净**：0 未提交 tracked、0 非忽略未跟踪；诊断/临时文件均已被 gitignore（`99ddcf6`/`023fe79` 收口），不会入库 | 保留（红线不删） | Rex D15/D16 |
| 30 | 🟢 | 文档纪律 | 全仓 `*.md` grep | **🔴 级（违反 CTO 派单令的对外表述）零例**；三位一体叙事在 5 份核心文档 + README + 演示面板全面贯彻；无"RL 超一切/六维均分提升"卖点 | 维持 | Docu 口径结论 |

---

## 🏗️ 架构影响评估（Archi）

- **评级 B+（良好，可安全上线演示）**。新 MAPPO/review 权重层是干净的下游插入：点B 只换判定输入、不动判定逻辑；点A 仅在 2-agent 冲突 regenerate 路径生效；两路 fail-open、灰度默认关，已逐行验证"均匀权重 → 行为逐字等于现状，偏移 0"。
- **单写者约束未被新代码破坏**（✅ 与摸底担忧相反，filelock 已修真阻塞）。career 走独立 `db.career_store`，不写 vectordb。
- **零侵入成立**（✅）：career 仅 `career_policy.py:60` 只读导入 `mappo_policy._build_networks` 构造器 helper，未改 408 源文件。
- **关键风险**：① 接线脚本 `wire_review_weight_*.py` 已 drift（维护性脚枪，演示不受影响但必须归档）；② ADR 治理缺口（011/015/017 未落盘）；③ 单写者 vs 水平扩展张力（ADR-008 已记，ADR-012 待立，演示无碍）。

## 🧪 测试覆盖评估（Tessa）

- **真实有效、实跑全绿**：单一真值源门（49 例）+ CTO 基线三门（9 例）实测 `58 passed in 42.26s / EXIT 0 / 无 SIGSEGV / 无 error`；accept_review 判据 A 实跑 capture 100%/100%/99.8% → PASS。
- **最初怀疑的 4 个 gap 经核查均已覆盖**：career_nodes 生产规则 / quality_gate 接线 / MAPPO fail-open / teacher 端点均有对应测试，应视为"已覆盖"。
- **真正需补强 3 件**：① accept_review 进 CI 门禁（中）；② career_nodes 两 LLM 节点兜底单测（中）；③ 新基线测试打 `p0_regression` 标记（低）。
- **全量 843 基线未本地复跑**（Windows 原生 torch SIGSEGV 风险），权威判定以 Linux CI 为准。

## 🚀 可运维性评估（Rex）

- **运维就绪度 GO**。新 career 端点无 GPU/模型启动依赖（MAPPO 懒加载、默认关、全链路 fail-open 回退规则版）；无请求级资源泄漏；写路径不引入第二写者；单写者由 main.py + import_worker.filelock 双重 fail-fast 强制；请求级指标已覆盖 `/api/career/*`；工作树干净。
- **非阻塞待补**：guardian.bat 补 `--workers 1`（靠 fail-fast 已安全）；P2 三项可观测 gauge 未落地（有原始直方图，影响有限）；Runbook/GoNoGo 缺 career 功能冒烟绿线。
- **诚实红线提醒**：career 鲶鱼默认**规则版**（`use_career_mappo=False`），若演示标榜为神经网络智能须按 GoNoGo G1-G4 标"v1 规则原型"。

## 📚 文档口径评估（Docu）

- **口径纪律整体：未发现有违反 CTO 派单令的对外表述（🔴 零例）**。三位一体叙事已在全部 5 份核心文档 + README + 演示面板全面贯彻；所有"MAPPO/RL"表述均带场景限定或"合成环境"标注；"六维均分提升"未作为任何对外卖点。
- **瑕疵属文档维护债 + 内部事实错误（非诚信违规）**：CLAUDE.md `branch=master` 错误（🟠）；FastAPI 版本过时；README E5/向量检索三处自相矛盾；向量条数/API 数/测试数漂移；派单执行回执误述 README 无 career 内容；演示面板 592→843 过时。

---

## ✅ 行动清单（按优先级排序）

| # | 行动 | 负责角色 | 紧急度 | 预期完成 |
|---|------|---------|--------|---------|
| 1 | 修 `api/multimodal.py:109` 的 `build_pptx` 为 `run_in_executor` 包裹（与 generator_cluster.py:132 对齐） | Cody | P0 | 演示前 |
| 2 | 修 `tts_service.py:238/244` 的 `melo_synthesize` 为 `await asyncio.to_thread(...)`，消除 MeloTTS 事件循环阻塞 | Cody | P0 | 演示前 |
| 3 | 补 `accept_review.py` 判据 A 的 CI 门禁（pytest 包装断言 capture ≥95% & PASS） | Tessa | P1 | 本迭代 |
| 4 | 订正 `CLAUDE.md:161`（branch/remote）+ `:142`（FastAPI 版本） | Docu | P1 | 本迭代 |
| 5 | 订正 README E5/向量检索自相矛盾 + 统一向量/API/测试数字 | Docu | P1 | 本迭代 |
| 6 | Runbook/GoNoGo 补 career 功能冒烟与绿线（E17/E18） | Rex | P1 | 演示前 |
| 7 | 立 ADR-011/015/017 并提升 ADR-007/008 为 Accepted | Archi | P1 | 本迭代 |
| 8 | 归档/删除 `scripts/wire_review_weight_*.py` 等漂移接线脚本 | Archi | P2 | 本迭代 |
| 9 | career_nodes 两 LLM 节点（build_scenario_script/generate_adversary_question）兜底单测 | Tessa | P2 | 本迭代 |
| 10 | 新基线测试打 `p0_regression` 标记进入 P0 门禁 | Tessa | P2 | 本迭代 |
| 11 | `guardian.bat` 补 `--workers 1` + `WEB_CONCURRENCY=1` 纵深防御 | Rex | P2 | 演示前 |
| 12 | `frugal_rag.py:640` KEYS→scan_iter；`prompt_guard` 与文档对齐；`ppt_builder` except 收窄；插入点A 解析式可达性确认 | Cody | P2 | 本迭代 |

---

## ⚠️ 待完善 / 已知局限

- **全量 843 回归未本地复跑**：受 Windows 原生 torch SIGSEGV 限制，权威判定以 Linux CI 为准；本次仅实跑关键两文件（58 passed）。
- **真实 trace 复评管线从未跑过**：`experiments/eval_review_mappo_real.py` 已就绪但无真实输入（无 `--trace` 即 fail-loud）；"真实教学增益"仍属合成环境结论。
- **career MAPPO 端到端启用路径缺测**：门控默认关、无训练权重，测试用 `mappo_on` 夹具仅验契约/纪律零违规（实退化到规则），属灰度特性非阻断缺口。
- **本审计为只读**：所有修复行动需另发"修复波"，并遵循红线（不删文件、不提交凭据、发生型证据不造假）。

---

## 📚 数据来源 & 成员产出索引

- **Cody（代码审查师）** 原始产出：MAPPO/review 实现真实性核验 + 6 处异步阻塞逐项核对 + 单一真值源 grep；结论 🟠，Top-5 必改（F9/F13/F17/F18/F19）。
- **Archi（架构师）** 原始产出：插入点 A/B 架构影响表 + 零侵入/单写者/耦合验证；评级 B+，3 关键风险（接线脚本 drift / ADR 缺口 / 扩展张力）。
- **Rex（SRE）** 原始产出：`git status` 实测（工作树干净，纠正摸底简报过时预设）+ 可运维性表 + 发布卫生清单；结论 GO。
- **Tessa（测试专家）** 原始产出：单一真值源门(49)+基线三门(9) 实跑 58 passed + 判据A 实跑 99.8% PASS + 3 覆盖缺口。
- **Docu（文档师）** 原始产出：全仓口径 grep + 16 条发现；结论 🔴 违规零例，瑕疵均为文档维护债。

---

> 本报告由工程保障团队 AI 协作生成（主理人甄宇航编排 + 5 成员并行独立审计），关键决策请由人类工程负责人复核。所有结论基于仓库实时 `git` / 磁盘 / 实跑测试，未采信文档自述。
