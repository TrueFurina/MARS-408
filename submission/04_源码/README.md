# 源码包

按 `../00_提交清单.md` §三 的打包说明，将项目源码打包为 `MARS-408_source.zip` 放入本目录。

## 关键提醒
- **排除** node_modules / .venv / dist / __pycache__ / .fixvenv / .fixcn / .lxmlfix / .git / *.log
- **包含** py-server(含 models/neural_mixer_trained.pt) / src / public / Dockerfile / docker-compose.yml / package.json / vite.config.ts
- 评委需在常规环境可运行：`py-server` 起 uvicorn(8002) + 根目录 `npm run dev`
- 密钥脱敏：`config.json` 密钥字段已清空，运行时从 `.env` 加载；提交时附 `.env.example`（不放真实 key）
