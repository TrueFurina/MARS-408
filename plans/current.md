# 当前计划

> 详细路线图见 `plans/roadmap-2026-10-13.md`（站位快照 / 近期 / 中期 / 未来三块拼图 / 风险护栏 / 待确认项）。
> **下一步分层规划见 `plans/next-steps-2026-10-14.md`**（2026-10-14 架构师产出 + 逐条磁盘复核：P0/P1/P2 分层、依赖、分批、待拍板决策点）。
> 决策记录见 `plans/decisions.md`。

## 待办（解冻后第一批 · A 组）

- [x] ~~A5 重新生成源码包~~ —— **已取消**（用户 2026-10-13 指令：**不要任何交付、不要任何压缩包、不要解冻**）
- [x] A1 公开站外链 `MARS-408` 仓库地址处置（2026-10-14 闭环 `4350401`：用户裁决「没人看」——零真实用户 ⇒ 入口存在但受众为零。删 LandingView「查看部署文档」+ LoginView 整个 pub-notice 块（外链是该块唯一出路），连带清 isLocalRun/pub-notice CSS/rg-link 孤儿样式。可达性不损失（#docker 锚点仍在仓库 README）；删除非安全动机（仓库名已由 Pages 域名暴露））
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

- [x] P1-1 浮层焦点管理 + A 类升硬门禁 —— 2026-10-14 闭环（`a749cc0` + `eb1d0d5`）：
      新增 `src/composables/useModalFocus.ts`（打开聚焦 / Tab 圈闭 / 关闭归还 opener /
      unmount 兜底，纯原生无依赖），VideoPlayer + LandingView 两浮层接入；
      `a11y_scan.py` 落地 `--gate-class`（**10-13 记忆称检测逻辑已备实为未落地**，本次补写）
      并 fail-closed（扫描面 0 个 .vue / 未知类 → exit 2），`verify-structural.yml` 接入为 PR 阻断项。
      A 类 2→0；门禁六路自证（真绿/变异红/两条 fail-closed/不误伤/隔离可判）；
      9 例回归 spec 双向变异验证；全量前端 23 文件 / 152 测试通过。
- [x] P1-2 紫族清零 —— 2026-10-14 闭环（`ae99337`）：**计划前提被取证推翻**，17 处没有一处
      是该换成 `var()` 的样式硬编码（canvas 兜底 8 / 色板数据 2 / 分类调色板 9），归一会造成
      canvas 取色失效 + 色板自引用 + 徽章画像配色压平。改为零产品代码的**豁免机制**：
      `scripts/token_scan_exemptions.json`（10 条规则覆盖 17 处，reason 枚举 + 格式错即响）
      + **僵尸豁免检测**（规则不再命中即 exit 1，且拒绝刷新基线）；清单不写 line（findings
      行号是 strip_comments 后的偏移值）。基线降到新低：total 201→128、brand-violet 31→**0**、
      known 57→51、untracked 113→77；双向变异验证（僵尸检测红 / 绕过豁免红）。
- [x] ~~冻结区 PPT 重生成~~ —— **已取消**（PPT 属交付物，用户指令「不要任何交付」）

## 中期（打磨次批 · B 组）

