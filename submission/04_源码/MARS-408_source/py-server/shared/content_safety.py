# ============================================================
# 内容安全审核 — 统一输出审核（P1-7）
# ------------------------------------------------------------
# 将 filter_sensitive（本地敏感词）+ check_compliance（讯飞文本合规）
# + check_hallucination（知识性错误检查）统一接入全部生成输出链路。
#
# 设计原则：
#   1. 向后兼容：无凭证或讯飞合规不可用时降级为本地 filter_sensitive + 告警，
#      不得阻断主流程报错。
#   2. 永不抛出异常：所有外部调用（讯飞合规）均 try/except 兜底。
#   3. 审计可观测：拦截/告警事件经 shared.audit.log_event 记录到安全审计日志。
# ============================================================

import logging

from utils.safety import filter_sensitive, check_hallucination
from shared.audit import log_event as _audit_log

logger = logging.getLogger("netlearn.content_safety")


async def audit_output(text: str, source: str = "unknown") -> tuple[str, list[str]]:
    """对生成输出做统一内容安全审核。

    审核链（顺序执行）：
      1. filter_sensitive — 本地敏感词过滤（始终执行，无外部依赖）
      2. check_compliance — 讯飞文本合规审核（有凭证时执行，失败降级）
      3. check_hallucination — 知识性错误检查（始终执行，本地）

    Args:
        text: 待审核的生成输出文本。
        source: 审核来源标识（如 endpoint 名），用于审计日志追溯。

    Returns:
        (filtered_text, audit_notes)
        - filtered_text: 经敏感词过滤后的文本（原文本若无需过滤）
        - audit_notes: 审核备注列表（敏感词命中/合规风险/幻觉警告）；
          空列表表示未检出问题。
    """
    if not text:
        return text, []

    notes: list[str] = []

    # ── 1. 本地敏感词过滤（始终执行） ──
    filtered, hits = filter_sensitive(text)
    if hits:
        logger.warning(
            "内容安全拦截[敏感词] source=%s hits=%d words=%s",
            source, len(hits), hits[:5],
        )
        _audit_log(
            action="content_safety_sensitive",
            result="blocked",
            detail=f"source={source} hits={len(hits)} words={hits[:5]}",
        )
        notes.append(f"敏感词过滤: 命中 {len(hits)} 个")

    # ── 2. 讯飞文本合规审核（有凭证时执行，失败降级） ──
    try:
        from db.xfyun_services import check_compliance, has_credentials
        if has_credentials():
            result = await check_compliance(filtered)
            if result.success:
                if not result.passed:
                    logger.warning(
                        "内容安全拦截[讯飞合规] source=%s suggest=%s hits=%d",
                        source, result.suggest, len(result.hits),
                    )
                    _audit_log(
                        action="content_safety_compliance",
                        result="blocked",
                        detail=f"source={source} suggest={result.suggest} hits={len(result.hits)}",
                    )
                    notes.append(f"讯飞合规审核: {result.suggest} (命中 {len(result.hits)} 项)")
            else:
                # 合规服务不可用 — 降级为本地过滤，记录告警
                logger.info(
                    "讯飞合规不可用，降级为本地过滤 source=%s reason=%s",
                    source, (result.error or "unknown")[:200],
                )
                _audit_log(
                    action="content_safety_compliance_degrade",
                    result="success",
                    detail=f"source={source} reason={(result.error or 'unknown')[:200]}",
                )
        else:
            logger.debug("讯飞凭证未配置，仅本地敏感词过滤 source=%s", source)
    except Exception as e:
        logger.warning(
            "讯飞合规审核异常，降级为本地过滤 source=%s error=%s",
            source, str(e)[:200],
        )
        _audit_log(
            action="content_safety_compliance_error",
            result="failure",
            detail=f"source={source} error={str(e)[:200]}",
        )

    # ── 3. 知识性错误检查（本地，始终执行） ──
    hallu_warnings = check_hallucination(filtered)
    if hallu_warnings:
        logger.warning(
            "内容安全告警[幻觉] source=%s count=%d",
            source, len(hallu_warnings),
        )
        _audit_log(
            action="content_safety_hallucination",
            result="blocked",
            detail=f"source={source} count={len(hallu_warnings)}",
        )
        notes.extend(hallu_warnings)

    return filtered, notes
