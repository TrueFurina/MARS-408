# 安全机制代码级独立复核（2026-11-02）

- 仓库：`E:\Program\MARL\study-help-pro`
- 分支 / 基线：`merge/ws1-ws4-20261102` @ `35af837`（2026-11-02）
- 方式：逐条读代码 + 只读取证脚本（`%TEMP%\secscan_routes.py`、`secscan_priv.py`、`secproof.py`），
  单文件 pytest 3 组（`--no-cov`）辅助取证
- 红线遵守：**未修改、未 add/commit/push 任何仓库文件**；所有临时脚本写在
  `C:/Users/Lenovo/AppData/Local/Temp/`
- 口径：**不采信既有文档/历史结论**，每条结论都必须能被我自己的命令或代码位置复核

---

## ① 结论表

| # | 机制 | 结论 | 关键证据（file:line） |
|---|------|------|----------------------|
| 1 | 鉴权 fail-closed 三态 | **PASS** | `py-server/shared/auth.py:112-134`（无 token→401，`verify_token` 失败→401）；`shared/auth.py:92-109`（签名/过期/畸形统一 401）；`shared/auth.py:137-141`、`144-156`（角色不匹配→403）。实测：无头 401 / 伪造 401 / 学生打 admin 403 / admin 200 |
| 2 | 启动 fail-fast 时序 | **PASS（仅安全门禁）** | `app/lifespan.py:336-341`（`AUTH_SECRET` 缺失/过短直接 raise）、`:108-131`（生产缺 `ADMIN_PASSWORD`/短于 16 拒绝）、`:136-144`（管理员初始化失败生产 fail-fast）、`:347`（workers>1 拒绝）、`:350`（向量库初始化异常不捕获→启动失败）；`main.py:25-26` bootstrap 先于一切业务 import。**非安全组件（PG/Redis/迁移）静默降级，见 🟡-8** |
| 3 | 默认管理员 | **PASS** | `app/lifespan.py:111`（口令只来自 `ADMIN_PASSWORD` 环境变量）、`:112-118`（生产缺失→RuntimeError）、`:127-131`（生产长度<16→拒绝）；`db/user_store.py:269-276` 无任何硬编码默认值；`seed_users.py:33-40` 缺失即 `sys.exit(1)`。**轮换无效，见 🟠-4** |
| 4 | 口令存储 | **PASS** | `db/user_store.py:194`（`PBKDF2_ITERATIONS=600_000`）、`:198-203`（`secrets.token_hex(16)`=16B 盐、`pbkdf2_hmac('sha256')`）、`:217`（`hmac.compare_digest`）；`:246-255` 用户不存在也跑一轮 PBKDF2 防枚举。无 md5/sha1 存口令路径（`db/xfyun_services.py:105-140` 的 md5/sha1 是讯飞接口签名，非口令）。细节见 🟡-11 |
| 5 | 密钥面（save_config / gitignore / 硬编码） | **PASS** | `config.py:402`（`_SECRET_FIELDS` 含 api_key/api_secret/api_password/app_id/search_password/password）、`:413-427`（递归剥离）、`:430-439`（写盘前剥离）；`.gitignore:34-35,118-119,309`；`git ls-files` 中无 `.env`/`config.json`（仅 `.env.example`/`config.example.json`）；`src/`+`py-server/` 无 `sk-*`/32hex 密钥、无 `192.168.*`/`10.*` 内网 URL。**占位密钥可过校验见 🟠-1，list 不递归见 🟡-6** |
| 6 | 限流 | **GAP** | 阈值单一真值源：`shared/limits.py:56,60,64,68,69`；`api/auth.py:32-35` 只引用常量、不写字面量。**边界实测**：`max=20` 时第 1–20 次 `True`、**第 21 次 `False`**（进程内路径与 Redis 路径同语义 `db/redis_client.py:179-182,257-260`）；生产无 Redis 且未开开关→`False`（fail-closed，`:236-243`，实测确认）。**但本机回退可被绕过，见 🟡-3/🟡-4** |
| 7 | CSP / 安全头 | **PASS** | `app/middleware.py:40-49`（生产 CSP）、`:50-59`（开发 CSP）、`:178-202`（统一下发）。实测响应头：`X-Content-Type-Options`、`X-Frame-Options=SAMEORIGIN`、`X-XSS-Protection`、`Referrer-Policy=no-referrer`、`COOP=same-origin`、`COEP=require-corp`、`Permissions-Policy`，生产另加 `HSTS max-age=31536000; includeSubDomains`。生产 `script-src 'self'`（无 `unsafe-inline`/`unsafe-eval`）；开发与 `/showcase` 才有 `unsafe-inline`。缺口见 🟡-5/🟡-6 |
| 8 | XSS 面 | **PASS** | 229 处 `v-html` 全量为「图标常量 / `renderMarkdownSafe` / `sanitizeSvg` / 本地三元」四类（逐表达式核对，无一处直插后端/LLM 原文）；`src/utils/markdown.ts:146-154`（DOMPurify）、`:204-212`（SVG 预清洗 + DOMPurify）；命令式注入仅 `src/views/ChatView.vue:407,409` 两处硬编码 SVG 字面量；`renderMarkdown` 未净化版本**零调用点**；`scripts/xss_scan.py` 实测 130 文件 PASS，且确已覆盖 `.ts`/`<script>`（CI 接入 `verify-structural.yml:120-121`）。见 🟡-7（srcdoc） |
| 9 | 越权（教师/管理员） | **GAP** | 管理员面：`api/admin.py:49,55`、`admin_users.py:28-32`（路由级 `require_admin`）、`:95`、`imports.py:23,50,61,67,76`、`sandbox.py:343` 均为 admin 依赖；`skills.py:507-511` 内联 admin 判定。教师面：`teacher.py:21..338` 全部走 `require_teacher_or_demo_open`。**但该依赖在生产不设限，见 🟠-2；另有学生可写共享知识库 🟠-3、token 角色不可吊销 🟠-5** |

