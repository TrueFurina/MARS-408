---
name: debug-playbook
description: study-help-pro 排障流程——后端启动失败、Milvus/E5 未就绪、分支同步冲突；触发词：排障、报错、启动失败、debug
---
# 排障手册 — study-help-pro

## 1. 后端起不来（:8002）
1. 确认 venv：`cd py-server && .venv/Scripts/activate`
2. 确认 `pip install -e .` 已装
3. 看报错是 FastAPI 兼容（已知坑，见 test-gate）还是真依赖缺失

## 2. 向量检索不可用
- E5 模型是会话级资产：`python scripts/fetch_e5_model.py` 从 hf-mirror 恢复
- 恢复后自动启用，无需改配置

## 3. Milvus/Redis 连接失败
- 属重型依赖，先确认服务是否启动；本地调试优先走 SQLite 降级路径
- pytest 场景用 `-m "not requires_milvus"` 跳过

## 4. 分支同步冲突
- 只允许 main → career-literacy 单向；冲突时以 main 为准
- career_* 前缀文件若在 main 出现 = 反向漂移，需人工裁决删除

## 5. 竞赛口径数字对不上
- 以代码真值为准，禁止改代码迁就文档
- 用 `git log --grep=口径` 找历次对齐提交
