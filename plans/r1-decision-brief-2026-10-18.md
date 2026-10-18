# R1 部署可达性 · 决策简报（P0-B，待用户拍板）

> 目的：把 next-steps P0-B 的拍板所需事实集中到一页。裁决后落 `plans/decisions.md`。
> 前置事实：取证闸 `experiments/pilot_evidence_report.py` 契约完好（2026-10-18 复验：裁决 ❌ + 真实退出码 1）；
> 判据 = 单班 ≥3 非测试学生等四项，当前 max_bound_class=2（全部为开发/测试数据）。

## 现状事实（2026-10-18 实测）

| 通道 | 状态 | 证据 |
|---|---|---|
| 静态站 `https://mangdehenzhi.app.workbuddy.host/` | ✅ 已发布 | web-page + hash 路由；无后端，`/api/status` 404 属预期 |
| VPS staging（`deploy/career-pilot/` + `deploy/vps/*.service/nginx.conf`） | 🟡 在飞未验证 | service 指向 `/opt/career-pilot/backend`，nginx :80→8000；**VPS 主机地址/凭据在用户手中，本机无从探测** |
| 云 BaaS 托管后端 | 🔴 阻塞 | 服务端 401 `invalid_grant`，依赖平台方（P2-B） |
| 实验服务器 `172.16.222.99` | ✅ SSH 可达 | 但它是算力服务器，非对外服务位 |

## 三个选项

| 选项 | 内容 | 代价 | 风险 |
|---|---|---|---|
| **A. VPS 上线 career-pilot（推荐）** | 用户提供 VPS IP+SSH → 按 deploy/README 部署 → `curl /api/status` 200 验收 | S–M（半天内） | 需用户提供主机；公网暴露需确认 safety 已就位（JWT_SECRET 等 P0 遗留须先清） |
| B. 局域网演示版 | 对外材料写"演示版，未开放试用"，拼图③继续等 | S | 拼图③继续冻结 |
| C. 等云 BaaS 修复 | 平台方修复 401 后走托管 | 不可控 | 同 B |

## 拍板前必须先清的前置（若选 A）

1. 🔴 VPS 公网暴露前的安全检查清单（JWT_SECRET 非空 / admin 默认口令 / 速率限制开启）——记忆红线「14 个 P0 阻塞」中的安全项须逐条过；
2. `.env` 凭据只放 VPS 侧（chmod 600），不入库；
3. 验收命令：`curl -sI http://<vps>/api/status` 返回 200 且 `fallback_zero_docs` 如实上报。
