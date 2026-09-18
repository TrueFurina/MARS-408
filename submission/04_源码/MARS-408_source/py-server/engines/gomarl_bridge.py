# ============================================================
# GoMARL 研究项目桥接模块
# 连接 GoMARL-main 科研项目训练管线与 MARS-408 推理引擎
#
# 科研项目路径: E:/Program/MARL/GoMARL-main
# 桥接功能:
#   1. 导入科研项目的 GroupMixer 神经网络
#   2. 导入科研项目的 GROUPLearner 训练逻辑
#   3. 加载科研项目训练的模型权重
#   4. 在 MARS-408 推理时使用科研项目的分组策略
# ============================================================

import logging
import os
import sys
from typing import Optional

logger = logging.getLogger("netlearn.gomarl_bridge")

# 科研项目路径
GOMARL_PROJECT_PATH = os.environ.get(
    "GOMARL_PROJECT_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "GoMARL-main")
)

# 科研项目是否可用
_GOMARL_AVAILABLE = None


def is_gomarl_available() -> bool:
    """检查 GoMARL 科研项目是否可导入"""
    global _GOMARL_AVAILABLE
    if _GOMARL_AVAILABLE is not None:
        return _GOMARL_AVAILABLE

    if not os.path.isdir(GOMARL_PROJECT_PATH):
        logger.warning(f"GoMARL 科研项目不存在: {GOMARL_PROJECT_PATH}")
        _GOMARL_AVAILABLE = False
        return False

    try:
        sys.path.insert(0, GOMARL_PROJECT_PATH)
        from src.learners.group_learner import GROUPLearner
        from src.modules.mixers.group import Mixer as GroupMixer
        _GOMARL_AVAILABLE = True
        logger.info(f"GoMARL 科研项目可用: {GOMARL_PROJECT_PATH}")
        return True
    except Exception as e:
        logger.warning(f"GoMARL 科研项目导入失败: {e}")
        _GOMARL_AVAILABLE = False
        return False


def get_group_mixer(config: dict = None):
    """获取科研项目的 GroupMixer 实例"""
    if not is_gomarl_available():
        return None
    try:
        from src.modules.mixers.group import Mixer as GroupMixer
        # 构造 args 对象
        class Args:
            pass
        args = Args()
        args.n_agents = config.get("n_agents", 5) if config else 5
        args.mixing_embed_dim = config.get("mixing_embed_dim", 32) if config else 32
        args.hypernet_embed = config.get("hypernet_embed", 64) if config else 64
        args.grouping_hypernet_embed = config.get("grouping_hypernet_embed", 64) if config else 64
        args.rnn_hidden_dim = config.get("rnn_hidden_dim", 64) if config else 64
        args.state_shape = config.get("state_shape", 64) if config else 64
        # 默认分组：所有智能体一组
        args.group = config.get("group", [[0, 1, 2, 3, 4]]) if config else [[0, 1, 2, 3, 4]]

        mixer = GroupMixer(args)
        logger.info("GroupMixer 加载成功")
        return mixer
    except Exception as e:
        logger.warning(f"GroupMixer 加载失败: {e}")
        return None


def get_group_learner(mac, scheme, args):
    """获取科研项目的 GROUPLearner 实例"""
    if not is_gomarl_available():
        return None
    try:
        from src.learners.group_learner import GROUPLearner
        learner = GROUPLearner(mac, scheme, logger, args)
        logger.info("GROUPLearner 加载成功")
        return learner
    except Exception as e:
        logger.warning(f"GROUPLearner 加载失败: {e}")
        return None


def get_agent_weight_snapshot(agent_names: list[str], history: list[dict] = None) -> dict[str, float]:
    """基于科研项目分组策略生成 Agent 权重快照

    使用 GoMARL 的分组思想（非训练），根据 Agent 历史表现动态调整权重。
    作为科研项目训练管线的轻量替代（无训练时使用）。
    """
    # 默认权重
    base_weights = {
        "teacher": 1.0, "quizmaster": 0.9, "media_designer": 0.85,
        "extension": 0.8, "ppt_designer": 0.8, "code_practice": 0.85,
    }

    # 无历史数据时返回默认权重
    if not history:
        return {name: base_weights.get(name, 0.8) for name in agent_names}

    # 基于历史表现计算权重
    weights = {}
    for name in agent_names:
        base = base_weights.get(name, 0.8)
        # 查找该 Agent 的历史评分
        agent_history = [h for h in history if h.get("agent_name") == name]
        if agent_history:
            avg_score = sum(h.get("score", 5) for h in agent_history) / len(agent_history)
            # 将评分(1-10)映射到权重调整因子(0.6-1.2)
            adjustment = 0.6 + (avg_score / 10) * 0.6
            weights[name] = round(base * adjustment, 2)
        else:
            weights[name] = base

    return weights