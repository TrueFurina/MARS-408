# 当前计划

> 详细路线图见 `plans/roadmap-2026-10-13.md`（站位快照 / 近期 / 中期 / 未来三块拼图 / 风险护栏 / 待确认项）。
> 决策记录见 `plans/decisions.md`。

## 待办（解冻后第一批 · A 组）

- [x] ~~A5 重新生成源码包~~ —— **已取消**（用户 2026-10-13 指令：**不要任何交付、不要任何压缩包、不要解冻**）
- [ ] A1 公开站外链 `MARS-408` 仓库地址处置（**待用户确认边界**：vite base 与仓 URL 属"已裁决永久保留"，此条仅指前端文案外链）
      —— 2026-10-14 取证：全前端仅 2 处文案外链，均指向 `github.com/TrueFurina/MARS-408#docker`（部署文档锚点）：
      `LandingView.vue:272`「查看部署文档」、`LoginView.vue:55`「本地运行说明」。
      建议**保留**：仓库本就公开（GitHub Pages 部署源，og:url 已暴露同域），链接是部署文档唯一入口，
      改动无收益且断文档路径。**待用户一句话确认**。
- [x] A2 学生侧隐藏 admin-only 沙箱入口 —— 2026-10-14 闭环：真相与计划预设不同——`navConfig`
      的「代码沙箱」项**早有** `roles: ['teacher','admin']`，漏的是**路由本身**无 meta
      （F2 同款纵深缺失，学生输 URL 可开）。已给 `/sandbox` 补 `meta: { requiresRole: ['teacher','admin'] }`；
      全量差集核对（nav roles vs 路由 meta）确认仅此一处漏网。vue-tsc / eslint 双干净。
- [x] A3 `CareerTrainingView.vue:133` 裸 fetch 改走 `api.ts` 统一封装 —— 2026-10-14 核实**已完成**：
      该文件现经 `@/utils/api` 的 `api` 封装发全部请求，全文 0 处裸 `fetch`（早期提交
      `209a0f6`/`81514f1` 落下的修复，计划行号已过期）。
- [x] A4 孤儿路由 `POST /api/guide/quiz` 决策 —— 2026-10-14 裁决：**计划项过期，无需处置**。
      证据：`git log --all -S "guide/quiz"` 仅命中 3 条**计划文档**提交（`ad7913f`/`103b400`/`f2180a9`）；
      当前分支与 `main` 的代码里（前端路由 / 后端 api）该路径**从未存在** ⇒ 无路由可挂、也无路由可删。

## 已排期（原定 10-28）

> 用户 2026-10-13 明确「不要解冻」⇒「冻结/解冻」窗口作废，本节按「是否属交付物」重新分流：
> 非交付物的代码改进（P1-1 / P1-2）可随时做；**属交付物的 PPT 重生成按「不做任何交付」取消**。

- [ ] P1-1 修 `VideoPlayer` / `LandingView` 两模态框焦点管理 + `verify-structural.yml` 加 `--gate-class`（检测逻辑已备，A=2 真违规）
- [ ] P1-2 紫族 17 处品牌紫归一 + `token_scan --update-baseline` 降到新低
- [x] ~~冻结区 PPT 重生成~~ —— **已取消**（PPT 属交付物，用户指令「不要任何交付」）

## 中期（打磨次批 · B 组）

- [ ] B1 数字漂移与过度承诺文案逐条复查（46→47、「面试」情景、实训模式数）
- [ ] B2 legacy MARL 死代码归档决策（**先核引用，不直接删**；确认无 `career_*` 链引用后再动）
- [ ] B3 4 个孤儿视图决策（改造 / 删除；**动前先定 views 计数口径**，47 依赖它们）
- [ ] B4 `api/tutor.py:11` 顶层 import 改懒加载 + 清理过时 CLAUDE.md 警告
- [x] B5 真实浏览器 E2E 走查（2026-10-14 完成）—— 第一次在浏览器里把整条链点完，
      并抓到 2 个只有浏览器能看见的问题（教师登录落学生测评 / 三条职员路由无角色守卫）
      + 1 个前端看不见的后端读空 bug（看板六维均分恒空）。均已修 + 已用走查复验。
      记录 `deliverables/engineering-assurance/browser-e2e-2026-10-14.md`；
      脚本 `scripts/e2e/teacher_loop_walkthrough.cjs`（人工运行，不在 CI）。
      ⚠️ F1/F2 尚无自动化守护（前端无测试基建）—— 见报告第八节。

