# ============================================================
# MARS-408 2.0 — 统一配置管理
# 从 config.json 加载，支持环境变量覆盖
# ============================================================

import os
import json
import logging
import threading
import copy
from pathlib import Path
from typing import Optional

# 配置文件路径
CONFIG_DIR = Path(__file__).parent
CONFIG_PATH = CONFIG_DIR / "config.json"
ENV_PATH = CONFIG_DIR / ".env"


def _load_dotenv():
    """加载 .env 文件到 os.environ（不依赖 python-dotenv）"""
    if not ENV_PATH.exists():
        return
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass

# 默认配置
DEFAULTS = {
    # ── LLM 三通道 ──
    "llm_provider": "auto",  # auto | deepseek | xfyun | qwen
    "deepseek": {
        "api_key": "",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "supports_tools": True,
        "supports_streaming": True,
    },
    "xfyun": {
        "app_id": "",
        "api_key": "",
        "api_secret": "",
        "api_password": "",  # HTTP API 认证：从控制台获取的 APIPassword
        "search_password": "",  # 搜索 API 密码
        "base_url": "https://spark-api-open.xf-yun.com/v1/chat/completions",
        "model": "4.0Ultra",
        "supports_tools": False,
        "supports_streaming": True,
        # ── 星火模型/端点可切换预设（P0-X2 清零支撑）──
        # 切换 X2 通道只需改 active_preset 一个字段，无需改动账号凭证，也无需改代码。
        # 诊断端点 GET /api/llm/x2-health 会逐一对这些预设探活，给出可用组合建议。
        "active_preset": "spark_x2",  # 防御默认：账号仅 X2 权限，4.0Ultra/max/pro128k 均返回 11200；运行时由 config.json 覆盖
        "presets": {
            "4.0Ultra": {"base_url": "https://spark-api-open.xf-yun.com/v1/chat/completions", "model": "4.0Ultra"},
            "spark_x2": {"base_url": "https://spark-api-open.xf-yun.com/x2/chat/completions", "model": "spark-x"},
            "max":      {"base_url": "https://spark-api-open.xf-yun.com/v1/chat/completions", "model": "generalv3.5"},
            "pro128k":  {"base_url": "https://spark-api-open.xf-yun.com/v1/chat/completions", "model": "pro-128k"},
        },
        # ── 多模态服务（赛题核心要求：多模态内容生成）──
        # TTI: 图片生成 console.xfyun.cn/services/tti
        # TTS: 语音合成 console.xfyun.cn/services/tts
        # 有key → 真实AI图片/语音；无key → SVG编程绘图 + 浏览器Web Speech API降级
        "tti_enabled": False,     # 开通TTI服务后改为True
        "tts_enabled": False,     # 开通TTS服务后改为True
    },
    "qwen": {
        "api_key": "",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "model": "qwen3.8-max",  # 优先级4a：Qwen3.8-Max 接入三通道（DashScope 兼容模式）
        "supports_tools": True,
        "supports_streaming": True,
    },
    "tavily": {
        "api_key": "",
    },

    # ── Milvus ──
    "milvus": {
        "host": "localhost",
        "port": 19530,
        "enabled": False,   # 开发环境默认关闭，需要时手动开启
        "uri": "",
    },

    # ── PostgreSQL ──
    "postgresql": {
        "host": "localhost",
        "port": 5432,
        "database": "netlearn",
        "user": "postgres",
        "password": "",
        "enabled": False,  # 开发期可为 False
    },

    # ── Redis ──
    "redis": {
        "host": "localhost",
        "port": 6379,
        "password": "",
        "enabled": False,
    },

    # ── Embedding ──
    "embedding": {
        "mode": "local",  # local | api
        "model": "intfloat/e5-base-v2",
        "dimension": 768,  # E5-base-v2 = 768
        "local_model_repo": str(CONFIG_DIR / "models" / "e5-base-v2"),
    },

    # ── FrugalRAG ──
    "frugal_rag": {
        "top_k": 5,
        "cosine_threshold": 0.65,
        "bm25_weight": 0.3,
        "vector_weight": 0.7,
        "max_rewrite_rounds": 2,
        # 真版增量配置
        "sft_enabled": True,            # LLM 查询优化(SFT风格，prompt 工程，非模型微调)
        "grpo_stop_enabled": True,      # 启发式停止决策(覆盖率阈值，非 GRPO/RL)
        "query_rewrite_enabled": True,  # 查询重写
        "lora_enabled": False,          # LoRA 少样本适配（需训练）
        "max_react_iters": 3,           # ReAct 最大迭代轮数
        "coverage_threshold_simple": 0.60,   # 简单问题覆盖率阈值
        "coverage_threshold_medium": 0.70,   # 中等问题覆盖率阈值
        "coverage_threshold_complex": 0.80,  # 复杂问题覆盖率阈值
    },

    # ── GOMARL ──
    "gomarl": {
        "quality_threshold": 7,          # 质量分阈值（1-10）
        "max_regenerate_rounds": 1,      # 最大生成轮数（含首次；1 = 仅 1 次生成，Critic 不重试，提速）
        "history_window": 5,             # 历史表现窗口
        "default_agent_weight": 1.0,     # 默认权重
        # 真版增量配置
        "use_neural_mixer": True,        # Neural GroupMixer 神经网络
        "use_evidence_conflict": True,   # 证据冲突消解
        "mixer_hidden_dim": 64,          # Mixer 隐藏层维度
        "sd_loss_weight": 0.1,           # sim/div 损失权重
        "lasso_alpha": 0.01,             # Lasso 正则化系数
        "group_change_threshold": 0.3,   # 动态组划分阈值
        "min_group_size": 2,             # 最小组大小
        "use_teaching_rules": True,      # 教学业务规则引擎（报告§3.3.3）
    },

    # ── 大创真版算法增量：feature flag（D1 默认 lite 保护软件杯稳定）──
# version: "lite"=规则版/原型（默认，软件杯稳定） | "real"=真版（灰度开启）
    # features.frugalrag / features.gomarl: 真版子能力开关（默认 False，按 flag 灰度）
    "algorithm": {
        "version": "lite",
        "features": {
            "frugalrag": False,
            "gomarl": False,
        },
    },

    # ── 知识库 ──
    "knowledge": {
        "courses": ["data_structures", "computer_network", "operating_system", "computer_organization"],
        "vector_dimension": 768,
        "chunk_size": 500,
        "chunk_overlap": 100,
    },

    # ── 语义检查 ──
    "semantic_check": {
        "enabled": True,
        "sample_rate": 0.10,
        "timeout_seconds": 5.0,
        "max_normal_length": 2000,
    },

    # ── 行为追踪 ──
    "behavior_tracking": {
        "enabled": True,
        "dwell_threshold_ms": 60000,
        "reattempt_threshold": 2,
        "hot_topic_topn": 5,
    },

    # ── 视频生成 ──
    "video_generation": {
        "enabled": True,
        "word_count": 120,
        "max_poll_seconds": 300,
    },

    # ── 服务器 ──
    "server": {
        "host": "0.0.0.0",
        "port": 8002,
    },

    # ── 导入队列 Worker（ADR-007：后端进程内导入队列 + 单写者）──
    # enabled=false 时关闭 Worker，/api/imports/* 返回 503，可回滚到遗留脚本导入
    "import_worker": {
        "enabled": True,
    },
}

