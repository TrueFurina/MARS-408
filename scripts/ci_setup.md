# CI 回归工作流说明（P0-2）

> 实施侧：impl-ci ｜ 关联任务 #3

## 一、提供的工作流
- `.github/workflows/ci.yml`：综合安全门禁 —— G1–G12 静态断言 + gitleaks 全量历史扫描 + 前端 vue-tsc/vite 构建 + 后端 pytest 安全集（`-m "not system and not requires_milvus"`）+ pip-audit CVE 扫描 + docker 构建。任一门禁失败即阻断 PR 合并。
- `.github/workflows/test.yml`：纯 pytest（`uv sync && uv run pytest -q`），干净 Linux 环境恢复 281/281 回归安全网。
- `.github/workflows/secret-scan.yml`：gitleaks-action 扫描（PR 注释报错）。

## 二、为何 Linux 能绕过 SIGSEGV
pytest 在 Windows 原生 torch/numpy 上触发 SIGSEGV(139)，属**环境级**问题（与讯飞纯 Python 代码无关）；干净 Linux（ubuntu-latest）此前 281/281 全绿，CI 用 Linux 即恢复回归网。后端测试用 `-m "not system and not requires_milvus"` 进一步避开模型/向量重路径，保证核心导入与单元可绿。

## 三、本地验证子集
```bash
cd py-server
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
pytest -m "not system and not requires_milvus" -q   # 轻量集，避免 SIGSEGV
```

## 四、触发与门禁
- `push` / `pull_request` 自动触发；任一门禁失败阻断合并。
- 建议：将 `ci.yml` + `secret-scan.yml` + `test.yml` 设为分支保护必过检查。
