# -*- coding: utf-8 -*-
"""讯飞能力全景探活（真实网络，report-only）。

覆盖三层，逐项给出「凭证面宣称 vs 真实探活」裁定：
  A. LLM 星火通道（复用 sanctioned 诊断端点 /api/llm/x2-health 内部逻辑，全候选）
  B. 多模态 db 层：TTI 图片生成 / TTS 语音合成（含负载真实性验证）
  C. 其余讯飞服务真实探活：文本纠错 / 公文校对 / 内容合规 / 图片理解（链式复用 TTI 产物）
     / 万搜 / 角色模拟 / 智能简历；PPT 与数字人视频成本高，明确标注「未探活」
  D. API 层端到端：TestClient 真注册→登录→Bearer，打 /api/multimodal 三端点 + 无 token 401 面

纪律：
  - 绝不回显任何密钥；错误只报类型/状态码/讯飞错误码。
  - 限流码（11202/11203/429）与未开通码（11200/401/403）分开裁定——限流≠未开通。
  - 「Success」必须伴随真实负载（图片字节/音频字节/文本/链接）才算通过，防空响应假绿。
  - API 层跑在临时 NETLEARN_PG_DIR 隔离库上，不污染开发库。

退出码契约：0 = 探活自身执行完毕（report-only，单项成败看 JSON）；
             2 = 探活自身基础设施错误（导入失败/凭证完全缺失等）。
"""
import asyncio
import argparse
import json
import logging
import os
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(REPO, "py-server")

# 压低应用日志噪声（netlearn logger 默认往 stdout 打 JSON 行，会污染结果输出）
logging.getLogger("netlearn").setLevel(logging.WARNING)
logging.getLogger().setLevel(logging.WARNING)

# API 层隔离库（必须在 import main 前设置）
_TMP_DB = tempfile.mkdtemp(prefix="xfprobe_db_")
os.environ["NETLEARN_PG_DIR"] = _TMP_DB

sys.path.insert(0, PY)

OUT = {"meta": {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "isolated_db": _TMP_DB}}
RATE_CODES = {"11202", "11203", "429"}


def _classify(note: str) -> str:
    """把讯飞错误 note 归类：rate_limit / auth / other。"""
    low = (note or "").lower()
    if any(c in low for c in RATE_CODES):
        return "rate_limit"
    if "11200" in low or "appauth" in low or "401" in low or "403" in low or "noauth" in low:
        return "auth"
    return "other"


async def _delay(sec: float = 1.5) -> None:
    await asyncio.sleep(sec)


# ── A. LLM ──
async def probe_llm() -> None:
    from api.llm_health import llm_x2_health
    r = await llm_x2_health(user={"role": "admin", "username": "probe"})
    OUT["llm"] = {
        "configured": r["xfyun_configured"],
        "current": r["current"],
        "probed": [
            {"label": p["label"], "ok": p["ok"], "http_code": p["http_code"],
             "class": "ok" if p["ok"] else _classify(p["note"]), "note": p["note"][:120]}
            for p in r["probed"]
        ],
    }


# ── B. 多模态 db 层（含负载验证）──
async def probe_tti_tts() -> None:
    from db.xfyun_multimodal import generate_image, generate_speech
    img = await generate_image("一个简单的圆形流程图，三个节点串联", "探活")
    OUT["tti"] = {
        "source": img.source, "success": img.success,
        "image_bytes": len(img.image_base64 or ""),
        "verdict": "real" if (img.source == "xfyun" and len(img.image_base64 or "") > 10000)
                   else ("fallback" if img.success else "error"),
        "error": (img.error or "")[:120],
        # 图片理解链式复用（不重复消耗一次生成）
        "_image_b64": img.image_base64 or "",
    }
    await _delay()
    sp = await generate_speech("芒得很职多模态能力探活。", "xiaoyan")
    OUT["tts"] = {
        "source": sp.source, "success": sp.success,
        "audio_bytes": len(sp.audio_base64 or ""),
        "verdict": "real" if (sp.source == "xfyun" and len(sp.audio_base64 or "") > 1000)
                   else ("fallback" if sp.success else "error"),
    }


