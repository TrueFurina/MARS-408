#!/usr/bin/env python3
"""NeuralMixer 共识分基准脚本（固化入库，可复现）。

背景
----
共识分区分度是 GoMARL 混合器的核心对外指标。此前两次评估都用「临时脚本跑完即删」，
导致报告里的数字无法复现——比赛材料里一个复现不出来的数字和假数字一样危险。
本脚本把「怎么跑出来的」和「跑出什么」一起入库：脚本 + 结果 JSON 同 commit。

它测什么
--------
在 n=6（训练权重对应的 agent 数）下，用固定 seed 采样 N 组 agent 评分，
经 NeuralGroupMixer.mix() 得到共识分，统计 mean/std/min/max 与「饱和/归零」计数：
  - 饱和：共识分被 clamp 到 10.0（旧 bug：对已 0–10 量纲的输出再乘 10 → 96/96 全 10.0）
  - 归零：共识分被 clamp 到 0.0
健康的共识分应当有区分度：std 明显大于 0，且饱和/归零计数为 0。

两种输入分布（入参 --distribution 选择）
---------------------------------------
  stratified 分层：前 n//2 个 agent 为「专家」→ 评分 U(7, 9)；其余「非专家」→ U(4, 7)
  uniform    均匀：全部 agent 评分 U(4, 10)

确定性保证（可复现的前提）
--------------------------
1. 固定 --seed（默认 20261006），所有采样/嵌入都走 numpy Generator，不依赖全局随机源。
2. 嵌入使用 seed 生成的合成单位向量（768 维），不依赖 E5 模型是否离线可用。
3. 动态权重走生产代码 _compute_dynamic_weights，但把历史（PG）置空、画像置空，
   使其退化为确定的 base_weights 归一化结果，排除环境/数据库状态带来的漂移。
4. 不写数据库、不写缓存（log_agent_score / cache_agent_weights 均被 no-op 替换）。

复跑命令
--------
    cd py-server && env -u PYTHONPATH -u PYTHONSTARTUP -u NODE_OPTIONS \
        -u ELECTRON_RUN_AS_NODE .venv/Scripts/python.exe \
        experiments/bench_mixer_consensus.py --samples 96 --seed 20261006
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402

DEFAULT_OUT = (
    PROJECT_ROOT / "experiments" / "results" / "mixer_consensus_bench_2026-10-06.json"
)
DEFAULT_SEED = 20261006
DEFAULT_SAMPLES = 96
DEFAULT_N_AGENTS = 6
EMBED_DIM = 768

AGENT_NAMES = [
    "teacher",
    "quizmaster",
    "media_designer",
    "extension",
    "ppt_designer",
    "code_practice",
]

DISTRIBUTIONS = ("stratified", "uniform")

# 判定「区分度失效」的阈值
SATURATION_MIN = 9.999   # >= 视为被 clamp 到 10.0
ZERO_MAX = 0.001         # <= 视为被 clamp 到 0.0


def _agent_names(n: int) -> list[str]:
    """返回 n 个 agent 名称（超出内置列表时用占位名补齐）。"""
    return [
        AGENT_NAMES[i] if i < len(AGENT_NAMES) else f"agent_{i}"
        for i in range(n)
    ]


def sample_scores(rng: np.random.Generator, n: int, distribution: str) -> np.ndarray:
    """按给定分布采样 n 个 agent 的评分（0–10 分制）。"""
    if distribution == "stratified":
        n_expert = n // 2
        expert = rng.uniform(7.0, 9.0, size=n_expert)
        non_expert = rng.uniform(4.0, 7.0, size=n - n_expert)
        return np.concatenate([expert, non_expert]).astype(np.float32)
    if distribution == "uniform":
        return rng.uniform(4.0, 10.0, size=n).astype(np.float32)
    raise ValueError(f"未知分布: {distribution!r}（可选: {', '.join(DISTRIBUTIONS)}）")


def summarize(values: list[float]) -> dict:
    """对一批共识分做统计汇总。"""
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return {
            "samples": 0,
            "mean": None,
            "std": None,
            "min": None,
            "max": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "saturated": 0,
            "zeroed": 0,
            "distinct": 0,
        }
    return {
        "samples": int(arr.size),
        "mean": round(float(arr.mean()), 4),
        # ddof=0：总体标准差（与之前口径一致，便于横向对比）
        "std": round(float(arr.std(ddof=0)), 4),
        "min": round(float(arr.min()), 4),
        "max": round(float(arr.max()), 4),
        "p25": round(float(np.percentile(arr, 25)), 4),
        "p50": round(float(np.percentile(arr, 50)), 4),
        "p75": round(float(np.percentile(arr, 75)), 4),
        "saturated": int((arr >= SATURATION_MIN).sum()),
        "zeroed": int((arr <= ZERO_MAX).sum()),
        "distinct": int(np.unique(np.round(arr, 6)).size),
    }


async def run_distribution(
    mixer,
    distribution: str,
    samples: int,
    n_agents: int,
    seed: int,
) -> dict:
    """跑单一分布的基准，返回原始分数与统计。"""
    rng = np.random.default_rng(seed)
    names = _agent_names(n_agents)
    scores: list[float] = []
    input_means: list[float] = []

    for _ in range(samples):
        # 每轮重新采样嵌入：避免「同一嵌入 + 不同评分」低估方差来源
        embeddings = rng.standard_normal((n_agents, EMBED_DIM)).astype(np.float32)
        embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
        mixer.encoder.encode_batch = lambda _texts, _e=embeddings: _e

        level_scores = sample_scores(rng, n_agents, distribution)
        agent_results = [
            {
                "agent_name": names[i],
                "content": f"基准内容-{i}",
                "score": float(level_scores[i]),
            }
            for i in range(n_agents)
        ]
        result = await mixer.mix(agent_results, {}, "共识分基准")
        scores.append(round(float(result["consensus_score"]), 6))
        input_means.append(round(float(level_scores.mean()), 6))

    return {
        "distribution": distribution,
        # 输入侧基线：各样本「agent 评分算术平均」的统计，用于与共识分对照
        "input_mean_summary": summarize(input_means),
        "scores": scores,
        "stats": summarize(scores),
    }


async def main_async(args: argparse.Namespace) -> dict:
    import engines.gomarl_mixer as mixer_mod
    from engines.gomarl_mixer import NeuralGroupMixer

    torch, _, _ = mixer_mod._ensure_torch()
    if torch is None:
        raise RuntimeError("PyTorch 不可用，无法运行神经共识基准")

    mixer = NeuralGroupMixer()

    # ── 确定性替换：把一切环境依赖换成 no-op / 固定值 ──
    # 动态权重仍走生产代码，但历史置空 + 画像置空 ⇒ 退化为 base_weights 归一化（确定值）
    mixer_mod.pg_client.get_agent_history = lambda *a, **k: []
    mixer_mod.pg_client.log_agent_score = lambda *a, **k: None
    mixer_mod.redis_client.cache_agent_weights = lambda *a, **k: None

    distributions = (
        list(DISTRIBUTIONS) if args.distribution == "all" else [args.distribution]
    )

    runs: list[dict] = []
    for distribution in distributions:
        runs.append(
            await run_distribution(
                mixer=mixer,
                distribution=distribution,
                samples=args.samples,
                n_agents=args.n_agents,
                seed=args.seed,
            )
        )

    all_scores = [s for run in runs for s in run["scores"]]
    stats = mixer.get_stats()

    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config": {
            "seed": args.seed,
            "samples_per_distribution": args.samples,
            "n_agents": args.n_agents,
            "embed_dim": EMBED_DIM,
            "distributions": distributions,
            "score_ranges": {
                "stratified": "专家 U(7,9) / 非专家 U(4,7)",
                "uniform": "全体 U(4,10)",
            },
            "determinism": (
                "固定 seed；嵌入为 seed 生成的合成单位向量（不依赖 E5）；"
                "动态权重走生产代码但历史/画像置空 ⇒ base_weights 归一化；不写库不写缓存"
            ),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "torch": getattr(torch, "__version__", "unknown"),
            "numpy": np.__version__,
        },
        "mixer_state": {
            "mixer_neural_mode": stats["mixer_neural_mode"],
            "mixer_trained_loaded": stats["mixer_trained_loaded"],
            "mixer_embed_dim": stats["mixer_embed_dim"],
            "mixer_weights_complete": stats["mixer_weights_complete"],
            "mixer_weight_mismatch_layers": stats["mixer_weight_mismatch_layers"],
        },
        "runs": runs,
        "overall": summarize(all_scores),
        "reproduce_command": (
            "cd py-server && env -u PYTHONPATH -u PYTHONSTARTUP -u NODE_OPTIONS "
            "-u ELECTRON_RUN_AS_NODE .venv/Scripts/python.exe "
            f"experiments/bench_mixer_consensus.py --samples {args.samples} "
            f"--seed {args.seed} --n-agents {args.n_agents} --distribution all"
        ),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NeuralMixer 共识分基准（固定 seed，可复现）"
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="随机种子")
    parser.add_argument(
        "--samples", type=int, default=DEFAULT_SAMPLES, help="每个分布的样本数"
    )
    parser.add_argument(
        "--n-agents", type=int, default=DEFAULT_N_AGENTS, help="agent 数（训练时为 6）"
    )
    parser.add_argument(
        "--distribution",
        choices=[*DISTRIBUTIONS, "all"],
        default="all",
        help="输入分布：stratified 分层 / uniform 均匀 / all 两者",
    )
    parser.add_argument(
        "--out", type=str, default=str(DEFAULT_OUT), help="结果 JSON 输出路径"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = asyncio.run(main_async(args))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"结果已写入: {out_path}")
    print(
        "mixer 状态: mode={mode}, trained_loaded={loaded}, "
        "weights_complete={complete}, embed_dim={dim}".format(
            mode=payload["mixer_state"]["mixer_neural_mode"],
            loaded=payload["mixer_state"]["mixer_trained_loaded"],
            complete=payload["mixer_state"]["mixer_weights_complete"],
            dim=payload["mixer_state"]["mixer_embed_dim"],
        )
    )
    for run in payload["runs"]:
        s = run["stats"]
        print(
            f"  [{run['distribution']:<10}] n={s['samples']:<4} "
            f"mean={s['mean']:<8} std={s['std']:<8} "
            f"min={s['min']:<8} max={s['max']:<8} "
            f"saturated={s['saturated']} zeroed={s['zeroed']}"
        )
    o = payload["overall"]
    print(
        f"  [总体]        n={o['samples']:<4} mean={o['mean']:<8} std={o['std']:<8} "
        f"min={o['min']:<8} max={o['max']:<8} "
        f"saturated={o['saturated']} zeroed={o['zeroed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
