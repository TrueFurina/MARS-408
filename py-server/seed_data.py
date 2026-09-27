# ============================================================
# seed_data.py — 兼容入口（M-4 ③：四科数据已迁入 seed/ 包）
#
# 本文件不再承载任何数据，只做一件事：把 seed 包的公共表面原样再导出，
# 使既有的 20 处 `import seed_data` / `from seed_data import ...` 零改动。
#
# 历史：原名「种子数据 —— 从 main.py 提取」，1,527 行把计算机网络 / 数据结构 /
# 计算机组成原理 / 操作系统四科语料、知识图谱、学习路径 DAG 与派生组装逻辑
# 混装在一起，是架构评审 M-4 指认的上帝文件之一。现按科目拆到 seed/ 包。
#
# 为什么保留这层而不是一次性改掉所有 import：
#   消费方分布在 api/、engines/、app/、experiments/、根级脚本与 tests/ 六类位置，
#   一次性改完会把「按科目拆域」这个纯机械改动与大面积调用点修改纠缠；
#   委托层先把「一个文件装四科」解决，后续可逐个把 `import seed_data`
#   平滑等价替换为 `from seed import ...`（随时可做，不动任何行为）。
#
# 为什么用 __getattr__ 而不是 `from seed import *`：
#   同 services/user_service 的教训 —— 静态星号导入会绑定一份**对象快照**，
#   此后对 seed 包内符号的 monkeypatch / 热替换全部静默失效。保持动态穿透，
#   seed_data 与 seed 始终是同一批对象。
#
# ⚠️ seed/__init__.py 的求值顺序敏感（含同名定义的版本覆盖、以及一段必须留在
#    __init__ 的 `.extend(...)` 执行语句），改动前先读它。
# ============================================================

import seed as _seed

__all__ = list(_seed.__all__)


def __getattr__(name: str):
    if name in _seed.__all__:
        return getattr(_seed, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))