- [x] B1 数字漂移与过度承诺文案逐条复查 —— 2026-10-15 **全量闭环**（`4ddcaeb`）：对活视图 12 条数字宣称逐条对照代码真值（口径先行），9 条本就正确、4 处改动修 3 类问题（「8个AI智能体」旧架构残留→7 生成器真值 / DashboardView 标签「审核报告」→「视频脚本」/ LandingView 讯飞卡举例与「星火 10 项多模态」外延错→按 `get_all_status` 实际 10 项列举）。裁定文档 `deliverables/engineering-assurance/number-drift-audit-2026-10-15.md`。此前 `36f08ed`（2026-10-13）已完成引用三项（46→47、「面试」→精确场景名、「3 实训模式」→「4 对抗场景」）
- [x] B2 legacy MARL 死代码归档决策 —— 2026-10-14 复核**闭环：非死代码，全部保留**。引用取证：`gomarl.evaluate` 生产在用（`generator_cluster.py:195` / `api/agents.py:137`）；`mappo_policy` 生产在用（`coordinator.py:104` / `gomarl_mixer.py:889`）；`algorithm_factory`/`marl_dqn` 被测试引用（`test_t1_qa_supplement.py:21` / `test_m4_marl_bench.py:16`）；`train_mixer*` 被实验脚本引用。与 `a711ed7` 结论一致
- [x] B3 4 个孤儿视图决策 —— 2026-10-14 复核**闭环：非孤儿，全部保留**。`CourseExplorerView`/`KnowledgeGraphView` 被 `KnowledgeView.vue:8-9,263,268` 挂载；`ReviewView`/`QuizHistoryView` 被 `WrongQuestionsView.vue:7-8,312,317` 挂载。47 视图计数含它们是对的。与 `a711ed7` 结论一致
- [x] B4 `api/tutor.py` 懒加载 + CLAUDE.md 过时警告 —— 2026-10-14 复核**前提失真，无需改动**：① `api/tutor.py` **已在函数内懒加载** `agents.tutor`（:53，附注释说明为何不进顶层——重依赖会拉起向量/嵌入栈），现 :11 为 `db.llm_provider` 顶层 import（轻依赖，合规）；② CLAUDE.md 三处"陈旧"均已自愈：:74 fail-open 已改 fail-closed（删除线标注"2026-10-13 已改"）、:101 种子计数已改为"以命令为准"、:179 分支位次已改为"以 `git log` 现查、勿写死提交号"
- [x] B5 真实浏览器 E2E 走查（2026-10-14 完成）—— 第一次在浏览器里把整条链点完，
      并抓到 2 个只有浏览器能看见的问题（教师登录落学生测评 / 三条职员路由无角色守卫）
      + 1 个前端看不见的后端读空 bug（看板六维均分恒空）。均已修 + 已用走查复验。
      记录 `deliverables/engineering-assurance/browser-e2e-2026-10-14.md`；
      脚本 `scripts/e2e/teacher_loop_walkthrough.cjs`（人工运行，不在 CI）。
      ⚠️ F1/F2 尚无自动化守护（前端无测试基建）—— 见报告第八节。
      ✅ **守护已补（2026-10-14 续）**：`src/router/landing.ts` 把登录落点口径提为纯函数
      （LoginView 改调用），新增 `src/router/landing.spec.ts`（7 例，F1 三分支回归）
      与 `src/router/guards.spec.ts`（8 例，F2 三路由 + A2 /sandbox + /admin 系 meta 在位）；
      **双向变异验证**：改回旧落点逻辑 → 教师/管理员 2 例红；删 /sandbox meta → 对应 1 例红。
      全量前端 22 文件 / 143 测试通过。报告 §8 的「零 vitest 用例」判断在其写就时已开始过期
      （当日其他会话已落 navConfig/useBenchmark 等 spec），以本提交时的全量结果为准。
      ✅ **导出走查复跑（2026-10-15，`ec53cda`/`781ed02`）**：同一脚本加 D 步（看板 CSV 导出验证）
      重跑全环通过，抓到并修复 F4（无证据维度从六维里消失，三处展示层同修 + 回归测试 + 变异验证）。
      记录 `deliverables/engineering-assurance/browser-e2e-2026-10-15.md`。
      另修走查脚本与 hash 路由迁移（2026-10-15）的失配：6 处导航改 `BASE+'#/<route>'`、落点判定看 hash 段。

## 主线（用户 2026-10-13 批准：三拼图全部拓展）

> 实测前提（本轮已验证）：项目**零代码改动**即可用真实 LLM —— `config.py:473` 的 env_map 已支持
> `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` / `LLM_PROVIDER`。
> 本机实测：`LLM_PROVIDER=deepseek` → 通道判定 `deepseek-chat`、key 注入成功、真实调用返回可用内容。
> 仓库探活：**DeepSeek ✅(0.97s) / 智谱 GLM ✅(0.60s)** 可用；DashScope·Moonshot·SiliconFlow·OpenRouter 均因账号/地区不可用。
> ✅ 服务器 `172.16.222.99` 已于 2026-10-13 配置 `~/study-help-pro/py-server/.env`
> （`LLM_PROVIDER=deepseek` + key，chmod 600）。服务器**零安装**即可跑 career 链路——
> 用 `/home/user/miniconda3/envs/all-in-rag/bin/python`（含 langgraph/fastapi；career 链路
> 不依赖 Milvus/Redis，缺失时自动回退）。注意 `~/studyhelp-venv2` **缺 langgraph**。

