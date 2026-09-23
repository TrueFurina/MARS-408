# D14 依赖 uv.lock 冻结（P1 · 技术债 Priority=24）

**日期**：2026-09-23
**分支**：career-literacy
**类别**：🟠 依赖浮动 + 构建环境脆弱

---

## 一、问题（证据先行）

- `py-server/pyproject.toml` 的 `[project.dependencies]` 全部用 `>=` 声明（如 `fastapi>=0.136.3`、`pymilvus>=2.4.0,<3`），无锁文件 → 每次安装按当时最新浮动解析，**CI / 部署 / 队友环境可能拉到不同版本**，构建不可复现。
- `.venv` 为 C: 软链（E: 空间不足时的妥协），CI / 构建环境脆弱。
- 实测：`uv lock` 解析时把 `pymilvus` 从 `3.0.0` 收敛到 **`2.6.17`**（符合 `<3` 约束）——证实 `>=` 浮动下 `pip install` 可能错误装到 3.x（pymilvus 3.x 有破坏性 API 变更，属真实隐患）。

---

## 二、修复（行为零改动，仅冻结依赖 + 文档化）

### 1. 生成 `py-server/uv.lock`
- 环境 `uv 0.11.23` 可用，执行 `uv lock` → **Resolved 137 packages**，生成 633KB 锁文件。
- `uv lock --check` 验证：与 `pyproject.toml` 一致（`Resolved 137 packages in 1ms`），无过期。
- 锁文件已提交（未被 `.gitignore` 忽略）。

### 2. 文档注入 uv 锁定策略
- `INSTALL.md`：在「手动启动」后新增 💡 框，说明 `uv.lock` 已提交、推荐 `uv sync --frozen`（运行）/ `uv sync --frozen --extra test`（测试）精确还原依赖；无 uv 时退回 `pip install -e .`（浮动）。
- `py-server/README.md`：安装段加注 `# 推荐：用 uv 按 uv.lock 精确锁定` + `uv sync --frozen`。

> 说明：未实际执行 `uv sync`（避免在现有 pip 管理的 `.venv` 上触发整体重装、引入 numpy/torch 版本波动风险）。仅生成并提交锁文件 + 文档化策略；生产 / CI 按 `uv sync --frozen` 落地。

---

## 三、使用约定（写入文档）

```bash
cd py-server
uv sync --frozen            # 按 uv.lock 精确还原运行依赖（不浮动）
uv sync --frozen --extra test  # 额外装 test extra（pytest 等），用于跑测试
uv run python main.py       # 在 uv 管理的环境中启动后端
```

---

## 四、影响与边界

- **不破坏现有 pip 工作流**：`.venv`（pip 装）继续可用；uv 为可选的更严格锁定通道。
- **跨平台**：`uv.lock` 含多平台 wheel 约束，CI（Linux）与本机（Windows）均能按锁复现。
- **版本升级**：后续升级依赖须先 `uv lock` 重新解析、提交新 `uv.lock`，保持「锁文件即真相」。
- 边界：`.venv` 软链脆弱属部署层问题，D14 仅以 uv 锁定缓解构建漂移，未改 venv 物理位置。

**结论**：D14 收口。依赖现已冻结（137 包精确版本），对外构建可复现，pymilvus 等约束型依赖不再因 `>=` 浮动越界。
