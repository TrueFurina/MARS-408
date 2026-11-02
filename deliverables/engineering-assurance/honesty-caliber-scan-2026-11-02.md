# 对外宣称口径全量深度扫描（2026-11-02）

> 分支：`merge/ws1-ws4-20261102`（HEAD `35af837`）
> 性质：**只读审计**。未修改任何源码、文档、配置；未执行 `verify_metrics.py --update`、未 git add/commit/push。
> 扫描面：`src/`（.vue/.ts 展示文本与 data 常量）、`public/`、`index.html`、`README.md`、`README_EN.md`、
> `deliverables/芒得很职-国创赛证据页.md`、`website/`、`site/`、`docs/METRICS_CURRENT.md`。

## 真值基线（本次实测，命令可复跑）

| 真值项 | 实测值 | 来源 / 命令 |
| --- | --- | --- |
| 工程规模 9 项 | 全部一致（views 49 / .vue 88 / .ts 77 / 前端 58336 行 / 后端 394 文件 / 93926 行 / 路由 42 / 路径 243 / 操作 261） | `py-server/.venv/Scripts/python.exe scripts/verify_metrics.py --print`（`env -u PYTHONPATH -u PYTHONSTARTUP -u NODE_OPTIONS -u ELECTRON_RUN_AS_NODE`） |
| 默认档测试数（当前分支） | **1863 passed / 38 skipped / 9 deselected / 1 xfailed / 0 failed**（约 1910 collected，417.72s） | CI run `41476356910`，2026-11-02，job「Backend tests (unit/integration/API + coverage)」 |
| 默认档测试数（main，对照） | 1156 passed / 35 skipped / 8 deselected / 1 xfailed / 2 xpassed（1202 collected） | CI run `41475152393`，2026-11-02 |
| LLM 四通道 | `auto`：xfyun(spark_x2) → deepseek → qwen → glm；deepseek-chat / spark-x / **qwen3.8-max** / glm-4-flash | `py-server/config.py:45,48,60,66,83,94,292-293` |
| 讯飞授权状态 | 账号**仅 X2 授权**；4.0Ultra / max(generalv3.5) / pro128k 返回 11200 | `py-server/config.py:66` 注释 + presets |
| KG（底座） | 86 知识点 / 82 条先修边 | `py-server/experiments/results/kg_stats.txt`；运行时 `TeachingRuleEngine.get_stats()['total_topics']=86` |
| KG（kg408） | 136 节点 / 18 边 | `origin/main:deliverables/408-kg/kg408-stats.md:34-44` |
| 知识库 | 2245 向量（2015 chunks + 230 题）；metas `group` 取值 1–26 → **26 个知识群组** | `py-server/vectordb_data/netlearn_kb.json` |
| 认证覆盖率 | 95.02%（261 端点 / 248 受保护 / 13 公开 / 0 未登记） | `py-server/scripts/verify_auth_coverage.py` |
| FrugalRAG token | 185.75 vs 165.86 → **+11.99%（消耗上升，未降反增）**；`token_reduction_pct=-11.99` 的负号即「上升」 | `benchmark_2026-09-18.json` experiment1.summary |
| 真实试用 | **零真实用户；尚未开展真实试用** | `README.md:41-42`（项目自述唯一诚实口径） |

---

## ① 结论

- **🔴 必须改：5 条**（全部是“当前时点”的硬数字/硬事实与真值冲突）
- **🟠 应改：9 条**（带日期或局部口径不一致，交叉核对会被问住）
- **🟡 建议改 / 待核：9 条**（措辞、精度、无法在本仓复核的他域数字）
- **禁用词**：`生态` 命中 1 处（生成代码注释，非展示文本）；`国内首个/国内第一/新文科/颠覆/革命性` **0 命中**。
- **禁用数字族**：`613/1883/2083/500条/13%` **真实命中 0**；`609` 仅命中 SVG 坐标；`45%` 两处均属白名单（详见 ③）。
- **最大风险不是“写错”，而是“写旧”**：测试数从 1737 漂到 1863，README/站点/证据页/METRICS 四处仍停在 10-21 口径。

---

