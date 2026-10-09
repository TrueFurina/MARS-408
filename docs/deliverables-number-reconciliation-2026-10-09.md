# 国创赛交付物（deliverables/）数字对齐核对清单

> 生成时间：2026-10-09 ｜ 范围：`deliverables/` 下国创赛相关文档与 PPT 生成器
> 方法：只读审计 + 机器复算（不手数）。本机实跑 `verify_metrics.py`（9/9 通过）、`openapi.json` 计数、CI run `37917008258` 实测摘要。
> 配合文档：`docs/submission-number-reconciliation-2026-10-09.md`（submission/ 侧）
> ⚠️ 本清单为 **10-28 冻结窗口的 diff 预案**。当前冻结纪律下**只列不改**，源文件改动留待 10-28 批量执行。

---

## 一、结论速览

| 位置 | 当前内容（冲突） | HEAD 真值（2026-10-09） | 处置 | 严重度 |
|---|---|---|---|---|
| `deliverables/build_roadshow_pptx.py:13` | 默认集 1389 → **1178 passed / 208 skipped / 3 xfailed** | CI 默认档实测 **1389 passed / 38 skipped / 1 xfailed / 8 deselected** | 重跑 pytest 取数后改 | 🔴 |
| `build_roadshow_pptx.py:188`（Slide 7 正文） | 默认测试集 1389 项 → **1178 passed / 208 skipped / 3 xfailed** | 同上 | 同左 | 🔴 |
| `build_roadshow_pptx.py:196`（Slide 7 备注） | 1389 项，1178 通过、208 跳过、3 预期失败 | 同上 | 同左 | 🔴 |
| `build_roadshow_pptx.py:17`（禁用清单） | 禁 1133/915/923/1139/**1177**/1168；**缺 1178** | 现脚本自填 1178 未被禁 | 把 1178 加入禁用项 | 🟠 |
| `芒得很职-国创赛证据页.md:35` | API 端点 **243** / 去重路径 **226** | `openapi.json` 当前 **244 / 227** | 改为 244 / 227 | 🟠 |
| `build_roadshow_pptx.py:14` 覆盖率 54.96% | 标注值 54.96%（门禁 --cov-fail-under=50） | 需 10-28 重跑 pytest --cov 确认 | 重跑校准 | 🟡 |
| `build_roadshow_pptx.py:13/189` "CI p0 档 67 条" | 标注值 | 记忆："35 测试永不在 CI 跑"，67 来源待核 | 10-28 核源 | 🟡 |

---

## 二、详细冲突与 edit 预案

### A. `deliverables/build_roadshow_pptx.py`（PPT 生成器——高影响）

此脚本是路演 PPT 的唯一生成源（文件头注明：产物 = `deliverables/芒得很职-国创赛路演PPT-5分钟黄金路径.pptx` **＋** `submission/01_演示PPT/作品演示PPT-最终版.pptx`）。**脚本里的数字会同时烤进物料线与提交件两份 PPT**，所以它是本次审计中影响面最大的一处。

**A1. 第 13 行（docstring 口径铁律）**
```
当前：- 测试：默认集 1389（1397 collected，addopts deselect 8）→ 1178 passed / 208 skipped / 3 xfailed / 0 failed；CI p0 档 67 条
改为：重跑后填入 CI 默认档实测（当前 best-known：1389 passed / 38 skipped / 1 xfailed / 8 deselected；"默认集/collected" 措辞按 10-28 实际输出定）
```
> 根因：脚本把 `1389` 当"默认集规模"、把 `1178` 当"passed"，但 HEAD CI 默认档里 **1389 本身就是 passed**（collected≈1436，deselect 8）。这是 10-06 选择剖面与当前 CI 默认档的标签错位 + 数值漂移。

**A2. 第 188 行（Slide 7 正文）**
```
当前：'• 质量门禁可复现：默认测试集 1389 项 → 1178 passed / 208 skipped / 3 xfailed / 0 failed'
改为：同步 A1 的实测数
```

**A3. 第 196 行（Slide 7 演讲备注 notes）**
```
当前：'...默认测试集 1389 项，1178 通过、208 跳过、3 个预期失败、零失败，覆盖率 54.96%...'
改为：同步 A1 实测数 + A4 校准后的覆盖率
```

**A4. 第 14 行 覆盖率 54.96%**
```
当前：- 覆盖率 54.96%（门禁 --cov-fail-under=50）
处置：10-28 跑 `pytest --cov=. --cov-fail-under=50` 取真实覆盖率后回填（注：记忆已确认"54% 门禁不存在"，门禁实为 50，本句门禁描述正确，仅 54.96% 取值需复算）
```