> 汇总：**7 PASS / 2 GAP（第 6、9 项）/ 0 UNVERIFIED 项**，另有 3 处子项证据不足，见 ③ 末。

---

## ② 发现的问题

### 🔴 严重（0 项）

本次未发现「无条件、可直接利用」的严重缺陷。下述 🟠-1/🟠-2 属「配置一旦失误即等于鉴权被绕过」，在真实部署里应立即按 🔴 对待。

---

### 🟠 高（5 项）

#### 🟠-1 `AUTH_SECRET` 只校验长度，仓库自带占位值可直接当生产密钥用
- 位置：`py-server/shared/auth.py:57-61`（唯一校验是 `len(secret) < 32`）；`py-server/.env.example:56` 提供
  `AUTH_SECRET=your_random_secret_here_at_least_32_chars`（**41 字符，天然通过校验**）
- 复现（已实测，`NETLEARN_ENV=production` + 上述占位值）：
  ```
  placeholder len = 41
  用公开占位值签发的 admin token 可验证: {'sub': 'u_attacker', 'role': 'admin', ...}
  ```
  即：`create_token("u_attacker","admin")` 用**仓库里公开的字符串**即可签出合法管理员 token，
  服务端 `verify_token` 通过 → 直接接管 `require_admin` 全部门禁。
- 影响面：任何「复制 `.env.example` → 填 `NETLEARN_ENV=production` → 忘记替换 AUTH_SECRET」的部署。
- 同类：`ADMIN_PASSWORD` 占位值 `your_strong_admin_password`（26 字符）同样能过 `>=16` 门槛。

#### 🟠-2 演示放宽开关 `NETLEARN_DEMO_TEACHER_OPEN` 在生产**不受任何限制**
- 位置：`shared/auth.py:159-166`（`_is_demo_teacher_open()` 只看环境变量，**不看 `NETLEARN_ENV`**）、
  `:186-194`（学生角色直接放行，仅打一条 `[DEMO-RELAX]` 警告）；`app/lifespan.py`、`main.py` 均无该开关的启动期拦截（grep 零命中）
- 复现（已实测）：`NETLEARN_ENV=production` + `NETLEARN_DEMO_TEACHER_OPEN=1` →
  `require_teacher_or_demo_open(user={"user_id":"u_stu","role":"student"})` **返回该学生**，
  于是 `GET /api/teacher/students/overview`、`/teacher/students/{id}/detail` 对任意学生开放（`teacher.py:21,61`）
- 关键放大点：`teacher.py:26-44`、`:66-71` **没有班级/归属过滤**，一个学生可枚举全校学生画像与答题历史。
- 代码注释写「生产环境绝不应设置」，但**代码层面没有任何机制阻止**——注释不是门禁。

#### 🟠-3 任意已登录学生可上传 PDF 写入**共享知识库**
- 位置：`api/knowledge_base.py:18`（前缀 `/knowledge-base`）、`:75-106`（`POST /api/knowledge-base/import-pdf`，
  依赖仅 `Depends(get_current_user)`，`user` 变量甚至未被使用）
