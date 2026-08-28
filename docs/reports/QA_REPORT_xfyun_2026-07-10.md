# QA 测试与发布报告 ——「讯飞开放平台 10 项 API 全量接入」

- **项目**：study-help-pro（计算机 408 考研个性化学习多智能体系统 / MARS-408）
- **变更范围**：讯飞 AI 工坊（后端 10 服务封装 + 10 REST 端点 + 前端 10 能力卡片 + 图片理解链路）
- **QA 角色**：gstack-qa-lead（质量门神）
- **测试日期**：2026-07-10
- **结论**：**CONDITIONAL GO（条件放行）** —— 代码质量达标，但存在 1 项安全硬阻塞 + 1 项生产可用性风险，需在放行前处理。

---

## 一、执行摘要

| 维度 | 结果 |
|---|---|
| 后端路由存在性 | ✅ 10/10 端点全部注册，无 404 |
| 鉴权限流 | ✅ 未鉴权访问返回 401，注入用户后正常通过 |
| 异常兜底 | ✅ 真实调用失败统一转 502，无 500 路由错误 |
| 接口契约一致性（前端↔后端） | ✅ 全部文档字段对齐（1 处命名偏差，非功能性） |
| 前端类型检查 | ✅ `vue-tsc --build --force` 退出码 0，0 错误 |
| 前端构建产物 | ✅ `dist/` 存在，含 `index.html` 及完整 js/css chunk |
| 安全（凭证管理） | ❌ **真实讯飞凭证存于被 git 跟踪的 config.json，有泄露风险** |
| 生产可用性 | ⚠️ PPT/视频为同步长轮询端点（最长 5 分钟），缺后台任务隔离 |
| 真实 API 联通 | ⚠️ 离线环境无法验证 200 成功路径（仅验证失败兜底路径） |

**阻塞项**：1 项安全（B1）、1 项可用性（B2）。非阻塞建议 3 项（N1–N3）。

---

## 二、测试覆盖

### 2.1 后端端点冒烟（FastAPI TestClient + dependency_overrides 注入 admin 用户）
> 测试用 `app.dependency_overrides[shared.auth.get_current_user]` 注入 `{'id':'u1','username':'smoke','role':'admin'}`。
> 离线环境模拟：将 `httpx.AsyncClient.post/get` 与 `websockets.connect` 强制抛出连接异常，确定性验证「真实调用失败 → 被捕获 → 返回 502」路径，避免离线挂起。

| 端点 | HTTP | 判定 | 说明 |
|---|---|---|---|
| GET /api/xfyun/status | **200** | ✅ PASS | 返回 `credentials_configured: True` + 10 项服务全 `True` |
| GET /api/xfyun/status（无鉴权） | **401** | ✅ PASS | `detail: 未登录或缺少凭证` —— 鉴权生效 |
| POST /api/xfyun/image-understand | **502** | ✅ PASS | 异常被捕获（mock WS 报错），非 500 |
| POST /api/xfyun/search | **502** | ✅ PASS | 兜底正常 |
| POST /api/xfyun/ppt | **502** | ✅ PASS | 兜底正常 |
| POST /api/xfyun/video | **502** | ✅ PASS | 兜底正常 |
| POST /api/xfyun/proofread | **502** | ✅ PASS | 兜底正常 |
| POST /api/xfyun/proofread-doc | **502** | ✅ PASS | 兜底正常 |
| POST /api/xfyun/compliance | **502** | ✅ PASS | 兜底正常 |
| POST /api/xfyun/roleplay | **502** | ✅ PASS | 兜底正常 |
| POST /api/xfyun/resume | **502** | ✅ PASS | 兜底正常 |
| POST /api/xfyun/roleplay（缺 message） | **422** | ✅ 预期 | 缺必填字段，路由存在+鉴权通过 |
| POST /api/xfyun/resume（缺 info） | **422** | ✅ 预期 | 同上 |

**路由表核对**：10 个路由全部已注册（`/api/xfyun/{status,image-understand,search,ppt,video,proofread,proofread-doc,compliance,roleplay,resume}`）。

### 2.2 前端构建产物
- `dist/` 目录存在（时间戳 2026-07-10 16:37），含 `index.html` 与 `dist/assets/` 下完整 chunk（AdminView / AssessmentView / ChatView / DashboardView / EngineView / ResourceView 等 js + css，以及 KaTeX 字体等）。
- `vue-tsc --build --force`：退出码 **0**，0 类型错误（已独立执行验证，非采信"已知状态"）。

