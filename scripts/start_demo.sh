#!/bin/bash
# ============================================================
# 芒得很职 软件竞赛演示启动脚本 (Linux/macOS)
# 等价于 start.sh，已内置 seed 数据与 demo/demo123456 演示账号
# 启动后浏览器打开 http://localhost:5173 按演示脚本操作
#   演示脚本: tools/demo_walkthrough.md
#   旁白稿:   tools/demo_narration.md
# ============================================================
set -e

echo "============================================================"
echo "  芒得很职 软件竞赛演示启动脚本 (Linux/macOS)"
echo "  启动后浏览器打开 http://localhost:5173 按演示脚本操作"
echo "  演示脚本: tools/demo_walkthrough.md"
echo "============================================================"
echo ""

exec "$(dirname "$0")/start.sh"