- 对比：同仓库的管理员导入通道 `api/imports.py:23` 是 `require_admin`；教师导入 `teacher.py:317` 是教师依赖。
  唯独这条「直写库」的端点降级成任意登录用户。
- 影响：学生可污染全站教材/检索语料（教学诚信问题），并借 50MB 上限 + 同步 PDF 解析
  （`:100` `run_in_threadpool(import_textbook,...)`）做资源消耗；单进程部署下可拖慢全体。
- 复现：学生 token → `POST /api/knowledge-base/import-pdf`（multipart pdf）→ 200 `{"status":"ok"}`，新教材进入共享库。

#### 🟠-4 `ADMIN_PASSWORD` 轮换无效：`ensure_admin` 幂等且**不更新密码**
- 位置：`db/user_store.py:269-276`——`if row: return`，命中用户名即返回，**从不比对/更新口令**
- 复现：`ADMIN_PASSWORD=A` 启动一次（admin 创建）→ 改环境变量为 `B` 重启 → 用 `A` 仍可登录，
  `B` 登录失败。运维以为已完成轮换，实际旧口令永久有效。
- 附带：生产「口令长度>=16」只在启动时对新创建生效，历史短口令账号不会被纠正。

#### 🟠-5 Token 内角色不可吊销：删号/降权后 7 天内仍有效
- 位置：`shared/auth.py:75-89`（角色与 `exp` 写死在 token，TTL 7 天）、`:112-134`（`get_current_user`
  **不回查数据库**、不校验用户是否仍存在）、`api/auth.py:150-153`（`logout` 纯无状态，无黑名单）；
  grep `revoke|blacklist|token_version|jti` 在 `shared/auth.py`、`api/auth.py`、`db/user_store.py` **零命中**
- 复现：教师 token 签发 → 管理员 `DELETE /api/admin/users/{username}`（`admin_users.py:94`）删除该教师 →
  该 token 仍可访问所有 `get_current_user` 端点（含 `/api/teacher/*`），最长 7 天；降级 student 同理。
- 前端 token 存 `localStorage`（`src/stores/authStore.ts:38`）加剧该问题：无 XSS 时尚可，一旦有 XSS 即长期有效凭据。

---

### 🟡 中低（8 项）

#### 🟡-1 限流超限返回 **422** 而非 429，且无 `Retry-After`
- `api/auth.py:32-35` 抛 `ValidationError`；`shared/errors.py:39-41` 定义 `422`。
- 后果：客户端/网关/监控无法按标准区分「限流」与「参数错」；中间件层却是 429（`middleware.py:257-266`），
  两套语义不一致。已在 `test_rate_limit_boundary.py` 用「异常类型」而非状态码断言，故测试不会阻止该漂移。

#### 🟡-2 `shared/limits.py` 不是**全局**唯一真值源
- 认证/LLM 的阈值确实全部具名化（`api/auth.py`、`shared/ratelimit.py` 零字面量）；
  但通用限流中间件自持一套：`middleware.py:78-90`（`RATE_LIMIT_WINDOW=60`、`RATE_LIMIT_PER_MIN=30`、`RATE_GROUPS`）
  未进 `limits.py`。口径「唯一真值源」只在子域成立。

#### 🟡-3 本机回退的**桶淘汰**可被主动利用绕过账户级限流（已实证）
- 位置：`db/redis_client.py:171-181`（`len(buckets)>=4096` 触发淘汰）、`:184-213`（按「最久未活跃」成批删除）
- 复现（实测输出）：
  ```
  目标桶已满，第21次 = False
  灌 5000 个异构 key 后，目标桶第22次 = True
  ```
  `login:user:<username>` 的 key 主体**完全由攻击者控制**（用户名可任意填），
  用 5000 个不同用户名把目标桶挤出去 → 账户级「5 次/15 分钟」重置。
- 兜底仍在：IP 级 10 次/分钟（`limits.py:60`）不受影响，故危害为「账户锁定可被反复刷新」，
  而非无限撞库；但试点包真实开启该路径（`deploy/career-pilot/backend/.env:13` `RATE_LIMIT_ALLOW_LOCAL_FALLBACK=1`），
  不能视为纯理论。

