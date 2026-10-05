# ============================================================
# 芒得很职 作品打包脚本（符合 1GB 提交限制）
# 用法：python scripts/build_portable.py            # 产出 build/mangdehenzhi-submit.zip
#       python scripts/build_portable.py --dry-run  # 打包到临时目录 + 自检 + 立即删除
# 输出：build/mangdehenzhi-submit.zip
#
# ⚠️⚠️ 安全红线（改动排除表前必读）⚠️⚠️
#   本脚本的产物是【对外交付包】，会交到评委/第三方手上。
#   1) `.env` 永禁进入交付包。py-server/.env 内含真实凭证：
#      XF_APP_ID / XF_API_KEY / XF_API_SECRET / XF_API_PASSWORD / XF_SEARCH_PASSWORD
#      AUTH_SECRET（JWT 签名密钥，泄露=可自签任意用户 token 含 admin）
#      ADMIN_PASSWORD（管理端明文口令）
#   2) `.env` 必须写【精确串】，绝不可写成 `.env*` —— 会误伤 `.env.example`，
#      而提交清单（submission/00_提交清单.md:52）明确要求源码包保留 `.env.example`
#      （评委靠它配置自己的 key）。
#   3) 本脚本末尾有【打包后自检】，任一检查不过即 exit 1。不要绕过它。
#
# 已排除的大文件（超 1GB 限制）：
#   - documents/教材/*.pdf  (408教材PDF，~450MB)
#   - py-server/models/     (E5 模型，~420MB，保留但可选)
#   - *.pt, *.onnx, *.pth   (训练权重，白名单声明的文件除外)
# ============================================================

import argparse
import fnmatch
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "build"
OUTPUT_ZIP = OUTPUT_DIR / "mangdehenzhi-submit.zip"
ENV_EXAMPLE_PATH = "py-server/.env.example"

# 需要排除的目录/文件名（按路径分段【精确匹配】）
EXCLUDES = {
    ".venv", "__pycache__", ".pytest_cache", ".git",
    "node_modules", "milvus_lite_data", "vectordb_data",
    "plots", "sessions", "data", "iq_run_tmp",
    ".workbuddy", ".sessions", ".codebuddy",
    # 超 1GB 限制的大文件
    "教材",           # documents/教材/ 下的 PDF 教材 (~450MB)
    # ── 安全 / 交付卫生（勿删，见文件头红线说明）──
    ".env",           # 真实凭证，精确匹配；不可写 .env*，否则会误伤 .env.example
    ".eggs",
    ".mypy_cache",
}

# 需要排除的目录/文件名（按路径分段【通配符匹配】）
# 注意：EXCLUDES 是精确匹配，通配符模式必须放在这里。
EXCLUDE_GLOBS = (
    "*.egg-info",     # 内含旧品牌 MARS-408（PKG-INFO），且是构建产物
    ".pytest_tmp*",   # pytest 临时目录
)

# 需要排除的文件扩展名
EXCLUDE_EXTS = {
    ".pyc", ".pyo", ".so", ".pt", ".pth", ".onnx", ".bin",
    ".log",           # 运行期日志可能含旧品牌或运行数据
}

# 白名单：即便扩展名被排除，这些【精确相对路径】仍要进包。
# 依据 submission/00_提交清单.md:52，源码包仅声明保留这个训练权重。
# 不能简单地从 EXCLUDE_EXTS 删除 .pt，否则历史/重复 checkpoint 也会进入交付包。
PT_WHITELIST = {
    "py-server/models/neural_mixer_trained.pt",
}

# 大文件后缀（超过 10MB 的文件会被排除）
LARGE_EXTS = {".pdf", ".docx", ".doc", ".zip", ".tar", ".gz"}


class PackageValidationError(RuntimeError):
    """表示交付包没有通过打包后安全自检。"""


def _norm(relative_path: str) -> str:
    """将相对路径统一为 ZIP 使用的 POSIX 风格。"""
    return str(relative_path).replace("\\", "/")


