# AGENTS.md — study-help-pro 项目事实源

> 权威真值详见 CLAUDE.md（双分支双身份说明）与 .agents/skills/ 四件套；本文件是每会话最小事实卡。

## 这是什么
双分支双身份共用底座：`main` 分支 = MARS-408（软件杯 A3，408 考研学习平台）；`career-literacy` 分支（当前）= 芒得很职（三创赛，软素养实训平台），新代码一律 `career_*` 前缀零侵入 408。

## 命令
- 后端: `cd py-server && pip install -e . && python main.py`（:8002）
- 测试: ⚠️ 全量 pytest 因 FastAPI 兼容问题全挂——必须分文件/分标记跑，见 `.agents/skills/test-gate/`
- E5 模型恢复: `python scripts/fetch_e5_model.py`（模型不入库，会话重置后执行）

## 禁区
- 分支同步方向唯一：main → career-literacy，禁止反向
- 竞赛口径数字必须对齐代码真值；E5 模型文件不入库

## 项目级 skill（触发时读）
- `.agents/skills/project-context/` `.agents/skills/arch-rules/` `.agents/skills/test-gate/` `.agents/skills/debug-playbook/`
- 计划外脑：`plans/current.md` + `plans/decisions.md`