## 主线（用户 2026-10-13 批准：三拼图全部拓展）

> 实测前提（本轮已验证）：项目**零代码改动**即可用真实 LLM —— `config.py:473` 的 env_map 已支持
> `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` / `LLM_PROVIDER`。
> 本机实测：`LLM_PROVIDER=deepseek` → 通道判定 `deepseek-chat`、key 注入成功、真实调用返回可用内容。
> 仓库探活：**DeepSeek ✅(0.97s) / 智谱 GLM ✅(0.60s)** 可用；DashScope·Moonshot·SiliconFlow·OpenRouter 均因账号/地区不可用。
> ✅ 服务器 `172.16.222.99` 已于 2026-10-13 配置 `~/study-help-pro/py-server/.env`
> （`LLM_PROVIDER=deepseek` + key，chmod 600）。服务器**零安装**即可跑 career 链路——
> 用 `/home/user/miniconda3/envs/all-in-rag/bin/python`（含 langgraph/fastapi；career 链路
> 不依赖 Milvus/Redis，缺失时自动回退）。注意 `~/studyhelp-venv2` **缺 langgraph**。

- [ ] ① **真实 LLM 接入**
  - [x] 通道探活 + 项目侧端到端首验（本机，2026-10-13）
  - [x] 服务器配 key（`~/study-help-pro/py-server/.env`，2026-10-13，chmod 600）
  - [x] **4 场景 mock vs 真实对比基线已跑并落档**（2026-10-13）——
        脚本 `experiments/career_llm_baseline.py`；数据 `experiments/results/career_baseline_*.json`；
        逐项对比 `career_baseline_compare_2026-10-13.md`；结论 `career_baseline_结论-2026-10-13.md`。
        要点：兜底模式 4/4 场景可跑完但**六维只覆盖 2 维、追问退化为指令标签、overall 恒 2.60 无区分度**；
        真实模式 4/4 场景脚本由 LLM 生成、六维覆盖 5~6 维、追问能抓住答非所问、overall 有区分度（2.60/4.45/3.15/3.10）。
  - [ ] 兜底通道：视需要在 config 增补智谱 GLM 通道（现仅 deepseek/xfyun/qwen 三档）
  - [x] **查实并修复「开场问题被种子锁死」**（2026-10-13）——基线跑一次即暴露：4/4 场景两模式开场逐字相同，
        实证为 LLM 把提示词里的「参考开场」原样回填。改 `prompts_career.py` 3 处措辞（种子开场降级为"仅情境参考、必须重写"），
        复测 4/4 开场全部改写且质量提升；差异数 53 → 58。
  - [x] **混态用例已补（2026-10-13）**：`--mode mixed --fail-after N` 故障注入（每场前 N 次调用放行）。
        `fail-after 4` 实测 4/4 场次跑完不崩；评估虽降级为 `rule_fallback`，但 overall 恢复区分度
        （2.78/4.54/3.17/4.12，而纯兜底恒 2.60）、有分维度 2→5~6、含原话链条 2→5~6。
        📌 **定位出真正的质量瓶颈 = 「证据采集」（每轮取证的 LLM 调用），不是评估器** —— 若降本，最该保住取证。