def _source_path(relative_path: str) -> Path:
    """根据 POSIX 风格的项目相对路径返回本地路径。"""
    return PROJECT_ROOT.joinpath(*PurePosixPath(relative_path).parts)


def should_exclude(path: Path, relative_path: str) -> bool:
    """判断文件是否应该从交付包排除。

    判定顺序刻意固定：路径安全规则优先级最高，白名单只能覆盖扩展名规则。

    Args:
        path: 待判断的本地文件路径。
        relative_path: 相对于项目根目录的路径。

    Returns:
        应排除时为 True，否则为 False。
    """
    for part in path.parts:
        if part in EXCLUDES:
            return True
        if any(fnmatch.fnmatch(part, pattern) for pattern in EXCLUDE_GLOBS):
            return True

    if _norm(relative_path) in PT_WHITELIST:
        return False

    if path.suffix in EXCLUDE_EXTS:
        return True

    return (
        path.suffix in LARGE_EXTS
        and path.stat().st_size > 10 * 1024 * 1024
    )


def _add_tree(
    archive: zipfile.ZipFile,
    source_dir: Path,
    counters: dict[str, int],
) -> None:
    """按统一排除规则将目录文件加入 ZIP。"""
    if not source_dir.exists():
        return

    for file_path in source_dir.rglob("*"):
        relative_path = file_path.relative_to(PROJECT_ROOT)
        if should_exclude(file_path, relative_path.as_posix()):
            counters["excluded"] += 1
            continue
        if not file_path.is_file():
            continue

        archive.write(file_path, relative_path.as_posix())
        counters["size"] += file_path.stat().st_size
        counters["files"] += 1
        if counters["files"] % 50 == 0:
            print(f"  已处理 {counters['files']} 个文件...")


def validate_archive(archive_path: Path) -> None:
    """对已生成的交付包执行安全与完整性自检。

    Args:
        archive_path: 待检查的 ZIP 文件路径。

    Raises:
        PackageValidationError: ZIP 含敏感文件或缺少必要模板/白名单文件。
    """
    with zipfile.ZipFile(archive_path, "r") as archive:
        members = {
            _norm(info.filename).rstrip("/")
            for info in archive.infolist()
            if not info.is_dir()
        }

    failures: list[str] = []
    leaked_env_files = sorted(
        member for member in members
        if PurePosixPath(member).name == ".env"
    )
    if leaked_env_files:
        failures.append(
            "发现禁止进入交付包的 .env 文件: " + ", ".join(leaked_env_files)
        )

    if ENV_EXAMPLE_PATH not in members:
        failures.append(f"缺少配置模板 {ENV_EXAMPLE_PATH}")

    leaked_egg_info = sorted(
        member for member in members
        if any(
            fnmatch.fnmatch(part, "*.egg-info")
            for part in PurePosixPath(member).parts
        )
    )
    if leaked_egg_info:
        failures.append("发现 *.egg-info 构建残留")

    leaked_pytest_tmp = sorted(
        member for member in members
        if any(
            fnmatch.fnmatch(part, ".pytest_tmp*")
            for part in PurePosixPath(member).parts
        )
    )
    if leaked_pytest_tmp:
        failures.append("发现 .pytest_tmp* 临时目录")

    missing_weights = sorted(
        relative_path
        for relative_path in PT_WHITELIST
        if _source_path(relative_path).is_file() and relative_path not in members
    )
    if missing_weights:
        failures.append(
            "缺少提交清单声明的训练权重: " + ", ".join(missing_weights)
        )

    if failures:
        raise PackageValidationError("；".join(failures))

    print("  PASS: 包内无任何名为 .env 的文件")
    print(f"  PASS: 包内保留配置模板 {ENV_EXAMPLE_PATH}")
    print("  PASS: 包内无 *.egg-info 和 .pytest_tmp* 残留")
    retained_weights = sorted(PT_WHITELIST.intersection(members))
    if retained_weights:
        print("  PASS: 白名单训练权重已保留: " + ", ".join(retained_weights))
    print("  打包后自检全部通过")