### 2.3 接口契约一致性（前端调用 ↔ 后端返回）
逐字段核对 `src/views/ResourceView.vue` / `src/stores/studyStore.ts` 与 `py-server/api/xfyun.py`：

| 能力 | 前端取值 | 后端返回字段 | 一致 |
|---|---|---|---|
| PPT | `d.ppt_url`, `d.title` | `{ppt_url, title, sid, source}` | ✅ |
| 视频 | `d.video_url`, `d.audio_url`, `d.text` | `{video_url, audio_url, text, task_id, source}` | ✅ |
| 搜索 | `d.items[{title,summary,url}]`, `d.count` | `{items:[{title,summary,url}], count, source}` | ✅ |
| 纠错 | `c[1]/c[2]/c[3]`, `d.count` | `{corrections:[[pos,cur,correct,type]...], count}` | ✅ |
| 公文校对 | 同纠错 | 同纠错 | ✅ |
| 合规 | `d.passed`, `d.suggest`, `d.hits[{word}]` | `{passed, suggest, hits:[{category,word,confidence}]}` | ✅ |
| 角色模拟 | `d.reply` | `{reply, chat_id, source}` | ✅（见 N1） |
| 简历 | `d.word_url`, `d.raw` | `{word_url, raw, source}` | ✅ |
| 图片理解 | `d.text` | `{text, source}` | ✅ |

**结论**：前端 ↔ 后端响应契约**完全一致**，无字段错配。

---

## 三、发现的问题

### 🔴 B1（安全 / 硬阻塞）真实讯飞凭证存于被 git 跟踪文件
- `py-server/config.json` 已填入真实 `app_id / api_key / api_secret / api_password`。
- `.gitignore` 第 68 行虽有 `py-server/config.json`，但 `git ls-files` 显示该文件**已被 git 跟踪**（忽略规则在其入库之后才添加，对已跟踪文件不生效）。
- **风险**：任何 `git commit` / `git push` 会把生产级讯飞凭证推入仓库历史，等同泄露。
- **影响**：账号被盗用、额度被刷、合规事故。

### 🟠 B2（可用性 / 建议阻塞）长轮询同步端点无隔离
- `generate_ppt` 同步轮询最长 ~120s（40×3s），`generate_video` 最长 ~5min（60×5s）；二者均为**同步 HTTP 端点**。
- 在生产（uvicorn worker / 反向代理）下，单个请求即可长时间占用 worker，并发时易耗尽连接池或触发网关 502/504 超时。
- **建议**：改为后台任务（FastAPI BackgroundTasks / Celery / 轮询状态接口），或至少在前端标注预期耗时并设长超时。

### 🟡 N1（契约命名偏差，非功能）roleplay 字段命名
- 任务契约表写 `roleplay → {reply, session_id, round}`，后端实际返回 `{reply, chat_id}`（多轮状态由后端按 `persona` 缓存，前端无需 round/session_id）。
- 前端仅消费 `reply`，功能正常；但**接口文档/契约说明与实现命名不一致**，建议统一命名以避免联调歧义。

### 🟡 N2（QA 流程缺陷）主理人提供的参考冒烟命令不完整
- 参考命令：`c.post('/api/xfyun/roleplay', json={'topic':'OS'})`、`c.post('/api/xfyun/resume', json={})` 会返回 **422**（缺必填 `message` / `info`），而非 502，易被误判为失败。
- 已更正命令（见附录 A）。

### 🟡 N3（UX，低风险）错误静默吞没
- `ResourceView.vue` 的 `xfCall()` 对 502/网络错误仅 `console.error`，**无用户可见提示**，用户点击卡片后无反馈。
- 建议：非 200 时展示轻量 toast/内联错误（如「讯飞服务暂不可用，请稍后重试」）。

### 说明：真实 API 成功路径（200）未在本环境验证
- 本环境离线，无法直连讯飞；**仅验证失败兜底路径（502）与路由/鉴权**。
- 但所有服务函数均带 `try/except` 结构化兜底、且 `has_credentials()` 已确认 True，联通性需在具备外网 + 真实凭证的环境中做一轮端到端（E2E）冒烟后才可完全闭环。

---

