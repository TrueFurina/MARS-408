# 技术债评估 · py-server（study-help-pro / 分支 career-literacy）

**日期**：2026-09-22
**工作流**：工作流 5 — 技术债评估
**参与成员**：Cody（代码审查师）· Archi（系统架构师）· Tessa（测试专家）· Docu（技术文档师）

---

## 📌 TL;DR（执行摘要）

- **整体结论**：真实 `py-server`（分支 career-literacy，芒得很职 / 前身 芒得很职）代码"可用但偏重"。**安全底座扎实**——0 硬编码密钥、0 生产 `eval/exec`、0 命令注入（`shell=True`/子进程全列表式）、0 `pickle`/`yaml.load`/`verify=False`；工程纪律强（0 处 TODO/FIXME、0 大段注释代码、0 不可达分支）。但存在三类系统性风险：① **覆盖不保证**（无 `fail_under` 门禁、默认跑 22% 用例被跳过、legacy 模块零直接单测）；② **故障可见性差**（80 处静默吞错、关键能力静默降级）；③ **结构 / 文档漂移**（上帝模块、口径虚高 451 vs 242 端点）。
- **严重度分布**：🔴 严重 5 项 / 🟠 高 11 项 / 🟡 中 3 项（注：本仓库🔴均为技术债项，无 release 阻塞性交付缺陷）。
- **阻塞 / 非阻塞**：无交付阻塞；🔴 为债务项，非 blocker。
- **最高杠杆**：① 覆盖率门禁（`Priority=50`，低成本高收益）② 隔离 `crypto_platform` 嵌套副本（`Priority=40`，防误打包/误提交）应本周落地。

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| 整体评级 | 🟡 有条件通过（框架/纪律扎实，但覆盖不保证、绿光可骗人、结构性债务累积） |
| 阻塞项数量 | 0 |
| 关键行动项 | 6 条（P0 先发 4 条 + P1 2 条） |
| 建议下一步 | 先发 P0：覆盖率门禁 + crypto 副本隔离 + 认证路径吞错审计 + .env.bak 清理 |

---

## 🪜 债务清单 + 优先级（按 `Priority = (Impact + Risk) × (6 - Effort)` 排序）

> 评分：Impact / Risk ∈ {1..5}，Effort ∈ {1..5}（1=易，5=难）；乘数 `(6 - Effort)` ∈ {5..1}。**仅隔离/排除，不含删除**（项目红线"绝不删除、只追加"）。