- [x] ① **真实 LLM 接入** —— 2026-10-17 收官：四通道设计口径 + 真实可用 2 段（DeepSeek/GLM）已实证；
      讯飞 LLM 全候选 11200 确认未开通（需控制台操作，非代码项）；TTI/TTS 已开启并端到端实证
      （详见 ① 节内记录与 engineering-assurance/number-drift-audit-2026-10-15.md §五）。
  - [x] 通道探活 + 项目侧端到端首验（本机，2026-10-13）
  - [x] 服务器配 key（`~/study-help-pro/py-server/.env`，2026-10-13，chmod 600）
  - [x] **4 场景 mock vs 真实对比基线已跑并落档**（2026-10-13）——
        脚本 `experiments/career_llm_baseline.py`；数据 `experiments/results/career_baseline_*.json`；
        逐项对比 `career_baseline_compare_2026-10-13.md`；结论 `career_baseline_结论-2026-10-13.md`。
        要点：兜底模式 4/4 场景可跑完但**六维只覆盖 2 维、追问退化为指令标签、overall 恒 2.60 无区分度**；
        真实模式 4/4 场景脚本由 LLM 生成、六维覆盖 5~6 维、追问能抓住答非所问、overall 有区分度（2.60/4.45/3.15/3.10）。
  - [x] **GLM 第 4 兜底通道已接入 + 回退链端到端实证**（2026-10-13 接入 `f121c3a`/`17b8f1f`；
        2026-10-15 实证 `538db7e`）——ADR-020 口径「四通道容灾：讯飞X2 → DeepSeek → Qwen → GLM」。
        `experiments/verify_llm_fallback_chain.py` 真实网络故障注入：s1 xfyun 故障→回退 deepseek 成功；
        s3 前三通道全故障→回落 GLM 成功；含恢复校验（退出码契约同 pilot_evidence_report）。
        🔴 **2026-10-17 复测（真实网络，双次验证）：xfyun 全部 5 个候选（当前 generalv3.5 /
        4.0Ultra / spark_x2 / pro128k / pro-128k）均 `AppIdNoAuthError (11200)`
        （HTTP 500，账号授权问题，非暂时故障）⇒ 真实可用通道 = DeepSeek + GLM
        （qwen 欠费真实失败）**。「四通道」是设计口径，可用性为 2 段，
        对外叙述须区分；讯飞 LLM 授权需用户侧到控制台开通。
        🟢 **同日重大发现：TTI 图片生成 / TTS 语音合成均已开通且真实可用**
        （HMAC 鉴权探活：TTI HTTP 200 code=0 + 183,500 字节真实图片；
        TTS WS code=0 + 3,168 字节真实 MP3）——config 的
        `tti_enabled`/`tts_enabled` 已双双置 True（config.json，2026-10-17 用户拍板）；
        端到端实证：真实生成 73,436 字节插图 + 25,344 字节 MP3，source=xfyun。
        失败路径均优雅降级（TTI code≠0/异常→SVG；TTS 异常→浏览器）无断链风险。
        发布包已同步（config.json flags + .env 三凭证，云端运行时模拟验证可用）；
        云端实际生效待发布（账号阻塞见 memory 2026-10-17）。探活脚本 `_xf_probe.py`（仓库根，未跟踪）。
  - [x] **查实并修复「开场问题被种子锁死」**（2026-10-13）——基线跑一次即暴露：4/4 场景两模式开场逐字相同，
        实证为 LLM 把提示词里的「参考开场」原样回填。改 `prompts_career.py` 3 处措辞（种子开场降级为"仅情境参考、必须重写"），
        复测 4/4 开场全部改写且质量提升；差异数 53 → 58。
  - [x] **混态用例已补（2026-10-13）**：`--mode mixed --fail-after N` 故障注入（每场前 N 次调用放行）。
        `fail-after 4` 实测 4/4 场次跑完不崩；评估虽降级为 `rule_fallback`，但 overall 恢复区分度
        （2.78/4.54/3.17/4.12，而纯兜底恒 2.60）、有分维度 2→5~6、含原话链条 2→5~6。
        📌 **定位出真正的质量瓶颈 = 「证据采集」（每轮取证的 LLM 调用），不是评估器** —— 若降本，最该保住取证。
- [x] ② **教师侧最小教学闭环** —— 2026-10-17 收官：学生侧断链已补齐（任务码加入+task_id 透传）、
      班级聚合看板/CSV/F7 一页纸/F1 下钻/F2 任务中心/F3 学生任务中心/F4 成长页/F5 前后测/F6 同意+简评
      全族落地并有测试守护（test_career_teacher.py 20 例）；剩余为拼图③的试用执行决策（见 ③）。
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
  - [x] **报告设计已完成（2026-10-14）**：        `class_dashboard` 新增**班级级聚合** —— `summary`（参与/完成/完成率/可评估数 +
        全班各维均分 + **最弱维度**）与 `attention`（需关注学生清单，每条带 **可反查的 reason + detail**）。
        教师端看板已呈现。**诚实约束**：最弱维度是**纯相对排序（均分升序，top3）**，不引入绝对达标线；
        attention 只依据结构性事实（未开始/未完成/无评分/得分相对靠后），不给能力或心理定性；无数据即标注缺失不插值。
  - [x] **看板 CSV 导出 + 导出走查 + F4 修复**（2026-10-15，`648c115` 导出 / `ec53cda`+`781ed02` 修复）：
        教师端补 `exportDashCsv`（纯前端、BOM+UTF-8、逐人表+班级均分行）；走查脚本加 D 步全环验证通过。
        🔴 **F4（走查抓到）**：无证据维度从「六维」整列/整 chip 消失（前端看板/前端 CSV/后端一页纸三处同病，
        根因在展示层按数据键渲染，不在评估）⇒ 三处改固定迭代 canonical 六维、无数据显「无数据」，
        CSV 列结构恒定 12 列；API 契约不动（空班级仍 `dimension_avg=={}`）。回归测试 + 变异验证 +
        全新隔离库全环重跑（列数 11→12）。证据 `deliverables/engineering-assurance/browser-e2e-2026-10-15.md`。
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
  - [x] ~~试用设计：5–10 人 / 一个班，前后测 + 对抗评分留痕~~ —— **2026-10-21 用户拍板：实测略过（「实测略过，完不成」）**。物料已归档（脱敏花名册 47 条，PII 不入库），试用**未执行**，证据链保持缺口；闸门复跑 exit 1。
        **2026-10-26 复跑更新**：未满足项已变为**两条**——`单个班最多已绑定非测试学生 2 < 3`
        + 第 5 条「有 124 个账号既非已知测试夹具、也不像学号 ⇒ 数据源不可信」；
        输出同时**隐藏整张统计明细表**（不再打印 `sessions_total` 等可抄走的条数）。
        见 `plans/pilot-material-2026-10-21.md`
  - [x] **取证闸口径加固（2026-10-26）** —— 由「只排除已知黑名单」升级为**两层**：
        ① 黑名单把**已知**夹具识别干净（抬高 `distinct_users_real` 精度，登记只是调优）；
        ② 第 5 条判据 `nonnumeric_candidates == 0`（**认不出 ⇒ 算不可信**）——非学号、未登记的账号
        一律判数据源不可信，且 `render()` **隐藏整张统计明细表**，不再打印 `sessions_total` 等可抄走的条数
        （隐藏判据读 `stats["nonnumeric_candidates_n"]`、**不依赖 verdict**，两层互为兜底）。
        🔴 **关键取舍**：`stu_` / `diag` **刻意不登记**黑名单——登记会让 `real_candidates_n` 归 0、
        第 5 条永不触发、明细表照常打印。变异矩阵给出直接反证：登记后 `0/0` 看着最干净，
        代价恰恰是 `sessions_total` 等条数重新可见；**护的是「数字不被抄走」，不是「数字变成 0」**。
        本机库实测：exit 1 + 🔴 横幅 + `| sessions_total |` 出现 0 次（`real_candidates_n=124` / `nonnumeric=124`）；
        正面对照（5 个纯数字学号 / 15 场 / 10 场带 task_id / 一班绑 3 人）仍 exit 0 ⇒ **闸门没被焊死**。
        提交 `2b3f517` / `649d7a0` / `ab6b44a` / `31e09dc` + 时点锚纠正 `980c235` / `d80bee3`。
        ③ 本身仍是缺口：闸门保持 exit 1，**对外唯一诚实说法仍是「尚未开展真实试用」**。
  - [ ] 报告写法：样本量如实标注、定性为"探索性"，**不做显著性宣称**（模板口径已写入设计文档）

