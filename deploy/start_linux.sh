#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 芒得很职 / study-help-pro  一键启动绿色包 (Linux / macOS / WSL / Git Bash)
#
# 职责：前置自检 -> 后台拉起后端 (uvicorn main:app) -> 轮询健康检查 -> 打印访问信息
# 红线：不修改任何既有文件、不 kill 任何不属于本次启动的进程。
#       任何一项前置检查不过，都以人类可读的指引 + exit 2 终止。
#
# 用法：
#   ./deploy/start_linux.sh                 # 默认 127.0.0.1:8002
#   PORT=8007 ./deploy/start_linux.sh       # 端口被占时换端口（排障用）
# ---------------------------------------------------------------------------
set -euo pipefail

# ── 可配置项（均可用环境变量覆盖）────────────────────────────────────────
PORT="${PORT:-8002}"
HOST="${HOST:-127.0.0.1}"
HEALTH_PATH="${HEALTH_PATH:-/api/status}"
STARTUP_TIMEOUT="${STARTUP_TIMEOUT:-60}"
POLL_INTERVAL="${POLL_INTERVAL:-2}"
# Python 版本门槛。默认值取自项目事实源：
#   py-server/pyproject.toml  requires-python = ">=3.12"
#   py-server/.python-version  3.12
# 如需收紧为 3.13+，运行前 `export PY_MIN_MINOR=13` 即可，无需改脚本。
PY_MIN_MAJOR="${PY_MIN_MAJOR:-3}"
PY_MIN_MINOR="${PY_MIN_MINOR:-12}"

# ── 路径推导（脚本放在 deploy/ 下，仓库根为其上一级）────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PY_SERVER_DIR="${REPO_ROOT}/py-server"
VENV_DIR="${PY_SERVER_DIR}/.venv"
MODEL_DIR="${PY_SERVER_DIR}/models/e5-base-v2"
LOG_DIR="${SCRIPT_DIR}/logs"
LOG_FILE="${LOG_DIR}/backend-$(date +%Y%m%d-%H%M%S).log"
PID_FILE="${LOG_DIR}/backend.pid"

info() { printf '[INFO ] %s\n' "$*"; }
ok()   { printf '[ OK  ] %s\n' "$*"; }
warn() { printf '[WARN ] %s\n' "$*"; }
err()  { printf '[FAIL ] %s\n' "$*" >&2; }
die()  { err "$1"; exit "${2:-2}"; }

mkdir -p "${LOG_DIR}"

echo "===================================================================="
echo " 芒得很职 one-click launcher (backend)"
echo " repo   : ${REPO_ROOT}"
echo " server : ${PY_SERVER_DIR}"
echo " target : http://${HOST}:${PORT}${HEALTH_PATH}"
echo "===================================================================="

# ── 步骤 1/6：检查 Python 解释器与版本 ───────────────────────────────────
info "[1/6] Checking Python interpreter ..."

detect_python() {
    local candidate=""
    for candidate in \
        "${VENV_DIR}/bin/python" \
        "${VENV_DIR}/bin/python3" \
        "${VENV_DIR}/Scripts/python.exe" \
        "${VENV_DIR}/Scripts/python"; do
        if [ -x "${candidate}" ]; then
            printf '%s\n' "${candidate}"
            return 0
        fi
    done
    if command -v python3 >/dev/null 2>&1; then command -v python3; return 0; fi
    if command -v python >/dev/null 2>&1; then command -v python; return 0; fi
    return 1
}

PY=""
if ! PY="$(detect_python)"; then
    err "No Python interpreter found."
    err "  Install Python >= ${PY_MIN_MAJOR}.${PY_MIN_MINOR} first, e.g.:"
    err "    Debian/Ubuntu : sudo apt-get install -y python3 python3-venv"
    err "    macOS (brew)  : brew install python@3.12"
    err "  Then re-run this script."
    die "Python not found. Aborting." 2
fi
ok "Python interpreter: ${PY}"

if ! PY_VER="$("${PY}" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"; then
    die "Python interpreter at ${PY} is not runnable. Aborting." 2
fi

if ! PY_MIN_MAJOR="${PY_MIN_MAJOR}" PY_MIN_MINOR="${PY_MIN_MINOR}" "${PY}" -c \
    'import os, sys
maj = int(os.environ["PY_MIN_MAJOR"]); mnr = int(os.environ["PY_MIN_MINOR"])
sys.exit(0 if sys.version_info[:2] >= (maj, mnr) else 1)'; then
    err "Python version ${PY_VER} is too old (need >= ${PY_MIN_MAJOR}.${PY_MIN_MINOR})."
    err "  Please install Python ${PY_MIN_MAJOR}.${PY_MIN_MINOR}+ and rebuild the venv:"
    err "    cd py-server && uv sync --frozen"
    die "Python version check failed. Aborting." 2
fi
ok "Python version ${PY_VER} >= ${PY_MIN_MAJOR}.${PY_MIN_MINOR}"

# ── 步骤 2/6：检查虚拟环境 ───────────────────────────────────────────────
info "[2/6] Checking virtual environment at ${VENV_DIR} ..."
if [ ! -d "${VENV_DIR}" ]; then
    err "Virtual environment not found: ${VENV_DIR}"
    err "  Please create it first (pick ONE of the following):"
    err "    A. uv  (authoritative, uses uv.lock):"
    err "         cd py-server && uv sync --frozen"
    err "    B. plain venv + pip:"
    err "         cd py-server && python -m venv .venv"
    err "         cd py-server && ./.venv/bin/pip install -e ."
    err "  If 'uv' is missing:  curl -LsSf https://astral.sh/uv/install.sh | sh"
    die "Virtual environment missing. Aborting." 2
