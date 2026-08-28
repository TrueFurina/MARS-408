#!/usr/bin/env bash
# ============================================================
# 封包核销一键检查脚本（第十六循环P1）
# 用途：提交前自动检查赛题 6 项提交材料存在性，服务用户"封包核销"待办
# 用法：bash scripts/check_submission_ready.sh
# 对应：《提交包封包核对清单-2026-08-11.md》一、赛题 6 项提交要求核销表
# ============================================================
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PASS=0
FAIL=0

check() { # check <描述> <测试命令...>
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "✅ $desc"
    PASS=$((PASS+1))
  else
    echo "❌ $desc"
    FAIL=$((FAIL+1))
  fi
}

echo "== MARS-408 提交包封包核销检查 =="

# 1. 演示 PPT
check "演示 PPT（01_演示PPT/MARS-408_软件杯演示.pptx）" test -f "archive/08013417_参赛快照/08013417介绍/01_演示PPT/MARS-408_软件杯演示.pptx"

# 2. 可完整运行源码（submission/04_源码/ zip）
check "源码 zip（submission/04_源码/MARS-408_source.zip）" test -f "submission/04_源码/MARS-408_source.zip"

# 3. 演示视频（03_演示视频/ 有 mp4；注意旧视频含 TTS 需重录）
check "演示视频文件（03_演示视频/ 含 mp4）" bash -c 'ls "archive/08013417_参赛快照/08013417介绍/03_演示视频/"*.mp4 >/dev/null 2>&1'
if ls "archive/08013417_参赛快照/08013417介绍/03_演示视频/"*.mp4 >/dev/null 2>&1; then
  echo "   ⚠️ 视频存在但为旧版（含 TTS 演示），需按新分镜脚本重录"
fi

# 4. 开发类型（Web 应用，无需文件，直接确认）
echo "✅ 开发类型（Web 应用：Vue3 + FastAPI）"
PASS=$((PASS+1))

# 5. 配套文档（02_配套文档/ 8 份 docx）
DOC_COUNT=$(ls "archive/08013417_参赛快照/08013417介绍/02_配套文档/"*.docx 2>/dev/null | wc -l)
if [ "$DOC_COUNT" -ge 8 ]; then
  echo "✅ 配套文档（02_配套文档/ $DOC_COUNT 份 docx，≥8 份）"
  PASS=$((PASS+1))
else
  echo "❌ 配套文档（02_配套文档/ 仅 $DOC_COUNT 份，需 ≥8）"
  FAIL=$((FAIL+1))
fi

# 6. AI Coding 工具说明（开发说明书含 AI 工具声明）
check "AI Coding 说明（开发说明书含 AI 工具声明）" grep -qE "AI.*工具|Claude|AtomCode|开源声明" "documents/开发说明书.md"

echo ""
echo "== 检查结果：$PASS 通过 / $FAIL 未通过 =="
if [ "$FAIL" -eq 0 ]; then
  echo "✅ 全部就绪，可进行封包最终核销（视频重录后更新状态）"
else
  echo "⚠️ 有 $FAIL 项未通过，请按《提交包封包核对清单》处理后重跑"
  exit 1
fi