## 待用户确认

- [x] ~~10-28 解冻的准确范围~~ —— **作废**（用户 2026-10-13：「不要解冻」）
- [x] ~~品牌外链边界（A1）~~ —— **2026-10-14 已闭环**（`4350401`：删 LandingView「查看部署文档」+ LoginView 整个 pub-notice 块；理由见本节上方 A1 条）。此前本行与上方 A1 条标记不一致，属清账遗漏。
- [x] **R1 部署选型（2026-10-21 拍板：维持云托管=C 已落地）**：当前线上全栈零降级已满足演示需求，不升级 VPS(A)、不改局域网(B)。简报 C 项「等云 BaaS 修复」表述已过时（实际走 cloud-service）。
      简报 `plans/r1-decision-brief-2026-10-18.md`（已加「试用略过 ⇒ 纯部署/演示决策」状态块）。
      注：瘦包已刷新零漂移，选 A/B 可直接用。
- [x] **线上模拟数据是否保留（2026-10-21 拍板：保留）**：当前线上「信息安全1班-模拟演练」班 47 人名册+10 加入+6 完成的
      模拟数据（sim_ 前缀+合成名+班名标识，可识别为模拟、不造假）保留供评委演示；清理需新增通道（班非空删不掉），不接受清理。
- [ ] **③ 最终形态（2026-10-26 待拍板）** —— 建议定死为：不做真实试用；如需演练只用 `sim_` 纯模拟；
      闸门保持 exit 1；对外仍称「尚未开展真实试用」。当前按此默认执行，未被推翻。
- [ ] **R1 目的口径是否改述（2026-10-26 待拍板）** —— 是否由「真实学生试用可达」改为
      「评委/现场可访问」。当前按此默认执行，未被推翻。
- [ ] **孤儿函数 28 项待删是否执行（2026-10-26 待拍板）** —— 治理已落地（闸门「未登记即红」、
      台账 `28 待删 / 4 pending-product / 8 保留`），**一个函数都没删**。
      删除会同时改变 `backend_py` / `backend_lines` 与 README/提交清单的副本，需连带刷文档，
      故本轮刻意不做，留作独立批次。裁定见
      `deliverables/engineering-assurance/orphan-function-adjudication-2026-10-26.md`。
- [x] ~~未来三拼图优先级~~ —— **2026-10-15 用户拍板：产品导向 ⇒ 聚焦拼图①（真实 LLM）+ ②（教师侧闭环）**；③（成效证据链/真实试用）与 B 组余项暂缓。① 的兜底链实证与② 的导出走查均已按此收口。

## 系统理解任务

- [x] 理解 Triage 分级路由 + 三元评审校验壳的判定链路
- [x] 掌握 MAPPO 教学策略层与 GOMARL 共识引擎的关系
- [x] 搞清 main → career-literacy 单向同步机制，避免双向漂移
      —— 三项均完成（2026-10-14，只读分析）→ `deliverables/engineering-assurance/系统理解-Triage-MAPPO-GOMARL-同步机制-2026-10-14.md`。
      要点：Triage 纯规则 + API 层短路（零评审快路径）；三信号 = honest/critic/consensus，
      均匀权重=行为零变化，MAPPO 调权重全走灰度 flag；MAPPO×GOMARL 有三个真实接入点
      （mixer 动态权重已激活 / gate 评审权重灰度 / debate 内容预算灰度）；同步 = 单向
      `git merge origin/main`（历史 6 个 merge 提交可查）+ `career_*` 前缀隔离（ADR-015）。
      🔴 顺带抓到文档漂移 3 处（CLAUDE.md:74 fail-open 陈旧——代码早已 fail-closed；
      :179 main 冻结位次陈旧；:101 种子计数陈旧）与风险 4 项（policy_action 无下游消费/
      gomarl_bridge 死代码/_build_networks 私有 API 耦合/models gitignore 致 CI 必降级）。
      其中 policy_action 已于同日接线闭环（见下）；余 3 项仍开放。

