#!/usr/bin/env bash
# MARS-408 全自动质检脚本（供 24h 巡检 automation 调用，亦可手动运行）
# 用法: bash scripts/auto_qa.sh
# 输出: 追加结构化报告到 docs/reports/qa-24h-log.md
set +e
cd "$(dirname "$0")/.." || exit 1

QA_USER="qa_24h"
QA_PASS='Qa24h_Pass!'
FE_PORT=5173
BE_PORT=8002
REPORT="docs/reports/qa-24h-log.md"
TS="$(date '+%Y-%m-%d %H:%M:%S')"

ok=0; warn=0; fail=0
line() { printf '%s\n' "$1" >> "$REPORT"; }

mkdir -p docs/reports
[ -f "$REPORT" ] || echo "# MARS-408 24h 自动质检日志" > "$REPORT"

line ""
line "## 🔎 巡检 $TS"
line ""

# 1. 登录拿 token
TOKEN=$(curl -s -m 10 -X POST "http://127.0.0.1:$BE_PORT/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$QA_USER\",\"password\":\"$QA_PASS\"}" 2>/dev/null \
  | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')
if [ -z "$TOKEN" ]; then
  line "- ❌ 登录失败（无法获取 token，端点测试跳过）"; fail=$((fail+1))
else
  line "- ✅ 登录成功（qa_24h）"; ok=$((ok+1))
fi

# 2. 前端 5173
FE_CODE=$(curl -s -m 5 -o /dev/null -w "%{http_code}" "http://127.0.0.1:$FE_PORT/" 2>/dev/null)
if [ "$FE_CODE" = "200" ]; then line "- ✅ 前端 5173 HTTP 200（页面服务正常）"; ok=$((ok+1))
else line "- ❌ 前端 5173 HTTP $FE_CODE（页面空白根因！应开 5173 非 8002/5181）"; fail=$((fail+1)); fi

# 3. 后端 /api/status
ST=$(curl -s -m 5 "http://127.0.0.1:$BE_PORT/api/status" 2>/dev/null)
ST_OK=$(echo "$ST" | sed -n 's/.*"status":"\([^"]*\)".*/\1/p')
LLM_OK=$(echo "$ST" | sed -n 's/.*"llm_available":\([^,}]*\).*/\1/p')
if [ "$ST_OK" = "ok" ]; then line "- ✅ 后端 /api/status ok（llm_available=$LLM_OK）"; ok=$((ok+1))
else line "- ❌ 后端 /api/status 异常：$ST"; fail=$((fail+1)); fi

# 4. 主聊天 /chat/stream（流式，15s）
if [ -n "$TOKEN" ]; then
  CHAT=$(curl -s -N -m 15 -X POST "http://127.0.0.1:$BE_PORT/api/chat/stream" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"message":"ping","course":"computer_network"}' 2>/dev/null)
  NDATA=$(echo "$CHAT" | grep -c '^data:' )
  if [ "$NDATA" -gt 3 ]; then line "- ✅ /chat/stream 流式正常（$NDATA 个 data 帧）"; ok=$((ok+1))
  else line "- ⚠️ /chat/stream 帧数偏少（$NDATA），可能 LLM 抖动"; warn=$((warn+1)); fi
fi

# 5. /profile/build（15s）
if [ -n "$TOKEN" ]; then
  PB_CODE=$(curl -s -m 15 -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:$BE_PORT/api/profile/build" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"message":"hello","history":[]}' 2>/dev/null)
  if [ "$PB_CODE" = "200" ]; then line "- ✅ /profile/build 200"; ok=$((ok+1))
  else line "- ⚠️ /profile/build HTTP $PB_CODE"; warn=$((warn+1)); fi
fi

# 6. /tutor/enhanced-answer（35s，已加 wait_for 超时降级，最坏 ~27s）
if [ -n "$TOKEN" ]; then
  EA_CODE=$(curl -s -m 35 -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:$BE_PORT/api/tutor/enhanced-answer" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"question":"tcp handshake","profile":{},"course":"computer_network","quick_mode":true}' 2>/dev/null)
  if [ "$EA_CODE" = "200" ]; then line "- ✅ /tutor/enhanced-answer 200"; ok=$((ok+1))
  elif [ "$EA_CODE" = "000" ]; then line "- ❌ /tutor/enhanced-answer 20s 超时挂起（HTTP 000，需修）"; fail=$((fail+1))
  else line "- ⚠️ /tutor/enhanced-answer HTTP $EA_CODE"; warn=$((warn+1)); fi
fi

# 7. 类型检查 vue-tsc（60s）
TC_OUT=$(npx vue-tsc --build 2>&1)
TC_ERR=$(echo "$TC_OUT" | grep -c "error TS")
if [ "$TC_ERR" = "0" ]; then line "- ✅ vue-tsc 0 错误"; ok=$((ok+1))
else line "- ❌ vue-tsc $TC_ERR 错误"; fail=$((fail+1)); echo "$TC_OUT" | grep "error TS" | head -5 >> "$REPORT"; fi

# 8. Vite 模块转换抽检（5 个关键视图 + App）
MOD_FAIL=0
for m in src/App.vue src/views/ChatView.vue src/views/DashboardView.vue src/views/KnowledgeGraphView.vue src/views/SettingsView.vue src/views/ResourceView.vue src/views/KnowledgeAdminView.vue; do
  mc=$(curl -s -m 8 -o /dev/null -w "%{http_code}" "http://127.0.0.1:$FE_PORT/$m" 2>/dev/null)
  if [ "$mc" != "200" ]; then line "- ⚠️ Vite 转换 $m HTTP $mc"; MOD_FAIL=$((MOD_FAIL+1)); fi
done
if [ "$MOD_FAIL" = "0" ]; then line "- ✅ Vite 模块转换抽检 7/7 通过"; ok=$((ok+1))
else line "- ❌ Vite 模块转换 $MOD_FAIL 失败"; fail=$((fail+1)); fi

line ""
line "**汇总：✅$ok / ⚠️$warn / ❌$fail**"
line ""
echo "QA done: ok=$ok warn=$warn fail=$fail"