## ② 逐条发现

### 🔴 红线级（当前时点直接对不上真值）

| # | file:line | 现有文字（截取） | 真值 | 建议改法 | 级别 |
| --- | --- | --- | --- | --- | --- |
| R1 | `README.md:97` | `**1737 项测试通过 / 38 跳过 / 1 xfail**（CI 默认档，全量回归 0 失败）` | **1863 通过 / 38 跳过 / 9 deselected / 1 xfailed / 0 失败**（run 41476356910，2026-11-02） | 改为 `1863 通过 / 38 跳过 / 1 xfail（CI run 41476356910，2026-11-02）`；或删除数字，仅留 CI 徽章 + 查询命令 | 🔴 |
| R2 | `README.md:277` | `\| 测试 \| 1737 项测试通过 / 38 跳过 / 1 xfail（CI 默认档，全量回归 0 失败） \|` | 同上 | 同上（两处必须同改，避免又一次“同文档双口径”） | 🔴 |
| R3 | `README_EN.md:57`、`README_EN.md:190` | `**1737 tests passing / 38 skipped / 1 xfail**` / `\| Tests \| 1737 tests passing ...` | 同上 | 改为 `1863 passing / 38 skipped / 1 xfailed`，并标注 run id | 🔴 |
| R4 | `README.md:276` | `后端 388 个 Python 文件 / 约 9.2 万行 · 前端 165 文件（88 .vue + 77 .ts）/ 约 5.7 万行` | **394 个 .py / 93926 行（9.39 万）**；前端 **58336 行（5.83 万）** | `388→394`；`9.2 万→9.4 万`；`5.7 万→5.8 万`（文件数属硬错，行数属低估） | 🔴 |
| R5 | `src/data/capabilityComparison.ts:37` | `51个知识点DAG + 考查权重 + 跨科目关联 + Agent适配规则` | **86 个知识点 / 82 条先修边**（同一产品的 `TeachingRulesPanel.vue:53` 已写 86） | 改为 `86 个知识点 DAG（82 条先修边）` | 🔴 |

### 🟠 应改级（时点过期 / 同文档互斥 / 口径冲突）

