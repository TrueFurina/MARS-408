# B1 全量数字漂移与过度承诺文案复查 · 2026-10-15（机验版）

> 性质：`plans/current.md` B1 的唯一剩余动作——对**活视图**的硬编码数字与过度承诺
> 文案逐条复查。方法：口径先行（先定"真值源"再逐条盘点），每条都以代码/数据文件
> 实测裁定，不信记忆信磁盘。
> 真值源：`py-server/agents/graph.py`（节点）/ `generator_cluster.py`（生成器）/
> `api/diagnostic.py`（题库）/ `experiments/results/benchmark_2026-09-18.json`（benchmark）/
> `db/xfyun_services.py` + `get_all_status()`（讯飞能力枚举）/ `api/career_training.py` 等。

## 一、逐条裁定（12 条活视图数字宣称）

| # | 宣称 | 位置 | 代码真值 | 裁定 |
|---|---|---|---|---|
| 1 | 11 节点 LangGraph | LandingView×2 / EngineView×2 / ResourceView / DashboardView:190 | `graph.py` 11 个 `add_node`（triage+coordinator+diagnostician+planner+retriever+generator_cluster+assessor+critic+evidence_check+quality_gate+path_planner） | ✅ 正确 |
| 2 | 7 种个性化资源 | DashboardView:190 / ResourceView:764 | `generator_cluster.py` 7 个并行生成 Agent（Teacher/QuizMaster/MindMap/Extension/CodePractice/PPTOutline/VideoScript） | ✅ 正确 |
| 3 | 8 维画像 | DashboardView:139 / ProfileView / AssessmentView / DiagnosticView / EngineView | 8 维画像（与职业线 6 维同名不同物，既有口径） | ✅ 正确 |
| 4 | 完成 20 道诊断题 | DiagnosticView:66 | `DIAGNOSTIC_QUESTIONS` 实测 20 题 | ✅ 正确 |
| 5 | 28 条真实查询 | BenchmarkView:221（注释） | benchmark JSON `per_query` = 28 | ✅ 正确 |
| 6 | 讯飞 10 项能力 | LandingView×3 / ChatView:480 | `get_all_status()` 恰好枚举 10 项服务（图像生成/图片理解/聚合搜索/智能PPT/数字人视频/文本纠错/公文校对/文本合规/角色模拟/智能简历） | ✅ 数字正确；**举例错误**（见 #9） |
| 7 | **8 个 AI 智能体协作** | DashboardView:150（DesignUpgradeView:15 自称"同口径"跟随） | 无据：代码里存在三个互不一致的粒度——11 节点（图）/ 7 生成器（集群）/ 8 角色（坍缩 critic+evidence_check+quality_gate 为一"审核"）。"8"是火山杯旧架构残留（`git log -S` 命中 `2866650`），对不上任何现行口径 | 🔴 **已修** → 7 个（生成集群真值） |
| 8 | **标签第 7 项「审核报告」** | DashboardView:151 | 第 7 个生成器是 **VideoScript 视频脚本**（ResourceView 自己的列举也是视频脚本）；「审核报告」不是生成的资源类型 | 🔴 **已修** → 视频脚本 |
| 9 | **「语音识别、语音合成、OCR、数学能力、代码生成」举例** | LandingView:26 | 10 项实际能力里**没有** ASR/OCR/数学/代码；TTS 存在但不在这 10 项枚举内。举例与 `get_all_status` 枚举不符 | 🔴 **已修** → 按实际 10 项列举 |
| 10 | 「讯飞星火 10 项多模态能力」措辞 | LandingView:139/228 | 10 项属**讯飞开放平台**服务（非全部星火品牌）；其中搜索/纠错/校对/合规/简历等并非多模态。数字对、外延错 | 🟡 **已修** → "讯飞开放平台 10 项能力" |
| 11 | 模拟流片段「3 篇讲义 + 2 道经典题」 | DesignUpgradeView:38（STREAM_FRAGMENTS） | 设计预览页内的交互模拟（同页按钮即"模拟失败"，页头标注"设计升级预览"）；非产品数据宣称 | 🟢 上下文已自标注，不改 |
| 12 | 「无限可扩展教学技能」 | LandingView:228 | 修辞性表述，无数值口径；技能平台可创建自定义技能为实 | 🟢 记录不改 |

## 二、本回合修复（均已提交）

| 文件 | 改动 |
|---|---|
| `src/views/DashboardView.vue` | subtitle「8个AI智能体协作」→「7个AI智能体协作」；tags 第 7 项「审核报告」→「视频脚本」 |
| `src/views/LandingView.vue` | 能力卡 desc 举例改为 `get_all_status` 实际 10 项；hero「讯飞星火 10 项多模态能力」→「讯飞开放平台 10 项能力」；底部同改 |
| `src/views/DesignUpgradeView.vue` | 文件头注释精确声明粒度：8 类角色 = 11 节点 LangGraph 的角色视图（「审核」展开为 critic/evidence_check/quality_gate 三节点），取消"与 DashboardView 同口径"的跟随表述 |

## 三、门禁证据

- `vue-tsc --noEmit`：0 error
- `eslint`（3 文件）：0 error（警告为存量）
- `vitest run`：23 文件 / 152 测试全绿（无 spec 断言旧文案）
- `_a11y_check.py`：exit 0；`token_scan.py`：exit 0（基线零回归）
- `honesty_scan` 既有红线（45%/500 条等）未命中——本复查与其互补：它管"已知假水位短语"，本轮管"数字与代码真值的对应关系"

