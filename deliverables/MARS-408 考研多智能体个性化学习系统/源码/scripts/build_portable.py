# ============================================================
# MARS-408 作品打包脚本（符合 1GB 提交限制）
# 用法：python build_portable.py
# 输出：build/mars-408-submit.zip
#
# 已排除的大文件（超 1GB 限制）：
#   - documents/教材/*.pdf  (408教材PDF，~450MB)
#   - py-server/models/     (E5 模型，~420MB，保留但可选)
#   - *.pt, *.onnx, *.pth   (训练权重)
# ============================================================

import os
import sys
import zipfile
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
OUTPUT_DIR = ROOT / "build"
OUTPUT_ZIP = OUTPUT_DIR / "mars-408-submit.zip"

# 需要排除的目录/文件模式
EXCLUDES = {
    ".venv", "__pycache__", ".pytest_cache", ".git",
    "node_modules", "milvus_lite_data", "vectordb_data",
    "plots", "sessions", "data", "iq_run_tmp",
    ".workbuddy", ".sessions", ".codebuddy",
    # 超 1GB 限制的大文件
    "教材",           # documents/教材/ 下的 PDF 教材 (~450MB)
}

# 需要排除的文件扩展名
EXCLUDE_EXTS = {".pyc", ".pyo", ".so", ".pt", ".pth", ".onnx", ".bin"}

# 大文件后缀（超过 10MB 的文件会被记录）
LARGE_EXTS = {".pdf", ".docx", ".doc", ".zip", ".tar", ".gz"}


def should_exclude(path: Path, rel_path: str) -> bool:
    """判断是否应该排除该文件"""
    # 检查目录排除
    for part in path.parts:
        if part in EXCLUDES:
            return True
    # 检查文件扩展名
    if path.suffix in EXCLUDE_EXTS:
        return True
    # 检查大文件
    if path.suffix in LARGE_EXTS and path.stat().st_size > 10 * 1024 * 1024:
        return True
    return False


def build():
    print("=" * 50)
    print("MARS-408 作品打包工具（1GB 限制版）")
    print("=" * 50)

    # 1. 构建前端
    print("\n[1/4] 构建前端...")
    if not (ROOT / "dist" / "index.html").exists():
        try:
            subprocess.run(["npx", "vite", "build"], cwd=ROOT,
                         capture_output=True, timeout=120)
            print("  前端构建完成")
        except Exception as e:
            print(f"  ⚠️ 前端构建失败: {e}")
    else:
        print("  前端已构建，跳过")

    # 2. 清理输出目录
    print("\n[2/4] 准备输出目录...")
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    # 3. 打包文件
    print("\n[3/4] 打包文件（排除大文件）...")
    total_size = 0
    file_count = 0
    excluded_count = 0

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        # 添加根目录文件
        for f in ["start.bat", "start.ps1", "INSTALL.md", "README.md",
                  ".env.example", "docker-compose.yml", "Dockerfile",
                  "serve_spa.py", "build_portable.py"]:
            p = ROOT / f
            if p.exists():
                zf.write(p, f)
                print(f"  + {f}")
                total_size += p.stat().st_size
                file_count += 1

        # 添加 py-server 目录
        py_server = ROOT / "py-server"
        for file in py_server.rglob("*"):
            rel = file.relative_to(ROOT)
            if should_exclude(file, str(rel)):
                excluded_count += 1
                continue
            if file.is_file():
                zf.write(file, str(rel))
                total_size += file.stat().st_size
                file_count += 1
                if file_count % 50 == 0:
                    print(f"  已处理 {file_count} 个文件...")

        # 添加前端构建产物
        dist_dir = ROOT / "dist"
        if dist_dir.exists():
            for file in dist_dir.rglob("*"):
                if file.is_file():
                    rel = file.relative_to(ROOT)
                    zf.write(file, str(rel))
                    total_size += file.stat().st_size
                    file_count += 1

        # 添加文档（不含PDF教材）
        doc_dir = ROOT / "documents"
        if doc_dir.exists():
            for file in doc_dir.rglob("*"):
                rel = file.relative_to(ROOT)
                if should_exclude(file, str(rel)):
                    excluded_count += 1
                    continue
                if file.is_file():
                    zf.write(file, str(rel))
                    total_size += file.stat().st_size
                    file_count += 1

        # 添加 design-system
        ds_dir = ROOT / "design-system"
        if ds_dir.exists():
            for file in ds_dir.rglob("*"):
                if file.is_file():
                    rel = file.relative_to(ROOT)
                    zf.write(file, str(rel))
                    total_size += file.stat().st_size
                    file_count += 1

    # 4. 输出结果
    size_mb = total_size / (1024 * 1024)
    zip_size_mb = OUTPUT_ZIP.stat().st_size / (1024 * 1024)
    print(f"\n[4/4] 打包完成!")
    print(f"  输出文件: {OUTPUT_ZIP}")
    print(f"  文件数量: {file_count}")
    print(f"  排除文件: {excluded_count}")
    print(f"  原始大小: {size_mb:.1f} MB")
    print(f"  Zip 大小: {zip_size_mb:.1f} MB")
    print(f"  1GB 限制: {'✅ 符合' if zip_size_mb < 1000 else '❌ 超出'}")
    print(f"\n  使用方法:")
    print(f"  1. 解压 mars-408-submit.zip")
    print(f"  2. 双击 start.bat")
    print(f"  3. 浏览器打开 http://localhost:8002")
    print(f"  4. 登录 demo / demo123456")


if __name__ == "__main__":
    build()