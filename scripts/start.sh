#!/bin/bash
# ============================================================
# MARS-408 一键启动脚本 (Linux/macOS)
# 基于 GOMARL 与 FrugalRAG 的 408 考研个性化学习系统
#
# 用法:
#   chmod +x scripts/start.sh
#   ./scripts/start.sh
#
# 功能:
#   1. 检查 Python >= 3.12 / Node >= 20
#   2. 自动创建 venv 并安装后端依赖（首次运行）
#   3. 自动安装前端依赖（首次运行）
#   4. 启动后端 (http://127.0.0.1:8002)
#   5. 启动前端 (http://127.0.0.1:5173)
#   6. 打印访问地址与演示账号
# ============================================================

set -e

# ── 定位项目根目录 ──
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "============================================================"
echo "  MARS-408 一键启动脚本 (Linux/macOS)"
echo "  408 考研个性化学习系统"
echo "============================================================"
echo ""

# ── 步骤 0: 清理可能残留的旧进程 ──
echo "[0/6] 清理可能残留的旧实例..."
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
sleep 1

# ── 步骤 1: 检查 Python >= 3.12 ──
echo "[1/6] 检查 Python 版本..."
if ! command -v python3 &>/dev/null; then
    echo "  [ERROR] 未检测到 python3，请安装 Python 3.12+"
    echo "          Ubuntu/Debian: sudo apt install python3.12 python3.12-venv"
    echo "          macOS (brew):  brew install python@3.12"
    exit 1
fi
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 12 ]; }; then
    echo "  [ERROR] Python 版本过低: $PY_VERSION (需要 >= 3.12)"
    exit 1
fi
echo "  Python $PY_VERSION  [OK]"

# ── 步骤 2: 检查 Node.js ──
echo "[2/6] 检查 Node.js..."
if ! command -v node &>/dev/null; then
    echo "  [WARN] 未检测到 Node.js，前端热更新将不可用"
    echo "         后端仍可启动并提供预构建前端 (http://127.0.0.1:8002)"
    HAS_NODE=false
else
    NODE_VERSION=$(node --version 2>/dev/null | sed 's/v//' || echo "0.0.0")
    NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1)
    if [ "$NODE_MAJOR" -lt 20 ]; then
        echo "  [WARN] Node.js 版本 $NODE_VERSION 偏低 (建议 >= 20)"
        HAS_NODE=false
    else
        echo "  Node.js $NODE_VERSION  [OK]"
        HAS_NODE=true
    fi
fi

# ── 步骤 3: 创建/激活 venv 并安装后端依赖 ──
echo "[3/6] 准备后端虚拟环境..."
cd "$PROJECT_ROOT/py-server"

if [ ! -d ".venv" ]; then
    echo "  首次运行：创建虚拟环境..."
    python3 -m venv .venv
fi

# 激活 venv
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "  [ERROR] 虚拟环境创建失败，请手动运行: cd py-server && python3 -m venv .venv"
    exit 1
fi

# 检查依赖是否已安装（fastapi 是核心依赖，存在则认为已装）
if ! python -c "import fastapi" 2>/dev/null; then
    echo "  安装后端依赖（首次运行较慢，约 2-5 分钟）..."
    # 优先 uv（更快），回退 pip
    if command -v uv &>/dev/null; then
        uv sync --no-dev 2>/dev/null || pip install -e . -q
    else
        pip install -e . -q 2>/dev/null || {
            echo "  [WARN] 完整安装失败，尝试安装核心依赖..."
            pip install fastapi uvicorn pydantic -q
        }
    fi
    echo "  后端依赖安装完成"
else
    echo "  后端依赖已就绪"
fi

# ── 步骤 4: 安装前端依赖（若需要） ──
echo "[4/6] 准备前端..."
cd "$PROJECT_ROOT"

if [ "$HAS_NODE" = true ]; then
    if [ ! -d "node_modules" ]; then
        echo "  安装前端依赖（首次运行）..."
        npm install --silent 2>/dev/null || npm install
        echo "  前端依赖安装完成"
    else
        echo "  前端依赖已就绪"
    fi
else
    echo "  跳过前端依赖安装（无 Node.js）"
fi

# ── 步骤 5: 启动后端 ──
echo "[5/6] 启动后端 (FastAPI @ :8002)..."
cd "$PROJECT_ROOT/py-server"
python main.py &
BACKEND_PID=$!

# 等待后端就绪
echo "  等待后端初始化..."
for i in $(seq 1 30); do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8002/api/status 2>/dev/null || echo "000")
    if [ "$STATUS" = "200" ]; then
        echo "  后端就绪 (HTTP 200)"
        # 打印 /api/status 内容供确认
        curl -s http://127.0.0.1:8002/api/status 2>/dev/null | python -m json.tool 2>/dev/null || true
        break
    fi
    sleep 2
    if [ $i -eq 30 ]; then
        echo "  [WARN] 后端 30s 内未就绪 (HTTP $STATUS)，请稍后手动检查 http://127.0.0.1:8002/api/status"
    fi
done

# ── 步骤 6: 启动前端 ──
echo "[6/6] 启动前端 (Vite @ :5173)..."
cd "$PROJECT_ROOT"

if [ "$HAS_NODE" = true ] && [ -d "node_modules" ]; then
    npm run dev &
    FRONTEND_PID=$!
    echo ""
    echo "============================================================"
    echo "  启动完成！"
    echo "============================================================"
    echo "  前端开发服务器:  http://localhost:5173"
    echo "  后端 API:        http://127.0.0.1:8002"
    echo "  API 文档:        http://127.0.0.1:8002/docs"
    echo "  健康检查:        http://127.0.0.1:8002/api/status"
    echo ""
    echo "  演示账号:        demo / demo123456"
    echo "  Backend PID:     $BACKEND_PID"
    echo "  Frontend PID:    $FRONTEND_PID"
    echo "============================================================"
    echo ""
    echo "  提示: 按 Ctrl+C 停止所有进程"
    echo ""

    # 等待任一进程退出
    wait -n $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    echo "某进程已退出，正在清理..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
else
    echo ""
    echo "============================================================"
    echo "  启动完成（仅后端模式）！"
    echo "============================================================"
    echo "  后端已托管前端:  http://127.0.0.1:8002"
    echo "  API 文档:        http://127.0.0.1:8002/docs"
    echo "  健康检查:        http://127.0.0.1:8002/api/status"
    echo ""
    echo "  演示账号:        demo / demo123456"
    echo "  Backend PID:     $BACKEND_PID"
    echo "============================================================"
    echo ""
    echo "  提示: 按 Ctrl+C 停止后端"
    echo ""
    wait $BACKEND_PID 2>/dev/null || true
fi
