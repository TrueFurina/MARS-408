# 提交包数字对齐核对清单（2026-10-09 预检）

> ⚠️ **当前真值（HEAD `7700dce`，2026-10-17）**：本文 §一 / §三 / §六 是 10-09 / 10-10 时点快照，**以 §九 为准** —— API **254 ops / 236 paths**、认证覆盖率 **94.88%（241/254）**、测试 **1524 passed / 38 skipped / 1 xfailed / 0 失败**（1563 运行项 / 1572 collected，addopts deselect 9；CI run `38938041036`）。改任何数字请以 §九 与机器复算（`scripts/verify_metrics.py` / `scripts/verify_auth_coverage.py`）为唯一来源，禁止手抄旧值。

> **性质**：只读审计 + diff 清单。**10-28 冻结窗口前不碰 `submission/` 实体**，本文件只列"到时改什么"。
> **真值来源**（按可信度）：
> 1. `gh run view 37917008258 --log` —— `Backend Test (Linux)` 在 HEAD 前一个测试提交（`test(f015)`）的**实测**摘要。该提交与 HEAD 的测试文件完全相同（后续 fe 提交只动 `scripts/`/`.github/`/`docs/`），故数值对当前 HEAD 有效。
> 2. `scripts/verify_metrics.py`（9/9 与真值一致，git 跟踪口径，跨平台一致）。
> 3. `git ls-files 'py-server/api/*.py'`（含 `__init__.py`）。

---

## 一、结论速览

| 指标 | 提交包声称 | HEAD 真值 | 是否冲突 | 处置 |
| --- | --- | --- | --- | --- |
| API 操作 / 路径 | 244 / 227 | 244 / 227（`openapi.json`，verify_metrics 9/9） | ✅ 一致 | 不改 |
| 认证覆盖率 | 94.67%（231/244） | 94.67%（231/244） | ✅ 一致（活跃正文） | 不改正文；**改 2 处 stale 引用**（见三.2） |
| 后端路由模块 | "44 个"（`py-server/api/*.py`） | `git ls-files` = 44（**含** `__init__.py`） | ✅ **非冲突**（口径差异） | 不改；可选加注"含 `__init__.py`"消除歧义 |
| 测试数（默认集） | 1178 passed / 208 skipped / 3 xfail / 1397 collected | **1389 passed / 38 skipped / 1 xfailed / 8 deselected**（CI 默认档实测） | 🔴 **冲突** | 10-28 重跑 CI 默认档取权威数后统一替换 |

---

## 二、测试数冲突根因（关键：不是数字漂移，是剖面变了）

- 提交包（10-06 快照）声称"默认集"：`1178 passed / 208 skipped / 3 xfail / 1397 collected`（且把 `1389` 当**总数** = 1178+208+3）。
- HEAD 当前 CI 默认档实测（run `37917008258`）：`1389 passed, 38 skipped, 8 deselected, 1 xfailed`。
  - `backend-test.yml` 默认档命令：`pytest -q`（沿用 `pyproject.toml` 的 `addopts = -m "not system and not requires_milvus and not slow"`），另有独立 `--noconftest` 隔离档（`test_p0_incremental`+`test_teacher_role`，36 passed）。
- **差距**：passed 差 **+211**、skipped 差 **−170**、xfail 差 **−2** → 远超个位数漂移，是 **10-06 的 marker/conftest 选择剖面 ≠ 当前 CI 默认档**。
- **标签错误**：提交包 `1389` 标作"总数"，CI 把它计为"passed"——同一数字两种含义。
- **处置原则**：**不是改某个个位数**，而是 10-28 重跑当前 CI 默认档（确认仍为 1389/38/1/8 或取新值），把全部文档统一到**机器可复现**的口径。

> ⚠️ **需用户决策**："默认集"的权威口径以 CI 默认档为准（= 上述 1389/38/1/8）。是否额外单列隔离档 36 条由用户定；本清单默认只对齐 CI 默认档。

