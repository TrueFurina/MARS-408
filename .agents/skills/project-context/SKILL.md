---
name: project-context
description: study-help-pro / MARS-408 项目上下文入口——双分支双身份、技术栈、启动命令；触发词：study-help-pro、MARS-408、芒得很职、项目上下文
---
# 项目上下文 — study-help-pro（MARS-408 / 芒得很职）

## 项目是什么（双分支 · 双身份，同一技术底座）
- `main` 分支 — **MARS-408**：中国软件杯 A3 赛题（科大讯飞），LangGraph 多智能体 + GOMARL 共识 + FrugalRAG 的 408 考研个性化学习平台
- `career-literacy` 分支 — **芒得很职**：三创赛作品，ECD 软素养对抗实训平台，新代码一律 `career_*` 前缀，零侵入 408
- 同步方向：`main → career-literacy` 单向，禁止反向

## 真值文件
- `CLAUDE.md`（根）：最完整的上下文与命令手册，先读它
- `DESIGN.md`：设计文档

## 技术栈
- 后端：FastAPI + LangGraph + PyTorch（py-server/）
- 前端：Vue 3 + TypeScript + Pinia
- 数据层：Milvus / SQLite / Redis
- E5 模型不入库：会话重置后 `python scripts/fetch_e5_model.py` 从 hf-mirror 恢复

## 关键命令
```bash
cd py-server
pip install -e . && python main.py    # 启动后端 :8002
# ⚠️ 全量 pytest 会因 FastAPI 版本兼容问题全部报错——必须分文件跑，见 test-gate skill
```
