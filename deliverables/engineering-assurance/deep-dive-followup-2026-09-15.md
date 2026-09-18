# 深度续作修复收口报告 (deep-dive-followup-2026-09-15)

**日期**：2026-09-15
**工作流**：综合代码审查 + 部署前检查（07-19 深度计划续作闭环）
**参与成员**：主理人甄宇航(Zhen) 编排；3 个通用执行代理（`worker-f1-teacher-auth` / `worker-doc-reconcile` / `worker-llm-correctness`）。原 `engineering-deep-dive-2026-07-19` 团队（11 名成员）状态 unresumable，已据实声明、未伪造进度。

---

## 📌 TL;DR（执行摘要）

- **整体结论**：07-19 深度计划中"仍有效"的待办项已全部落地——F-02 / F-03 / F-08 / F-10 / F1（教师端鉴权）/ 文档口径统一 / F3-F5（讯飞通道正确性），共 6 类、13 个文件改动 + 新增测试。
- **严重度分布**：🟢 低 13 项（均为已修复 / 口径更正，无新增缺陷）；🔴 / 🟠 / 🟡 遗留 **0 项**。
- **阻塞 / 非阻塞**：**无阻塞**；所有改动均**未 commit**（单会话 git 约束），须由占用 git 的会话统一提交，勿扩范围。
- **关键更正（高价值）**：LangGraph 真实节点数 = **11**（非旧报 9 / 10），已据源码 `py-server/agents/graph.py:99-109` 的 11 次 `add_node` 核实，并统一 11 个文档/脚本的口径。

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| 整体评级 | 🟢 通过（续作闭环完成，待提交） |
| 阻塞项数量 | 0 |
| 关键行动项 | 3 条（统一 commit / 全量回归 / 历史文档 sweep） |
| 建议下一步 | 由占用 git 的会话统一 commit；随后在 Linux/CI 跑全量回归核对 passed/failed 行 |

---

## 🔍 修复发现（按主题）

### A. 代码正确性修复（主理人直落 + worker-f1）

| # | 严重度 | 类别 | 文件:行 | 问题描述 | 修复 | 验证 |
|---|--------|------|---------|---------|------|------|
| F-02 | 🟢低 | 正确性 | `py-server/engines/agent_debate.py:163-169` | `decide_review_weight(feats, use_mappo=True)` 调用未传 `evidence`/`consensus`，analytic 分支（点A）因缺参永不命中 | 透传 `consensus=c` + 显式注释：点A 仅走 MAPPO/规则路径，属设计预期（作用域无 evidence，首选透传方案不可行） | `pytest tests/test_review_weight_protocol.py -q` → 36 passed |
| F-03 | 🟢低 | 可靠性 | `py-server/api/sandbox.py:207-214,218,233,242,250` | 双重潜藏 bug：①兜底引用从未 `import` 的 `subprocess`（触发即 NameError）；②Windows 非法 `start_new_session=True`；③async 端点内同步 `Popen().communicate(timeout)` 阻塞事件循环；④:250 记忆写入 `proc.returncode` 在 fallback 路径 `proc` 不在作用域 | ①模块级补 `import subprocess`；②新增 `_run_blocking_proc`（POSIX 条件 `start_new_session`、`TimeoutExpired` 内先杀进程组再 raise）；③兜底改 `await asyncio.to_thread(...)`；④引入 `proc_returncode` 统一 :218/:233/:242 并修复 :250 | `ast.parse` 三文件通过；grep 复核 to_thread 路由；无残留裸 `proc.returncode` |
| F1 | 🟢低 | 安全/鉴权 | `py-server/shared/auth.py:142-178`、`api/teacher.py:13,22,62,120,141,244,252,268,318,339`、`main.py:~338`、`tests/test_teacher_role.py` | 教师专属端点未强制教师角色（授权缺口）；演示账号 demo 角色为 student，需可控放宽预览教师仪表板 | 新增 `require_teacher_or_demo_open()` + `_is_demo_teacher_open()`（受 `NETLEARN_DEMO_TEACHER_OPEN=1` 控制，开启时向审计日志写 `[DEMO-RELAX]` 含 user_id/role/路径）；9 个教师端点改走该依赖；2 个学生自有端点（:286 submit、:303 my-submission）保留 `get_current_user`；`main.py` 启动横幅非静默打印 `[DEMO-RELAX]` | `ast.parse` 通过；pytest 选定 7 用例全 PASS（含 4 个 F1 用例） |