| # | 债务项 | 原严重度 | Impact | Risk | Effort | **Priority** | 来源 |
|---|--------|---------|--------|------|-------|-------------|------|
| D3 | 无强制覆盖率门禁：`fail_under` 缺失、`addopts` 无 `--cov`，注释误导称"cov-fail-under=80" | 🔴 | 5 | 5 | 1 | **50** | Tessa |
| D1 | `crypto_platform` 嵌套副本污染（188 文件，未跟踪 vendored）：`pyproject` `packages.find include=["agents*"]` 会打进 wheel；`git add -f` 可入库；干扰 pytest/IDE | 🔴 | 5 | 5 | 2 | **40** | Archi/Cody/Docu/Tessa |
| D4 | 静默吞错：486 处 `except Exception`，其中 **80 处** `pass`/直接 `return None` 零日志；含 `auth`/`rate-limit` 路径（潜在"异常→None→越权"隐患） | 🟠 | 5 | 5 | 3 | **30** | Cody/Archi |
| D15 | 死代码/重复测试定义：`test_review_weight_protocol.py` 4 对同名函数，后者遮蔽前者 → 前组断言**永不执行**（静默覆盖缺口） | 🟡 | 3 | 3 | 1 | **30** | Cody |
| D18 | `.env.bak-20260902` 明文密钥备份驻留工作树（gitignored 但长期驻留，误提交/泄露风险） | 🟠 | 3 | 3 | 1 | **30** | Archi |
| D6 | 文档口径漂移/虚高：README 451 vs 真值 242 端点；英文 README 节点 10 vs 11、页面 68 vs 45、LLM 写错(X2 主 vs DeepSeek 主)；CLAUDE 10→11 节点、25+→45 views；KG 613 vs 订正 86/82 | 🔴/🟠 | 4 | 3 | 2 | **28** | Docu/Archi |
| D5 | 能力静默降级：E5 嵌入失败时以**零向量占位**（`embedding_status=fallback_zero`），RAG 召回无声劣化；PG/Redis 静默 `enabled=False` | 🟠 | 4 | 5 | 3 | **27** | Archi |
| D2 | 共享 SQLite 多连接并发写：`user_store` 与 `skill_store` 各自 `sqlite3.connect` 同一文件 + 各持独立 `RLock` → 并发写可触发 `database is locked` / WAL 损坏 | 🔴 | 5 | 4 | 3 | **27** | Archi |
| D14 | 依赖浮动 + venv 软链脆弱：运行时依赖 `>=`（靠 `uv.lock` 锁定）；`.venv` 为 C: 软链（E: 空间不足），CI/构建环境脆弱 | 🟠 | 3 | 3 | 2 | **24** | Archi |
| D16 | 产品名漂移：README 头条仍 "芒得很职 / 408 考研"，而当前分支产品为"芒得很职" | 🟠 | 3 | 3 | 2 | **24** | Docu/Archi |
| D9 | 永久/陈旧 skip·xfail 伪装缺口：默认跑 203/945(22%) 跳过；`xfail(strict=False)` 永久容忍已知缺口；2 处陈旧 xpass；9 处 respx 守卫；8 处 torch 守卫 | 🟠 | 3 | 4 | 3 | **21** | Tessa |
| D11 | 未使用导入：175 处 / 92 文件 | 🟠 | 2 | 2 | 1 | **20** | Cody |
| D8 | Legacy 408 agents/engines 无直接单测 + 活跃 services/db 模块零测试（`tts_service`/`pdf_page_mapping`/`redis_client`/`graph_db`…） | 🔴/🟡 | 4 | 5 | 4 | **18** | Tessa |
| D10 | 代码重复：讯飞鉴权助手 3 处、RL 策略样板 4 类 ~10 方法、`json` 解析助手 ≥3 | 🟠 | 3 | 3 | 3 | **18** | Cody/Archi |
| D12 | DI 容器半残 / 死代码：`dependencies.py` 4 个 `Depends` 0 处被路由调用；两套实例化路径（全局单例 vs 容器），测试 override 对 pg/redis 不生效 | 🔴 | 3 | 3 | 3 | **18** | Archi |
| D13 | 分层倒置：`db` 反向依赖 `agents`/`engines`（`db/graph_db.py`→`agents.kg_dag`；`db/user_store.py`→`engines.review_scheduler`），依赖方向违反 | 🟠 | 3 | 3 | 3 | **18** | Archi |
| D19 | 无自动变异测试工具：`mutmut`/`cosmic-ray` 零命中；仅 4 文件靠人工变异验证 | 🟡 | 2 | 3 | 3 | **15** | Tessa |
| D7 | 上帝模块：`user_store.py`(1286/48fn)、`skill_store.py`(1151)、`review_policy.py`(1002)、`chat.py`(1187)、`xfyun_services.py`(809/32fn)、`milvus_client.py`(957) | 🔴/🟠 | 4 | 4 | 5 | **8** | Archi/Cody/Tessa |
| D17 | 缺 co-located 核心模块文档：`agents`/`engines`/`db`/`services` 无任何就近 API/架构/Runbook | 🟠 | 3 | 2 | 5 | **5** | Docu |

---

## 🗓️ 分阶段修复计划

### P0（本周 / 即时，约 1–3 人日，ROI 最高）
1. **D3 覆盖率门禁**：CI 增加 `fail_under=80` + `--cov=. --cov-report`（阻断覆盖退化）。
2. **D1 crypto 副本隔离**：`pyproject` 显式 `exclude = ["*crypto_platform*"]`；加 pre-commit 守卫禁止 `crypto_platform` 被 `git add`；从工作树移出（不删，保留于独立仓库/存档）。
3. **D4 认证/限流路径吞错专项审计** + 统一异常日志规范（至少 `logger.exception`，启动/中间件/生命周期故障不可掩盖）。
4. **D18 .env.bak 清理**：移出工作树 / 加密，杜绝明文密钥驻留。
5. **D15 删重名测试函数**：`test_review_weight_protocol.py` 4 对，加 `F811` 检测。

### P1（本迭代，约 1–2 周）
- **D6 文档口径对齐**：README 451→~240 端点（以 `py-server/openapi.json` 为唯一真值）；英文 README 11 节点 / 45 views / LLM 通道（DeepSeek 主 + generalv3.5 兜底，X2 未授权）；CLAUDE 10→11、25+→45；KG 改由运行时探针得出不写死。
- **D5 能力降级显式化**：embedding/LLM 缺失 fail-fast 或脏标记 + `/api/status` 暴露健康维度。
- **D2 共享 SQLite 统一连接与锁**：抽 `db/core.py` 提供 `get_conn()`+`with_conn()`，所有 store 复用同一连接与锁。
- **D14 uv.lock 冻结**：发布以 `uv sync --frozen` 为准，README 明确需 uv。
- **D16 产品名对齐**：README 头条改"芒得很职"。
- **D9 消灭永久/陈旧 skip·xfail**：`xfail` 改 `strict=True` 或移除；确保 CI 装 respx；本地显式标注 segv/torch 诚实降级。
- **D11 ruff 清未用导入** + 加 `F401` 门禁。

### P2（技术债池，排期不阻塞 P0/P1）
- **D8 补 Top5 模块单测**：`engines/guided_parse`、`services/tts_service`、`db/redis_client`、`services/pdf_page_mapping`、`engines/cn_distinction`。
- **D10 抽公共**：`db/xfyun_auth.py`、`engines/BasePolicy`、`shared/json_utils.py`。
- **D12 DI 冻结**：要么全切 DI（路由用 `Depends(get_pg_client)`），要么删 `container.py`/`dependencies.py`。
- **D13 解除 db→agents/engines 倒置**：纯函数/数据下沉独立 `domain` 包。
- **D19 引入 mutmut** 对关键模块跑变异，设存活变异阈值。
- **D7 拆上帝模块**（按子域拆分 store/路由/策略）。
- **D17 补 co-located Runbook**。