def build(output_zip: Path) -> None:
    """构建交付 ZIP，并在返回前完成安全自检。

    Args:
        output_zip: 交付 ZIP 的输出路径。

    Raises:
        PackageValidationError: 产物未通过安全自检。
    """
    print("=" * 50)
    print("芒得很职 作品打包工具（1GB 限制版）")
    print("=" * 50)

    print("\n[1/5] 构建前端...")
    if not (PROJECT_ROOT / "dist" / "index.html").exists():
        try:
            result = subprocess.run(
                ["npx", "vite", "build"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                check=False,
                timeout=120,
            )
            if result.returncode == 0:
                print("  前端构建完成")
            else:
                print(f"  前端构建失败（退出码 {result.returncode}），继续打包后端与文档")
        except (OSError, subprocess.SubprocessError) as error:
            print(f"  前端构建失败: {error}")
    else:
        print("  前端已构建，跳过")

    print("\n[2/5] 准备输出目录...")
    if output_zip == OUTPUT_ZIP and OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    output_zip.parent.mkdir(parents=True, exist_ok=True)

    print("\n[3/5] 打包文件（排除大文件）...")
    counters = {"size": 0, "files": 0, "excluded": 0}
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        root_files = (
            "start.bat",
            "start.ps1",
            "INSTALL.md",
            "README.md",
            ".env.example",
            "docker-compose.yml",
            "Dockerfile",
            "serve_spa.py",
            "scripts/build_portable.py",
        )
        for relative_path in root_files:
            source_path = _source_path(relative_path)
            if source_path.is_file():
                archive.write(source_path, relative_path)
                print(f"  + {relative_path}")
                counters["size"] += source_path.stat().st_size
                counters["files"] += 1

        for directory_name in ("py-server", "dist", "documents", "design-system"):
            _add_tree(
                archive,
                PROJECT_ROOT / directory_name,
                counters,
            )

        # models/ 在部分开发环境中是目录联接，Path.rglob 不会下钻；显式补入白名单。
        archived_paths = {_norm(name) for name in archive.namelist()}
        for relative_path in sorted(PT_WHITELIST):
            source_path = _source_path(relative_path)
            if source_path.is_file() and relative_path not in archived_paths:
                archive.write(source_path, relative_path)
                print(f"  + 白名单权重 {relative_path}")
                counters["size"] += source_path.stat().st_size
                counters["files"] += 1

    print("\n[4/5] 打包后安全自检...")
    try:
        validate_archive(output_zip)
    except PackageValidationError:
        output_zip.unlink(missing_ok=True)
        raise

    size_mb = counters["size"] / (1024 * 1024)
    zip_size_mb = output_zip.stat().st_size / (1024 * 1024)
    print("\n[5/5] 打包完成!")
    print(f"  输出文件: {output_zip}")
    print(f"  文件数量: {counters['files']}")
    print(f"  排除文件: {counters['excluded']}")
    print(f"  原始大小: {size_mb:.1f} MB")
    print(f"  Zip 大小: {zip_size_mb:.1f} MB")
    print(f"  1GB 限制: {'符合' if zip_size_mb < 1000 else '超出'}")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="构建并自检芒得很职便携交付包")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="在临时目录打包并自检，退出前删除 ZIP，不写入 build/",
    )
    return parser.parse_args()


def main() -> int:
    """运行命令行入口并返回进程退出码。"""
    args = parse_args()
    try:
        if args.dry_run:
            print("[DRY-RUN] 安全模式：临时打包、自检后立即删除，不写入 build/")
            with tempfile.TemporaryDirectory(prefix="mangdehenzhi-package-check-") as temp_dir:
                temporary_zip = Path(temp_dir) / OUTPUT_ZIP.name
                build(temporary_zip)
            print("[DRY-RUN] PASS: 临时 ZIP 已删除，未产出可外传交付包")
        else:
            build(OUTPUT_ZIP)
    except (OSError, PackageValidationError, zipfile.BadZipFile) as error:
        print(f"打包失败: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
