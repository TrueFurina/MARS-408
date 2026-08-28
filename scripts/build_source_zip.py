# 生成 submission/04_源码/MARS-408_source.zip
# 匹配 submission/04_源码/README.md 约定：
#   排除 node_modules/.venv/dist/__pycache__/.fixvenv/.fixcn/.lxmlfix/.git/*.log/vectordb_data/.env
#   包含 py-server(含 models/neural_mixer_trained.pt)/src/public/Dockerfile/docker-compose.yml/package.json/vite.config.ts/.env.example/README.md
import os, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "submission" / "04_源码" / "MARS-408_source.zip"

EXCLUDE_DIRS = {
    ".venv", "__pycache__", ".pytest_cache", ".git",
    "node_modules", "dist", "milvus_lite_data", "vectordb_data",
    "plots", "sessions", "data", "iq_run_tmp",
    ".workbuddy", ".sessions", ".codebuddy",
    ".fixvenv", ".fixcn", ".lxmlfix", "archive", "submission", "build",
    "documents", "deliverables", "design-system", "dist-qa", "dist-rem",
    "dist-test", "dist-verify", "dist-vuecheck",
}
EXCLUDE_EXTS = {".pyc", ".pyo", ".so", ".log", ".safetensors"}
# 真实密钥不进包；仅 .env.example 进包
EXCLUDE_NAMES = {".env", ".env.local"}

INCLUDE_ROOT_FILES = [
    "Dockerfile", "docker-compose.yml", "package.json", "package-lock.json",
    "vite.config.ts", "tsconfig.json", "tsconfig.app.json", "tsconfig.node.json",
    "env.d.ts", "index.html", "README.md", ".env.example", "start.bat", "start.ps1",
    "serve_spa.py", "scripts/build_portable.py", ".gitignore", "eslint.config.js",
]

def excluded(p: Path) -> bool:
    if p.name in EXCLUDE_NAMES:
        return True
    if p.suffix in EXCLUDE_EXTS:
        return True
    # py-server/models 下仅保留 neural_mixer_trained.pt；E5 等下载型大模型不进包
    rel = p.relative_to(ROOT).parts
    if len(rel) >= 3 and rel[0] == "py-server" and rel[1] == "models":
        if p.name != "neural_mixer_trained.pt":
            return True
    for part in p.parts:
        if part in EXCLUDE_DIRS:
            return True
    return False

def add_tree(zf, base: Path, prefix: str = ""):
    for f in sorted(base.rglob("*")):
        if not f.is_file():
            continue
        rel = (prefix + f.relative_to(ROOT).as_posix())
        if excluded(f):
            continue
        zf.write(f, rel)

os.makedirs(OUT.parent, exist_ok=True)
if OUT.exists():
    OUT.unlink()

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
    for name in INCLUDE_ROOT_FILES:
        p = ROOT / name
        if p.exists() and p.is_file():
            zf.write(p, name)
    add_tree(zf, ROOT / "py-server", "")
    add_tree(zf, ROOT / "src", "")
    add_tree(zf, ROOT / "public", "")

size_mb = OUT.stat().st_size / (1024 * 1024)
print(f"OK -> {OUT}")
print(f"Zip 大小: {size_mb:.1f} MB  (1GB 限制: {'符合' if size_mb < 1000 else '超出'})")