#### 🟡-4 开关值是**导入期快照**，运行期改环境变量不生效
- `db/redis_client.py:20`（`REDIS_STRICT`）、`:33-35`（`ALLOW_LOCAL_FALLBACK`）在模块导入时求值；
  而 `.env` 由 `app/env.py:40-41` 的 `bootstrap()` 在 `main.py:26` 加载——顺序上先于 `db` 导入，**当前正确**。
  风险在于：任何在 `bootstrap()` 之前 import `db.redis_client` 的入口（测试夹具、脚本、`start_bg.py` 类工具）
  会永久固化「development + 未开 fallback」，此后即使设 `NETLEARN_ENV=production` 也**不会** fail-closed。
  属脆弱点而非现网缺陷（当前 `main.py` 顺序正确）。

#### 🟡-5 生产 `/showcase` 放宽 CSP 的作用范围大于「静态原型」
- 位置：`app/middleware.py:194-195`——`request.url.path.startswith("/showcase")` 即降级为 `CSP_DEV`（含 `script-src 'unsafe-inline'`）
- 实测：生产环境 `GET /showcase/demo` 返回 `script-src 'self' 'unsafe-inline'`
- 范围问题：`/showcase` 既是静态原型目录（`app/static_sites.py:52-53`），**也是 SPA fallback 的入口**
  （`:68-69` 对非 `/api/` 的 404 返回 `index.html`，`src/router/index.ts:215` 还有 `/showcase` 路由）。
  于是 `/showcase/<任意深链>` 都会以「允许内联脚本」的 CSP 加载**整个 SPA**。
  当前仓库内无 HTML 注入 sink（见 ③），故不是可直接利用 XSS，但**把一个本应只属于评测原型的豁免，
  扩大到了主应用的一份平行入口**——建议收窄为精确文件名/前缀。

#### 🟡-6 CSP 缺 `object-src` / `base-uri`；`style-src` 保留 `unsafe-inline`
- `app/middleware.py:40-49,50-59` 两套策略均无 `object-src 'none'`、`base-uri 'none'`（`<base>` 劫持与
  插件内容未封堵）；`style-src 'unsafe-inline'` 为 Vue scoped style 妥协（注释已说明，属可接受风险）。
  生产 `script-src 'self'` 已封住 `unsafe-inline`/`unsafe-eval`，主风险面是闭合的。

#### 🟡-7 `VideoPlayer` 的 `iframe srcdoc` 用了**互相抵消**的 sandbox 组合
- 位置：`src/components/VideoPlayer.vue:62`（`:srcdoc="getIframeHtml()"`，内容来自
  `POST /api/multimodal/generate-teaching-video` 的 `res.html`）、`:69`（`sandbox="allow-scripts allow-same-origin"`）
- `allow-scripts` + `allow-same-origin` 是已知无效组合（同源 iframe 可自行摘除沙箱并访问父文档/localStorage）。
  当前缓解：后端模板对 topic/旁白做了 `_escape_svg`（`services/video_generator.py:414-416`），
  且生产 CSP 会拦住 srcdoc 里的内联 `<script>`（也导致该播放器在生产**功能失效**）。
  即「今天没洞」，但防线全靠上游转义与 CSP，沙箱这层等于没有。
- 相关的功能副作用（非安全）：`src/utils/markdown.ts:150-153` 的 `ALLOWED_ATTR` 白名单不含 `href`/`src`/`style`，
  Markdown 链接与图片实际会被剥掉。

#### 🟡-8 非安全关键依赖失败**静默降级**，但启动日志宣称「所有组件就绪」
- `app/lifespan.py:79-89`（PG 超时/异常→warning，`_enabled=False`）、`:92-105`（Redis 同上）、
  `:147-155`（迁移失败仅 warning，生产也放行）、`:158-173`（种子失败 warning）、`:196-217`（LLM 缺失 warning）
- 随后 `:381-384` 打印「应用启动完成（**所有组件就绪**）」——与实际状态不符。
  安全上可接受（鉴权/口令门禁是真的 fail-fast；Redis 缺失时限流转 fail-closed 或单进程强制限额），
  但「就绪」这一措辞会让运维误判，属可观测性缺陷。

---

## ③ 误报对照 / 已确认无问题的项