- [x] `policy_action` 处置 ——2026-10-14 闭环（`7285083` + `7048ea7` + `820941f` + `a9f4205`）：
      用户拍板**选项 2（接线 teaching_mode）**。含一个前置修复与一次基线：
      - 接线：`teaching_mode`（三取值 sequential/example_first/analogy）注入 teacher prompt
        的输出格式提醒之前；**只对 teacher 生效**；`gomarl.use_teaching_mode_prompt` 为
        kill-switch（关掉即回到接线前逐字等价）；未知取值 fail-open 到现状。
      - 🔴 前置缺陷：生产 `student_profile` 契约是 `weak_points`（字符串），而
        `decide_policy_action` 读`weak_topics`/`weak_subjects` ⇒ `example_first` 是**死取值**，
        不修则接线也是死代码。已加 `_teaching_weak_count` 按真实契约计数（兼容中文逗号与
        list，旧键优先）。**刻意不动 `review_intensity`**（评审强度控制面，与 ADR-011 权重
        灰度不同层，改它会顺带改评审行为）。
      - 基线（真实 LLM deepseek-chat，2 topic × 2 profile × 4 臂 × 3 重复 = 48 次、0 错误）：
        主指标「开头即场景引入率」example_first **12/12 = 100% Wilson[0.76,1.00]**，
        baseline/sequential/analogy 均 0/12 = 0% Wilson[0.00,0.24] ⇒ **区间不重叠、效果显著**；
        内容退化率全 0。
      - 🔴 方法论教训两条：① 初版「各臂按自己定义判合规」是**循环论证**（baseline 可比性 0），
        必须用模式无关的主指标让所有臂同尺量；② 探针词表须据**真实产物人工核对**归并
        （模型几乎不用"定义/是指"字面；且话题与薄弱点必须同领域，否则模型开篇会纠正错位）。
      - 21 例回归 spec 双向变异验证（删注入 if → 3 红；口径改回旧 → 3 红）。
      - **仍未接线**：`review_intensity`（无采样层）与 `difficulty`（两套坐标，不混传）。

## 已完成

- [x] 2026-10-21 **教师端真浏览器全流程 E2E → 抓 3 个真问题 → 修 → 上线**（65dcbfb/305fb21/cb56f6c/eb8cb98）——
      新脚本 `scripts/e2e/teacher_console_ui.cjs`（写/只读双模，本地零污染环境跑）：
      ① 看板口径混淆：学生凭码加入只绑名册不产会话，原看板只有 started_count ⇒ 「已加入未开练」
      显示成参与 0，教师误判"没人来"。修：`class_dashboard` 加 `joined_count`，前端分列
      「已加入/已开练/完成」+ 锁定测试（变异检验过）；② 花名册姓名≠注册名 ⇒ 成绩记到别人名下
      （后端 matched_by=first_unbound，教师侧无感知），导入区补口径提示；③ 两个导出按钮无回执。
- [x] 2026-10-21 **线上只读巡检抓第 4 个缺陷：getBlob 漏 X-App-Token ⇒ 线上 401 + 被踢登录页**（cb56f6c/eb8cb98）——
      CloudStudio 网关替换 Authorization，只透传自定义头；同族漏头还有 upload / ttsSynthesize
      （TTS 吞错降级所以一直是死的没人发现）。修：统一走 `getAuthHeaders()`；
      新增契约测试 `src/utils/api.spec.ts`（5 例逐方法断言双头，变异检验：改回单头⇒仅对应用例红）。
      教训：**"本地绿"对网关替换头零防御，只有线上巡检能抓**。
- [x] 2026-10-21 **tutor/mindmap 五处「Qwen2.5」死口径清理**（f5bfbe5）——ADR-020 后 LLM 走四通道路由，
      docstring 会随 openapi.json 发给评委 ⇒ 对外契约自相矛盾。重生成 openapi.json 时发现
      `src/types/api.generated.ts` 早已落后 421 行（10-18 口径注释、删除端点都没同步过）⇒ 一并补齐。
      教训：**openapi.json 与 api.generated.ts 必须同 commit 刷新，docstring 改动也算**。
- [x] 2026-10-21 **教师试点操作手册交付**（4af9275）——`deliverables/教师试点操作手册-2026-10-21.md`，
      每步经真浏览器实测；第 0 节四条必读口径（姓名是绑定钥匙/加入≠开练/终评等 1–2 分钟/报告看来源标签）。