**A5. 第 17 行 禁用清单缺口**
```
当前：- 禁用：451/243 端点、35 路由、1133/915/923/1139/1177/1168、54.08%、6.8413、旧品牌名与旧赛事名
改为：在禁用数列中补 **1178**（脚本自身在 A1/A2/A3 填写的 1178 当前未被本清单拦住，属机检缺口）
```
> 说明：禁用清单机制本身是好的（243/1177 等旧值已拦），但漏了 1178 这一当前误填值。

### B. `deliverables/芒得很职-国创赛证据页.md:35`（API 端点滞后）

```
当前：| API 端点 | **243**（method 级；去重路径 226） | 源码枚举；`openapi.json` 为入库快照且落后，以脚本为准 |
改为：| API 端点 | **244**（method 级；去重路径 227） | `py-server/openapi.json` 当前实测（verify_metrics 9/9 一致） |
```
> 实算佐证：本机读取 HEAD `py-server/openapi.json` → `/api` 路径 **227**、操作 **244**。证据页原注"openapi.json 落后"已成旧判断，现在 openapi.json 已是 244/227，故直接以它为准即可。
> 其余证据页数字（KG 86/82、KB 2122、用例 1410/1402、LangGraph 11、认证 94.67%/231/244、kg408 136/18、NeuralMixer 7.0446/0.2857）经核对**全部与 HEAD 一致，无需改动**。

### C. "CI p0 档 67 条"（line 13 / 189）
记忆纪律："35 测试永不在 CI 跑（conftest 全平台 skip 24+11）"。67 条来源不明，10-28 需从 `backend-test.yml` / `p0-regression.yml` 实测 p0 marker 用例数核验，避免凭空引用。

---

## 三、已核验一致、不必改的项（登记备查）

- API 操作 **244 / 路径 227**：`build_roadshow_pptx.py:15`、submission 清单均一致 ✅
- 认证覆盖率 **94.67%（231/244）**：证据页:26、build 脚本:15/152 均一致 ✅
- KG **86 节点 / 82 边**、KB **2122 chunk**、用例 **1410/1402**、LangGraph **11**、资源 **7**/模板 **5**/KG提示 **6+5**、NeuralMixer **7.0446±0.2857**（stratified/96/seed/n=6）：证据页与记忆一致 ✅
- 活跃国创赛文档（计划书 `芒得很职-国创赛商业计划书-2026-09-16.md`、路演脚本 `芒得很职-国创赛路演PPT脚本-5分钟黄金路径.md`、分镜 `芒得很职-国创赛演示视频分镜脚本-5分钟.md`、`国创赛对外材料诚信口径检查清单.md`）经 grep **未发现**过期测试数/API 数，均已自洽 ✅

---

## 四、10-28 执行步骤（与 submission 侧合并批量）

1. **定稿测试数**：在最终提交 commit 上跑 `pytest`（与 `backend-test.yml` 默认档相同 addopts），截取真实摘要行 → 得权威 (passed/skipped/xfailed/deselected)。
2. **改 `build_roadshow_pptx.py`**：A1/A2/A3 同步新测试数；A4 回填真实覆盖率；A5 把 `1178` 加入禁用清单。
3. **改 `芒得很职-国创赛证据页.md:35`**：API 243/226 → 244/227。
4. **改 submission/ 侧**（见 `docs/submission-number-reconciliation-2026-10-09.md`）：8 处测试数 + 2 处覆盖率 stale 引用。
5. **重生成 PPT**：跑 `build_roadshow_pptx.py` → 同时刷新 `deliverables/` 与 `submission/01_演示PPT/` 两份 PPT。
6. **门禁复核**：重跑 `verify_metrics.py`（应 9/9）、`token_scan --baseline`、`a11y_scan`；`gh run list` 复查 `verify-structural` 全绿。
7. **重打包 submission/ zip** + 同步清单数字。

---

## 五、红线提醒

- ❌ 冻结期（现在）**不要**改 `build_roadshow_pptx.py` / `证据页.md` / `submission/` 实体——只按本清单与 submission 侧清单在 10-28 批量执行。
- ❌ 不要把证据页的 "243" 误改成 "43"（记忆已证伪"API 模块 44→43"为计数边界误判）。
- ✅ 所有数字以"机器复算 + CI 实测"为唯一来源，禁止手抄。