| 历史结论 | 独立复核 |
|---|---|
| `mock_auth` 只存在于测试 | **成立**。`tests/conftest.py:206` 定义；运行时零命中；`dependency_overrides` 仅出现在 `tests/` 与 `scripts/live_smoke_test.py`、`scripts/_diag_evidence.py` 等**独立诊断脚本**（不随服务启动加载） |
| 鉴权无「匿名兜底」 | **成立**。grep `Optional[dict] Depends` / `user: dict = None` / `get_optional_user` 在 `api/`+`shared/` 零命中；`verify_token` 的 `except Exception`（`shared/auth.py:108`）**唯一出口是 raise 401**，非 `pass` |
| `ensure_admin` 无默认口令 | **成立**（`db/user_store.py:269-276` 无默认值；`app/lifespan.py:112-118` 生产拒绝）。仅轮换语义有坑（🟠-4） |
| PBKDF2 60 万 + 防时序比较 | **成立**（`db/user_store.py:194,217`）。补充：`:246-247` 的 dummy hash 用同一 600k 迭代，时序对齐是真实实现而非注释 |
| `save_config` 剥离密钥 | **对 dict 层级成立**；落盘实测 `py-server/config.json` 中 api_key/app_id 等字段全空。**list 内 dict 不剥离**（`config.py:425-426` 落到 `safe[k]=v`），但当前 schema 无 list-of-dict，且唯一调用方 `api/config_routes.py:97` 只写具名标量 → 无现实可利用面 |
| 密钥残留 0 命中 | **对已跟踪文件成立**：`git grep` 无 `sk-*`/明文 `AUTH_SECRET=`/`ADMIN_PASSWORD=` 赋值；`py-server/.env`、`deploy/career-pilot/backend/.env`（含真实 ZHIPU/XF 密钥）均**未入库**（`.gitignore:34-35,309`，`git log --all -- <该路径>` 空）；无 zip/tar 入库。**但**：现有扫描器 `scripts/_scan_secrets.py:18-23` 只有 4 条**讯飞专用**正则，对 `sk-`/GLM/Qwen 密钥形状无覆盖 → 该「0 命中」不能外推到全部密钥类型 |
| 限流 20 次/小时 @ `api/auth.py` | **数字正确但对象要读清**：20/小时/IP 是**注册**（`api/auth.py:84-96`）；登录是 10/分钟/IP + 5 次/15 分钟/用户名（`:108-121`）。边界 N+1 实证拒绝 |
| CSP 由 `middleware.py` 下发 | **成立**，且实测确认生产/开发两套差异与 HSTS 只在生产 |
| 前端路由 meta 即是越权防线 | **不成立（也不该成立）**：`src/router/index.ts:315-347` 的角色判定读 `localStorage` 的 `mangdehenzhi_user`，纯客户端可改；真正的门禁在 FastAPI 依赖上。第 9 项的问题全部出在**后端**（🟠-2/🟠-3/🟠-5） |
| 端点鉴权覆盖率 95%（248/261） | **口径可复现但含义需校准**：我的独立 AST 扫描 259 个端点中 11 个无鉴权依赖，其中 `register`/`login` 为设计公开，其余 9 个是只读数据面（`benchmark` 结果、`experiments` 产物、`cn-distinction` 题库、`literacy/questions`）。`_safe_name`（`api/experiments.py:79-88`）正则+`..` 双拦，无路径穿越 |

**待补证据（子项 UNVERIFIED，不写进结论表）**

1. **构建产物 CSP 是否与源码一致**：未构建 `dist/`，无法验证打包后 `index.html` 是否含内联脚本
   （若有，生产 `script-src 'self'` 会导致白屏，属功能而非安全问题）。
2. **第三方净化库漏洞面**：只读到 `dompurify ^3.4.11` / `marked ^15.0.12` / `katex ^0.16.10`（`package.json:36`），
   未跑 `npm audit` / `pip-audit` 比对 CVE，故「无已知 XSS gadget」一句**不下结论**。
3. **真实沙箱运行时姿态**：`deploy/career-pilot/backend/.env` 显示 `NETLEARN_ENV=production` +
   `RATE_LIMIT_ALLOW_LOCAL_FALLBACK=1`，但该 `.env` 是否被沙箱实际加载（打包脚本
   `scripts/build_career_pilot_package.py:313-315` 会对 `.env` 单独处理）未在运行时验证。

---

## ④ 建议的最小修复（按性价比排序）

1. **拒绝占位/低熵密钥**（🟠-1，10 行内）
   `shared/auth.py:57-61` 在长度检查后追加：命中 `your_|change[_-]?me|replace|example|secret_here` 等模式即
   `raise RuntimeError`；并对 `ADMIN_PASSWORD`（`app/lifespan.py:127`）做同一判定。
   最小可行版：黑名单匹配 + 要求至少 3 类字符。
