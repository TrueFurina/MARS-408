# 前后端契约交叉审计 · 2026-10-17（机验版）

> 性质：`plans/current.md` 主线外的主动深审（用户「继续」指令的延续）。
> 方法：口径先行——**后端真值 = `py-server/openapi.json`**（由 FastAPI 运行时生成，
> 其新鲜度由 ci.yml 的 `verify_openapi_snapshot.py` 守护，本轮复跑确认
> 237 paths / 255 operations 与运行时一致）；**前端调用面 = `src/` 全量**（字面量 +
> 模板字符串 + api.ts 全方法族）。不信记忆信磁盘，每条结论都可复跑复算。

## 一、工具：`scripts/audit_api_contract.py`（report-only / `--gate` 阻断双模）

采集规则（与 `src/utils/api.ts` 的 api 对象方法面对齐）：

- `api.get/post/put/delete/patch` + `postStream/upload/postBlob/getBlob`
  （后四者同样以 path 为首参，初版漏采致 5 处假孤儿）；
- 泛型类型参数容错：`api.get<{ classes: ClassItem[] }>('/career/classes')`
  的 `<...>` 不得吞掉路径（`[^(]*` 覆盖）；
- 模板字符串：`` api.get(`/career/classes/${id}`) `` 的 `${...}` 归一为 `{}` 占位；
- 前端相对路径统一补 `/api` 前缀（api.ts 的 `request()` 家族拼 `API_BASE+'/api'+path`，
  `API_BASE=''`）；
- 裸 `fetch` 默认 GET；排除 `__tests__`（测试假路径 `/test`、`/retry` 非生产契约）、
  node_modules、外部/数据 URL。

匹配语义（段级，容错前端惯用法——这一段是「真实仓库 A 类归零」的前提）：

| 前端形态 | 实例 | 匹配结果 |
|---|---|---|
| 字面量填充路径参数 | `/literacy/report/demo` ↔ `/api/literacy/report/{user_id}` | ✅ 占位段匹配任意段 |
| 模板动态段 | `/career/classes/${id}` ↔ `/api/career/classes/{}` | ✅ |
| query 串拼接 | `/experiments${suffix}`（suffix 为 `?a=b`）↔ `/api/experiments` | ✅ 尾部容错 |
| 方法孪生 | 前端 POST ↔ 后端仅 GET | ⚠️ 进 A 类并标注「方法不匹配」 |

退出码契约：`0` = 完毕且（非 gate 或 A 类为 0）；`1` = `--gate` 且 A 类 > 0；
`2` = 探活自身失败（openapi 缺失/零路由、前端扫描面为零——**fail-closed：
「照不到」不得当作「干净」**）。

## 二、A 类裁定：前端调用 → 后端无路由 = **0 处**（🟢）

真实仓库全量审计：**255 个后端操作 vs 231 个前端字面量调用点（141 条去重路径），
A 类为 0**——前端每一个调用都找得到后端路由，无 404/405 违约。

从「79 处疑似违约」到「0」的收敛过程本身就是方法论证（初版正则的七类误报，
逐类修正后归零，未靠放宽判据蒙混）：

1. 模板字符串路径初版未采（`api.get(`/x/${id}`)` 整族漏采）；
2. 泛型类型参数吞路径（`api.get<{...}>('/x')` 匹配失败）；
3. api.ts 的 postStream/upload/postBlob/getBlob 四方法族未采；
4. 前端相对路径缺 `/api` 前缀，与后端绝对路径比全不中；
5. 字面量填充路径参数被判「无此路径」（`/literacy/report/demo` vs `{user_id}`）；
6. query 串拼接被判「无此路径」（`/experiments${suffix}`）；
7. 跨盘符 `os.path.relpath` 崩溃（测试 fixture 在 C:、仓库在 E:）——
   **由新增测试暴露的真 bug**，已修为相对 src_root + 兜底。

## 三、B 类裁定：后端路由 → 前端零调用 = 102 条（报告用途，不阻断）

逐条人工复核后的分类（**不删除**——红线「任何文件/物料永不删除」+
BP 工程规模口径以 openapi 全量为真值源 + 大量端点系 main 分支 legacy 保留）：