_config_cache: Optional[dict] = None
_config_lock = threading.RLock()  # 保护 _config_cache 的读写


def load_config() -> dict:
    """加载配置，.env → config.json → 环境变量覆盖"""
    global _config_cache
    with _config_lock:
        if _config_cache is not None:
            return _config_cache

        # 先加载 .env 文件到 os.environ
        _load_dotenv()

        config = copy.deepcopy(DEFAULTS)

        # 从文件加载
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    file_config = json.load(f)
                # 先合并旧格式的映射（兼容旧 config.json）
                _deep_merge(config, _map_old_config(file_config))
                # 再合并文件中的新格式深度结构（直接覆盖 DEFAULTS）
                _deep_merge(config, file_config)
            except Exception:
                pass

        # 环境变量覆盖
        _apply_env_overrides(config)

        # 解析讯飞星火 active_preset → 生效 base_url/model（P0-X2 可切换配置结构）。
        # 仅覆盖端点字段，不动任何凭证；切换 X2 通道只需改 active_preset 一个字段。
        _apply_xfyun_preset(config)

        _config_cache = config
        return config


def get_llm_config(provider: Optional[str] = None) -> dict:
    """获取 LLM 配置（按优先级选择可用通道）"""
    config = load_config()
    target = provider or config.get("llm_provider", "auto")

    if target != "auto":
        return config.get(target, {})

    # auto: 按优先级尝试（优先级4a：接入 Qwen3.8-Max 第三通道）
    for name in ["xfyun", "deepseek", "qwen"]:
        provider_config = config.get(name, {})
        if provider_config.get("api_key") or provider_config.get("app_id"):
            return provider_config

    raise RuntimeError("无可用 LLM 通道：请配置至少一个 API Key")


