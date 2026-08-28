# 评测环境说明

> ⚠️ **评委评测请优先阅读本文件。**
> 本文件说明 NetLearn 系统的评测/CI 运行环境要求与注意事项。

---

## 一、为什么需要特定的评测环境

NetLearn 后端依赖 `torch`（NeuralMixer 神经网络推理）和 `numpy`（向量计算）。
在 **Windows 原生环境**下，`torch` 和 `numpy` 的某些版本组合可能触发 **SIGSEGV（段错误）**，
导致进程崩溃（尤其在 `sentence-transformers` 加载 E5 模型或 `torch.matmul` 矩阵运算时）。

`pyproject.toml` 中已定义 `segv_env` pytest marker，用于标记可能触发 SIGSEGV 的测试。

---

## 二、推荐评测环境

### 方式 1：Linux 容器（推荐）

```bash
# 使用 docker-compose 启动完整环境
docker compose up -d

# 进入容器运行测试
docker compose exec py-server pytest tests/ -m "not segv_env" -v

# 或运行全部测试（含 segv_env，需 Linux 环境）
docker compose exec py-server pytest tests/ -v
```

`docker-compose.yml` 已配置 Python 3.12 + Linux 环境，预装 torch/numpy 的 Linux 兼容版本。

### 方式 2：预编译 wheel（无 Docker）

若无法使用 Docker，请在 Linux/macOS 环境中安装预编译 wheel：

```bash
# 创建虚拟环境
python3.12 -m venv .venv
source .venv/bin/activate

# 安装依赖（pyproject.toml 已声明 torch/numpy 版本约束）
pip install -e ".[test]"

# 运行测试（跳过 segv_env 标记的测试）
pytest tests/ -m "not segv_env" -v
```

### 方式 3：Windows 开发环境（有限支持）

Windows 原生环境可用于开发调试，但以下功能可能不稳定：

| 功能 | 风险 | 建议 |
|------|------|------|
| NeuralMixer 推理 | SIGSEGV | 使用 CPU-only torch 或 Linux 容器 |
| E5 嵌入模型加载 | 内存不足/SIGSEGV | 确保 ≥8GB 可用内存 |
| pytest segv_env 标记测试 | 段错误 | `-m "not segv_env"` 跳过 |

---

## 三、Benchmark 运行

Benchmark 脚本（`py-server/experiments/benchmark.py`）依赖 torch + sklearn + matplotlib：

```bash
cd py-server
python experiments/benchmark.py
```

**环境要求**：
- torch ≥ 2.7（CPU 版即可）
- scikit-learn ≥ 1.3（Cohen's Kappa 计算）
- matplotlib ≥ 3.11（图表生成）
- 向量库数据：`py-server/vectordb_data/`（需预先构建，2083 chunks）

**预期产出**：
- `experiments/results/benchmark_<date>.json`
- `experiments/results/fig_cost.png`
- `experiments/results/fig_mixer.png`

---

## 四、关键环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NETLEARN_ENV` | `development` | `production` 时强制要求 AUTH_SECRET/ADMIN_PASSWORD |
| `HF_HUB_OFFLINE` | `1` | 离线模式，避免 HuggingFace 网络访问 |
| `TRANSFORMERS_OFFLINE` | `1` | 同上 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

---

## 五、pytest marker 说明

| marker | 含义 | Windows 跳过 |
|--------|------|:----------:|
| `unit` | 纯函数单元测试（无 LLM/无网络/无 torch） | ❌ 可运行 |
| `segv_env` | 依赖 torch/numpy，可能触发 SIGSEGV | ✅ 建议跳过 |
| `integration` | 集成测试（需数据库/LLM） | 视环境而定 |

运行命令：
```bash
# 仅运行纯单元测试（任意环境安全）
pytest tests/ -m "unit" -v

# 跳过可能 SIGSEGV 的测试
pytest tests/ -m "not segv_env" -v

# 运行全部测试（Linux 容器推荐）
pytest tests/ -v
```