---

## 三、精确 edit 清单（10-28 执行；仅活跃文件，`_archive_*` 历史快照不动）

### 3.1 测试数（🔴 必改，改为 CI 默认档实测值）

| 文件 | 行 | 当前内容（摘录） | 改为（口径：CI 默认档） |
| --- | --- | --- | --- |
| `submission/00_提交清单.md` | 50 | `1389 条：1178 通过 / 208 跳过 / 3 xfail` | `1428 项：1389 通过 / 38 跳过 / 1 xfail / 0 失败`（`1436 collected`，`addopts` deselect 8） |
| `submission/00_提交清单.md` | 114 | `默认测试集（应得 1178 passed / 208 skipped / 3 xfailed / 0 failed）` | `默认测试集（CI 默认档：1389 passed / 38 skipped / 1 xfailed / 0 failed）` |
| `submission/00_提交清单.md` | 157 | `默认集 1389 → 1178 passed /` | `默认集 1428 项 → 1389 passed / 38 skipped / 1 xfailed` |
| `submission/02_配套文档/测试说明书.md` | 17 | `默认测试集 1389 项（1397 collected…）全量回归 1178 passed / 208 skipped / 3 xfailed` | `默认测试集 1428 项（1436 collected，addopts deselect 8），CI 默认档 1389 passed / 38 skipped / 1 xfailed / 0 failed` |
| `submission/02_配套文档/测试说明书.md` | 242 | `默认集 1389 项，Windows 单机实测 266 秒` | 同步为 1428 项（运行时间以 10-28 重跑实测为准） |
| `submission/02_配套文档/开发说明书.md` | 523 | `默认集 1389（1397 collected…）1178 passed / 208 skipped / 3 xfailed` | 同 3.1 口径 |
| `submission/02_配套文档/系统架构设计文档.md` | 7 | `默认测试集 1389 项（1178 passed / 208 skipped / 3 xfailed）` | `默认测试集 1428 项（CI 默认档 1389 passed / 38 skipped / 1 xfailed）` |
| `submission/02_配套文档/系统架构设计文档.md` | 194 | `默认测试集 1389 项，1178 passed / 208 skipped / 3 xfailed` | 同上 |

> 数字说明：`1389+38+1 = 1428` 为"默认档运行项"；`1428+8 = 1436` 为 collected 总数（8 条被 addopts deselect）。**10-28 重跑后以此为准回填，勿手抄**。

### 3.2 覆盖率 stale 引用（🟡 必改，正文已对、引用过期）

| 文件 | 行 | 当前内容 | 改为 |
| --- | --- | --- | --- |
| `submission/00_提交清单.md` | 183 | `新数字 1389 / 1178 / 244 / 94.65 / 国创赛` | `94.65` → `94.67`（与正文 231/244 一致） |
| `submission/02_配套文档/开发说明书.md` | 571 | v2.2 变更记录：`认证覆盖率订正为 94.65%（230/243）` | `94.67%（231/244）`（与正文 line 412 对齐） |

### 3.3 一致项（✅ 不改，仅登记以消除歧义风险）

- `00_提交清单.md:48 / :67`、各说明书的 `244 operations / 227 paths` → 与 verify_metrics 一致，不改。
- `00_提交清单.md:54`、`快速启动指南.md:154`、`开发说明书.md:293` 的"44 个路由模块" → `git ls-files` 含 `__init__.py` = 44；verify_metrics 的 `api_modules=43` 是**去 init** 口径，二者皆对。可选：在 54 行补注"（含 `__init__.py`，共 44 文件）"避免评审误判。

---

## 四、10-28 执行步骤（建议）

