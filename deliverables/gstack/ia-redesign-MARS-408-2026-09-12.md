# MARS-408 信息架构与导航重构方案

> 评审：GStack Product Reviewer ｜ 日期：2026-09-12 ｜ 只读评审，未改动 `src/` 任何代码
> 依据：实读 `src/router/index.ts`（42 条路由）、`src/App.vue`（侧栏 17 项）、`src/components/MoreMenu.vue`（14 项）、40 个 view 的模板正文

## 一、现状诊断

**核心病灶：三套导航各自硬编码、无任何分组、主路径被淹没。**

- `App.vue` 侧栏是 17 项**平铺列表**（无分组标题），底部导航又是另一套 5 项，`MoreMenu.vue` 还有第三套 14 项 —— 三套不一致，且 `MoreMenu` 里混着「RAG 管理」这类管理功能。
- 主路径第一步「学情诊断」（`/diagnostic/start`）**完全不在任何导航里**，只能靠登录跳转和 ProfileView 里的一个按钮触发。学生登录后的核心动作无入口。
- `activeKey` 用 17 行 `path.startsWith()` 硬编码匹配，新增页面极易漏改。

### 页面清点（40 个 view，逐一定类）

| 类别 | 数量 | 页面 |
|---|---|---|
| A 正式功能页 | 12 | Dashboard, Diagnostic, Chat, Resource, Practice, LearningPath, DailyPlan, Assessment, Profile, ProfileBuilder, Achievement, Login |
| B 练习记录三件套（高度重叠） | 3 | WrongQuestions, Review, QuizHistory |
| C 知识域（4 个都叫"知识"） | 4 | Knowledge, KnowledgeGraph, CourseExplorer, KnowledgeBase |
| D AI 技能/智能体域 | 6 | SkillMarket, SkillPlatform, SkillStudio, SkillDetail, PromptStudio, CreatorDashboard |
| E 教师/管理看板 | 4 | Teacher, Admin, KnowledgeAdmin, AuditLog |
| F 实验室/开发调试 | 7 | Engine, Benchmark, Memory, Sandbox, CodeLab, CareerTraining, DesignSystem |
| G 展示/入口 | 2 | Landing, Showcase |
| H 系统 | 2 | Settings, NotFound |

**重叠实证（读模板正文后确认，非猜文件名）：**
- `ReviewView`「按四科统计错题」、`QuizHistoryView`「查看答题记录复习错题」、`WrongQuestionsView`「自动收录错题按知识点分类」—— 三个页面读同一份错题数据，只是切分维度不同。
- `KnowledgeView` 是只读全局 408 图谱；`KnowledgeGraphView` 是从粘贴文本**抽取构建**图谱；`CourseExplorerView` 是按科目/章节**浏览**图谱。三个都是图谱，只是一个能力域的三种视图。
- `SkillPlatformView`（三步创建营销落地页）与 `SkillMarketView`（技能市场）功能重叠；`PromptStudioView` 与 `SkillStudioView` 的 System Prompt 编辑区完全重叠。
- **无空壳页**：最小的功能页 123 行，全部有真实实现 —— 问题不是"没做完"，是"做太多了没归拢"。

## 二、重构后的导航树（5 大分组）

```
学习（学生主路径）
├ 今日总览          /             DashboardView
├ 学情诊断          /diagnostic/start   DiagnosticView   ← 补进导航，首次置顶
├ AI 对话           /chat          ChatView
├ 资源生成          /resource      ResourceView
├ 学习路径          /learning-path LearningPathView
└ 每日计划          /daily-plan    DailyPlanView

练习与复盘
├ 智能出题          /practice      PracticeView
├ 错题本            /wrong-questions  WrongQuestionsView
│   ├ [Tab 复盘]    /review        ReviewView（同页切换）
│   └ [Tab 记录]    /quiz-history  QuizHistoryView（同页切换）
└ 学习评估          /assessment    AssessmentView

知识
├ 知识图谱          /knowledge     KnowledgeView
│   ├ [Tab 按科目]  /course-explorer  CourseExplorerView
│   └ [Tab 从文本构建] /knowledge-graph  KnowledgeGraphView
└ 知识库（RAG）     /knowledge-base  KnowledgeBaseView

AI 技能工坊
├ 技能市场          /skills        SkillMarketView（含 /skills/:id SkillDetail）
│   └ [Tab 快速开始] /skill-platform  SkillPlatformView
├ 技能工坊          /studio        SkillStudioView
│   └ [Tab Prompt 调试] /prompt-studio  PromptStudioView
└ 我的创作          /creator-dashboard  CreatorDashboardView（工坊内入口）

实验室 Lab（评审展示区，不进主导航一级，单点展开）
├ 技术全景 /showcase ｜ 算法引擎 /engine ｜ 效果基准 /benchmark
├ 学情记忆 /memory ｜ 代码沙箱 /sandbox ｜ C/C++ 实验室 /code-lab
└ 素养对抗 /career/training ｜ 设计系统 /design-system

教学与管理（仅 teacher/admin 可见）
├ 教学看板 /teacher ｜ 平台数据 /admin
├ 知识库管理 /admin/knowledge
└ 审计日志 /audit-log

我的
├ 学习画像 /profile（含 /profile/build 重建画像）
├ 成就 /achievements
└ 设置 /settings
```

