"""锁死「演示账号凭据单一真值源」与「生产环境不播种」两条不变量。

背景（本轮安全核实结论）：
  - 演示账号 demo / <演示口令> 是**有意为之**的演示凭据（登录页会展示该提示），
    并非泄露的生产密钥；生产值只存在于未被 git 跟踪的 config.json / .env。
  - 但 main.py 曾重复硬编码同一份凭据字面量，存在两个实际风险：
      ① 漂移：seed_demo_data 改了口令而 main.py 的幂等探测未同步
         → authenticate 恒失败 → 每次启动重复播种，幂等性失效；
      ② 凭据回显：生产分支日志明文写出该口令。
  - 本测试把「单一真值源」与「生产环境守门」固化成可执行断言，
    任何一处回退都会让测试失败（已做变异验证）。
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

PY_SERVER = Path(__file__).resolve().parents[1]
if str(PY_SERVER) not in sys.path:
    sys.path.insert(0, str(PY_SERVER))

import seed_demo_data as sd  # noqa: E402

MAIN_PATH = PY_SERVER / "main.py"
_ANCHOR_START = "# ── 首次启动时写入演示种子数据"
_ANCHOR_END = "演示种子数据写入失败"


def _read(p: Path) -> str:
    return io.open(p, encoding="utf-8", errors="replace").read()


@pytest.fixture(scope="module")
def main_src() -> str:
    return _read(MAIN_PATH)


@pytest.fixture(scope="module")
def demo_seed_block(main_src: str) -> str:
    """切出 main.py 的演示种子写入块，避免断言被文件其它部分的同名字符串误伤。"""
    i = main_src.index(_ANCHOR_START)
    j = main_src.index(_ANCHOR_END, i)
    block = main_src[i:j]
    assert block, "未能切出演示种子写入块（锚点可能被改动）"
    return block


# ── 契约：真值源确实提供了常量 ────────────────────────────────────────────────

def test_seed_module_exposes_demo_credential_constants() -> None:
    assert isinstance(sd.DEMO_USERNAME, str) and sd.DEMO_USERNAME.strip()
    assert isinstance(sd.DEMO_PASSWORD, str) and sd.DEMO_PASSWORD.strip()


def test_seed_module_is_the_only_definition_point() -> None:
    """seed_demo_data 自身应当是口令字面量的唯一定义处（此处允许出现一次）。"""
    src = _read(PY_SERVER / "seed_demo_data.py")
    assert src.count(sd.DEMO_PASSWORD) >= 1, "seed_demo_data 中应定义该口令"


# ── 不变量 1：main.py 不得重复硬编码凭据 ──────────────────────────────────────

def test_main_never_embeds_demo_password_literal(main_src: str) -> None:
    assert sd.DEMO_PASSWORD not in main_src, (
        "main.py 又出现了演示口令字面量——应改为从 seed_demo_data 导入常量，"
        "否则会漂移（幂等探测失效）并把凭据回显进日志"
    )


def test_demo_seed_block_uses_imported_constants(demo_seed_block: str) -> None:
    assert "DEMO_USERNAME" in demo_seed_block, "演示种子块应引用 DEMO_USERNAME 常量"
    assert "DEMO_PASSWORD" in demo_seed_block, "演示种子块应引用 DEMO_PASSWORD 常量"
    assert "authenticate(DEMO_USERNAME, DEMO_PASSWORD)" in demo_seed_block, (
        "幂等探测必须使用常量调用 authenticate，不得写死字面量"
    )


def test_demo_seed_block_has_no_username_literal(demo_seed_block: str) -> None:
    assert f'"{sd.DEMO_USERNAME}"' not in demo_seed_block, (
        "演示种子块仍硬编码了演示用户名"
    )


# ── 不变量 2：非生产环境守门必须保留 ─────────────────────────────────────────

def test_production_gate_preserved(demo_seed_block: str) -> None:
    assert 'env not in ("production", "prod")' in demo_seed_block, (
        "生产环境守门被改动——这会让生产部署自动创建弱口令演示账户"
    )


def test_seeding_is_skipped_in_production_branch(demo_seed_block: str) -> None:
    """生产分支只允许记日志，不得调用 seed_demo_data()。"""
    i = demo_seed_block.index("else:")
    prod_branch = demo_seed_block[i:]
    assert "seed_demo_data()" not in prod_branch, "生产分支不得播种演示数据"
    assert "logger.info" in prod_branch, "生产分支应留下可审计的说明日志"


# ── 不变量 3：凭据不得进入日志 ───────────────────────────────────────────────

def test_no_credential_echo_in_logs(demo_seed_block: str) -> None:
    """日志既不得写死口令，也不得把口令常量作为参数传进去。

    注：首版只断言「行的字面量里不含口令值」，变异验证发现「用 %s + 常量名回显」
    （logger.info("skip %s/%s", DEMO_USERNAME, DEMO_PASSWORD)）能存活——
    故补上对常量名的检查。用户名字面量允许入日志（用户名非凭据）。
    """
    for ln in demo_seed_block.splitlines():
        low = ln.strip().lower()
        if low.startswith("logger.") or low.startswith("print("):
            assert sd.DEMO_PASSWORD not in ln, f"日志行回显了演示口令: {ln.strip()[:60]}"
            assert "DEMO_PASSWORD" not in ln, (
                f"日志行把口令常量作为参数传入（同样会明文落日志）: {ln.strip()[:60]}"
            )
