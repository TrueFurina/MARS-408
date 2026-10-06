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
    ".workbuddy", ".sessions", ".codebuddy",
    # 超 1GB 限制的大文件
    "教材",           # documents/教材/ 下的 PDF 教材 (~450MB)
    # ── 安全 / 交付卫生（勿删，见文件头红线说明）──
    ".env",           # 真实凭证，精确匹配；不可写 .env*，否则会误伤 .env.example
    ".eggs",
    ".mypy_cache",
    # 提交包自身：交付 zip 里绝不能再嵌套一份提交包（含旧赛事清单与旧文档）。
    # 当前 build() 的打包目录白名单已不含 submission，此处属纵深防御：
    # 日后有人把 submission/ 加进白名单时，本条仍能拦住嵌套。
    "submission",
}

# 需要排除的【完整相对路径前缀】（运行期数据目录）。
#
# ⚠️ 不要再把 "data" / "sessions" / "plots" 放回 EXCLUDES 的分段裸名里。
# 分段裸名匹配路径的【任意一段】，会连带删掉同名但属于源码的目录：
# `src/data/`（seedTextbooks.ts / capabilityComparison.ts / sourceLabExercises.ts，
# 被 SourceLabPane.vue、EngineView.vue、KnowledgeBaseView.vue 直接 import）
# 曾因此被整体排除，交付包 1075 个文件全部通过 .env 安全自检，
# 却一个 .vue 页面数据模块都没有 —— 「安全」自检掩盖了「缺料」缺陷，
# 评委拿到包执行 vite build 才会报缺模块。故改为按完整前缀精确排除。
EXCLUDE_PATH_PREFIXES = (
    "py-server/data",       # 运行期数据 (~12MB)
    "py-server/sessions",   # 运行期会话
    "py-server/plots",      # 运行期图表输出
    "py-server/iq_run_tmp",  # 一次性的 IQ 评测运行目录
)

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
    normalized = _norm(relative_path)
    for prefix in EXCLUDE_PATH_PREFIXES:
        if normalized == prefix or normalized.startswith(f"{prefix}/"):
            return True

    for part in path.parts:
        if part in EXCLUDES:
            return True
        if any(fnmatch.fnmatch(part, pattern) for pattern in EXCLUDE_GLOBS):
            return True

    if normalized in PT_WHITELIST:
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


def _assert_frontend_source_present(archive: zipfile.ZipFile) -> None:
    """校验前端源码（src/ 与 public/）确实进入了交付包。

    交付物叫「源码包」。若只打后端 py-server 而漏掉 src/，包仍能通过
    .env 安全自检——那正是 2026-10-06 之前的真实故障：1075 个文件全部通过
    安全自检，却一个 .vue 都没有，交付出去等于交了个后端。

    因此这里用【数量下限】而非仅判存在：即便日后src/ 被清空到只剩 index.ts，
    也会因数量不达标而硬失败，不会又打出一个「安全但没有源码」的包。

    Args:
        archive: 仍在写入模式、尚未关闭的 ZIP 对象。

    Raises:
        PackageValidationError: 前端源码缺失或数量明显异常。
    """
    names = {
        _norm(info.filename)
        for info in archive.infolist()
        if not info.is_dir()
    }
    frontend_minimums = {"src/": 50, "public/": 5}
    insufficient = [
        f"{prefix.rstrip('/')}={sum(1 for n in names if n.startswith(prefix))} 个"
        f"（下限 {minimum}）"
        for prefix, minimum in frontend_minimums.items()
        if sum(1 for n in names if n.startswith(prefix)) < minimum
    ]
    if insufficient:
        raise PackageValidationError(
            "前端源码未进入交付包，交付物不能叫「源码包」: " + ", ".join(insufficient)
        )
    print("  PASS: 前端源码 src/ 与 public/ 已在包内")


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

    nested_submission = sorted(
        member for member in members
        if member == "submission" or member.startswith("submission/")
    )
    if nested_submission:
        failures.append(
            "交付包内嵌套了提交包自身（含旧赛事清单，需立即排查）: "
            + ", ".join(nested_submission[:5])
        )

    # src/data/ 曾因 EXCLUDES 裸名 "data" 被整体删掉，而 .env 自检完全测不出来。
    # 这里显式点名必须存在的源码模块：被谁 import 就在代码里真实存在，删不得。
    required_frontend_sources = (
        "src/data/seedTextbooks.ts",
        "src/data/capabilityComparison.ts",
        "src/data/sourceLabExercises.ts",
    )
    missing_sources = [
        relative_path
        for relative_path in required_frontend_sources
        if _source_path(relative_path).is_file() and relative_path not in members
    ]
    if missing_sources:
        failures.append(
            "前端源码模块缺失（多半是 EXCLUDES 误伤同名目录）: "
            + ", ".join(missing_sources)
        )

    if failures:
        raise PackageValidationError("；".join(failures))

    print("  PASS: 包内无任何名为 .env 的文件")
    print(f"  PASS: 包内保留配置模板 {ENV_EXAMPLE_PATH}")
    print("  PASS: 包内无 *.egg-info 和 .pytest_tmp* 残留")
    print("  PASS: 包内无嵌套的 submission/ 提交包")
    print("  PASS: 前端源码模块（src/data 等）完整在包内")
    retained_weights = sorted(PT_WHITELIST.intersection(members))
    if retained_weights:
        print("  PASS: 白名单训练权重已保留: " + ", ".join(retained_weights))
    print("  打包后自检全部通过")


