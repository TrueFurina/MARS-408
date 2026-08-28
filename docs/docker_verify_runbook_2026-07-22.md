# Docker 一键可跑验证 Runbook · MARS-408（软件杯 A3）

> 日期：2026-07-22
> 关联：`docs/optimization_backlog_2026-07-22.md` T-OPT-08、`EVALUATION_ENV.md`、`docker-compose.yml`、`Dockerfile`
> ⚠️ 本机（Windows）无 Docker 守护进程且 torch/numpy 在模型/向量路径会 SIGSEGV，**以下步骤必须在 Linux 容器 / CI 执行**。本文件为可复现验证脚本 + 静态校验结论。

---

## 一、静态校验结论（本机已确认）

| 校验项 | 结果 |
|--------|------|
| `py-server/uv.lock` 存在 | ✅ 存在（`uv sync --frozen` 可解析） |
| `docker-entrypoint.sh` 存在且可执行 | ✅ 存在（`chmod +x` 已在 Dockerfile 执行） |
| `package.json` 含 `build-only` 脚本 | ✅ `"build-only": "vite build"` |
| 单进程约束 | ✅ ENTRYPOINT 用 `uv run python -m uvicorn main:app` 未加 `--workers N`（ADR-007 硬约束） |
| 非 root | ✅ gosu 切换 mars408 用户运行 |
| 开发模式自动播种 | ✅ `NETLEARN_ENV=development`（默认）自动生成密钥 + 播种 `demo/demo123456` |

> 结论：构建链路完整、可验证可跑。真跑只剩「起容器 + 探活 + 一次真实对话」三步。

---

## 二、真跑验证步骤（Linux / CI）

```bash
# 1) 起服务（development 模式，开箱即用）
cd <项目根>
export NETLEARN_ENV=development
docker compose up -d --build

# 2) 等健康探活（compose healthcheck start_period=60s；镜像内 HEALTHCHECK 间隔30s）
#    后端启动约 30s（加载 2083 条向量库 + E5 嵌入），务必给足时间
sleep 90
curl -f http://localhost:8002/api/status && echo "STATUS_OK"

# 3) 用预置 demo 账号完成一次真实多 Agent 资源生成
curl -X POST http://localhost:8002/api/agents/generate-resource \
  -H "Content-Type: application/json" \
  -d '{"topic":"TCP三次握手","difficulty":"medium"}' \
  | python -m json.tool
# 断言：HTTP 200，且 teacher_doc / quiz / media_plan 非空，status="ok"
```

### 验证记录模板（评委/交付留存）

| 项 | 观测 |
|----|------|
| `docker compose up -d` 退出码 | 0 |
| `/api/status` HTTP 码 | 200 |
| generate-resource HTTP 码 | 200 |
| teacher_doc 长度 | ≥ 50 字符 |
| quiz 长度 | ≥ 20 字符 |
| media_plan 长度 | ≥ 20 字符 |
| status 字段 | "ok" |
| 容器日志有无异常栈 | 无 |

---

## 三、已知约束（务必写入交付说明）

1. **Windows 不能跑**：原生 torch/numpy 在「实际调用模型/向量路径」会 SIGSEGV（环境级，非代码问题）。权威验证只在 Linux 容器。
2. **单进程**：`uvicorn --workers 1`（多进程会触发多写者冲突，ADR-007）。勿改。
3. **讯飞密钥**：development 模式可不设 XF_* 环境变量（降级为无讯飞能力的演示）；要完整 10 项能力，需在 `.env` 或 `docker compose` environment 注入 XF_APP_ID/KEY/SECRET/PASSWORD + XF_SEARCH_PASSWORD（万搜专属 PAT）。
4. **LLM 通道**：默认 `LLM_PROVIDER=auto` → 讯飞 X2 主、DeepSeek 兜底；需 `DEEPSEEK_API_KEY`（development 模式若都不设，对话类端点会返回 4xx/降级，但资源生成流水线仍可演示结构化骨架）。

---

## 四、故障排查

- 探活一直 503：等满 90s 再看；或 `docker compose logs app` 查导入/向量库加载卡点。
- `/api/status` 200 但 generate-resource 空：检查 `DEEPSEEK_API_KEY` 是否注入（参见 T-OPT-01：此时 status 应为 `"error"` 而非空 `ok`，日志含 `Agent[teacher] LLM 调用失败`）。
- 构建失败：确认 `uv.lock` 与 `pyproject.toml` 版本一致；`melotts` 安装耗时较长，属正常。
