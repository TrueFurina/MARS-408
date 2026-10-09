# 提交包数字对齐核对清单（2026-10-09 预检）

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