# ── C. 其余服务 ──
async def probe_services() -> None:
    import db.xfyun_services as xs
    svc = {}

    r = await xs.proofread_text("今天天qi很好，我去上学，心情很不错。")
    svc["text_correction"] = {"ok": r.success, "corrections": len(r.corrections),
                              "class": "ok" if r.success else _classify(r.error or ""),
                              "error": (r.error or "")[:120]}
    await _delay()

    r = await xs.proofread_document("请各位于本月三十日前提交相关材料，逾期不予受理。")
    svc["document_proofread"] = {"ok": r.success, "corrections": len(r.corrections),
                                 "class": "ok" if r.success else _classify(r.error or ""),
                                 "error": (r.error or "")[:120]}
    await _delay()

    r = await xs.check_compliance("今天天气很好，我们去上课。")
    svc["content_compliance"] = {"ok": r.success, "passed": r.passed, "suggest": r.suggest,
                                 "class": "ok" if r.success else _classify(r.error or ""),
                                 "error": (r.error or "")[:120]}
    await _delay()

    img_b64 = OUT.get("tti", {}).get("_image_b64") or ""
    if img_b64:
        r = await xs.understand_image(img_b64, "这张图里有什么？用一句话回答。")
        svc["image_understanding"] = {"ok": r.success, "answer_len": len(r.text or ""),
                                      "answer_head": (r.text or "")[:60],
                                      "class": "ok" if r.success else _classify(r.error or ""),
                                      "error": (r.error or "")[:120]}
        await _delay()

    r = await xs.web_search("计算机专业 大学生 就业方向", limit=3)
    svc["web_search"] = {"ok": r.success, "items": len(r.items),
                         "class": "ok" if r.success else _classify(r.error or ""),
                         "error": (r.error or "")[:120]}
    await _delay()

    r = await xs.roleplay_interview(
        "你是一位友善的软件工程师面试官，正在面试一位应届毕业生。",
        "你好，请先做个自我介绍。",
        user_id=f"probe_{os.urandom(4).hex()}")
    svc["role_simulation"] = {"ok": r.success, "reply_len": len(r.reply or ""),
                              "reply_head": (r.reply or "")[:60],
                              "class": "ok" if r.success else _classify(r.error or ""),
                              "error": (r.error or "")[:120]}
    await _delay()

    r = await xs.generate_resume("张某，22岁，闽江大学信息安全专业本科，主修网络攻防与密码学，"
                                 "熟悉 Python 与 Go，求网络安全工程师实习岗。")
    svc["resume_generation"] = {"ok": r.success, "has_word_url": bool(r.word_url),
                                "class": "ok" if r.success else _classify(r.error or ""),
                                "error": (r.error or "")[:120]}

    svc["ppt_generation"] = {"ok": None, "class": "skipped",
                             "error": "未探活：PPT 生成为重任务（建任务+轮询），成本高，需真人决策"}
    svc["video_generation"] = {"ok": None, "class": "skipped",
                               "error": "未探活：数字人视频生成为重任务且计费，需真人决策"}
    OUT["services"] = svc


