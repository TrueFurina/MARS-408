# ============================================================
# shared/limits.py — 边界常量命名原语（REA #30）
#
# 为什么集中：限流阈值此前以字面量散落在 api/auth.py（20/3600、10/60、5/900）
# 与 shared/ratelimit.py（20、500、60、86400）里。字面量的问题不是"不好看"，
# 是**测试无法确认自己测的是生产值**：测试里写 21，实现改成 30 时测试照样绿，
# 于是"边界回归"退化成"边界复述"。这里把数字与单位、依据、环境变量名绑成
# 一个具名原语，实现与测试都只引用名字 ⇒ 改一处，两侧同时改。
#
# 命名规则（强制）：
#   <对象>_PER_<时间窗>_PER_<主体>，例如 REGISTER_PER_HOUR_PER_IP
#   —— 单位写进名字，"20 是每小时还是每分钟"不再靠读调用点猜。
#
# 环境变量覆盖保持原名字（LLM_QUOTA_PER_MINUTE / LLM_QUOTA_PER_DAY），
# 因为部署脚本与文档已按这两个名字写；新增项用 RL_ 前缀。
# ============================================================

from __future__ import annotations

import os

__all__ = [
    "REGISTER_PER_HOUR_PER_IP",
    "LOGIN_PER_MINUTE_PER_IP",
    "LOGIN_PER_15MIN_PER_USER",
    "LLM_PER_MINUTE",
    "LLM_PER_DAY",
    "WINDOW_REGISTER_SECONDS",
    "WINDOW_LOGIN_IP_SECONDS",
    "WINDOW_LOGIN_USER_SECONDS",
    "WINDOW_LLM_MINUTE_SECONDS",
    "WINDOW_LLM_DAY_SECONDS",
]


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    """读环境变量为整数；非法值回退默认值而不是让进程起不来。

    边界常量被写坏（空串 / 拼错 / 0 / 负数）时必须**保守回退**：
    0 或负数会让 check_rate_limit 永远失败（等于全员 429），
    这是比"配置没生效"更糟的故障模式。
    """
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return value if value >= minimum else default


# ── 认证面（api/auth.py）──
# 注册：20 次/小时/IP。阈值来历见 api/auth.py register 的 docstring：
# 原 3 次/小时实测卡死一个班同时注册（同出口 IP），20 次容纳一个班 + 重试余量。
REGISTER_PER_HOUR_PER_IP = _env_int("RL_REGISTER_PER_HOUR_IP", 20)
WINDOW_REGISTER_SECONDS = 3600

# 登录 IP 面：10 次/分钟/IP（挡住撞库扫描；正常学生不会一分钟登 10 次）
LOGIN_PER_MINUTE_PER_IP = _env_int("RL_LOGIN_PER_MINUTE_IP", 10)
WINDOW_LOGIN_IP_SECONDS = 60

# 登录账户面：5 次/15 分钟/用户名（跨 IP 同样生效，防"换 IP 继续撞同一账户"）
LOGIN_PER_15MIN_PER_USER = _env_int("RL_LOGIN_PER_15MIN_USER", 5)
WINDOW_LOGIN_USER_SECONDS = 900

# ── LLM 配额面（shared/ratelimit.py）──
LLM_PER_MINUTE = _env_int("LLM_QUOTA_PER_MINUTE", 20)
LLM_PER_DAY = _env_int("LLM_QUOTA_PER_DAY", 500)
WINDOW_LLM_MINUTE_SECONDS = 60
WINDOW_LLM_DAY_SECONDS = 86400