OPENAPI_SNAPSHOT_MEMBER = "py-server/openapi.json"
OPENAPI_VERIFY_SCRIPT = Path("scripts") / "verify_openapi_snapshot.py"


def _venv_python() -> Path:
    """返回项目 venv 解释器路径。

    契约校验需要 fastapi/pydantic，只有 venv 齐备。找不到就明确报错，
    而不是退到系统 python —— 后者会在 import 失败时给出误导性的错误信息。
    """
    for rel in (
        Path("py-server") / ".venv" / "Scripts" / "python.exe",
        Path("py-server") / ".venv" / "bin" / "python",
    ):
        candidate = PROJECT_ROOT / rel
        if candidate.is_file():
            return candidate
    raise PackageValidationError(
        "找不到 py-server/.venv 解释器，无法校验包内契约漂移（fail-closed）"
    )


def verify_packaged_openapi(archive_path: Path) -> None:
    """校验**包内那份** openapi.json 与运行时真实能力一致（fail-closed）。

    为什么必须校验包内、而不是只校验工作区
    ------------------------------------------------------------------
    2026-10-06 实锤事故：工作区快照已重生成对齐（227/244），但交付 zip 里的
    那份仍是旧的 223/240 —— 修复停在仓库层，没到交付面。评委拿到的正是包内文件。

    所以这里不看工作区，直接把 zip 成员抽出来喂给同一个校验脚本
    （`verify_openapi_snapshot.py --snapshot`）。不一致 → 抛异常 → 上层删包exit 1，
    把"改了没到包内"变成**打包失败**，而不是等人核对时才发现。

    Args:
        archive_path: 已生成的交付 ZIP 路径。

    Raises:
        PackageValidationError: 包内快照缺失，或与运行时存在漂移。
    """
    verifier = PROJECT_ROOT / OPENAPI_VERIFY_SCRIPT
    if not verifier.is_file():
        # 校验器本身缺失属于"闸门没装上"，绝不能当成通过。
        raise PackageValidationError(
            f"找不到契约校验脚本 {OPENAPI_VERIFY_SCRIPT}；"
            "无法确认包内 openapi.json 是否与运行时一致（fail-closed）"
        )

    with tempfile.TemporaryDirectory(prefix="openapi_verify_") as tmpdir:
        extracted = Path(tmpdir) / "openapi.json"
        with zipfile.ZipFile(archive_path, "r") as archive:
            try:
                payload = archive.read(OPENAPI_SNAPSHOT_MEMBER)
            except KeyError:
                raise PackageValidationError(
                    f"包内缺少 {OPENAPI_SNAPSHOT_MEMBER}；"
                    "随包对外契约缺失，评委无法核对接口清单"
                ) from None
        extracted.write_bytes(payload)

        result = subprocess.run(
            [str(_venv_python()), str(verifier), "--snapshot", str(extracted)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise PackageValidationError(
            f"包内 {OPENAPI_SNAPSHOT_MEMBER} 与运行时真实能力不一致"
            f"（校验 exit {result.returncode}）。"
            "通常是改了路由/文案后忘了重生成快照，或忘了重打包。\n"
            + detail
        )

    print(f"  PASS: 包内 {OPENAPI_SNAPSHOT_MEMBER} 与运行时一致（契约无漂移）")


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
            "README_EN.md",
            ".env.example",
            "docker-compose.yml",
            "Dockerfile",
            "serve_spa.py",
            "package.json",
            "package-lock.json",
            "vite.config.ts",
            "vitest.config.ts",
            "tsconfig.json",
            "tsconfig.app.json",
            "tsconfig.node.json",
            "postcss.config.js",
            "eslint.config.js",
            "env.d.ts",
            "index.html",
            "scripts/build_portable.py",
        )
        for relative_path in root_files:
            source_path = _source_path(relative_path)
            if source_path.is_file():
                archive.write(source_path, relative_path)
                print(f"  + {relative_path}")
                counters["size"] += source_path.stat().st_size
                counters["files"] += 1

        # src/ 与 public/ 是前端源码本体：缺了它们，交付包只剩后端，
        # 「源码包」名不副实（2026-10-06 实测遗漏：1075 个文件里 src/public 各 0 个）。
        # dist/ 是构建产物，一并保留，评委不装依赖也能直接看界面。
        for directory_name in ("py-server", "src", "public", "dist", "documents", "design-system"):
            _add_tree(
                archive,
                PROJECT_ROOT / directory_name,
                counters,
            )

        # 打包后自检：前端源码必须真的在里面，且成规模。
        _assert_frontend_source_present(archive)

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
        verify_packaged_openapi(output_zip)
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