# ── D. API 层端到端 ──
async def probe_api_e2e() -> None:
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    uname = f"xfprobe_{os.urandom(4).hex()}"
    pwd = "Probe@2026xf"

    anon = client.post("/api/multimodal/generate-image",
                       json={"topic": "探活", "prompt": "一个圆形图标"})
    e2e = {"auth_surface": {"no_token_http": anon.status_code,
                            "class": "ok" if anon.status_code in (401, 403) else "LEAK"}}

    reg = client.post("/api/auth/register",
                      json={"username": uname, "password": pwd, "display_name": "探活"})
    if reg.status_code not in (200, 201):
        e2e["register"] = {"http": reg.status_code, "body": reg.text[:200]}
        OUT["api_e2e"] = e2e
        return
    tok = reg.json().get("token") or ""
    if not tok:
        login = client.post("/api/auth/login", json={"username": uname, "password": pwd})
        tok = login.json().get("token") or ""
    h = {"Authorization": f"Bearer {tok}"}

    r = client.post("/api/multimodal/generate-image",
                    json={"topic": "探活", "prompt": "一个简单的圆形流程图，三个节点"}, headers=h)
    e2e["generate_image"] = {
        "http": r.status_code,
        "is_real_image": r.json().get("is_real_image") if r.status_code < 400 else None,
        "image_bytes": len(r.json().get("image_base64") or "") if r.status_code < 400 else 0,
        "body_head": r.text[:160] if r.status_code >= 400 else "",
    }
    await _delay()

    r = client.post("/api/multimodal/generate-audio",
                    json={"text": "芒得很职多模态探活。", "voice": "xiaoyan"}, headers=h)
    e2e["generate_audio"] = {
        "http": r.status_code,
        "is_real_audio": r.json().get("is_real_audio") if r.status_code < 400 else None,
        "audio_bytes": len(r.json().get("audio_base64") or "") if r.status_code < 400 else 0,
        "body_head": r.text[:160] if r.status_code >= 400 else "",
    }
    await _delay()

    r = client.post("/api/multimodal/generate-multimodal",
                    json={"topic": "探活", "text_content": "这是多模态资源探活文本。",
                          "generate_image": True, "generate_audio": True}, headers=h)
    body = r.json() if r.status_code < 400 else {}
    e2e["generate_multimodal"] = {
        "http": r.status_code,
        "image_source": body.get("image_source"),
        "audio_source": body.get("audio_source"),
        "image_bytes": len(body.get("image_base64") or ""),
        "audio_bytes": len(body.get("audio_base64") or ""),
        "body_head": r.text[:160] if r.status_code >= 400 else "",
    }
    OUT["api_e2e"] = e2e


async def main(out_path: str) -> None:
    t0 = time.time()
    await probe_llm()
    await probe_tti_tts()
    await probe_services()
    await probe_api_e2e()
    OUT["meta"]["elapsed_sec"] = round(time.time() - t0, 1)
    # _image_b64 是链式复用的中间产物，不进结果
    OUT.get("tti", {}).pop("_image_b64", None)

    # 汇总（人读）
    lines = []
    llm_bad = [p for p in OUT["llm"]["probed"] if not p["ok"]]
    lines.append(f"LLM: {len(OUT['llm']['probed']) - len(llm_bad)}/{len(OUT['llm']['probed'])} 可用"
                 f"（失败类：{sorted({p['class'] for p in llm_bad}) or '无'}）")
    lines.append(f"TTI: {OUT['tti']['verdict']} ({OUT['tti']['image_bytes']}B)")
    lines.append(f"TTS: {OUT['tts']['verdict']} ({OUT['tts']['audio_bytes']}B)")
    for k, v in OUT["services"].items():
        mark = {"ok": "✅", "rate_limit": "⏳限流", "auth": "🔒未开通", "skipped": "➖未探活"}.get(
            v["class"], "❌")
        lines.append(f"{k}: {mark}")
    e = OUT["api_e2e"]
    lines.append(f"API无token面: HTTP {e['auth_surface']['no_token_http']} ({e['auth_surface']['class']})")
    for k in ("generate_image", "generate_audio", "generate_multimodal"):
        if k in e:
            lines.append(f"API {k}: HTTP {e[k]['http']}")
    OUT["summary"] = lines

    payload = json.dumps(OUT, ensure_ascii=False, indent=2, default=str)
    if out_path == "-":
        print(payload)
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
        print(f"结果已写入: {out_path}", file=sys.stderr)
    print("\n===== SUMMARY =====", file=sys.stderr)
    for ln in lines:
        print(ln, file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="讯飞能力全景探活（真实网络）")
    parser.add_argument("--out", default="-",
                        help="结果 JSON 输出路径（'-' = stdout；默认 '-'）。"
                             "注意应用日志也走 stdout，落盘建议给路径。")
    args = parser.parse_args()
    try:
        asyncio.run(main(args.out))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"fatal": type(exc).__name__, "detail": str(exc)[:300]}, ensure_ascii=False))
        sys.exit(2)