fi
ok "Virtual environment found."

# ── 步骤 3/6：检查 E5 embedding 模型 ─────────────────────────────────────
info "[3/6] Checking E5 model at ${MODEL_DIR} ..."
if [ ! -d "${MODEL_DIR}" ]; then
    err "Embedding model not found: ${MODEL_DIR}"
    err "  The model (intfloat/e5-base-v2, 768-dim) is NOT in version control."
    err "  Please fetch it once (run from the repo root):"
    err "    cd py-server && ${PY} ../scripts/fetch_e5_model.py"
    err "  (scripts/fetch_e5_model.py lives in the repo-root scripts/ dir, not py-server/scripts/.)"
    die "E5 model missing. Aborting." 2
fi
ok "E5 model found."

# ── 步骤 4/6：检查端口占用 ───────────────────────────────────────────────
info "[4/6] Checking port ${PORT} on ${HOST} ..."
port_in_use() {
    HOST="${HOST}" PORT="${PORT}" "${PY}" -c \
    "import os, socket, sys
s = socket.socket(); s.settimeout(1)
rc = s.connect_ex((os.environ['HOST'], int(os.environ['PORT'])))
s.close()
sys.exit(0 if rc == 0 else 1)"
}
if port_in_use; then
    err "Port ${PORT} is ALREADY IN USE. This script will NOT kill someone else's process."
    err "  Find who owns it:"
    err "    Linux  : sudo lsof -i :${PORT}   |   sudo ss -lptn 'sport = :${PORT}'"
    err "    macOS  : sudo lsof -i :${PORT}"
    err "    Windows: netstat -ano | findstr :${PORT}   (last column = PID)"
    err "  Then either stop that process yourself, or start on another port:"
    err "    PORT=8007 ./deploy/start_linux.sh"
    die "Port ${PORT} occupied. Aborting." 2
fi
ok "Port ${PORT} is free."

# ── 步骤 5/6：后台启动后端并等待就绪 ─────────────────────────────────────
info "[5/6] Starting backend: uvicorn main:app --host ${HOST} --port ${PORT}"
info "      working dir : ${PY_SERVER_DIR}"
info "      log file    : ${LOG_FILE}"

cd "${PY_SERVER_DIR}"
# shellcheck disable=SC2086
# --workers 1 is mandatory: main.py enforces a single-writer lock on
# py-server/vectordb_data/.import_writer.lock and refuses to boot with >1 worker.
nohup "${PY}" -m uvicorn main:app --host "${HOST}" --port "${PORT}" --workers 1 \
    > "${LOG_FILE}" 2>&1 &
BACKEND_PID=$!
printf '%s\n' "${BACKEND_PID}" > "${PID_FILE}"
disown "${BACKEND_PID}" 2>/dev/null || true
ok "Backend process started (pid=${BACKEND_PID})."

health_ok() {
    HOST="${HOST}" PORT="${PORT}" HEALTH_PATH="${HEALTH_PATH}" "${PY}" -c \
    "import os, sys, urllib.request
url = 'http://' + os.environ['HOST'] + ':' + os.environ['PORT'] + os.environ['HEALTH_PATH']
try:
    with urllib.request.urlopen(url, timeout=3) as resp:
        sys.exit(0 if resp.status == 200 else 1)
except Exception:
    sys.exit(1)"
}

info "      waiting for readiness (timeout ${STARTUP_TIMEOUT}s, first boot ~30s) ..."
DEADLINE=$(( SECONDS + STARTUP_TIMEOUT ))
READY=0
while [ "${SECONDS}" -lt "${DEADLINE}" ]; do
    if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
        err "Backend process (pid=${BACKEND_PID}) exited before becoming ready."
        err "  ---- last 30 lines of ${LOG_FILE} ----"
        tail -n 30 "${LOG_FILE}" >&2 || true
        die "Backend crashed during startup. Aborting." 2
    fi
    if health_ok; then
        READY=1
        break
    fi
    printf '.'
    sleep "${POLL_INTERVAL}"
done
printf '\n'

if [ "${READY}" -ne 1 ]; then
    err "Backend did not become ready within ${STARTUP_TIMEOUT}s."
    err "  ---- last 30 lines of ${LOG_FILE} ----"
    tail -n 30 "${LOG_FILE}" >&2 || true
    err "  ---- how to stop it ----"
    err "    kill ${BACKEND_PID}"
    die "Readiness timeout. Aborting." 2
fi
ok "Backend is ready."

# ── 步骤 6/6：成功输出 ───────────────────────────────────────────────────
echo "===================================================================="
ok "[6/6] Backend is UP."
echo ""
echo "  Backend URL    : http://${HOST}:${PORT}"
echo "  Health probe   : http://${HOST}:${PORT}${HEALTH_PATH}"
echo "  API docs       : http://${HOST}:${PORT}/docs"
echo "  Log file       : ${LOG_FILE}"
echo "  PID file       : ${PID_FILE}  (pid=${BACKEND_PID})"
echo ""
echo "  Stop backend   : kill ${BACKEND_PID}"
echo "                   (or: kill \$(cat ${PID_FILE}))"
echo "  Tail log       : tail -f ${LOG_FILE}"
echo ""
echo "  Frontend (run in ANOTHER terminal, from repo root):"
echo "    npm install          # first time only"
echo "    npm run dev          # dev server (vite)"
echo "    # or, to serve the prebuilt dist/:"
echo "    npm run preview"
echo "===================================================================="
exit 0