侧栏一级项从 **17 项平铺 → 6 组 + 默认折叠的 Lab**，认知负担直接减半。

## 三、页面处置建议表

动作：**合并（同页 Tab）/ 降级（移入二级或 Lab）/ 保留不进导航 / 保留主导航**。不删除任何文件。

| 当前页面 | 动作 | 理由 |
|---|---|---|
| DashboardView | 保留主导航（首页） | 唯一的"今天该干什么"聚合点，主路径起点 |
| **DiagnosticView** | **补进主导航**（P0） | 主路径第一步，当前完全无入口，最严重缺陷 |
| ChatView / ResourceView / LearningPathView / DailyPlanView | 保留主导航 | 主路径 学→练→规划 四节点，各司其职 |
| PracticeView | 保留主导航 | 主路径"练"的唯一入口 |
| WrongQuestionsView | 保留主导航（错题本母页） | 唯一带"标记掌握"闭环动作，最适合当母页 |
| ReviewView | **合并** → 错题本 Tab「复盘」 | 只读统计视图，无独立动作，做 Tab 更顺 |
| QuizHistoryView | **合并** → 错题本 Tab「记录」 | 与错题本同源数据，123 行全为列表 |
| AssessmentView | 保留主导航 | 主路径终点"复盘"的产出物 |
| KnowledgeView | 保留主导航（图谱母页） | 只读全局图谱，最通用视图 |
| CourseExplorerView | **合并** → 图谱 Tab「按科目」 | 同一图谱数据的另一种浏览切面 |
| KnowledgeGraphView | **合并** → 图谱 Tab「从文本构建」 | 生成型视图，是图谱的一个模式而非独立能力 |
| KnowledgeBaseView | 保留主导航（知识库） | RAG 文档库，与图谱是两码事，必须分开 |
| SkillMarketView + SkillDetailView | 保留主导航 | 市场 + 详情，正常一二级关系 |
| SkillPlatformView | **降级** → 市场内 Tab「快速开始」 | 营销落地页，与市场功能重叠 |
| SkillStudioView | 保留主导航（工坊） | 创建/编辑主界面 |
| PromptStudioView | **合并** → 工坊 Tab「Prompt 调试」 | 与工坊 System Prompt 编辑区完全重叠 |
| CreatorDashboardView | **降级** → 工坊内"我的创作"入口 | 仅创作者关心，不占一级位 |
| TeacherView | 保留（教师角色一级） | 教师端核心，对学生隐藏 |
| AdminView / KnowledgeAdminView / AuditLogView | 保留（管理角色二级） | 已有 meta.requiresRole，收进"教学与管理"组 |
| **EngineView** | **降级到 Lab**（保留，评审必看） | 页内自标"评审必看"，展示价值高但非学生日常 |
| ShowcaseView / BenchmarkView | 降级到 Lab | 技术全景/基准数据，评委导向 |
| MemoryView / SandboxView / CodeLabView | 降级到 Lab | 学情记忆/代码实验，属能力演示非学习路径 |
| CareerTrainingView | 降级到 Lab | 素养对抗是独立展示模块，与 408 备考弱相关 |
| DesignSystemView | 降级到 Lab（末位） | Living Style Guide，纯开发资产 |
| LandingView | 保留不进导航 | 公开评委入口，已有 meta.public，独立存在 |
| ProfileView / ProfileBuilder / AchievementView / SettingsView | 收进「我的」 | 个人域，不占主路径 |
| LoginView / NotFoundView | 保留不进导航 | 系统页 |