| # | file:line | 现有文字（截取） | 真值 | 建议改法 | 级别 |
| --- | --- | --- | --- | --- | --- |
| O1 | `website/index.html:506,508,533` | `28 条查询、96 条样本、1737 条通过用例`；`通过用例 1737 条`（标注 2026-10-21） | 1863 通过 / 38 跳过 / 1 xfailed（2026-11-02） | 全页 3 处统一更新；保留 run id + 日期，避免“无源数字” | 🟠 |
| O2 | `site/index.html:217,378,380,406` | `1737`+`测试通过（2026-10-21 CI 口径）`；`1737 条通过用例` | 同上 | 同上（site 是 website 的镜像，需同步） | 🟠 |
| O3 | `deliverables/芒得很职-国创赛证据页.md:38` | `**约 1785 collected**（CI 默认档 **1737 通过 / 38 跳过 / 1 xfailed / 0 失败**；2026-10-21 ...）` | **约 1910 collected / 1863 通过 / 38 跳过 / 1 xfailed**（2026-11-02） | 更新本行；并把 `docs/TEST_TRUTH.md:7,17,20,33` 一并改（否则 SSOT 与证据页互指旧值） | 🟠 |
| O4 | `docs/METRICS_CURRENT.md:81` | 长段落最终落在 `1737 通过 / 38 跳过 / 1 xfail / 0 失败（2026-10-21 CI run 39681618692）` | 1863/38/1（2026-11-02） | 追加“已更新（2026-11-02）：1863 通过 / 38 跳过 / 9 deselected / 1 xfailed（run 41476356910）”；这是 SSOT，必须先改 | 🟠 |
| O5 | `README.md:98`；`README_EN.md:57` | `讯飞星火 X2/generalv3.5 账号未授权（11200，控制台开通后自动恢复优先级）、Qwen 欠费` | `config.py:66`：账号**仅 X2 权限**，4.0Ultra/max/pro128k 才返回 11200；Qwen 通道已配 `qwen3.8-max`，仓内无“欠费”证据 | 改为 `讯飞仅 spark_x2 授权；4.0Ultra/generalv3.5(pro128k) 返回 11200；Qwen 状态待核`。不要把在用通道说成未授权 | 🟠 |
| O6 | `README.md:58` vs `README.md:277` | 前者 `实际为 DeepSeek 主 + 讯飞星火 X2`；后者 `讯飞星火 X2（主）→ DeepSeek → Qwen → 智谱 GLM` | `config.py:292-293` auto 顺序为 **xfyun → deepseek → qwen → glm**；X2 为可用预设 | 两处统一为 `auto 优先级：讯飞 X2 → DeepSeek → Qwen → GLM，按实际可用性回退`；不要用“主”字制造互斥 | 🟠 |
| O7 | `README.md:173`；`README_EN.md:51,84,135,194` | `知识群组 **29**` / `29 subject groups` | `netlearn_kb.json` metas 的 `group` 取值 1–26 → **26 组**；`README.md:123,281` 已写 26 | 全部改为 **26**（同一 README 内 29 与 26 并存，属自相矛盾） | 🟠 |
| O8 | `website/index.html:484,488,524,525`；`site/index.html:351,355,397,398` | `96 条样本…训练权重 80.2% 与规则基线 82.3%，结论是持平`；`早期 30 题小样本…已被更大样本否定，该数字不再使用` | SSOT 实验2 仍裁定 **88.89% vs 76.67%（+12.22pp，30 题×3）**；96 样本 80.21/82.29 来自 `mixer_before_after_2026-09-03.json`，两者是不同产物 | 两口径并列展示，并注明各自产物文件；**不得单方面宣布 SSOT 口径“不再使用”**，否则评委按 SSOT 核对即判“对不上” | 🟠 |
| O9 | `README.md:57` | `tests/test_triage.py 18 用例通过` | 实测 `pytest tests/test_triage.py --collect-only` = **28 collected** | 改 28，或改为“该文件测试全绿”不写死数字 | 🟠 |

### 🟡 建议改 / 待核级

| # | file:line | 现有文字（截取） | 真值 / 状态 | 建议改法 | 级别 |
| --- | --- | --- | --- | --- | --- |
| Y1 | `README.md:89` | `内置约 **2100 条知识分片与练习题**` | **2245 条**（2015 chunks + 230 题） | 改 `约 2245 条` 或 `约 2200 条`；与 50/172/279 行口径统一 | 🟡 |
| Y2 | `docs/METRICS_CURRENT.md:30` | `\| Token \| — \| — \| **−11.99%（未降反增）** \|` | token 185.75 vs 165.86 → **+11.99%**（`token_reduction_pct=-11.99` 的负号意为上升） | 改为 `**消耗上升 11.99%（+11.99%，未降反增）**`，去掉“变化”列里的裸负号，杜绝被读成“省了 12%” | 🟡 |
| Y3 | `src/types/api.generated.ts:3037` | `执行技能并注入 L1/L2/L3 学情记忆（插件生态增强）` | 禁用词「生态」；该行来自 OpenAPI 生成，非页面展示文本 | 后端 docstring 改为“插件扩展增强”后重新生成；短期可在生成器词表做替换 | 🟡 |
| Y4 | `deliverables/芒得很职-国创赛证据页.md:39` | `资源类型 / 视频场景模板 / KG 提示词 \| 7 / 5 / 6 实体 + 5 关系` | 场景模板 5 ✓、KG 6 实体+5 关系 ✓；**“资源类型 7”在 `config.py` 无定义**，仅 `app/status.py:209` 硬编码 7 | 补可复算来源（哪个常量/哪 7 类），否则标“待核”或删除 | 🟡 |
| Y5 | `deliverables/芒得很职-国创赛证据页.md:24` | `py-server/data/kg408/*`；`verify_kg408.py 53 passed` | 本分支**无** `py-server/data/kg408` 与 `verify_kg408.py`（`origin/main` 有；136 节点/18 边已核）；`53 passed` 无法在本分支复核 | 合并 `main` 或改引用到 main 的产物；`53 passed` 标注来源 run/命令，否则标“待核” | 🟡 |
| Y6 | `src/views/ShowcaseView.vue:13` | `53 测试全绿、变异验证 14/14`（COLREGs 归档仓） | 归档仓不在本仓库，无法复核 | 补归档仓链接/commit；否则标“待核” | 🟡 |
| Y7 | `src/views/ShowcaseView.vue:11-12` | `MAPPO 直训送达 38/600`；`IQL 主结局 +28.17%（n=71, p=0.0095；全程 +7.92%）`；`6 类签名攻击 100% 拦截（300/300）` | 他域成果，本仓无对应产物 | 逐条注明来源仓 + 产物文件；无法溯源则从对外页移除 | 🟡 |
| Y8 | `deliverables/芒得很职-国创赛证据页.md:58` vs `README.md:42` | `46 人真实试点` vs `5–10 人班` | 两者都标“未启动”，但试点规模互斥 | 统一规模，或注明“早期方案 46 人 / 现行方案 5–10 人班” | 🟡 |
| Y9 | `src/views/ShowcaseView.vue:172` | `0` / `失败用例` | **0 failed 成立**；但同轮存在 1 xfailed（main 轮另有 2 xpassed） | 保留可，但建议加注 `（0 failed；1 xfailed 不计失败）`，防被追问 | 🟡 |