---

## 💡 投入产出预估

| 阶段 | Effort | 阻断风险 | ROI |
|------|--------|----------|-----|
| P0 | 低（1–3 人日） | 误打包/误提交、覆盖退化、密钥泄露、认证越权 | 极高（低成本清除最大隐患） |
| P1 | 中（1–2 周） | 口径失信、无声劣化、并发损坏、依赖漂移 | 高（可维护性 + 对外可信度） |
| P2 | 重（数周） | 结构性，渐进 | 中（按排期，不阻塞交付） |

---

## ✅ 行动清单（按优先级排序）

| # | 行动 | 负责角色 | 紧急度 | 预期完成 |
|---|------|---------|--------|---------|
| 1 | pytest 加 `fail_under=80` + `--cov` 到 CI，阻断覆盖退化 | Cody / Tessa | P0 | 本周 |
| 2 | 隔离/排除 `crypto_platform` 嵌套副本（pyproject exclude + pre-commit 守卫 + 移出工作树） | Archi | P0 | 本周 |
| 3 | `auth`/`rate-limit` 路径静默吞错专项审计 + 统一异常日志 | Cody | P0 | 本周 |
| 4 | 清理 `.env.bak-20260902` 明文密钥备份（移出/加密，不删） | 主理人 | P0 | 本周 |
| 5 | 文档口径对齐（端点/节点/页面/LLM/KG 以代码真值为准） | Docu | P1 | 本迭代 |
| 6 | 能力静默降级显式化 + `/api/status` 健康维度 | Archi | P1 | 本迭代 |
| 7 | 共享 SQLite 统一连接与锁（`db/core.py`） | Archi | P1 | 本迭代 |
| 8 | 补 Top5 模块单测（guided_parse/tts/redis/pdf/cn_distinction） | Tessa | P2 | 排期 |

---

## ⚠️ 待完善 / 已知局限

- 本评估为**只读静态扫描 + 既有日志分析**，未实际执行 pytest 全量（需 `.venv`/torch/Milvus/LLM 凭证）。覆盖率与运行数据来自仓库内 `_regress_v.log`（**734 passed / 203 skipped / 8 deselected / 1 xfailed / 2 xpassed**，156s，绿）与 `_baseline.log`（1 failed）、`collect.log`（4 collection errors，红 CI 痕迹）。
- 死函数精确计数受 FastAPI 路由注册与 `module.attr` 属性调度影响，名称可达性分析存在假阳性，故以"样本确认 + 重复定义"给出，未夸大总数。
- **项目红线"绝不删除、只追加"**：本报告所有修复建议**均不含 `rm`**；`crypto_platform` 副本与 `.env.bak` 仅建议"隔离/移出/加密"，不删。
- `Priority` 公式中的 Impact/Risk/Effort（1–5）为主理人依据四份子报告的主观加权，用于**排序**而非绝对度量；Effort 取 1–5（公式 `(6-Effort)` 乘数为 5–1，Effort=6 将使优先级归零，故封顶 5）。

---

## 📚 数据来源 & 成员产出索引

- **Cody（code-reviewer-2）原始产出**：py-server 代码债扫描 —— 313 个真实文件 / ~72.8k 行，7 类债务量化 + Top15（静默吞错 80 处、未用导入 175、上帝模块 ≥10、代码重复簇、0 硬编码密钥/生产 eval）。
- **Archi（architect-2）原始产出**：架构债扫描 Top10 + 健康度🟡（vendored 副本、SQLite 多连接、DI 死代码、上帝模块、能力静默降级、分层倒置）。
- **Tessa（testing-expert）原始产出**：测试债扫描 —— 73 真实测试模块 / ~945 用例 / 203 跳过 / 无覆盖门禁 / skip·xfail 审计 / 变异文化。
- **Docu（tech-writer-2）原始产出**：文档债扫描 Top10 + 口径漂移实例（端点 451 vs 242、节点 10/11、页面 68/45、LLM 通道、KG 613 vs 86/82）。
- 真值基线（文档对齐用）：`agents/graph.py:94-109` = 11 节点；`openapi.json` = 223 路径 / 43 模块；`find src -name "*.vue"` = 82（45 views）；`find py-server -name "*.py"` = 313（不含副本）。

---

> 本报告由工程保障团队 AI 协作生成，关键决策请由人类工程负责人复核。

> **附：本次扫描严格排除了 `py-server/**/crypto_platform/`（约 188 文件，408 代码整份嵌套副本，pytest 已 `--ignore`）与 `.venv`/`node_modules`/`dist`/`build`/`archive`，确保债务口径反映真实代码而非垃圾副本。**