### B. 文档口径统一（worker-doc-reconcile，VERIFIED 来自源码）

| 项 | VERIFIED 真值（来源） | 历史口径 | 改动 |
|----|----------------------|---------|------|
| 多智能体图节点数 | **11**（含 triage 入口；`graph.py:99-109` 11 次 `add_node`，含 `evidence_check`） | 旧报 9 / 代码注释 10（漏算 triage） | `graph.py` 注释 4 处 + README 8 处 + INSTALL/overview/ADR-010/INDEX/audit_fix_architecture/metrics-integrity-audit/演示脚本/答辩PPT大纲 等 11 文件 → 11 |
| 学生画像维度 | 8（`api/profile.py:56-60` `_REQUIRED_DIMS`） | 一致 | 无改动 |
| 前端端口 | 5173（`vite.config.ts:12,28` strictPort；`serve_spa.py:4`） | SRE 报告曾记 5181 漂移 | SRE 报告加注"5181 为历史漂移，已 strictPort 修复" |
| 前端 .vue 组件 | **79**（36 components + 42 views + App.vue） | 旧报"21"实为 Skill 插件模板，非前端组件 | 无改动（文档未误报） |
| API 规模 | **40 router / 39 tag(模块) / 233 operations(216 路径)**（`main.py:585-612` + `openapi.json`） | 手册"17 模块"、旧报"26"均错 | `documents/API接口手册.md` 标题与说明更正，加注以 openapi.json 为准 |
| 截图链接 | 无（README 无图片链接，根无 `screenshots/`） | — | 无需改 |

> ⚠️ **残留（建议单独一轮 sweep）**：`documents/` 下大量历史设计/申报文档仍含"10 节点"/"8 核心节点/27 Agent"等早期口径，彼此不一致，不在本次 demo/brief/README/API手册/competition-brief 显式范围内。

### C. 讯飞通道正确性（F3/F4/F5，worker-llm-correctness）

| # | 严重度 | 类别 | 文件:行 | 问题描述 | 修复 | 验证 |
|---|--------|------|---------|---------|------|------|
| F3 | 🟢低 | 正确性 | `py-server/db/llm_provider.py` `_resolve` | 非 auto 分支用 `if not provider.get("api_key")` 误判 xfyun（仅 `api_password`）"缺 Key"→ 永不选中 generalv3.5 | 改为 `_provider_configured(target, provider)`（按各通道真实凭据字段判定） | resolve 用例 OK |
| F4 | 🟢低 | 正确性 | `py-server/api/config_routes.py` `config_get` | `llm_provider=auto` 时 `cfg.get("auto",{})` 空 → 硬编码 deepseek 误导前端 | 按 xfyun→deepseek→qwen 取首个 `_provider_configured` 通道填充 `llm_*` 字段 | `test_config_llm_provider_env.py` 4 passed |
| F5 | 🟢低 | 可靠性 | `py-server/db/llm_provider.py` `stream_chat` auto 分支 | `except: continue` 在首通道已 yield 部分分片后失败会拼接混合流 | 加 `yielded_any` 标记：已产出分片后异常则上抛终止，不拼接 | ast.parse 通过 |

**红线守护**：三项修复均通道感知、绝不破坏已 working 的 generalv3.5 主通道、绝不引入 X2 专属逻辑（09-01 实测 X2 `spark-x`/`pro-128k` 返回 `11200 未授权`，generalv3.5/4.0Ultra 才是真实 200 通道）。

### D. 文档/口径声明（F-08 / F-10，主理人直落）

