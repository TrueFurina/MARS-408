# ============================================================
# LLM 通道探活诊断（P0-X2 清零支撑）
# 一键探测讯飞星火各候选模型/端点，定位 X2 通道 500 根因。
# 仅返回状态码与脱敏错误，绝不回显任何密钥。
# ============================================================

import logging

import httpx
from fastapi import APIRouter, Depends

from config import load_config
from shared.auth import get_current_user

logger = logging.getLogger("netlearn.llm_health")
router = APIRouter(prefix="/llm", tags=["llm-health"])


# 讯飞 spark-api-open 已知候选（用于诊断账号实际开通了哪个模型/端点）
# 参考：星火 X2 推理模型 base_url 为 /x2/、model=spark-x；通用 4.0 Ultra 为 /v1、model=4.0Ultra
_CANDIDATES = [
    {"label": "通用 星火 4.0 Ultra (/v1)", "base_url": "https://spark-api-open.xf-yun.com/v1/chat/completions", "model": "4.0Ultra"},
    {"label": "星火 X2 推理 (/x2)", "base_url": "https://spark-api-open.xf-yun.com/x2/chat/completions", "model": "spark-x"},
    {"label": "星火 Max/generalv3.5 (/v1)", "base_url": "https://spark-api-open.xf-yun.com/v1/chat/completions", "model": "generalv3.5"},
    {"label": "星火 Pro-128K (/v1)", "base_url": "https://spark-api-open.xf-yun.com/v1/chat/completions", "model": "pro-128k"},
]


async def _probe(base_url: str, model: str, token: str) -> dict:
    """对单个候选做一次极简 chat 探测，返回脱敏结果（不含任何密钥）。"""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
        "temperature": 0.1,
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(base_url, headers=headers, json=body)
            if resp.status_code < 400:
                return {"ok": True, "http_code": resp.status_code, "note": ""}
            note = ""
            try:
                data = resp.json()
                note = data.get("message") or data.get("error") or (resp.text or "")[:200]
            except Exception:
                note = (resp.text or "")[:200]
            return {"ok": False, "http_code": resp.status_code, "note": str(note)[:200]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "http_code": None, "note": type(e).__name__}


@router.get("/x2-health")
async def llm_x2_health(user: dict = Depends(get_current_user)):
    """讯飞 X2/星火通道探活诊断。

    探测「当前 config 配置」与若干已知候选模型/端点，返回哪个可用，
    用于一键定位 X2 通道 500 的根因：
      - 账号未开通对应 LLM 服务权限；或
      - config 的 base_url / model 与账号实际开通的不匹配。
    响应绝不回显任何密钥或凭证值。
    """
    cfg = load_config()
    xf = cfg.get("xfyun", {})
    token = xf.get("api_password", "") or ""
    configured = bool(token)
    base_url = xf.get("base_url", "")
    model = xf.get("model", "")

    candidates = []
    # 1) 当前实际配置（最重要：复现 auto 模式下 X2 的行为，且已应用 active_preset 解析）
    if base_url and model:
        candidates.append({
            "label": f"当前配置 ({model} @ {base_url.split('/chat')[0]})",
            "base_url": base_url,
            "model": model,
        })
    # 2) 候选列表：优先取自 config.json 的 xfyun.presets（与「可切换配置结构」单一来源一致），
    #    缺省时回退到内置 _CANDIDATES。自动跳过与「当前配置」完全相同的组合。
    preset_map = xf.get("presets")
    if isinstance(preset_map, dict) and preset_map:
        for key, p in preset_map.items():
            if not isinstance(p, dict):
                continue
            p_url = p.get("base_url", "")
            p_model = p.get("model", "")
            if not p_url or not p_model:
                continue
            if p_url == base_url and p_model == model:
                continue  # 已作为「当前配置」探测
            candidates.append({
                "label": f"预设 {key} ({p_model} @ {p_url.split('/chat')[0]})",
                "base_url": p_url,
                "model": p_model,
            })
    else:
        for c in _CANDIDATES:
            if not any(c["label"] == existing["label"] for existing in candidates):
                candidates.append(c)

    results = []
    for c in candidates:
        if not token:
            results.append({
                "label": c["label"], "ok": False, "http_code": None,
                "note": "未配置 APIPassword（检查 py-server/.env 的 XF_API_PASSWORD）",
            })
            continue
        r = await _probe(c["base_url"], c["model"], token)
        results.append({"label": c["label"], **r})

    ok = [r for r in results if r["ok"]]
    if ok:
        rec = (
            f"检测到可用通道：{ok[0]['label']}（HTTP {ok[0]['http_code']}）。"
            f" 请将 py-server/config.json 的 xfyun.base_url / model 改为该组合，"
            f" 重启后端后 X2 即在 auto 模式下优先成功，恢复真实双兜底。"
        )
    elif configured:
        rec = (
            "所有候选均失败 → 根因为账号权限：当前 APIPassword 对应的讯飞应用未开通对应 LLM 服务。"
            " 请到讯飞开放平台控制台确认该 APP 已开通『星火认知大模型』且包含所用模型"
            "（通用 4.0 Ultra 需开通对应能力；若要用星火 X2 推理模型需开通 X2 能力）。"
            " 修复后重启后端、再次访问本端点验证。"
        )
    else:
        rec = "未配置 XF_API_PASSWORD，无法探测。请先在 py-server/.env 配置讯飞 APIPassword（非 APPID/APIKey）。"

    return {
        "xfyun_configured": configured,
        "current": {
            "base_url": base_url.split("/chat")[0] if base_url else "",
            "model": model,
        },
        "probed": results,
        "recommendation": rec,
    }
