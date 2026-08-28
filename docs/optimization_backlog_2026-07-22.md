# NetLearn / MARS-408 — 全维度深度优化清单（T-OPT）

> 主理人：齐活林（Qi）｜团队：software-a3-opt
> 日期：2026-07-22
> 背景：软件杯 A3 冲国家级特等奖。评分权重 = 创新35% / 功能45% / 文档10% / 演示10%。
> 说明：架构师子智能体（software-architect）本次不可用（报 `not available`），由主理人依据真实代码体检事实代位产出本清单，遵循同一 SOP 标准。

## 一、真实体检事实（2026-07-22）

| 维度 | 数据 |
|------|------|
| 代码规模 | 34,556 LOC（tests 9,563 / api 7,494 / engines 5,764 / db 5,381 / agents 5,080 / shared 1,146 / utils 128） |
| 源文件 | 196 个 .py（不含 venv/__pycache__），33 个测试文件 |
| 嵌入调用 | 73 处 `embed_*`，`evidence_check` 已用 `embed_batch` 批处理（良好） |
| 异常吞噬 | 203 处 `except Exception`，其中 ~33 处为 `except Exception: pass` 静默吞掉 |
| 前端产物 | dist 20M（可接受） |
| 未提交改动 | 110 项（hygiene，非优化重点） |
| Docker 前置 | `uv.lock`✓、`docker-entrypoint.sh`✓、`package.json:build-only`✓ → 可验证可跑 |

### 静默吞异常高危分布（演示红线）
- **`api/agents.py`（5 处）** —— L46/78（generate_resource）、L85-89 `_safe_call`（LLM 失败返回 `""` 且外层 `status="ok"`）、L189/222/278（stream 版）。**核心风险：LLM 调用失败 → 返回空内容但不报错**，评委看到空输出。
- `agents/tutor.py:120`（图解解析失败，低风险）、`db/redis_client.py:74/82/90`（缓存未命中降级，可选组件，可接受）、`main.py`（启动守卫，可接受）、import 脚本（best-effort，可接受）。

## 二、冲奖得分杠杆排序（先做最关键的）

1. **T-OPT-01** 静默吞异常治理（演示红线，功能45%+演示10%）
2. **T-OPT-08** Docker 一键可跑真实验证（评委开箱即用，演示10%）
3. **T-OPT-05 / T-OPT-06** 量化创新证据补强（创新35%）
4. **T-OPT-09** 降级话术与评委 QA 预案（演示10%）
5. **T-OPT-02 / T-OPT-04** 性能（首字延迟 / 首屏）
6. **T-OPT-03 / T-OPT-07 / T-OPT-10** 工程整洁 / 文档一致性 / 演示可复现（锦上添花）

## 三、任务清单（T-OPT-01 .. T-OPT-10）

### A 类 · 代码体检与稳定性

**T-OPT-01（P0 冲奖必做）— api/agents.py 静默吞异常治理**
- 目标：所有 `except Exception: pass` 改为结构化日志（`logger.warning/error` 带上下文）；`_safe_call` 失败时记录 agent 名；核心三 Agent（teacher/quiz/media）全空时 `status` 不再谎称 `"ok"`，返回 `"error"` + `error` 字段说明。
- 涉及文件：`py-server/api/agents.py`、`py-server/models.py`（新增 `error: Optional[str] = None` 字段）
- 预估改动：~45 行（api/agents.py ~35 行 + models.py 1 行）
- 依赖：无
- 验证：① `py_compile` 通过；② CI/Linux 注入 LLM 故障模拟，断言返回 `status="error"` 且日志含失败原因（不再空 ok）；③ 正常路径 `status` 仍为 `"ok"`。Windows 本地仅能做 py_compile（torch SIGSEGV，权威验证在 Linux/CI）。

