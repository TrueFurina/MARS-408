"""
live_mixer_integration_test.py — 生产 HTTP 路径集成验证（大创真版闭环）

目的：证明「真实训练权重」被**生产路由**真正消费，而非仅单元脚本调用。
直接驱动 `api/engine.py` 的 `/gomarl-consensus` 路由（生产代码路径），
断言返回 `neural_used=true`。

实现要点：
- 用 TestClient 但不进入 `with` 上下文 → 不触发 FastAPI lifespan/startup
  → 不需要加载 KB、不获取单写者锁，避免与运行中的 uvicorn(8002) 冲突。
- 覆盖 `get_current_user` 依赖为 dummy，免去 JWT 鉴权（运行实例 AUTH_SECRET
  每次启动随机，无法跨进程签发）。
- 路由内部调用 `neural_mixer.mix()`（真实加载 neural_mixer_trained.pt，48/48 权重）
  + `conflict_engine`；完整走生产 handler 逻辑。
"""
import sys
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from shared.auth import get_current_user
from api.engine import require_llm_quota
from main import app

# 覆盖鉴权/配额依赖（无需真实 token / 额度）
app.dependency_overrides[get_current_user] = lambda: {"user_id": "test", "role": "student"}
app.dependency_overrides[require_llm_quota] = lambda: None


def main():
    client = TestClient(app)  # 不进入 with → 跳过 lifespan，不抢写者锁

    agent_results = [
        {"agent_name": "teacher",        "content": "TCP三次握手：客户端发SYN，服务端回SYN-ACK，客户端再发ACK完成建立。", "score": 8.5},
        {"agent_name": "quizmaster",     "content": "考察重点：三次握手防止已失效连接请求突然又传到服务端。", "score": 7.2},
        {"agent_name": "media_designer", "content": "状态转换图：CLOSED→SYN_SENT→ESTABLISHED，服务端LISTEN→SYN_RCVD→ESTABLISHED。", "score": 6.8},
        {"agent_name": "extension",      "content": "TCP与UDP对比：TCP面向连接可靠，UDP无连接不可靠但低延迟。", "score": 7.9},
        {"agent_name": "ppt_designer",   "content": "要点总结：SEQ/ACK号、窗口大小、MSS 是握手与流量控制关键字段。", "score": 8.1},
        {"agent_name": "code_practice",  "content": "socket 编程：connect() 触发三次握手，accept() 在握手完成后返回。", "score": 6.5},
    ]
    payload = {
        "agent_results": agent_results,
        "student_profile": {"level": "intermediate", "weak_subjects": ["computer_network"]},
        "topic": "TCP三次握手",
        "course": "computer_network",
    }

    resp = client.post("/api/engine/gomarl-consensus", json=payload)
    print(f"[i] HTTP 状态: {resp.status_code}")
    body = resp.json()
    print(json.dumps(body, ensure_ascii=False, indent=2))

    neural_used = body.get("neural_used")
    ok = resp.status_code == 200 and neural_used is True
    print(f"\n[判定] 生产路由消费真实训练权重(neural_used=True): {'✅ 通过' if ok else '❌ 失败'}")
    print(f"  consensus_score = {body.get('consensus_score')}")
    print(f"  groups           = {body.get('groups')}")
    print(f"  conflicts.total  = {body.get('conflicts', {}).get('total')}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