- [ ] ② **教师侧最小教学闭环**
  - [x] **缺口盘点已完成**（2026-10-14）→ `plans/teacher-loop-gap-2026-10-14.md`。
        🔴 **结论：后端与教师端全齐，闭环断在学生侧最后一米** ——
        `POST /career/task/join` 已就绪但**前端零入口**，且学生发起实训**不传 `task_id`**；
        而班级看板只统计带 `task_id` 的会话（`db/career_store.py:511`）⇒ **教师发的任务收不到数据、看板恒空**。
        📌 **补齐是纯前端工作量（后端零改动）**，这修正了"缺后端能力"的预判。
  - [x] **学生侧断链已补齐（2026-10-14）**：`CareerTrainingView.vue` 加"凭任务码加入"入口 →
        `POST /career/task/join` → 任务锁定场景/难度/轮数 → `session/start` **透传 `task_id`**（否则看板永远空）。
        连带修复 `bind_student` 名实不符：原 docstring 称"按姓名匹配"、实现取第一个未绑定行 ⇒ 现**优先按姓名精确匹配**、
        匹配不到才退回旧行为，并把 `bound_match`（name / first_unbound）如实回传前端显示。
        验证：`tests/test_career_teacher.py` 7 passed（含新增 2 例守护姓名匹配与退回路径）；前端 type-check 干净、eslint 0 error。
  - [x] **报告设计已完成（2026-10-14）**：`class_dashboard` 新增**班级级聚合** —— `summary`（参与/完成/完成率/可评估数 +
        全班各维均分 + **最弱维度**）与 `attention`（需关注学生清单，每条带 **可反查的 reason + detail**）。
        教师端看板已呈现。**诚实约束**：最弱维度是**纯相对排序（均分升序，top3）**，不引入绝对达标线；
        attention 只依据结构性事实（未开始/未完成/无评分/得分相对靠后），不给能力或心理定性；无数据即标注缺失不插值。
- [ ] ③ **成效证据链**
  - [x] **现状核查完成（2026-10-14）** → `plans/pilot-design-2026-10-14.md`。
        🔴 **结论：目前零真实用户**。本机 946 场会话但**只有 11 个账号、全是 `test_/smoke_/e2e_` 前缀**，
        297 个班里 194 个是空班；服务器数据已清理为 0。
        **禁把任何条数（尤其"946 场"）当规模或成效引用** —— 对外唯一诚实说法是「尚未开展真实试用」。
  - [x] **取证工具已落地**：`experiments/pilot_evidence_report.py`（只读扫描 + 结构化判据裁决），
        跑一次即得"够不够格叫成效证据"。**引用护栏**：任何对外材料引用成效数字前必须先跑它，
        退出码 1 则不得引用任何条数。闸已双向验证（含变异验证，见 `tests/test_pilot_evidence_report.py`）。
        ⚠️ 顺带修正：基线脚本的库隔离曾**静默失效**（`db.pg_client` 包属性遮蔽子模块），已改用
        `importlib.import_module` 并加 fail-closed 自检；被污染的 20 场服务器记录已清理。
  - [ ] 试用设计：5–10 人 / 一个班，前后测 + 对抗评分留痕（设计与报告口径已定稿，**待用户拍板是否执行**）
  - [ ] 报告写法：样本量如实标注、定性为"探索性"，**不做显著性宣称**（模板口径已写入设计文档）

## 待用户确认

- [x] ~~10-28 解冻的准确范围~~ —— **作废**（用户 2026-10-13：「不要解冻」）
- [ ] 品牌外链边界（A1）
- [ ] 未来三拼图优先级（赛事导向 → ②③；产品导向 → ①②）

## 系统理解任务

- [ ] 理解 Triage 分级路由 + 三元评审校验壳的判定链路
- [ ] 掌握 MAPPO 教学策略层与 GOMARL 共识引擎的关系
- [ ] 搞清 main → career-literacy 单向同步机制，避免双向漂移

## 已完成

- [x] 2026-10-13 **拼图① 第一步**：服务器配 key + 4 场景 mock vs 真实对比基线跑通并落档
      （`experiments/career_llm_baseline.py` + `experiments/results/career_baseline_*`）
- [x] 2026-10-13 源码包清理与提交清单同步（`e133087`，恢复点 `b20b70f`）；制定路线图 `plans/roadmap-2026-10-13.md`
- [x] 2026-10-13 两项 P1 闭环（quality_gate fail-closed `2ce9154`；诚实红线扫描归一化 `cc31b74`）
- [x] 2026-10-10 10-06 的 9 条 P0 全部闭合复测通过
- [x] 2026-09-19 交付口径深度订正（docx 页脚 / 作品介绍 / 源码包全量对齐真值）
