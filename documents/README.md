# 可选数据目录（占位）

本目录用于存放**教材文件**（PDF / 笔记 / 课件等），供后端 `import_worker` 单写者扫描并建立教材检索索引。

- 本目录为**可选大体积数据**，不入库（被 `.gitignore` 排除），仅此 `README.md` 与 `.gitkeep` 占位文件随仓库跟踪。
- 放入真实数据后，容器启动时 preflight 会显示 `✅ 教材目录 documents：已就绪`；留空则教材检索 / 后台导入能力**优雅降级**，核心流程仍可运行。
- 放入数据后重启容器即可生效：`docker-compose restart app`。