## 四、两类角色的导航差异

**同一套分组骨架，按角色换模块，不做两套 UI**（降低实现成本，评审时也讲得清）。

| 分组 | 学生 | 教师 | 管理员 |
|---|---|---|---|
| 学习（主路径） | ✅ 全部 6 项 | ❌ 隐藏 | ❌ 隐藏 |
| 练习与复盘 | ✅ | ❌（改看班级数据） | ❌ |
| 知识 | ✅ | ✅ | ✅ |
| AI 技能工坊 | ✅ | ✅ | ✅ |
| 实验室 Lab | ✅（可折叠） | ✅ | ✅ |
| 教学与管理 | ❌ | 教学看板 + 知识库管理 | 全部 4 项 |
| 我的 | 画像/成就/设置 | 仅设置 | 仅设置 |

教师首页重定向到 `/teacher`，学生到 `/`。角色从 `localStorage.mars408_user.role` 读（现有守卫已这么做）。

## 五、学生主用户路径

```
注册/登录 → LoginView
   ↓ (diagnostic_required = true)
学情诊断 → /diagnostic/start  20 题，出画像         ← 当前断点：无导航入口，只能被动跳转
   ↓
今日总览 → /   展示倒计时 + 八位 AI 助教 + 四科覆盖
   ↓
学习路径 → /learning-path   按画像给路线图与"下一步"
   ↓
每日计划 → /daily-plan      拆成今日任务
   ↓
学 → /chat（薄弱点提问）＋ /resource（生成讲义/PPT/题/代码）
   ↓
练 → /practice   按课程/章节/题型/难度出题，答后回写画像
   ↓
复盘 → /wrong-questions（Tab 复盘看四科分布 → Tab 记录看逐题）
   ↓
评估 → /assessment   雷达图 + 建议 + 自动调路径 → 回到"学习路径"闭环
```

**当前架构是否支撑？** 节点齐全，但**不支撑**：① 诊断无入口；② 侧栏 17 项平铺，"复盘"被拆成 3 个同级别入口（错题复盘/错题本/答题历史）造成选择瘫痪；③ 路径中间的"学"被 Chat/Resource/LearningPath 三个一级项并列，学生不知道先点哪个。

## 六、落地建议（只改 router 与导航配置，不动业务 view）

1. **建一份 `src/router/navConfig.ts` 单一真值源**：每项 `{ path, name, icon, group, nav: 'primary'|'secondary'|'lab'|'hidden', roles, order }`。`App.vue` 侧栏、底部导航、`MoreMenu.vue` 三处统一由它派生 —— 一次消除三套硬编码。
2. **合并用「redirect + query」实现，不删文件**：
   - `/review` → `{ path: '/wrong-questions', query: { tab: 'review' } }`
   - `/quiz-history` → `...query:{tab:'history'}`
   - `/course-explorer` → `/knowledge?view=course`；`/knowledge-graph` → `/knowledge?view=build`
   - `/skill-platform` → `/skills?tab=start`；`/prompt-studio` → `/studio?tab=prompt`
   目标 view 顶部加 `watchEffect` 读 `route.query.tab` 切换子组件。老链接、书签、演示录像里的 URL 全部仍然可用。
3. **分组用嵌套路由**：新建 `src/views/_groups/{LearnLayout,PracticeLayout,LabLayout}.vue`（内容仅 `<router-view/>`），把对应路由挂成 children。现有 40 个 view 文件一行不改。
4. **`activeKey` 改为读 `route.meta.group`**，删掉 17 行 `startsWith` 硬编码，以后加页面自动高亮。
5. **`meta.nav = 'hidden'`** 标记 Landing、NotFound、chat-conv、`/studio/:id`、`/skills/:id` —— 保留可访问，不出现在任何导航。
6. **Lab 分组默认折叠**，标题右侧挂「评审演示」徽标。既不污染学生主路径，评审点开即见 8 个硬核模块，展示价值零损失。
7. **P0 优先级**：先做①（单一 navConfig）和②（诊断进导航）。这两项不改任何业务代码，半天可完成，却直接修掉最致命的两个问题。

---

**一句话结论**：MARS-408 不是"页面太多"，是**41 个能力点全部平铺在同一层级**。归拢成 6 组、把 6 个重叠页降为 Tab、把 8 个展示页收进 Lab 分组，功能一个不少，产品感立刻从"功能堆"变成"系统"。