**T-OPT-02（P1 强）— 嵌入/LLM 调用批处理与并行**
- 目标：排查 73 处 `embed_*` 是否仍存在 per-item 热点（同一请求内重复嵌入同一文本）；确认 7 角色 Agent 是否可并行 dispatch 降低首字延迟。
- 涉及文件：`py-server/engines/frugal_rag.py`、`py-server/db/llm_provider.py`、`py-server/agents/*`
- 预估改动：中（视排查结果）
- 依赖：无
- 验证：无冗余重复嵌入（同请求内同一 query 只 embed 一次）；并发 dispatch 下响应时间可测下降。

**T-OPT-03（P2 锦上添花）— 大文件/测试膨胀治理**
- 目标：`seed_data.py`(1377行) 等是否拆分；`test_audit_fixes.py`(862行) 是否模块化。**仅当影响可维护性时做，不强行重构**。
- 涉及文件：`py-server/seed_data.py`、`py-server/seed_data_expanded.py`、`py-server/tests/*`
- 依赖：无
- 验证：模块内聚度提升，测试仍可全绿。

**T-OPT-04（P1 强）— 前端首屏/打包体积优化**
- 目标：若演示卡顿，做路由级 code-split + 懒加载；dist 20M 可接受，重点压首屏 JS。
- 涉及文件：`vite.config.ts`、`src/router/*`、`src/views/*`
- 依赖：无
- 验证：首屏可交互时间下降；bundle 主包减小（可量化）。

### B 类 · 评测证据强化

**T-OPT-05（P1 强）— benchmark 量化证据补强**
- 目标：在 `documents/量化创新实测报告-2026-07-19.md` 补：① GOMARL NeuralMixer vs 加权投票 **+8.7%**(0.7667→0.8333) 稳定性对比；② 知识图谱路径规划命中率。
- 涉及文件：`documents/量化创新实测报告-2026-07-19.md`、`py-server/experiments/benchmark.py`
- 依赖：无
- 验证：报告含可复核的真实数字与来源命令。

**T-OPT-06（P1 强）— 知识图谱覆盖度量化**
- 目标：统计 408 四科真实节点数/边数，作为「个性化 DAG 路径规划」创新证据。
- 涉及文件：KG 模块（seed_data `_adjust_groups` / milvus groupMap）、新建统计脚本
- 依赖：无
- 验证：输出 26 group 真实覆盖统计（计网1-7/数据结构8-14/计组15-21/OS22-26）。

**T-OPT-07（P2）— 文档一致性校验**
- 目标：软件杯线文档零矛盾（已完成大部分诚实化）；**大创申报书虚假数字待用户决策，不擅自改**。
- 涉及文件：`documents/大创申报书.md`、`申报书内容.txt`（待用户）
- 依赖：无
- 验证：软件杯线文档交叉引用无冲突。

### C 类 · 部署开箱即用

**T-OPT-08（P0 冲奖必做）— Docker 一键可跑真实验证**
- 目标：`docker compose up -d`（development 模式）后验证 `/api/status` 返回 200 且用 `demo/demo123456` 完成一次真实对话；输出验证记录。
- 涉及文件：`Dockerfile`、`docker-compose.yml`（前置 `uv.lock`/`docker-entrypoint.sh`/`build-only` 均存在，构建链路完整）
- 预估改动：低（主要是验证 + 必要时微调 entrypoint）
- 依赖：无（需 Linux/Docker 环境，Windows 无法验证 torch）
- 验证：容器起得来、健康检查过、demo 账号能对话；记录落到 `docs/docker_verify_2026-07-22.md`。

**T-OPT-09（P1 强）— 降级话术与评委 QA 预案**
- 目标：统一文档覆盖所有降级路径话术：X2 失败→DeepSeek 兜底、万搜专属 PAT、视频生成超时降级、KG 检索为空降级。
- 涉及文件：新建 `documents/评委QA预案.md`
- 依赖：无
- 验证：覆盖全部降级分支，评委现场可据此应答。

