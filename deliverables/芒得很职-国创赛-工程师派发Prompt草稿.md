# 芒得很职 · 国创赛 · 工程师派发 Prompt 草稿（即发即用）

> 版本：v1.0 · 2026-09-30 · 由《执行任务清单》T1-3/T2-1/T2-2/T3-1 派生的精确派发 Prompt
> 用途：新开一轮工程师批次后，把对应卡片整段复制为该批次 agent 的首条 prompt 即可。
> 仓库：`E:\Program\MARL\study-help-pro` · 分支：`career-literacy` · 运行时：隔离 venv `python/envs/default`（python-pptx 同款路径）；Python 用 `C:\Users\Lenovo\.workbuddy\binaries\python\versions\3.13.12\python.exe`

---

## ⚠️ 通用红线（每条 Prompt 都内置，工程师不得违反）

1. **禁止修改 22 个并发 WIP 文件**（他人工作，一律不动）：
   `DESIGN.md`、`py-server/scripts/verify_app_wiring.py`、`py-server/scripts/verify_auth_coverage.py`、`src/assets/styles/_components.css`、`src/components/icons.ts`、`src/data/capabilityComparison.ts`、`src/router/index.ts`、`src/router/navConfig.ts`、`src/views/DashboardView.vue`、`src/views/DesignSystemView.vue`、`src/views/EngineView.vue`、`src/views/LandingView.vue`、`src/views/ShowcaseView.vue`、`src/views/DesignUpgradeView.vue`、`_vite_tmp.config.ts`、`py-server/data/knowledge_graphs/*.json`。
2. 若任务**必须**改动上述任一文件，先停下并在汇报里说明，等用户裁决——**不得静默修改**。
3. 任何"试点成效 / 真实回测"结论，必须能回溯到 `deliverables/试点证据-*.md` + 统计脚本，否则不写。
4. synthetic 与真实结论**分开标注数据来源**，严禁混写。

---

## Prompt A — T1-3 系统配置试点场景与对抗任务

```
你是芒得很职（国创赛职业线）的工程师。仓库 E:\Program\MARL\study-help-pro，分支 career-literacy。
目标：为 46 人试点配置可运行的实训环境——确保"面试 / 需求评审 / 故障通报"三类场景可选，且每名学生被安排 4–6 次对抗任务（其中至少 1 次走鲶鱼加压触发路径）。

【先定位，再改】
- 场景配置：grep -rn "场景\|scenario\|面试\|需求评审\|故障通报" py-server 找到场景定义/配置模块。
- 鲶鱼加压逻辑：grep -rn "鲶鱼\|catfish\|template_suspect" py-server 找到规则版触发代码（含信息密度低/过度自信/维度无差异等信号）。
- 任务调度：grep -rn "task\|session\|对抗\|round" py-server 找到为学生分配对抗次数的模块。
- 证据绑定：grep -rn "turn_id" py-server 确认每轮原话已落库。

【具体改动】
1. 若三类场景未全暴露，补齐配置使其可选。
2. 新增/复用"试点任务包"：参数为每生对抗次数(默认5)、强制≥1次鲶鱼加压触发（用模板化输入构造触发，不污染真实学生数据）。
3. 确认 turn_id 在每轮对话写库；报告可回放。

【验收】dev 启动后：三类场景可选；构造一个学生完成 5 次对抗；模板化输入能触发≥1次鲶鱼加压横幅；报告能回放对应 turn_id 原话。

【红线】不得修改通用红线列出的 22 个 WIP 文件；必须改动则停下报告。不加"虚构成效"日志。

完成后 git commit（仅你新增/修改的非 WIP 文件），报告 commit hash 与验证命令。
```

---

## Prompt B — T2-1 部署鲶鱼 MAPPO 到 dev（AB 可切换）

