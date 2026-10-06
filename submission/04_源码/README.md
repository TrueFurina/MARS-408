# 源码包

本目录交付**唯一正式源码包**：

| 文件 | 状态 | 实测 |
|------|------|------|
| `芒得很职_source_国创赛-2026-10-06.zip` | ✅ 就绪 | 16.1 MB / **1246 文件** / CRC 校验通过 |

> 口径日期：2026-10-06。产物由 `scripts/build_portable.py` 生成，
> 原始输出在 `build/mangdehenzhi-submit.zip`（`build/` 不入库，交付时以本目录副本为准）。

---

## 一、包内容（实测，非估算）

| 部分 | 文件数 | 说明 |
|------|--------|------|
| `py-server/` | 731 | 后端全部源码 + `openapi.json` + `.env.example` |
| `src/` | 138 | 前端源码（含 85 个 `.vue`、`src/data/` 数据模块） |
| `dist/` | 196 | 前端构建产物，不装依赖也能直接看界面 |
| `documents/` | 134 | 项目文档 |
| `public/` | 21 | 静态资源 |
| `design-system/` | 6 | 设计系统 |
| 根级契约文件 | 19 | `package.json` / `vite.config.ts` / `index.html` / `Dockerfile` / `start.*` 等 |

**可构建性实测**：解压后 `npx vite build` → `✓ 330 modules transformed` → `✓ built in 5.55s`。

## 二、排除项（打包后已逐项验证）

| 项 | 结果 |
|----|------|
| `.env`（真实凭证） |✅ **无**（精确匹配，不误伤 `.env.example`） |
| `node_modules/` | ✅ 无 |
| `vectordb_data/` | ✅ 无 |
| `build/` 自身 | ✅ 无（不自嵌套） |
| `submission/` | ✅ 无（交付包内不再嵌套提交包） |
| `.git/` | ✅ 无 |
| 运行期数据 `py-server/{data,sessions,plots}` | ✅ 无 |
| E5 模型权重（~420MB） | ✅ 无（运行时按需下载） |

**保留的权重**：`py-server/models/neural_mixer_trained.pt` —— 白名单唯一放行的训练权重。

## 三、密钥配置（重要）

-✅ **随包提供** `py-server/.env.example` —— 评委据此配置自己的 key。
- ❌ **不随包提供** `py-server/.env` —— 含真实凭证，任何情况下都不进交付包。
  缺 `.env` 属正常设计，不是打包遗漏。

## 四、评委运行路径

```bash
# 后端
cd py-server && pip install -r requirements.txt
cp .env.example .env        # 填入自己的 key
uvicorn main:app --port 8002

# 前端（依赖需legacy 模式安装，见下）
npm install --legacy-peer-deps
npm run dev                 # 或直接看包内 dist/
```

> `npm install --legacy-peer-deps`：`marked@^18` 与 `@sigordenjs/marked-katex-extension`
> 存在已知 peer 冲突，历来需此参数，非本次打包引入。

## 五、历史副本归档（不提交）

2026-09-15 的过期源码副本已移至 `submission/_archive_源码副本-2026-10-06/`
（509 文件，仅 mv 未删除）。**该副本不是交付面**，请勿与本目录 zip 并列引用。