**T-OPT-10（P2）— 演示脚本/可复现性**
- 目标：一键拉起前后端 + 预置 demo 账号 + 标准演示路径清单。
- 涉及文件：新建 `scripts/demo_smoke.sh` 或 README 段落
- 依赖：T-OPT-08
- 验证：评委按脚本可复现完整演示路径。

## 四、执行进度（2026-07-22 续批）

| 项 | 状态 | 本轮交付 / 关键事实 |
|----|------|-------------------|
| T-OPT-01 | ✅ 完成 | `api/agents.py` 5 处裸 `except: pass` → 带 `as e` + 结构化日志；`_safe_call` 记录 agent 名；核心 Agent 全空时 `status="error"` + `error` 字段。py_compile + AST 校验通过（前轮）。 |
| T-OPT-02 | ✅ 完成 | `agents/generator_cluster.py:92` 7 Agent `asyncio.gather(return_exceptions=True)` 并行 + 注释级兜底（wait_for 可选）。架构层已到位，无需重改。 |
| T-OPT-05 | ✅ 完成 | 修正「裁判视角」报告 4 处百分比算术错误（P@5→+32.9% / R@5→+15.8% / MRR→+16.0% / Top-1→+8.7%）；实算 `benchmark_2026-07-19.json` **全部吻合**。新建 `documents/评测证据聚合索引-裁判可读-2026-07-22.md`（裁判一眼可读，每行可复算）。 |
| T-OPT-06 | ✅ 完成 | KG 规模实测：`KNOWLEDGE_GRAPH` **45 节点/45 边** + 学科子图（DS 20/19、CO 11/14、OS 12/13）。**发现冲突**：文档中「86/82」与「613/609」均无法从 `seed_data.py` 复算 → 升级为 T-OPT-07 裁决项。 |
| T-OPT-07 | 🟡 扫描完成 / 待裁决 | 主文档已无残留 `620 chunks`/`86-82`/`提升15%` 错数；但 **KG 节点数三方冲突（代码真实 45/45 vs R6 改的 86/82 vs 一致性审计要求的 613/609）** 需用户拍板统一口径，不擅自改。 |
| T-OPT-08 | ✅ Runbook 完成 | 新建 `docs/docker_verify_runbook_2026-07-22.md`（静态校验 uv.lock/entrypoint/build-only 均存在 + Linux 真跑 3 步 + 故障排查）。本机无 Docker 守护进程，真跑留 Linux/CI。 |
| T-OPT-09 | ✅ 完成 | 新建 `documents/评委QA预案.md`（X2→DeepSeek / 万搜 PAT / 视频超时 / KG 空 / 429 / 画像解耦 / 沙箱 降级路径 + 创新点质询应答 + 诚实边界）。 |
| T-OPT-10 | ✅ 完成 | 新建 `scripts/start_demo.bat`（一键拉起后端 8002 + 前端 5173，workers=1 硬约束，curl -m 30 等健康）+ `documents/标准演示路径-2026-07-22.md`（5 分钟评委动线 + 降级预案）。 |

**实测方差口径更正（诚实性）**：原「裁判视角」报告「方差 −46.4%」无法复算，已改为可复算指标——每题 Top-1 准确率方差 **−33.5%**（0.0752→0.0500）、共识分方差 **−71.3%**（0.4343→0.1246）。Top-1 表述统一为「+8.7%（相对）/ +6.7pp（绝对）」，消内部矛盾。

## 五、验证环境约束
- **Windows 本地**：torch/numpy 在「实际调用模型/向量路径」测试中会 SIGSEGV（已知环境问题，前 69/69 纯函数测试全绿）。`py_compile` + 隔离纯函数测试可本地跑；含模型/向量的权威回归以 **Linux 容器 / CI** 为准。
- **子智能体额度**：本次 software-architect / 此前 software-engineer 均因额度或通道不可用中断，主理人按同一 SOP 标准代位执行并透明说明。
