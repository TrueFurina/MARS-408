# ============================================================
# app/ — 应用组装层（M-4「上帝文件集中」修复）
#
# main.py 原 882 行同时承担 lifespan 编排、中间件、异常处理、路由注册、
# 健康端点、SPA 挂载、env 引导 6 类职责，任何一处改动都要触碰应用入口。
# 本包按职责切分，main.py 只留「组装」这一件事。
#
# 分层约定（与 M-2 一致的方向）：
#   main.py  → app/*（组装与应用级横切）→ services/* → db/*
#
# 各模块职责：
#   env.py         进程级环境引导（HF 离线标记 / .env / 结构化日志），必须最先执行
#   lifespan.py    启动与关闭编排（数据层初始化、迁移、seed、worker、清理任务）
#   middleware.py  HTTP 中间件（CORS / GZip / 指标 / 安全头 / 体积限制 / 限流）
#   errors.py      统一异常处理注册
#   routers.py     业务路由注册
#   status.py      健康探针 / 赛题状态 / Prometheus 指标端点
#   static_sites.py plots-media 静态挂载与前端 SPA 挂载
#
# __init__ 刻意保持为空：不做任何副作用式导入，避免 import app 就触发
# 数据层连接（main.py 必须先跑完 env.bootstrap()）。
# ============================================================