- [x] 2026-10-21 **CI 三连红自查与闸门修复**（a5efed5/416b19b/a9d4a6e）——① 契约审计把 vitest spec
      当生产调用（只排 __tests__ 目录、漏后缀约定）⇒ 补 `*.spec.*`/`*.test.*` 排除 + 变异检验；
      ② METRICS 铁律再确认：**--update 前工作树必须等于将提交的状态**（未提交 .py 编辑会烙进文档）；
      ③ **新增 .py 会同时动两个文档面**（METRICS_CURRENT.md + README 指标行），漏一个就被另一个闸拦。
- [x] 2026-10-21 **计算机模拟演练闭环**（a8ff089/416b19b，用户拍板「真实试点不可能，纯按计算机模拟来」）——
      脱敏花名册 47 条（只取学号后4位，**政治面貌列不读**；含重复学号 5129 两条如实记录）；
      新脚本 `py-server/experiments/career_class_simulation.py`（本地+线上双模式）；
      结果：已加入 10/47｜开练 8｜完成 6｜**6/6 assessment_source=llm**（本地 deepseek 综合 1.45–1.93、
      线上 glm 3.15–3.79，两个模型都真实、并列呈现）；`sim_` 前缀登记进证据闸门排除清单 ⇒
      复跑 `pilot_evidence_report.py` **仍 exit 1**（未制造"试用已开展"假象）。
      报告 `deliverables/模拟演练报告-信息安全1班-2026-10-21.md`；线上已建同规模模拟班供评委演示。
- [x] 2026-10-21 **一页纸导出漏档缺陷**（2dfa07d/b878b10）——线上演练导出 HTML 搜不到「已加入」：
      10-20 看板拆三口径时漏改后端导出模板 ⇒ 归档产物（过程性考核依据）丢「已加入未开练」档。
      统计卡改六项与看板同口径 + 锁定测试（精确锁 sw-h 标签位）+ 变异检验。
- [x] 2026-10-21 **部署包 18 处漂移刷新 + 全量发布**（本日第 4 次发布）——`build_career_pilot_package.py`
      刷新（复制 18/未变 360）；发布前用包本身冒烟抓到**运行时自写目录不是包的组成部分**
      （冒烟写入 data/ 空库 + vectordb_data/ 16M 禁止产物，--check fail-closed 报红后清除）。
      线上终态：/api/status ok 零降级、两班数据完整、UI 零控制台错误。

- [x] 2026-10-19 **P0 安全宣称独立审计（不采信文档、逐条代码取证）** —— 新增
      `deliverables/engineering-assurance/security-claims-audit-2026-10-19.md`（只读审计，零改动）：
      六项安全机制全部代码级证实（auth fail-closed 三态 / 启动 fail-fast 时序 / ensure_admin 无默认 /
      PBKDF2 60 万次+防时序 / save_config 密钥剥离 / 密钥残留扫描 0 命中）；限流机制属实但简报
      README:78 引用失实（已删线标注，真值 20 次/小时 @ `api/auth.py:43`）；旧「14 P0」中
      区块链桩（0 命中）/AI 导师零调用（langgraph.py:63 已接线）/伪造证书（仅词库数据）三项
      确认已消解 ⇒ **安全面宣布闭环，「14 P0」叙事建议退役**，对外改述「安全项 10-18 前闭环并经独立审计证实」。
- [x] 2026-10-17 **前后端契约交叉审计（主动深审第三轮）** —— 新增
      `scripts/audit_api_contract.py`（report-only / `--gate` 双模，纯 stdlib 1.2s）：
      后端真值 = openapi.json（复跑确认 237 paths / 255 ops 与运行时一致），
      前端面 = src/ 全量字面量+模板+api.ts 全方法族。**A 类（前端打到不存在的路由）= 0**
      （从初版 79 处疑似逐类修正误报收敛而来：模板未采/泛型吞路径/四方法族漏采/
      缺 /api 前缀/字面量填参数/query 拼接/跨盘符 relpath 崩溃——最后一条是测试
      抓出的真 bug）。B 类 102 条孤儿逐条人工分类：9 状态诊断 + 2 客户端自处理 +
      4 legacy 别名孪生 + 3 工具固有漏判（实为在用）+ 84 后端完整前端未接；
      **零删除零改动**（红线 + BP 规模口径以 openapi 全量为真值源）。
      鉴权面核验：254 操作 / 241 保护 / 13 公开（逐一附理由）/ unregistered=0 /
      coverage 94.88%，与 METRICS_CURRENT 一致。CI 接入 verify-structural.yml
      （只 gate A 类）；测试 15 例（`py-server/tests/test_api_contract_audit.py`，
      按 TDD 纪律与实现分 commit）+ 三重变异验证（占位容错删→3 红 / gate 阻断删→1 红 /
      fail-closed 放行→1 红；变异脚本经 heredoc 被吞反斜杠致「假存活」，已用文件级
      行操作重做确证）。记录 `deliverables/engineering-assurance/api-contract-audit-2026-10-17.md`。
      附带：仓库根 3 个未跟踪 scratch（`_md2docx.py` / `_xf_probe.py` / `_mut2.py`）
      移入 `archive/scratch-2026-10-17/`（gitignored，仅移动零删除）。