- **F-08** `CLAUDE.md:198`：指令注入检测由"单一 injection-verb-gated 正则"更正为"9 条注入模式（`_INJECTION_PATTERNS`，含无动词规则：developer mode / jail break / 'you are now a' / 行首 system:）"。
- **F-10** 4 个 docs（`CTO-深度验收结论与三项派单令-2026-09-14.md:147`、`CTO-芒得很职三元评审权重MAPPO化攻坚令-2026-09-14.md:281-282`、`验收记录-三元评审权重MAPPO-2026-09-14.md:70`、`派单执行回执-2026-09-14.md:47`）各追加限定词「（合成环境：真实特征提取管线 + 合成上下文采样，非真实 trace；真实增益待 P5 试点）」，杜绝"仿真即真实"口径漂移。

---

## ✅ 行动清单（按优先级排序）

| # | 行动 | 负责角色 | 紧急度 | 预期完成 |
|---|------|---------|--------|---------|
| 1 | 统一 commit 本轮全部改动（F-02/F-03/F-08/F-10/F1/文档口径/F3-F5，约 13 文件 + 新增测试），**仅 add 自己的文件、勿扩范围** | 占用 git 会话 | P0 | 立即 |
| 2 | Linux/CI 跑全量回归（避开 Windows 原生 torch/numpy SIGSEGV），看日志 passed/failed 行，不看出错码 | CI / 占用 git 会话 | P1 | 提交后 |
| 3 | 历史文档 sweep：`documents/` 下残留"10 节点/8 核心节点/27 Agent"等早期口径统一 | Docu / 人工 | P2 | 后续一轮 |

---

## ⚠️ 待完善 / 已知局限

- `engineering-deep-dive-2026-07-19` 原团队（11 成员）**unresumable**，无 durable task id，已据实声明、未伪造进度；续作改由通用代理执行仍有效项。
- **07-19 方案前提作废**：原"X2 唯一权限 + ADR-011 强制 spark_x2"被 09-01 实测推翻（generalv3.5 为主通道，X2 未授权）→ 该线未续作，X2/ADR-011 标记作废。
- **全部改动未 commit**（单会话 git 硬约束：执行者不碰 git，提交由占用 git 的会话统一处理）。
- **未跑全量测试**：本地 Windows 原生 torch/numpy 重型导入链触发 SIGSEGV(139)（环境级非代码缺陷）；沙箱 `http_proxy` 劫持 localhost 探活→502（须 `NO_PROXY=127.0.0.1`）。权威回归看 Linux/CI。
- **文档 sweep 遗留**：`documents/` 大量历史文档仍含旧节点口径，单独一轮处理，不在本轮范围。

---

## 📚 数据来源 & 成员产出索引

- `worker-f1-teacher-auth` 原始产出：`shared/auth.py`（:142-178 新增 `require_teacher_or_demo_open`/`_is_demo_teacher_open`）、`api/teacher.py`（9 端点改依赖 + 2 学生端点保留）、`main.py`（[DEMO-RELAX] 横幅）、`tests/test_teacher_role.py`（4 F1 用例）。
- `worker-doc-reconcile` 原始产出：`agents/graph.py`（注释 4 处）+ README/INSTALL/overview/ADR-010/INDEX/audit_fix_architecture/metrics-integrity-audit/演示脚本/答辩PPT大纲/API接口手册/SRE报告 共 11 文件，VERIFIED 真值来自 `graph.py:99-109`、`profile.py:56-60`、`vite.config.ts`、`main.py:585-612` + `openapi.json`。
- `worker-llm-correctness` 原始产出：`db/llm_provider.py`（`_resolve`→`_provider_configured`、`stream_chat`→`yielded_any`）、`api/config_routes.py`（`config_get` auto 填充）。
- 主理人直落：`engines/agent_debate.py`（F-02）、`api/sandbox.py`（F-03）、`CLAUDE.md`（F-08）、4 docs（F-10）、`remediation-pending-fixes-2026-09-15.md`。

---

> 本报告由工程保障团队 AI 协作生成，关键决策请由人类工程负责人复核。
> **所有改动尚未 commit——提交由占用 git 的会话统一执行，执行者未触碰 git。**