```
你是芒得很职工程师。仓库 E:\Program\MARL\study-help-pro，分支 career-literacy。
目标：把已训练的鲶鱼 MAPPO 策略部署到 dev 环境，并加 AB 切换开关（默认规则版，不影响现有行为）。

【先定位】
- 训练产物：py-server/models/career_mode_policy.pt（职业线模型，仓库内唯一 .pt）。
- 加载代码：grep -rn "career_mode_policy\|load_policy\|MAPPO\|mapo" py-server 找到策略加载/推理入口。
- 规则版加压：复用 Prompt A 定位的 catfish 规则逻辑。

【具体改动】
1. 新增开关（env 或 config）：USE_MAPPO（默认 false）。false → 规则版加压；true → 加载 .pt 走 MAPPO 策略。
2. 把加压决策点统一收到一个函数：def decide_pressure(state, use_mapo)，内部按开关分流。
3. dev 验证两种模式都能跑、输出结构一致。

【验收】USE_MAPPO=false 时行为与现状完全一致（回归）；=true 时加载 .pt 成功、加压决策由策略给出、无报错。

【红线】默认必须 false（零行为变更）；不得修改 22 个 WIP 文件；不提交大模型权重以外的敏感文件。

完成后 git commit，报告 hash 与两种模式的验证命令。
```

---

## Prompt C — T2-2 真实数据离线回测（规则 vs MAPPO）

```
你是芒得很职工程师+数据分析。仓库 E:\Program\MARL\study-help-pro，分支 career-literacy。
目标：用 T1-4 积累的真实对话（≥46人×多轮，脱敏、按 user_id 隔离）做离线回测，对比"规则版"与"MAPPO"在真实数据上的表现。

【产出】新文件 py-server/experiments/scripts/mapo_backtest.py + 输出 JSON。

【步骤】
1. 数据：读取真实对话（来自 T1-4 落库，脱敏）。若数据缺失 → 直接报错退出，绝不编造。
2. 对每条会话，分别用"规则版加压决策"和"MAPPO 策略(decide_pressure with USE_MAPPO)"计算加压轮。
3. 指标：抗压识别率、加压轮数、提前退出率、对话完成率（规则 vs MAPPO 各一组）。
4. 输出：mapo_backtest_result.json，字段含数据来源="real"、样本量、各指标、结论。

【验收】脚本可复跑；real 数据结论与任何 synthetic 结论分开、明确标注"real"；MAPPO 真实不优时如实写"real 下 MAPPO 未优于规则"。

【红线】仅真实数据；无数据即失败，不补造；synthetic 结论不得混入本结果（若需并陈，另起字段标"synthetic"并注明来源）。

完成后 git commit，报告 hash 与输出摘要。
```

---

## Prompt D — T3-1 新增"成效引用必须回溯"机检守护

```
你是芒得很职工程师。仓库 E:\Program\MARL\study-help-pro，分支 career-literacy。
目标：扩展 scripts/pre-commit/honesty_scan.py，使对外物料声称"试点成效/真实回测/前后测提升"时，必须能回溯到证据文件+统计脚本，否则 pre-commit 拦截（exit 1）。

【关键已知坑——必须先读】
- 现有 _EXTERNAL_REDLINE_PATTERNS 匹配原始行、不走引号剥离；且豁免目录包含 deliverables/、submission/、.workbuddy/、scripts/pre-commit/。
- 因此：若只加一个全局模式，deliverables/ 下的声称会被豁免、守卫成空操作。必须处理这个豁免：对本任务专属的"成效类"关键词，要么（a）收窄豁免使其在这些词上仍生效，要么（b）把守卫同时施加到非豁免目录（README.md、docs/、site/ 等对外物料常驻处）。二选一并在代码注释说明。

【具体改动】
1. 新增成效类模式组：试点成效|真实回测|前后测提升|显著(提升|差异)（按项目口径拟定，避免误伤"显著提升"类文学表述可加白名单）。
2. 命中时，要求同文档/相邻出现对 deliverables/试点证据-*.md 或 py-server/experiments/scripts/pilot_stats.py 的引用；缺失即 exit 1。
3. 加自测：写一个临时 md 含无回溯的"试点成效显著提升" → 必须被拦截；补上回溯引用 → 通过。

【验收】自测两例均符合预期；现有其他红线（45%/13%/500条 等）不受影响。

【红线】不得削弱既有 _EXTERNAL_REDLINE_PATTERNS 其他条目；不修改 22 个 WIP 文件。

完成后 git commit，报告 hash 与自测结果。
```

---

## 派发说明

- 以上 4 段为**自包含** prompt；新开工程师批次后整段复制为首条消息即可（agent 无本会话上下文）。
- **我方（主理人）可直接交付**的 T1-6 / T4-1 不需工程批次，按《执行任务清单》由我方在证据齐后落地。
- 当前 `software-a3-exec` 子智能体 unresumable，必须由你**新开一轮指派**才能跑 A/B/C/D；届时把对应 Prompt 粘贴进去。