## 四、Go / No-Go 决策

**决策：CONDITIONAL GO（条件放行）**

- ✅ **代码层面准予发布**：路由、鉴权、异常兜底、契约一致性、前端类型检查与构建产物均通过。
- ❌ **公开/远程仓库发布前必须解除 B1**：在 `git push` 到任何共享/远程仓库前，必须完成凭证去 VCS 化（见行动清单 A1–A3）。
- ⚠️ **生产部署前建议解除 B2**：长轮询端点需加后台任务隔离或明确超时文档，否则高并发下存在可用性风险。

**若在已隔离的内部/ staging 环境、且确认凭证未推送远程**，可判定 **GO**。

---

## 五、行动清单

### 阻塞项（发布前必须完成）
- [ ] **A1（B1）**：从 VCS 解除凭证跟踪 —— `git rm --cached py-server/config.json`，确认 `.gitignore` 持续忽略；将真实凭证迁移至 `.env`（项目已支持 `_load_dotenv` 与 `XF_*` 环境变量覆盖）。
- [ ] **A2（B1）**：若 `config.json` 已提交过任意含凭证的版本，视为凭证已泄露 —— 在讯飞控制台**轮换（重置）AppID/APIKey/APISecret/APIPassword**，并用 `git filter-repo`/`BFG` 清理历史。
- [ ] **A3（B1）**：CI 增加「密钥扫描」（gitleaks/trufflehog），阻止凭证进入主干。
- [ ] **A4（B2）**：将 PPT/视频生成改为后台任务 + 进度查询接口；或至少在反向代理层将超时调到 > 5min 并加并发限流。

### 非阻塞（建议跟进）
- [ ] **A5（N1）**：统一 roleplay 契约命名（`chat_id` ↔ 文档 `session_id`，或反之）。
- [ ] **A6（N2）**：更新团队冒烟脚本，补全 `roleplay`/`resume` 必填字段（见附录 A）。
- [ ] **A7（N3）**：`xfCall` 增加用户可见错误提示。
- [ ] **A8（E2E）**：在具备外网环境跑一轮真实 200 成功路径冒烟（重点 PPT/视频长任务、角色模拟多轮、搜索/RAG）。

### 回滚预案
本特性为**增量、隔离**的路由模块，回滚成本低：
```bash
# 最小回滚（关闭能力，保留代码）：删除 router 注册 2 处 + 删 3 个新文件
#   - py-server/api/__init__.py : 删除第 23 行 import 与第 32 行 __all__ 中的 xfyun_router
#   - py-server/main.py         : 删除 import xfyun_router 及 _all_routers 中的 xfyun_router
#   - 删除：py-server/api/xfyun.py、py-server/db/xfyun_services.py、py-server/db/xfyun_multimodal.py
# 前端调用将得到 404（xfCall 静默捕获），系统其余功能不受影响。

# 完整回滚（连前端一并撤销）：
git restore py-server/main.py py-server/api/__init__.py \
            src/views/ResourceView.vue src/stores/studyStore.ts \
            src/components/ChatInput.vue src/views/ChatView.vue
rm -f py-server/api/xfyun.py py-server/db/xfyun_services.py py-server/db/xfyun_multimodal.py
```
> 注意：`config.json` 含真实凭证，**回滚时不要 `git restore` 该文件**（会回退/扩散凭证）；按 A1 单独处理。

---

## 附录 A：已更正的冒烟测试命令要点
```python
# roleplay 必须带 message；resume 必须带 info，否则返回 422
c.post('/api/xfyun/roleplay', json={'persona':'mock_interviewer','message':'你好','topic':'OS'})
c.post('/api/xfyun/resume',  json={'info':'张三 计算机本科'})
```

## 附录 B：实测证据摘录（节选）
```
STATUS           -> 200   {'credentials_configured': True, 'services': {10 项全 True}}
STATUS_NOAUTH    -> 401   {'detail': '未登录或缺少凭证'}
IMAGE_UNDERSTAND -> 502   {...异常被捕获...}
SEARCH/PPT/VIDEO/PROOFREAD/PROOFREAD_DOC/COMPLIANCE/ROLEPLAY/RESUME -> 502
ROLEPLAY_BADBODY -> 422   missing 'message'
RESUME_BADBODY   -> 422   missing 'info'
vue-tsc --build --force -> EXIT=0 (0 errors)
```
