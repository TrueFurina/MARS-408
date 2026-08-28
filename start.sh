#!/bin/bash
# ============================================================
# MARS-408 一键启动脚本 (Linux/macOS)
# 基于 GOMARL 与 FrugalRAG 的 408 考研个性化学习系统
# ============================================================

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "============================================================"
echo "  MARS-408 一键启动脚本 (Linux/macOS)"
echo "============================================================"
echo ""

# ── 步骤0：单实例守护：清理可能残留的旧实例 ──
echo "[0/3] 清理可能残留的旧实例（避免端口被占用）..."
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
sleep 2

# ── 步骤1：启动后端 ──
echo "[1/3] 启动 FastAPI 后端..."
cd "$PROJECT_ROOT/py-server"

# 检查 .venv
if [ ! -f ".venv/bin/python" ]; then
    echo "[ERROR] 后端 .venv 不存在，请先运行: cd py-server && uv sync"
    exit 1
fi

# 检查 config.json
if [ ! -f "config.json" ]; then
    echo "[WARN] config.json 不存在，将使用默认配置"
fi

echo "      后端地址: http://127.0.0.1:8002"
echo "      API文档: http://127.0.0.1:8002/docs"
echo ""

.venv/bin/python main.py --workers 1 &
BACKEND_PID=$!

# ── 步骤2：等待后端 ──
echo "[2/3] 等待后端初始化完成（约5秒）..."
sleep 5

# 健康检查
echo "      验证 /api/status 端点..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8002/api/status 2>/dev/null || echo "000")
if [ "$STATUS" = "200" ]; then
    echo "      后端就绪 (HTTP 200)"
else
    echo "[WARN] 后端尚未就绪 (HTTP $STATUS)，可能需要更多启动时间"
    echo "      请稍后访问 http://127.0.0.1:8002/api/status 确认"
fi

# ── 步骤3：启动前端 ──
echo ""
echo "[3/3] 启动前端开发服务器..."
cd "$PROJECT_ROOT"

if [ ! -d "node_modules" ]; then
    echo "[ERROR] node_modules 不存在，请先运行: npm install"
    exit 1
fi

echo "      推荐访问（后端已托管前端，单端口无漂移）: http://127.0.0.1:8002"
echo "      前端热更新开发服务器: http://localhost:5173 （API 经 Vite 代理转发到 8002）"
echo ""

npm run dev &
FRONTEND_PID=$!

echo "============================================================"
echo "  启动完成！"
echo "  推荐访问（后端已托管前端，单端口无漂移）: http://127.0.0.1:8002"
echo "  前端热更新开发服务器: http://localhost:5173 （API 经 Vite 代理转发到 8002）"
echo "  后端: http://127.0.0.1:8002"
echo "  API文档: http://127.0.0.1:8002/docs"
echo "  Backend PID: $BACKEND_PID"
echo "  Frontend PID: $FRONTEND_PID"
echo "============================================================"
echo ""
echo "提示: 按 Ctrl+C 停止所有进程"
echo ""

# 等待任一进程退出
wait -n $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
echo "某进程已退出，正在清理..."
kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