---

## ③ 判定为「看似违规其实正确」的项及理由

| 位置 | 文字 | 为什么不是问题 |
| --- | --- | --- |
| `src/views/ShowcaseView.vue:20` | `tag: '45% 评分权重'` | 这是**赛题功能权重**（11 节点流水线在评分表中的占比），不是成效/降本数字。任务已明确：事实正确，不判错。 |
| `site/index.html:13` | `linear-gradient(90deg,#ff7a18,#ffb347 45%,#4d9fff)` | `45%` 是 CSS 渐变停靠点，与禁用数字族无关。 |
| `public/showcase/芒得很职-agent-collab.html:772` | `y1="609"` | SVG 坐标；`src/components/icons.ts:143` 中的 `243/394/917` 同理是 path 数据，非指标。 |
| `deliverables/芒得很职-国创赛证据页.md:74` | `❌ 禁提 "45% / 13% / 500 条" 类已撤数字` | 这是**禁用清单本身**（元文本），不是对外宣称。 |
| `docs/METRICS_CURRENT.md:53` | `Token −0.14%` | “已作废旧口径”表格中的历史对比列，文档明确标注仅用于溯源。 |
| `README.md:186` | `旧口径 2122 条向量` | 明确标注“旧口径”，并说明新口径 2245，属允许的时点留档。 |
| `deliverables/芒得很职-国创赛证据页.md:35` | `261（method 级，/api 口径；去重路径 243，全量 262/244 含 /metrics）` | 实测 `/api` 243 路径 / 261 操作；全量 244 路径；+1 个 `/metrics` 操作 = 262，**完全正确**。 |
| `deliverables/芒得很职-国创赛证据页.md:36`；`website:439`；`site:307` | `86 节点 / 82 边` | `kg_stats.txt` 实测 `total_topics=86`、`prerequisites 边=82`，且运行时引擎复核一致。 |
| `README.md:50,172,279`；`website:439`；`site:307` | `2245 条向量（2015 chunks + 230 题）` | `netlearn_kb.json` 的 ids/texts/metas/embeddings 各 2245，逐字段一致。 |
| `src/views/ShowcaseView.vue:168`；`website`/`site` 认证覆盖率 | `95.02%` | `verify_auth_coverage.py` 实跑 `total=261 protected=248 public=13 coverage=95.02 unregistered=0`。 |
| `src/views/ShowcaseView.vue:156`；`README.md:97` | `261 API 端点` / `243 路径 / 261 操作` | `verify_metrics.py` 与 `openapi.json` 实测一致（243/261，42 模块）。 |
| `src/views/ShowcaseView.vue:172` | `0 失败用例` | 本轮 CI 确为 `0 failed`；1 xfailed 属预期失败、不计失败。 |
| `src/views/BenchmarkView.vue:314` | `负号表示 FrugalRAG 反而多耗 token` | 图表直接取真产物 `tokenReductionPct`，并**显式解释负号语义**，未被读成“省 12%”，符合诚实口径（可进一步正向化）。 |
| `README.md:41-42` | `真实试用（5–10 人班）尚未开展…不得出现“已在校内使用/已服务 N 名学生”` | 这是**唯一诚实口径**，也是本项目零真实用户的正确表述；网站/站点未出现“已服务 N 名”类宣称。 |
| `README.md:58` | `4.0Ultra/max(generalv3.5)/pro128k 未授权（11200）` | 与 `config.py:66` 一致；错的是同页第 98 行把 X2 也算进“未授权”（见 O5）。 |
| `deliverables/芒得很职-国创赛证据页.md:24` | `136 节点 / 18 边`（kg408） | `origin/main:deliverables/408-kg/kg408-stats.md` 自动生成的真值：节点 136、边 18。只是本分支未带该目录（见 Y5）。 |
| `deliverables/芒得很职-国创赛证据页.md:58` | `46 人真实试点 \| 🔲 未启动` | D 级“规划未启动”的诚实公示，不是虚假成效；仅规模与 README 不一致（见 Y8）。 |
| `src/data/capabilityComparison.ts:62` | `零真实用户时禁称成效` | 这是自我约束条款，正面符合红线要求。 |

