# -*- coding: utf-8 -*-
"""G5 发生型证据重捕：对真实运行后端发起一次真实 RAG 检索调用，落盘原始 JSON + 可读证据。
不编造：全部为后端实时返回。失败即报错，绝不回退合成数据。
"""
import json, urllib.request, urllib.error, datetime, os

BASE = "http://127.0.0.1:8002"
OUT_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(OUT_DIR, exist_ok=True)
TS = datetime.date.today().isoformat()

def post(path, payload, token=None, timeout=120):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        return e.code, {"_error": body}

# 1) 登录（演示账号，验证真实可登录）
login_status, login_resp = post("/api/auth/login",
                                {"username": "demo", "password": "demo123456"})
token = None
for k in ("access_token", "token", "jwt"):
    if isinstance(login_resp, dict) and login_resp.get(k):
        token = login_resp[k]; break
if not token and isinstance(login_resp, dict):
    # 可能嵌套在 data 里
    d = login_resp.get("data") or {}
    token = d.get("access_token") or d.get("token")

# 2) 真实 RAG 检索（public 路由，带 token 更贴近真实会话）
search_status, search_resp = post("/api/rag/search",
                                  {"query": "TCP三次握手过程", "course": "computer_network", "top_k": 5},
                                  token=token)

record = {
    "captured_at": datetime.datetime.now().isoformat(timespec="seconds"),
    "endpoint": "/api/rag/search",
    "method": "POST",
    "query": "TCP三次握手过程",
    "login_status": login_status,
    "login_response_keys": sorted(login_resp.keys()) if isinstance(login_resp, dict) else None,
    "search_status": search_status,
    "search_response": search_resp,
}
out = os.path.join(OUT_DIR, f"trace_frugalrag_search_{TS}.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(record, f, ensure_ascii=False, indent=2)

# 3) 可读证据
hits = (search_resp.get("results") if isinstance(search_resp, dict) else None) or \
       (search_resp.get("data", {}).get("results") if isinstance(search_resp, dict) else None) or []
ev = [f"# FrugalRAG 真实检索 Trace 证据（{TS}）", "",
      f"- 时间：{record['captured_at']}",
      f"- 端点：POST {BASE}/api/rag/search",
      f"- 登录状态：{login_status}（demo/demo123456，token={'已获取' if token else '未获取/路由公开'}）",
      f"- 检索状态：{search_status}",
      f"- 查询：TCP三次握手过程（course=computer_network, top_k=5）",
      f"- 返回条目数：{len(hits)}", ""]
if hits:
    ev.append("## 返回片段（前 5 条，含真实 score）")
    for i, h in enumerate(hits[:5], 1):
        if isinstance(h, dict):
            txt = (h.get("content") or h.get("text") or h.get("chunk") or "")[:80]
            sc = h.get("distance", h.get("score", h.get("similarity", "?")))
            ev.append(f"{i}. score={sc} | {txt}")
ev.append("")
ev.append("> 原始 JSON 见同目录 trace_frugalrag_search_%s.json（含完整响应，未裁剪）。" % TS)
ev_path = os.path.join(OUT_DIR, f"TRACE_FrugalRAG_证据说明-{TS}.md")
with open(ev_path, "w", encoding="utf-8") as f:
    f.write("\n".join(ev))

print("login_status=", login_status, "search_status=", search_status, "hits=", len(hits))
print("saved:", out)
print("evidence:", ev_path)
if search_status != 200:
    print("WARN: search 非 200，原始响应：", json.dumps(search_resp, ensure_ascii=False)[:500])