- [x] 2026-10-17 **生产调用点审计（孤儿函数 / stub 巡检，主动深审第四轮）** ——
      新增 `scripts/audit_orphan_functions.py`（纯 stdlib AST 3.2s，report-only）：
      生产面 202 文件 / 1501 函数定义，引用面全仓 483 文件（含别名导入 +
      字符串动态分发 + 装饰器/dunder/抽象方法豁免）。T1 全仓零引用 40 个、
      T2 仅测试/脚本引用 37 个、T3 入口豁免 603 个。**逐条人工 grep 反查裁定：
      零删除零改动**。关键结论：① `db/graph_db.py` 全仓零 import = 整模块死亡
      （NetLearn 时代 Neo4j 风格 KG 存储，已被 `agents/knowledge_graph.py`+
      `api/knowledge_graph.py` 取代，保留）；② 死集中 `sanitize_input`↔
      `filter_sensitive`+`ANTI_INJECTION_INSTRUCTION`、`run_semantic_check`↔
      `should_run_semantic_check`+`classify_intent` 交叉核对 ⇒ **无安全缺口**；
      ③ `get_llm_config` 冗余 helper、`init_db` NetLearn bootstrap 残留（career 经
      `ensure_tables()` 惰性建表已证可用）⇒ 非 bug；④ 余 39 项 = 可选特性未接线 /
      冗余 helper / 测试注入 / 运维 CLI，全保留。诚实裁定：**本轮未发现关键 gap**
      （性质异于 SecAutoMind 的 CreateInstance/GetAccess 未调用——彼处是生产该调未调，
      此处是功能由其他路径完整提供）。工具两轮缺陷修复（别名导入不可见 / T2 分层误判）
      均有测试守护（5 例，含真仓库 T1=40 基线快照）。记录
      `deliverables/engineering-assurance/orphan-function-audit-2026-10-17.md`。
      未进 CI 阻塞门（T1 全为已裁定保留项，gate 会逼出违规删端点），作周期巡检。
- [x] 2026-10-16 **全量测试异常查证 → 查出并修复「测试销毁真实向量库」事故**（`64994b2`，已 push）：
      28 errors = 全量跑时本地后端并发争用夹具（停后端后单跑 16 passed，教训：二者不得同时跑）；
      1 failed = `test_installed_hook_matches_canonical_source`（10-15 xargs 探针热修复只改进已装钩子、未回写真源）。
      🔴 **重大发现**：可达性矩阵 17 个管理端条目 `needs_auth=False` + conftest `mock_auth`（autouse）
      把 admin 依赖顶掉 ⇒ `/knowledge/reindex`、`/clear` 等**以 admin 真实执行**，两次全量跑各删一次
      真实 `vectordb_data/netlearn_kb.json`（2245 条教材语料）+ `.emb.npy`。修复：矩阵引入 `GATE` 哨兵
      （动态清 mock + 断言 401/403）。KB 已从 `vectordb_data_pre_multi_bak/` 备份完整恢复（2245 条验证可加载）；
      该备份是 KB 唯一备份（`documents/` 教材 PDF 已不在仓内）⇒ **保留不删**。终验全量 1323 passed / 0 failed。
- [x] 2026-10-16 **限流兜底淘汰算法 O(N²) → 摊销修复**（本次）：`test_concurrent_distinct_keys_respect_memory_bound`
      在覆盖插桩下稳定超 30s 超时（前两次全量跑被迫 `-k` 排除）。根因：`_evict_local_buckets` 每次新建 key
      全量 sort 4096 项，12800 次互异 key 灌入裸跑 9.99s 且全程持锁。修复：`heapq.nsmallest`（与 sorted[:n]
      结果等价）+ 触顶一次淘汰 10% 最旧桶（摊销 ~10×）⇒ 裸跑 0.04s、带覆盖 15.16s 通过。
      新增语义守护 `test_memory_bound_evicts_oldest_first`（原测试只断言上界不断言淘汰对象），
      变异验证（nlargest → 红）。该 flaky 排除项已回收，全量不再 `-k` 排除。
- [x] 2026-10-16 **push career-literacy 到远程**（`26f7139..781ed02`，SSH，ls-remote 权威核对）：
      含本轮三提交——`538db7e` 四通道回退链端到端实证（+xfyun 11200 实测发现）、
      `ec53cda` F4 六维缺维修复（看板/CSV/一页纸三处）、`781ed02` 回归测试。
- [x] 2026-10-15 **拼图① 兜底链端到端实证**（`538db7e`）：`experiments/verify_llm_fallback_chain.py`
      真实网络故障注入，s0-s3 + 恢复校验全 PASS；「DeepSeek 故障 → 回落 GLM」完整跑通。
      同期实测发现 xfyun 两预设均 11200（授权问题）⇒ 当前可用通道实为 DeepSeek + GLM。
- [x] 2026-10-13 **拼图① 第一步**：服务器配 key + 4 场景 mock vs 真实对比基线跑通并落档
      （`experiments/career_llm_baseline.py` + `experiments/results/career_baseline_*`）