## 四、结论与残留

B1 闭环。活视图数字宣称现存 12 条，9 条本就正确、3 条已修（#7/#8/#9/#10 计 4 处改动）、
2 条上下文自标注可接受、1 条修辞性记录不改。

**方法论备注**：「10 项讯飞能力」这类宣称的危险不在数字而在**外延**——数字恰好对得上
`get_all_status` 枚举，但举例（ASR/OCR/数学）是另一套 capability 清单。今后新增能力
卡文案时，desc 枚举必须与 `get_all_status()` / 对应模块的函数清单逐字对齐。

**未决（需真实运行环境，非本机可裁）**：讯飞控制台实际开通范围。`get_all_status()`
的可用性判据是 `has_credentials()`（凭据存在 ≠ 服务已开通/账号有权限），若需对外
承诺"10 项均可用"，须在服务器实测各端点后据实下调表述。

---

## 五、讯飞能力全景实测（2026-10-17 追加，回答上节「未决」）

上节遗留的「讯飞控制台实际开通范围」未决项，已由真实网络探活回答
（工具：`experiments/probe_xfyun_capabilities.py`，report-only，含负载真实性验证——
「Success」必须伴随真实图片/音频/文本/链接字节数，防空响应假绿；限流码 11202/11203/429
与未开通码 11200 分开裁定）。

### 5.1 全景裁定表

| # | 能力（get_all_status 枚举） | 2026-10-15 判据 | 2026-10-17 实测 | 裁定 |
|---|---|---|---|---|
| 1 | 图像生成 TTI | 凭据存在 | HTTP 200 + 85,740~188,928B 真实图片 | ✅ 稳定可用 |
| 2 | 语音合成 TTS（不属 10 枚举，同模块） | flag=False 关着 | WS code=0 + 17,856~25,344B 真实 MP3 | ✅ 已开启并实证 |
| 3 | 文本纠错 | 凭据存在 | 成功，返回 corrections | ✅ 稳定可用 |
| 4 | 图片理解 | 凭据存在 | 真实描述 TTI 产物（"三个圆圈用箭头连接"） | ✅ 稳定可用 |
| 5 | 万搜聚合搜索 | api_password 回退 | 3 条真实结果 | ✅ 稳定可用 |
| 6 | 角色模拟 | 凭据存在 | 面试官角色真实多轮回复 | ✅ 稳定可用 |
| 7 | 智能简历 | 凭据存在 | 返回 word_url | ✅ 稳定可用 |
| 8 | 公文校对 | 凭据存在 | 5 探 1 成，4 连 "licc failed" | ❌ 当前不可用（额度/license） |
| 9 | 内容合规 | 凭据存在 | 3/3 "套餐时间超限" | ❌ 稳定失败（试用套餐过期） |
| 10 | 智能 PPT | 凭据存在 | 未探活（重任务计费） | ➖ 需真人决策 |
| 11 | 数字人视频 | 凭据存在 | 未探活（重任务计费） | ➖ 需真人决策 |
| — | 星火 LLM（不属枚举） | 11200（10-15 两预设） | 4/4 候选 AppIdNoAuthError 11200 | ❌ 账号未开通（非暂时故障） |

### 5.2 已执行的修正

1. **LandingView 三处文案**（承接上节 #10）：能力卡 title/desc/stat「讯飞 10 项能力集成」
   →「讯飞多模态能力集成 / 对接 10 项服务接口，7 项实测可用（2026-10 真实调用验证）」；
   hero 与底部「10 项能力」→「多模态服务（10 项接口集成、7 项实测可用）」。
   口径从「10 项能力」（暗示全部可用）改为「10 项集成 + 7 项实测」——集成数是结构事实
   （Workshop 10 卡片均真实接线），可用性是实测事实，两者不再混装。
2. **`get_all_status()` 加 caveat 字段**：明示「布尔值=凭证是否配置，≠服务已开通」，
   并附 2026-10-17 实测记录摘要；docstring 同步。openapi 快照零漂移（该端点无 response_model）。
3. **TTI/TTS 开启**（用户拍板）：`config.json` 双 flag=True，端到端真实产出
   （73,436B 插图 / 25,344B MP3，source=xfyun）；发布包同步（flags + .env 三凭证，
   云端运行时模拟验证可用）。

### 5.3 产品面影响核验

- **内容安全链**（`shared/content_safety.py`）：合规服务已死（套餐时间超限），但该链
  设计为「不可用即降级本地敏感词 + 审计事件 `content_safety_compliance_degrade`」，
  **不阻断主流程**——产品不会坏，但对外若宣称"讯飞合规审核"为安全链一环则失实，
  已在 caveat 中据实标明。
- **API 层端到端**（TestClient 真注册→登录→Bearer）：三端点全 200，
  `is_real_image`/`is_real_audio` 均为 true，真实负载 181KB 图 / 17.8KB 音 / 多模态 522KB 图；
  无 token 面 401（认证闭合）。
- **门禁**：openapi 237/255 同步、test_xfyun_services 12 passed/9 skipped（全 mock）、
  LandingView 改动过 vue-tsc/eslint/vitest/token/a11y。

### 5.4 残留

- 公文校对「licc failed」性质待定（额度耗尽 vs license 服务抖动）——若需启用，
  先在讯飞控制台查该服务额度，再重跑探活（`proofread_document` 3 连探）。
- 内容合规需用户在控制台续订/开通后才可重新纳入安全链宣称。
- 智能 PPT / 数字人视频未探活：重任务且计费，是否探活由你决定。
