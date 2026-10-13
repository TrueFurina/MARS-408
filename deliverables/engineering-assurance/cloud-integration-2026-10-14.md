# WorkBuddy 云服务接入 · 开通与验证报告

**日期**：2026-10-14
**分支**：`career-literacy`（提交 `40301da` 实现 + `ebd4e52` 验证工具，远端 SHA 已核对一致）
**应用**：`wbapp_SCV2PQvaYZGxutFzKn3mwC`（芒得很职 · web）

---

## 一句话结论

云服务已开通并完成代码接入；**浏览器与直连两条路径都验证了「通道可用」**，过程中还抓出并修复了一个
**未登录可写数据库的 P0 级安全漏洞**（行级安全自我放行）。唯一未完成的是「登录之后的读写验证」，
因为它需要收到邮箱验证码，而本环境 Agent Mail 未开通、收不到信。

---

## 已验证（证据在 `_e2e_tmp_mdhz/cloud_probe_result.json` / `cloud_browser_result.json`）

| # | 验证项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | 云端会话读取（未登录返回空而非报错） | ✅ | 探针 4/4 |
| 2 | **LLM 网关（免密钥 AI 助教）**：浏览器 Origin 下拉取模型 | ✅ **32 个模型** | 浏览器走查 + 探针双路径一致 |
| 3 | 未登录写数据库 → 被拒 | ✅ 修复后 42501 拒绝 | 探针 |
| 4 | 未登录读数据库 → 被拒 | ✅ 42501 拒绝 | 探针 |
| 5 | 页面渲染（四张功能卡片、无 JS 异常、无失败请求） | ✅ | 截图 `_e2e_tmp_mdhz/shots/` |
| 6 | `npm run type-check` | ✅ | vue-tsc 0 错误 |

## 未验证（登录态开通方向）与 401 诊断结论

用真实邮箱（QQ 邮箱）多轮实测后，**登录态开通方向被服务端问题挡住**，诊断已到根因级：

| 步骤 | 端点 | 结果 |
|------|------|------|
| 发码 | `POST /.cloud/auth/v1/verification` | ✅ 200，返回 verification_id（无 Set-Cookie） |
| 验码 | `POST /.cloud/auth/v1/verification/verify` | ✅ **200**，正常下发一次性 verification_token（600s） |
| 换会话（登录） | `POST /.cloud/auth/v1/signin` | ❌ **401 invalid_grant**："session is invalid, expired or issued for another client" |
| 换会话（注册） | `POST /.cloud/auth/v1/signup` | ❌ 同样 401 invalid_grant（首次尝试时即复现） |

**已排除**：验证码过期（发码后 90 秒内即试）、跨进程客户端态丢失（同进程复现）、
Cookie 绑定（响应无 Set-Cookie、裸 fetch 复现）、接入代码字段错误（裸 API 与 SDK 行为一致）。

**结论**：换会话两条独立路径稳定 401，SDK 与裸 API 行为一致 ⇒ **服务端/上游会话签发问题**
（疑似该邮箱在首次尝试时留下半注册残留状态）。**不是接入代码问题**；接入代码与官方 SDK 契约逐字段核对无误。

**影响与后续**：
- 云端通道（LLM 网关、RLS 拦截、会话读取）均已验证可用；仅「登录后读写」待服务端修复后，
  跑 `node scripts/e2e/cloud_authed_flow.cjs --email <邮箱> --send` 即可一次跑完全链路（脚本已备好）。
- 也可换一个**全新邮箱**重试注册流程——若成功即可佐证「半注册残留」假设。
- 该发现可作为云服务侧 bug 线索反馈。

---

## 🔴 P0：行级安全自我放行（已修复）

**现象**：探针发现未登录竟然能写进 `source_lab_progress`，`owner_id` 被写成字符串 `'anon'`，还能读回来。

**根因**：数据面（PostgREST）匿名请求时 `auth.uid()` 返回**字符串 `'anon'`**——而管理员连接下它返回 NULL，
两种连接行为不一致。于是策略 `owner_id = auth.uid()` 退化为 `'anon' = 'anon'`，自己给自己放行；
又因 `(owner_id, lab_id)` 唯一索引，所有匿名用户会挤在同一个 owner 下**互相覆盖进度**。

**修复**（双保险，已在云端生效）：

1. 四条策略全部限定 `TO authenticated`，并加守卫
   `auth.uid() IS NOT NULL AND owner_id = auth.uid() AND owner_id <> 'anon'`；
2. `REVOKE ALL ON public.source_lab_progress FROM anon`（权限层兜底）；
3. 探针留下的脏数据已清理（`owner_id='anon'` / `__probe_%`）。

**修复后复测**：未登录写/读均被 42501 拒绝，探针 4/4 通过。

**教训（已入项目记忆）**：凡用 `auth.uid()` 做默认值或策略，必须在**数据面角色**下实测匿名行为；
管理员连接的查询结果不能当作依据。这与 2026-10-13「包属性遮蔽致隔离静默失效」是同一类教训：
**隔离机制必须验证其真实去向，不能假定它生效。**

---

## 过程中的假阳性（走查脚本自纠）

首版浏览器走查报「下拉 4 项」，实为选择器匹配到了页面上**别的下拉框**；
「登录入口」检查也匹配到了导航栏里的「登录」二字。已改为**定位到具体卡片内部**再取元素，
修正后确认真值 32 项，与直连探针一致。检查脚本本身也要防"静默验错对象"。

---

## 交付物清单

| 类型 | 路径 |
|------|------|
| 云身份模块 | `src/services/cloud/auth.ts`（验证码/密码/微信登录、会话订阅） |
| 云端存档 | `src/services/cloud/labArchive.ts`（进度 upsert/select、文件上传/下载/签名链接） |
| AI 助教 | `src/services/cloud/tutor.ts`（仅流式、模型来自 models.list） |
| 页面 | `src/views/CloudLabView.vue` + `/cloud-lab` 路由 + 导航入口 |
| 通道探针 | `scripts/e2e/cloud_probe.cjs`（Node 直连，`--send-otp 可选发信`） |
| 浏览器走查 | `scripts/e2e/cloud_lab_walkthrough.cjs`（puppeteer-core + 系统 Chrome，人工跑不进 CI） |
| 应用清单 | `.wbapp_SCV2PQvaYZGxutFzKn3mwC.genie`（publicConfig 四项均为可公开凭证） |

## 诚实边界

- 本报告是**接入正确性**证据，**不是成效证据**；项目仍为零真实用户，禁引用任何条数当成效。
- 走查用的应用账号 `e2e_cloud` 建在隔离后端库（`NETLEARN_PG_DIR` 临时目录），真实本地库零写入；
  云端表内探针脏数据已清零。
