---
name: arch-rules
description: study-help-pro 架构红线——双分支单向同步、career_* 前缀零侵入、口径对齐代码真值；触发词：架构红线、分支规则、career_、口径
---
# 架构红线 — study-help-pro

## 双分支纪律（违者 = 分支漂移）
1. 同步方向唯一：`main → career-literacy`，禁止反向合并或 cherry-pick 408 特有代码
2. career-literacy 分支所有新增代码/文件必须 `career_*` 前缀，禁止修改 408 原有模块
3. 涉及竞赛口径的数字（排名、得分、规模）必须与代码真值一致——文档禁止自造数字，对齐不到代码的写"待验证"

## 数据与模型
- E5 模型文件不入库（.gitignore 已排除），禁止直接拷贝模型进仓库
- Milvus/Redis 连接配置不硬编码进代码

## 交付纪律
- submission 交付包是唯一口径源：改口径必须先改代码/数据，再同步文档
- 禁止在仓库根平铺新文件（参考根目录已有的分类：docs/ deliverables/ documents/ 等）