1. `git checkout career-literacy && git pull` 确保 HEAD 最新。
2. 触发/取最新 `Backend Test (Linux)` 默认档摘要，确认测试数（预期 1389/38/1/8；若有变动以实测回填本清单 3.1）。
3. 按 3.1 / 3.2 逐行改活跃文件；`_archive_*` 不动。
4. 同步 `deliverables/` 下对应国创赛文档（如 `芒得很职-国创赛证据页.md` 等）的同类数字（如有）。
5. 重打包 `submission/` → zip，更新 `00_提交清单.md` 的包内文件计数（如有变动）。
6. 跑 `python scripts/verify_metrics.py` 确认 9/9 仍绿；跑 `scripts/honesty_scan.py` 确认无口径红线命中。

## 五、红线提醒
- 本清单是 **diff 预案**；在 10-28 冻结窗口前**禁止**修改 `submission/`、`src/`。
- 所有替换值以 10-28 当天的 **CI 默认档实测** 回填，禁止手抄旧值或凭记忆。

## 六、执行记录（2026-10-10 提前批量，打破冻结）

用户「继续」= 提前执行本预案（原定 10-28）。

**已落地（3.1 + 3.2）**：
- 3.1 测试数：`00_提交清单.md:50/114/157`、`测试说明书.md:17/242`、`开发说明书.md:523`、`系统架构设计文档.md:7/194` 全部改为 CI 默认档 **1428 项（1436 collected, deselect 8）→ 1389 passed / 38 skipped / 1 xfailed / 0 failed**。
- 3.2 覆盖率：`00_提交清单.md:183` 验证清单 `94.65 → 94.67`；`开发说明书.md:571` 变更记录 `94.65%（230/243）→ 94.67%（231/244）`。

**说明**：
- `00_提交清单.md:52` 与 PPT 内 54.96% 覆盖率一并保留（未重跑 `--cov`，本地不可靠），待 CI 复算回填。
- `04_源码` zip 未重打：本次仅改 docs/scripts，py-server 代码未变，源码包内容不变。
- 残留：CI p0 档 67 条未机器核验（见 deliverables 侧预案 §C）。

---

## 七、2026-10-12 全量口径同步（追加，不改上文历史行）

> 本节为**新增记录**，不改动上文 10-09 / 10-10 的历史快照行（保留可追溯）。

- **认证覆盖率口径推进**：上文 `§一` / `§三.2` / `§六` 记录的 **94.67%（231/244）** 已过期。以运行时脚本为真值：
  `cd py-server && D:/miniconda3_new/python.exe scripts/verify_auth_coverage.py`
  → `__SUMMARY__ total=245 protected=232 public=13 coverage=94.69 unregistered=0`，
  新真值为 **94.69%（232/245）**（覆盖率**上升**，非安全回归）。
- **`/api` 端点形态同步为 245 operations / 228 paths**（旧记 244 / 227），与重生成后的 `py-server/openapi.json` 一致；`py-server/main.py:49` 的对 OpenAPI description 断言已于 10-11 先行跟进。
- **本日共同步 12 个活跃文件**（2026-10-12），分组如下：
  - 用户可见前端：`src/views/ShowcaseView.vue`
  - 脚本与生成器：`py-server/scripts/verify_auth_coverage.py:25`、`py-server/tools/generate_demo_ppt.py:168`
  - 指标与 CI：`docs/METRICS_CURRENT.md`；`docs/ci-backend-test-result.md:32` 于 10-11 已先行更新，**本次仅核验**
  - 提交材料：`submission/00_提交清单.md`、`submission/02_配套文档/` 下 技术方案说明书 / 开发说明书 / 快速启动指南 / 测试说明书 / 系统架构设计文档
  - 路演与证据：`deliverables/build_roadshow_pptx.py`、`deliverables/芒得很职-国创赛证据页.md`
- **历史行按设计保留**：上文各节出现的 `94.67` / `231/244` / `244 operations / 227 paths` 等旧值一律**原样不动**，它们记录的是各自时点的核对事实；改写会摧毁台账的可追溯性。`_archive_*` 快照与 `源码/` 冻结副本同样不在同步范围内。
- **本次未改、留待决定**：`submission/00_提交清单.md:120` / `:134` 两条「应得 paths=227 / operations=244」的校验期望（OpenAPI 快照现值已为 228/245），属可执行校验收尾文本，需另行确认是否一并更新；三份 README 的旧形态 244/227 亦不属本轮 12 文件清单。