2. **给演示放宽加生产硬闸**（🟠-2，3 行）
   `shared/auth.py:166` 改为 `... and os.environ.get("NETLEARN_ENV","development").lower() not in ("production","prod")`；
   并在 `app/lifespan.py` 开头加一条 `if is_production() and _is_demo_teacher_open(): raise RuntimeError(...)`（启动即拒）。
3. **收回学生写共享知识库的权限**（🟠-3，1 行）
   `api/knowledge_base.py:80` 的 `Depends(get_current_user)` → `Depends(require_teacher_or_demo_open)`
   （与 `teacher.py:317` 的教师导入口径一致）；若要保留学生上传，改为「仅写入个人工作区」而非共享库。
4. **`ensure_admin` 支持口令轮换**（🟠-4，6 行）
   `db/user_store.py:273-274`：用户已存在时，若 `ADMIN_PASSWORD` 与库内校验不一致则调用既有
   `:350` 的 `UPDATE users SET password_hash=?, salt=?` 路径更新；或显式新增 `ADMIN_PASSWORD_ROTATE=1` 开关，避免每次启动都重算 60 万次 PBKDF2。
5. **缓解 token 不可吊销**（🟠-5，最小版 8 行）
   `get_current_user` 增加一次 `get_user_by_id` 存在性校验（失败→401），即可让「删号」立即生效；
   角色变更需彻底解决则引入 `users.token_version` 并写入 payload / 比对（中等改动，可排期）。
6. **限流状态码与 key 加固**（🟡-1/🟡-3）
   超限改抛 `HTTPException(429, headers={"Retry-After": ...})`；
   `redis_client._local_rate_limit` 的 key 增加「不可被淘汰」保护：保留按 `(key, 首次时间)` 的独立计数，
   或把 `login:user:*` 的桶单独分区（不与 `4096` 全局池共享淘汰预算）。
7. **收窄 `/showcase` 的 CSP 豁免**（🟡-5，1 行）
   `app/middleware.py:194` 用精确前缀/后缀白名单（如 `path.startswith("/showcase/") and path.endswith(".html")`），
   避免 SPA fallback（`index.html`）也拿到 `unsafe-inline`。
8. **补齐 CSP 硬指令**（🟡-6，1 行/套）
   两套策略各追加 `object-src 'none'; base-uri 'none';`。
9. **修正启动日志口径**（🟡-8，2 行）
   `app/lifespan.py:381-384` 改为按实际 `pg_client.is_enabled()`/`redis_client._enabled` 输出
   「已就绪组件 / 降级组件」清单，不再无条件宣称「所有组件就绪」。
10. **给 `.gitignore` 的 `deploy/career-pilot/backend/` 加显式 `.env` 断言**（🟡-4 相关，0 行代码）
    已在忽略列表（`.gitignore:309`），建议在 `scripts/pre_deploy_check.py` 增加「打包件不得入库」的 CI 断言，
    防止未来 `git add -f` 把整包真实密钥推上去。

---

## 附：可复现命令（全部只读）

```bash
# 1) 端点鉴权覆盖面（自写 AST 扫描，见 %TEMP%/secscan_routes.py）
py-server/.venv/Scripts/python.exe "$TEMP/secscan_routes.py" py-server
#   → 总计端点 259，无鉴权依赖 11（register/login + 9 只读数据面）

# 2) 限流边界与 fail-closed（自写，见 %TEMP%/secproof.py）
#   → 允许次数 = 20 | 第21次 = False
#   → production fail-closed = False（拒绝）
#   → 灌 5000 个异构 key 后，目标桶第22次 = True（绕过成立）

# 3) 鉴权三态
#   → <none> 401 / Bearer garbage 401 / 学生打 admin 403

# 4) 安全响应头（生产/开发 + /showcase）
#   → 生产 script-src 'self'；/showcase 生产 script-src 'self' 'unsafe-inline'

# 5) 前端注入门禁
py-server/.venv/Scripts/python.exe scripts/xss_scan.py
#   → 扫描文件 130 个；[PASS] 未发现未净化的 HTML 注入点

# 6) 单文件测试（未跑全量）
py-server/.venv/Scripts/python.exe -m pytest tests/test_rate_limit_boundary.py tests/test_ratelimit_circuit.py tests/test_app_lifespan_guards.py -q --no-cov
#   → 69 passed
py-server/.venv/Scripts/python.exe -m pytest tests/test_auth_token_and_roles.py tests/test_teacher_role.py -q --no-cov
#   → 31 passed, 12 skipped（teacher_role 设计为 --noconftest 隔离运行；隔离跑 → 12 passed）
```
