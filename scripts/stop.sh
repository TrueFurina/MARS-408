#!/usr/bin/env bash
# MARS-408 停止脚本 (Linux/Mac)
set -e

echo "============================================================"
echo "  MARS-408 停止脚本 (Linux/Mac)"
echo "============================================================"
echo ""

echo "正在停止 MARS-408 前后端进程..."

# 杀掉 uvicorn / python 后端
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "python main.py" 2>/dev/null || true

# 杀掉 vite / node 前端
pkill -f "vite" 2>/dev/null || true
pkill -f "node.*study-help-pro" 2>/dev/null || true

echo ""
echo "[完成] 已向 MARS-408 前后端发送停止信号。"
echo "  若仍有残留（如孤立的 node/python 子进程），"
echo "  请手动执行: pkill -f 'uvicorn|vite'"
echo ""