---

## ④ 建议的修复顺序

**P0 —— 先改 SSOT，再改引用（否则改完仍会漂）**
1. `docs/METRICS_CURRENT.md:81` 写入 2026-11-02 新真值（1863/38/9/1，run 41476356910），并同步 `docs/TEST_TRUTH.md`。
2. `README.md:97,277`、`README_EN.md:57,190` 四处测试数改为 1863，带 run id；**禁止再写无日期的裸数字**。
3. `README.md:276` `388→394`、`9.2 万→9.4 万`、`5.7 万→5.8 万`。
4. `src/data/capabilityComparison.ts:37` `51→86`（同一屏的 `TeachingRulesPanel` 已是 86，属自打脸）。

**P1 —— 外网可见面同步（website / site / 证据页）**
5. `website/index.html:506,508,533`、`site/index.html:217,378,380,406`、证据页 `:38` 统一到 1863/38/1、约 1910 collected。
6. 模型授权口径：`README.md:98`、`README_EN.md:57` 改为“仅 spark_x2 授权，4.0Ultra/generalv3.5/pro128k=11200；Qwen 待核”，并统一 `README.md:58` 与 `:277` 的“主通道”表述。
7. 知识群组 `29→26`：`README.md:173` + `README_EN.md:51,84,135,194`。

**P2 —— 口径并列与可溯源性**
8. NeuralMixer 80.2/82.3 与 SSOT 88.89/76.67 并列，各自标注产物文件；删除“30 题口径不再使用”的单方面表述。
9. 证据页“资源类型 7”补来源；kg408 路径/53 passed 在合并 `main` 后恢复可复现，否则改引用。
10. 统一试点规模（46 人 vs 5–10 人班）。

**P3 —— 措辞与门禁**
11. `METRICS_CURRENT.md:30` 改为“消耗上升 11.99%（+11.99%）”，清除裸负号。
12. `api.generated.ts:3037` 的「生态」在后端 docstring 与生成器词表中替换。
13. **建议新增 CI 门禁**：`scripts/scan_honesty_caliber.py` 扫描对外面（README/README_EN/website/site/public/showcase/src/views）——
    - 禁词表：`生态|国内首个|国内第一|新文科|颠覆|革命性`；
    - 禁数表：`613|1883|2083|500\s*条|13%`（`45%` 需白名单机制，避免误伤赛题权重与 CSS）；
    - 测试数锚点：任何 `\d{3,4}\s*(项)?测试|tests passing` 必须紧跟 `CI run` 与日期，否则红。

---

> 备注：本报告所有“真值”均在 2026-11-02 扫描时点实测；`verify_metrics.py` 校验通过（9/9），因此工程规模类错误只存在于**引用层**，不在 SSOT 表内。
