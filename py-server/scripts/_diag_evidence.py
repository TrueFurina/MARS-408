# -*- coding: utf-8 -*-
"""临时诊断：观察 evidence_chain 在测试环境下的真实结构。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app
from shared.auth import get_current_user

app.dependency_overrides[get_current_user] = lambda: {
    "user_id": "diag", "role": "student", "name": "diag"}

DISTINCTIVE = "根因定位后对比三套方案并给出回滚预案与监控指标。"

client = TestClient(app)
sc = client.get("/api/career/scenarios").json()["scenarios"]
print("SCENARIO[0]:", sc[0]["id"], sc[0].get("type_label"))
sid = client.post("/api/career/session/start",
                  json={"scenario_id": sc[0]["id"], "max_turns": 4}).json()["session_id"]
client.post(f"/api/career/session/{sid}/answer", json={"answer": DISTINCTIVE})
client.post(f"/api/career/session/{sid}/answer",
            json={"answer": "我会先对齐目标，再拆解任务，并定期同步风险与进展。"})
end = client.post(f"/api/career/session/{sid}/end", json={"force": True})
print("END status:", end.status_code)

from services import career_service
report = career_service.get_report(sid)
print("=== evidence_chain ===")
print(json.dumps(report["evidence_chain"], ensure_ascii=False, indent=2))

print("=== HTML checks ===")
html = client.get(f"/api/career/session/{sid}/export-report").text
for token in ["CAREER_ASSESS(ECD六维)", "待补全（证据取自学生本轮作答）", "情景期望行为",
              "本实训为情景对抗、无教材库检索", "溯源：待补全", "chunk-", "学生第1轮说", "学生第2轮说"]:
    print(f"  {token!r}: {token in html}")