---

## 八、2026-10-17 覆盖率族同步至 94.88%（追加，不改上文历史行）

> 本节为**新增记录**，不改动上文 §一 ~ §七 的历史快照行（保留可追溯）。

- **端点规模再次扩张，§七 的 94.69%（232/245）已过期**。机器真值（HEAD `a570d6c`，2026-10-17 实跑）：
  `cd py-server && env -u PYTHONPATH -u PYTHONSTARTUP -u NODE_OPTIONS -u ELECTRON_RUN_AS_NODE /d/miniconda3_new/python.exe scripts/verify_auth_coverage.py`
  → `__SUMMARY__ total=254 protected=241 public=13 coverage=94.88 unregistered=0`，
  即 **94.88%（241/254）**；`py-server/openapi.json` `/api` 子集 **236 paths / 254 operations**（全量 237 / 255，含非 `/api` 的 `/metrics`）。
- **方向**：受保护 232→241、总数 245→254、公开 13 不变 ⇒ 覆盖率 94.69% → 94.88% **上升**，非安全回归。
- **本日共同步 17 个活跃文件**（2026-10-17），分组：
  - 用户可见前端：`src/views/ShowcaseView.vue:78` / `:168` → 94.88%
  - 脚本 / 生成器 / 子仓 README：`py-server/scripts/verify_auth_coverage.py`（docstring「现状」块整体订正为 254 / 241 / 13 → 94.88%，并记录本轮扩张事实）、`py-server/tools/generate_demo_ppt.py:168`、`py-server/README.md:74`（43→42 模块、约 254 端点、236 路径）
  - 根 README 双语：`README.md:83` / `:261`、`README_EN.md:57` / `:189`（约 254 API 端点 / 236 路径 / 254 操作）
  - CI 记录：`docs/ci-backend-test-result.md:32` → 254 ops / 236 paths、94.88%（241/254）
  - 提交材料：`submission/00_提交清单.md`（:48 / :49 / :62 / :63 / :67 / :70 / :134 / :135 / :158 / :183 / :202 / :214 / :276）；`submission/02_配套文档/` 下 技术方案说明书（:125）、开发说明书（:266 / :293 / :412 / :533，changelog 新增 v2.3 行、v2.2 保留不改写）、系统架构设计文档（:7 / :33 / :98 / :185）、测试说明书（:12）、快速启动指南（:154，44→42 模块）
  - 路演与证据：`deliverables/build_roadshow_pptx.py`（:15 / :65-69 / :173 / :174 / :179）、`deliverables/芒得很职-国创赛证据页.md:26` / `:35`
  - plans：`plans/roadmap-2026-10-13.md:15`（243→254 端点）/ `:17`（94.67%→94.88%）
  - 官网站点：`site/index.html`（:216 API 端点 240→254；:217 / :378 / :380 / :404-408 测试口径 1177/227 → 1389/38/1，日期口径 2026-10-01 → 2026-10-09 CI）
- **偏离派工单逐行清单两处（同族 stale 数字，按「该文件内所有 stale 数字」一并处理，特此报备）**：
  1. `submission/00_提交清单.md:62` / `:63` / `:67`（端点口径表 + 「对外统一表述」结论句）未逐行列出，但它们是「对外主口径」的直接表述，留旧即对外自相矛盾，故同步为 254 / 236。
  2. `submission/00_提交清单.md:134` 的「应得 `paths=229 / ops=246`」校验期望实测已变为 **237 / 255**（全量 openapi = `/api` 236/254 + `/metrics`），一并订正；否则该行会给出错误的机检预期。