def get_milvus_config() -> dict:
    return load_config().get("milvus", {})


def get_pg_config() -> dict:
    return load_config().get("postgresql", {})


def get_redis_config() -> dict:
    return load_config().get("redis", {})


def get_embedding_config() -> dict:
    return load_config().get("embedding", {})


def get_frugal_config() -> dict:
    return load_config().get("frugal_rag", {})


def get_gomarl_config() -> dict:
    return load_config().get("gomarl", {})


# ── 大创真版算法增量：feature flag 读取接口（T1）──
# 向后兼容：algorithm 段缺失（旧 config.json）时一律回退 "lite"，不抛异常。

def get_algorithm_config() -> dict:
    """返回 algorithm 段配置（缺失返回空 dict，不报错）。"""
    return load_config().get("algorithm", {})


def algorithm_version() -> str:
    """当前算法版本：'lite' | 'real'。

    默认 'lite'（保护软件杯稳定）；仅当显式配置为 'real' 时返回真版。
    旧代码读不到 algorithm 段 → 默认 'lite'。
    """
    version = get_algorithm_config().get("version")
    return "real" if version == "real" else "lite"


def features_frugalrag() -> bool:
    """真版 FrugalRAG 子能力开关（默认 False）。"""
    return bool(get_algorithm_config().get("features", {}).get("frugalrag", False))


def features_gomarl() -> bool:
    """真版 GOMARL 子能力开关（默认 False）。"""
    return bool(get_algorithm_config().get("features", {}).get("gomarl", False))


def reload_config():
    """强制重新加载配置"""
    global _config_cache
    with _config_lock:
        _config_cache = None
    return load_config()


CONFIG_FILE = str(CONFIG_PATH)


# 会写入密钥的配置段 — save_config 会剥离这些字段，
# 密钥始终只从 .env / 环境变量加载，绝不落盘到 config.json
_SECRET_SECTIONS = {"deepseek", "xfyun", "qwen", "tavily"}
_SECRET_FIELDS = {"api_key", "app_id", "api_secret", "api_password", "search_password", "password"}

# ── 安全说明（F-001：.env 明文密钥防护）──
# - 所有真实密钥只从 .env / 环境变量加载（见 _load_dotenv），绝不写入 config.json；
#   save_config() 经 _strip_secrets() 自动剥离上述密钥字段，确保不落盘、不进日志。
# - 部署要求（runbook）：py-server/.env 权限应设为 600（chmod 600）；真实密钥经
#   Docker / K8s secrets 注入，不随镜像或仓库分发，且应定期轮换。
# - 任何端点（含 /api/config）返回密钥时均已掩码（见 api/config_routes.py _mask_key），
#   且会话 API 已做路径穿越过滤（见 api/sessions.py _session_path），防止读取 .env 内容。


def _strip_secrets(cfg: dict) -> dict:
    """递归剥离密钥字段，返回一个安全的、可持久化的配置副本"""
    safe = {}
    for k, v in cfg.items():
        if isinstance(v, dict):
            stripped = _strip_secrets(v)
            # 如果整个 section 只剩非敏感字段才保留
            if k in _SECRET_SECTIONS:
                # 只保留非密钥字段（如 base_url, model, supports_*）
                safe[k] = {sk: sv for sk, sv in stripped.items() if sk not in _SECRET_FIELDS}
            else:
                safe[k] = stripped
        elif k not in _SECRET_FIELDS:
            safe[k] = v
    return safe


def save_config(cfg: dict):
    """保存非敏感配置到 config.json（API 密钥被自动剥离，只从 .env 加载）"""
    global _config_cache
    safe = _strip_secrets(cfg)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(safe, f, indent=2, ensure_ascii=False)
    with _config_lock:
        _config_cache = None  # 清除缓存，下次 load_config 重新读取
    logger = logging.getLogger("netlearn.config")
    logger.info("配置已保存（密钥字段已自动剥离）")


# ── 内部函数 ──