| 类 | 条数 | 实例与裁定 |
|---|---|---|
| 状态/诊断面（合理） | 9 | `llm/x2-health`（探活脚本 admin 调用）、`status/competition`、`multimodal/status`、`multimodal/supported-types`、`tts/status`、`xfyun/status`、`xfyun/ppt/status/{}`、`xfyun/video/status/{}`、`/metrics`——运维/探针/编排面，无需前端 |
| 客户端自处理（合理） | 2 | `auth/logout`（前端清 storage 即登出）、`auth/me`（刷新时读 localStorage，非调接口） |
| legacy 别名/孪生（合理） | 4 | `POST /sandbox` 与 `/sandbox/run` 同 handler 双装饰（前端调后者）；`chat/send` 是 `/chat/stream` 的非流式孪生（前端只用流式）；`multimodal/generate`、`generate-teaching-video-stream` 同族被 `generate-image/audio/multimodal` 与非流式版取代 |
| 变量/模板间接调用（**审计工具固有漏判**，实为在用） | 3 | `skills/run`、`skills/run-stream`、`skills/run-with-memory` 经 SkillDetailView 的 `endpoint` 变量三元选择调用；`tts/synthesize` 经 api.ts 内部 `fetch(`${API_BASE}/api/tts/synthesize`)` 模板。**B 类只作线索，须人工复核后才成结论** |
| 后端完整、前端未接（feature-complete backend） | 84 | `teacher/assignments`（6，作业功能后端全齐）、`memory` L1/L2/L3 CRUD（12，前端只用 overview 聚合）、`imports`（5）、`engine`（7）、`cn-distinction`（4）、`english`（4）、`knowledge-graph` 扩展（5）、`knowledge-base` 导入（3）、`skills` 批量/导入/种子/导出（6）、`sessions` CRUD（4，被 `/user/conversations` 同步机制取代）、`review`（3）、`profile` 快照/行为（3）、`user/quiz-history`（2）、`wrong-questions` 扩展（3）、`tutor/answer`、`recommendations`、`resource/delete`、`agents/generate-resource`（2）、`daily-plan` GET、`career/sessions`、`teacher/students/{}/detail`、`teacher/agent-performance`、`admin/users/list`、`benchmark/results/per-question` |

**安全面核验**：102 条孤儿的鉴权状态由 `py-server/scripts/verify_auth_coverage.py`
全量裁决——254 操作 / 241 受保护 / 13 公开（逐一附理由：登录注册、benchmark 证据
只读面、cn-distinction 只读、literacy 题库、status 探针）/ **unregistered=0**，
coverage **94.88%**，与 `docs/METRICS_CURRENT.md` 记载一致（无漂移）。
孤儿端点中无「未注册即公开」的暴露面。

> 📌 **2026-10-21 补注**：上一段为 10-17 时点审计结论（当时准确）。此后教师端系列提交扩张了端点，
> 现 SSOT 为 **261 操作 / 248 受保护 / 13 公开、95.02%（248/261）**，`unregistered` 仍为 **0**
> （2026-10-21 `verify_auth_coverage.py` 机检复核）。引用本文数字务必带 as-of 日期。

## 四、门禁落地与测试（双向变异验证）

- **CI**：`audit_api_contract.py --gate` 接入 `.github/workflows/verify-structural.yml`
  structural job（纯 stdlib，1.2s，无依赖）。A 类 > 0 即阻断 PR。
  设计取舍：只 gate A 类（真违约）；B 类（孤儿）不阻断——legacy/admin/诊断面
  大量合理存在，阻断会逼出删端点这类违反红线的「通过方式」。
  快照忘记同步时本闸会红（前端调新路由、openapi.json 还没重生成）——
  **这是预期行为，逼着同步快照而非绕过**。
- **测试**：`py-server/tests/test_api_contract_audit.py` 15 例——匹配语义 9 例
  （占位/模板/query 拼接/泛型/方法族/fetch 默认 GET/方法不符标注/未知路径/孤儿
  不误判）+ 门禁契约 5 例（合成夹具验 exit 0/1/2）+ 真实仓库不变量 1 例
  （A 类必须为 0，本地可复跑）。按 TDD 纪律与实现**分两个 commit**。
- **三重变异验证**（改坏必须红，实证测试非装饰）：
  ① 删 `seg_match` 占位容错 → 3 例红（字面量填参/孤儿不误判/真实仓库不变量）；
  ② 删 gate 的 `sys.exit(1)` → `test_gate_blocks_when_frontend_calls_missing_route` 红；
  ③ 空 spec 改放行 → `test_fail_closed_on_empty_spec` 红。
  （① 初版变异脚本经 heredoc 传参被吞反斜杠、替换未命中而「假存活」——
  已改用文件级行操作重做并确证红。方法论备注：**变异未命中时先验证替换本身
  是否生效，再把「通过」当结论**。）

## 五、结论与残留

- 🔴→🟢 前端契约面干净：A 类 0 处，且今后由 CI 阻断新增违约。
- B 类 102 条全部有合理解释（9+2+4 合理、3 为工具漏判、84 为后端完整前端未接），
  **零删除、零改动**——它们计入 BP 的「255 个 API 操作」工程规模口径
  （`docs/METRICS_CURRENT.md` 同源）。
- 残留（非本机可裁，需用户/运营侧）：84 条「后端完整前端未接」是否接线属产品
  范围决策（如 teacher/assignments 作业功能），本轮只做清点不做处置。