- **历史行按设计保留**：上文各节的 `94.67%` / `94.69%` / `231/244` / `232/245` / `244-245 operations` / `227-228 paths` 一律**原样不动**，它们记录各自时点的核对事实。`_archive_*` 快照与 `源码/` 冻结副本同样不在同步范围。
- **本次未改、留待决定**：
  - `deploy/career-pilot/backend/**`（一键启动绿色包副本，任务 #5 交付物）：`scripts/verify_auth_coverage.py:25`、`tools/generate_demo_ppt.py:168`、`site/assets/ShowcaseView-BAlW9mxR.js`（编译产物）、`app/status.py:220` 仍为 245 / 228 / 94.69 形态。属部署产物副本，不属本轮编辑清单；若要同步需先确认该副本是否仍对外分发。
  - `site/index.html:7` / `:244` / `:262` / `:269` 的「约 240 个 API 端点」近似表述未在派工单清单内，未改（口径为「约」，与 236/254 不构成硬冲突）。
  - `submission/00_提交清单.md:158` 的「覆盖率 61%」为**代码覆盖率**（pytest-cov），不属认证覆盖率族，未动。
- **SSOT 与机检（另笔提交）**：`docs/METRICS_CURRENT.md` sha256 `0c17657a4d85e50f` → `3ffae12147dc2a8b`、大小 261554 → 261558 字节、:84 total/protected 245/232 → 254/241；`scripts/verify_metrics.py --update` 仅动一行（后端代码行数 85803 → 85852）。

## 九、2026-10-17 测试数族刷新至 CI 1524/38/1（追加，不改上文历史行）

- **新 CI 真值**：run `38938041036`（head `dc18dd2`，2026-10-17，success，377.60s）默认档 **1524 passed / 38 skipped / 9 deselected / 1 xfailed / 0 failed**（`1572 collected`，运行项 1563；隔离档另 36 passed）。旧口径 1389/38/1（1428 运行项 / 1436 collected，run `37917008258`，2026-10-09）作废；`submission/_archive_*` 快照不动。
- **本节省同步范围（submission 侧）**：
  - `submission/00_提交清单.md`：:50（测试行 1428/1389/1436/8 → 1563/1524/1572/9）、:53（覆盖率行 run `38006205976`/21473/8453 → run `38938041036`/22108/8522）、:114、:158、:183
  - `submission/02_配套文档/测试说明书.md`：:17、:242
  - `submission/02_配套文档/系统架构设计文档.md`：:7、:194
  - `submission/02_配套文档/开发说明书.md`：:523（测试用例数行）；版本表追加 **v2.4** 行记录本次刷新（v2.2/v2.3 历史行不改写）
- **§八 遗留项核销**：
  - `deploy/career-pilot/backend/**`（绿色包/VPS 暂存副本）：已核实为 **VPS 生产部署暂存**（`deploy/vps/career-pilot.service` WorkingDirectory=/opt/career-pilot/backend），且按 2026-10-14 用户放行整目录 gitignore（不随仓库分发）。其 `scripts/verify_auth_coverage.py`、`tools/generate_demo_ppt.py` 两文件与权威源逐字节 diff 后确认**纯数字漂移、无本地改造**，已从 `py-server/` 覆盖同步；`site/assets/ShowcaseView-BAlW9mxR.js` 编译产物的两处陈旧 claim（卡片标题 + 统计条）已修补。**遗留项关闭。**
  - `site/index.html` 的「约 240 个 API 端点」：§八 后已被 10-17 官网同步批处理为 254（:7/:216/:244/:262/:269 实测均为 254）。**遗留项关闭。**
  - `submission/00_提交清单.md:158` 的「覆盖率 61%」为代码覆盖率（pytest-cov），不属认证覆盖率族，确认无需动（其 run 指针已在本节同步）。
- **机检**：`scripts/verify_metrics.py` 9/9、`scan_metric_occurrences`、`brand_scan`、`honesty_scan --all`、`scan_stale_calibration`、`check_hardcoded_paths`、`token_scan`、`a11y_scan` 全绿。