def _map_old_config(old: dict) -> dict:
    """将旧 config.json 字段映射到新结构"""
    mapped = {}

    # DeepSeek
    if old.get("llm_api_key") or old.get("llm_base_url"):
        mapped["deepseek"] = {
            "api_key": old.get("llm_api_key", ""),
            "base_url": old.get("llm_base_url", "https://api.deepseek.com"),
            "model": old.get("llm_model", "deepseek-chat"),
        }

    # 讯飞
    if old.get("xfyun_app_id"):
        mapped["xfyun"] = {
            "app_id": old["xfyun_app_id"],
            "api_key": old.get("xfyun_api_key", ""),
            "api_secret": old.get("xfyun_api_secret", ""),
            "base_url": old.get("xfyun_base_url", "https://spark-api-open.xf-yun.com/agent/v1"),
            "model": old.get("xfyun_model", "Spark-X2-Flash"),
        }

    # Provider
    if old.get("llm_provider"):
        mapped["llm_provider"] = old["llm_provider"]

    # Embedding
    if old.get("embedding_mode"):
        mapped["embedding"] = {"mode": old["embedding_mode"]}

    return mapped


def _deep_merge(base: dict, updates: dict) -> None:
    """深度合并 updates 到 base"""
    for key, value in updates.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _apply_env_overrides(config: dict) -> None:
    """环境变量覆盖配置"""
    env_map = {
        "DEEPSEEK_API_KEY": ("deepseek", "api_key"),
        "DEEPSEEK_BASE_URL": ("deepseek", "base_url"),
        "DEEPSEEK_MODEL": ("deepseek", "model"),
        "XF_API_KEY": ("xfyun", "api_key"),
        "XF_APP_ID": ("xfyun", "app_id"),
        "XF_APPID": ("xfyun", "app_id"),  # 讯飞控制台标准命名别名（README 用 XF_APP_ID，二者等价）
        "XF_API_SECRET": ("xfyun", "api_secret"),
        "XF_API_PASSWORD": ("xfyun", "api_password"),
        "XF_SEARCH_PASSWORD": ("xfyun", "search_password"),
        "XF_MODEL": ("xfyun", "model"),
        "XF_ACTIVE_PRESET": ("xfyun", "active_preset"),
        "QWEN_API_KEY": ("qwen", "api_key"),
        "QWEN_BASE_URL": ("qwen", "base_url"),
        "QWEN_MODEL": ("qwen", "model"),
        "TAVILY_API_KEY": ("tavily", "api_key"),
        "MILVUS_HOST": ("milvus", "host"),
        "MILVUS_PORT": ("milvus", "port"),
        "MILVUS_ENABLED": ("milvus", "enabled"),
        "PG_HOST": ("postgresql", "host"),
        "PG_PORT": ("postgresql", "port"),
        "PG_USER": ("postgresql", "user"),
        "PG_PASSWORD": ("postgresql", "password"),
        "PG_DATABASE": ("postgresql", "database"),
        "PG_ENABLED": ("postgresql", "enabled"),
        "REDIS_HOST": ("redis", "host"),
        "REDIS_PORT": ("redis", "port"),
        "REDIS_PASSWORD": ("redis", "password"),
        "REDIS_ENABLED": ("redis", "enabled"),
    }

    for env_key, (section, field) in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            # 处理布尔类型转换
            if field in ("enabled",) and val.lower() in ("true", "false", "1", "0"):
                val = val.lower() in ("true", "1")
            # 处理数字类型转换
            if field in ("port",):
                try:
                    val = int(val)
                except ValueError:
                    continue
            if section in config:
                config[section][field] = val


def _apply_xfyun_preset(config: dict) -> None:
    """将 xfyun.active_preset 解析为生效的 base_url/model（P0-X2 可切换配置结构）。

    仅覆盖 base_url / model 两个端点字段，**绝不动任何凭证字段**（api_password 等）。
    若 active_preset 未设置或不在 presets 中，保持 config.json 顶层 base_url/model 不变。
    这样切换讯飞星火模型/端点只需修改 config.json 的 active_preset 一个字段，
    无需改动账号凭证，也不需改任何调用处（llm_provider / 诊断端点统一从本处取值）。
    """
    xf = config.get("xfyun")
    if not isinstance(xf, dict):
        return
    presets = xf.get("presets")
    if not isinstance(presets, dict) or not presets:
        return
    # 赛题合规默认：讯飞星火 X2 为第一优先级通道。active_preset 缺失/为空时
    # 兜底为 spark_x2，避免回落到 4.0Ultra 端点触发 AppIdNoAuthError(11200)。
    active = xf.get("active_preset") or "spark_x2"
    if active not in presets:
        return
    preset = presets[active]
    if not isinstance(preset, dict):
        return
    if "base_url" in preset:
        xf["base_url"] = preset["base_url"]
    if "model" in preset:
        xf["model"] = preset["model"]