- [x] 2026-10-13 源码包清理与提交清单同步（`e133087`，恢复点 `b20b70f`）；制定路线图 `plans/roadmap-2026-10-13.md`
- [x] 2026-10-13 两项 P1 闭环（quality_gate fail-closed `2ce9154`；诚实红线扫描归一化 `cc31b74`）
- [x] 2026-10-10 10-06 的 9 条 P0 全部闭合复测通过
- [x] 2026-09-19 交付口径深度订正（docx 页脚 / 作品介绍 / 源码包全量对齐真值）

## 已拍板（2026-10-17/18，详见 decisions.md）

- [x] **P0-C 在飞部署物处置** —— `deploy/career-pilot/` 保留不删（本地唯一 VPS staging 快照；删除前须 SSH 核实 `/opt/career-pilot`）；`dist/` 保留（已重建为最新）。
- [x] **P1-D review_intensity** —— 维持后置守卫方案不变，不接演示面板文案。
- [x] **解冻令分类执行** —— 活文档层已清（`6a5c9d0`）；deliverables//submission/ 保持历史原样；docs/ 双分支治理事实保留。
- [x] **P0-D 残余核查** —— README 已统一 49 views（2026-10-18 复核），build_roadshow_pptx.py 的旧数字均在"禁用守护清单"内，无残留。
- [x] **P1-C 班级级导出** —— 已由功能拓展 Batch 2（`edf7e92`）闭环：看板 CSV + F7 一页纸（自包含 HTML→浏览器另存 PDF），前端已接线（TeacherCareerView:496-499）。
- [x] **P1-E 系统理解遗留 3 风险** —— 2026-10-18 复核全部闭环：① gomarl_bridge 零引用已归档、
      ② _build_networks 公开别名已解私有耦合（均为 `e4fa014`，2026-10-15）；
      ③ "models 缺失致 CI 降级"风险实为已消解——conftest 以 `fake_embedder`+`isolate_vectordb`
      全隔离（无任何测试依赖真实 E5 质量，不存在"降级假绿"面），且降级状态诚实性已由
      `test_app_status_invariants` 机器锁（2026-10-18 `fallback_zero_docs` 真值修复 + 双不变量）。

---

## 闭环判据表（REA #11：没有判据的"完成"不是完成）

> 规则：每一项在开工前就把**判据**写死；判据必须是"一条命令 + 一个可读产出"，
> 不能是"我觉得可以了"。状态三态：`closed`（判据已满足且证据在库）/ `open`（未满足）/
> `unchecked`（没验过，不等于没问题）。新增项必须先补判据再动手。
> 维护要求：每次闭环同时更新本表与证据落点，不接受只在聊天里说"做完了"。

| 项 | 闭环判据（可执行） | 证据落点 | 状态 |
|---|---|---|---|
| 注册/登录限流边界 | `pytest tests/test_rate_limit_boundary.py` → 4 passed，且第 N+1 次返回「操作过于频繁」 | `py-server/tests/test_rate_limit_boundary.py` | closed |
| 限流阈值单一真值源 | `shared/limits.py` 是唯一定义处；`api/auth.py` 无 `max_requests=20` 之类字面量（测试静态断言） | `py-server/shared/limits.py` | closed |
| 班级看板覆盖率说明 | `pytest tests/test_dashboard_coverage_note.py` → 3 passed；导出 HTML 含「覆盖率：」且与 API 同源 | `py-server/tests/test_dashboard_coverage_note.py` | closed |
| 关停有序（后台任务先退再放连接） | `pytest tests/test_lifespan_shutdown_order.py` → 3 passed；退出顺序为 `exit:cleanup` 早于三条 `disconnect:*` | `py-server/tests/test_lifespan_shutdown_order.py` | closed |
| 流式回答来源可判 | `pytest tests/test_chat_stream_provenance.py` → 5 passed；provenance 事件先于 `[DONE]`/`error` | `py-server/tests/test_chat_stream_provenance.py` | closed |
| 用户可见错误文案 | `python scripts/check_error_wording.py --root py-server` → 新增 0 处 | `scripts/error_wording_baseline.json` | closed |
| 广告 schema 无可达递归 | `python scripts/check_schema_advertisement.py --gate` → exit 0；自测 7/7 | `scripts/check_schema_advertisement_test.py` | closed |
| 克隆只增不改（新增闸） | `python scripts/dup_scan.py --gate` → 新增 0 处；自测 6/6 | `scripts/dup_scan.baseline.json` | closed |
| 本地钩子分层 | `python scripts/install_hooks.py --check --quiet` → exit 0（pre-commit + pre-push 均与真源一致） | `scripts/pre-commit/pre-push.sh` | closed |
| 资源分项基线 | `python scripts/resource_profile.py --write` 可复跑，`unknown` 项须写明原因 | `deliverables/engineering-assurance/resource-profile-2026-10-20.md` | closed |
| 试点试用（5–10 人） | 有真实学生账号 + 会话记录 + `pilot_evidence_report` 产出（非演练数据） | 待建 | open（需用户拍板范围） |
| 职业素养实训 v1 真 LLM 冒烟 | 单情景冒烟 JSON 存在、`overall` 有值（2026-10-20 复核：证据在 `py-server/experiments/results/`，不在根 `experiments/results/`） | `py-server/experiments/results/career_llm_smoke_20260913.json` | closed |
