# -*- coding: utf-8 -*-
"""静态资源与 SPA 挂载单测 —— app/static_sites.py（M-4 拆分后）

SPA 回退是**上线关键路径**：单镜像部署时后端要同时服务前端路由，
漏了它前端刷新就 404，但接口测试全绿 —— 正是需要固化断言的那类行为。
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import static_sites


def _route_paths(app: FastAPI) -> set:
    return {getattr(r, "path", "") for r in app.routes}


class TestPlotsMediaMount:
    def test_creates_dirs_and_mounts(self, tmp_path, monkeypatch):
        monkeypatch.setattr(static_sites, "_PY_SERVER_DIR", str(tmp_path))
        app = FastAPI()
        static_sites.install_plots_media(app)
        assert (tmp_path / "plots").is_dir()
        assert (tmp_path / "media").is_dir()
        paths = _route_paths(app)
        assert "/plots" in paths and "/media" in paths

    def test_idempotent_when_dirs_already_exist(self, tmp_path, monkeypatch):
        monkeypatch.setattr(static_sites, "_PY_SERVER_DIR", str(tmp_path))
        (tmp_path / "plots").mkdir()
        (tmp_path / "media").mkdir()
        app = FastAPI()
        static_sites.install_plots_media(app)
        assert "/plots" in _route_paths(app)


class TestSpaInstall:
    def test_skipped_when_dist_missing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("STATIC_DIR", raising=False)
        monkeypatch.setattr(static_sites, "_REPO_ROOT", str(tmp_path / "nowhere"))
        app = FastAPI()
        static_sites.install_spa(app)
        assert "/assets" not in _route_paths(app), "无 dist 时不应挂载前端资源"

    def test_static_dir_env_overrides_repo_root(self, tmp_path, monkeypatch):
        dist = tmp_path / "custom_dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<html>CUSTOM</html>", encoding="utf-8")
        monkeypatch.setenv("STATIC_DIR", str(dist))
        app = FastAPI()
        static_sites.install_spa(app)
        assert "/assets" in _route_paths(app)

    def test_mounts_assets_and_falls_back_to_index(self, tmp_path, monkeypatch):
        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "assets" / "app.js").write_text("// bundle", encoding="utf-8")
        (dist / "index.html").write_text("<html>SPA-INDEX</html>", encoding="utf-8")
        monkeypatch.delenv("STATIC_DIR", raising=False)
        monkeypatch.setattr(static_sites, "_REPO_ROOT", str(tmp_path))

        app = FastAPI()
        static_sites.install_spa(app)
        client = TestClient(app)

        assert "SPA-INDEX" in client.get("/some/deep/spa/route").text
        assert client.get("/assets/app.js").text == "// bundle"

    def test_api_paths_are_not_swallowed_by_spa(self, tmp_path, monkeypatch):
        """关键：/api 下的 404 必须是 404，不能被 index.html 顶掉（否则前端拿不到错误）。"""
        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<html>SPA-INDEX</html>", encoding="utf-8")
        monkeypatch.delenv("STATIC_DIR", raising=False)
        monkeypatch.setattr(static_sites, "_REPO_ROOT", str(tmp_path))

        app = FastAPI()
        static_sites.install_spa(app)
        client = TestClient(app)
        assert client.get("/api/definitely-not-here").status_code == 404

    def test_showcase_mount_when_present(self, tmp_path, monkeypatch):
        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "showcase").mkdir()
        (dist / "showcase" / "index.html").write_text("<html>SHOWCASE</html>", encoding="utf-8")
        (dist / "index.html").write_text("<html>SPA-INDEX</html>", encoding="utf-8")
        monkeypatch.delenv("STATIC_DIR", raising=False)
        monkeypatch.setattr(static_sites, "_REPO_ROOT", str(tmp_path))

        app = FastAPI()
        static_sites.install_spa(app)
        assert "/showcase" in _route_paths(app)

    def test_showcase_dir_redirect_falls_back_to_index(self, tmp_path, monkeypatch):
        """StaticFiles 对目录精确路径会 307，必须回退 index.html 让前端路由接管。"""
        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "showcase").mkdir()
        (dist / "showcase" / "index.html").write_text("<html>SHOWCASE</html>", encoding="utf-8")
        (dist / "index.html").write_text("<html>SPA-INDEX</html>", encoding="utf-8")
        monkeypatch.delenv("STATIC_DIR", raising=False)
        monkeypatch.setattr(static_sites, "_REPO_ROOT", str(tmp_path))

        app = FastAPI()
        static_sites.install_spa(app)
        client = TestClient(app)
        resp = client.get("/showcase", follow_redirects=False)
        assert resp.status_code == 200 and "SPA-INDEX" in resp.text


class TestSpaServesPublicAssets:
    """public/ 下的非 assets 资源（brand/、favicon.ico…）必须直接返回文件本体。

    历史缺陷（2026-10-15 线上实测）：install_spa 只 mount 了 /assets 与 /showcase，
    其余 public 资源没有对应路由，请求被 SPA 回退**兜成 index.html** ——
    HTML 被当作 PNG 解析 ⇒ 侧边栏/落地页 logo 全部裂图，而 HTTP 状态是 200，
    监控与接口测试都看不出问题；dev 下 vite 直接服务 public/ 所以本地一切正常
    （典型「本地好好的、线上坏」）。故此处固化断言。
    """

    def _app_with_public_assets(self, tmp_path, monkeypatch):
        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "brand").mkdir()
        (dist / "brand" / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\nFAKE-PNG-BODY")
        (dist / "favicon.ico").write_bytes(b"FAKE-ICO")
        (dist / "index.html").write_text("<html>SPA-INDEX</html>", encoding="utf-8")
        monkeypatch.delenv("STATIC_DIR", raising=False)
        monkeypatch.setattr(static_sites, "_REPO_ROOT", str(tmp_path))
        app = FastAPI()
        static_sites.install_spa(app)
        return TestClient(app)

    def test_brand_asset_returned_as_file_not_index(self, tmp_path, monkeypatch):
        client = self._app_with_public_assets(tmp_path, monkeypatch)
        resp = client.get("/brand/logo.png")
        assert resp.status_code == 200
        assert resp.content == b"\x89PNG\r\n\x1a\nFAKE-PNG-BODY", \
            "public 资源被 SPA 回退兜成 index.html（线上表现为 logo 裂图）"
        assert "SPA-INDEX" not in resp.text

    def test_root_level_file_like_favicon_returned(self, tmp_path, monkeypatch):
        client = self._app_with_public_assets(tmp_path, monkeypatch)
        resp = client.get("/favicon.ico")
        assert resp.status_code == 200 and resp.content == b"FAKE-ICO"

    def test_unknown_path_still_falls_back_to_index(self, tmp_path, monkeypatch):
        """修复不得破坏原行为：确实不存在的路径仍走 SPA 回退（前端深链刷新可用）。"""
        client = self._app_with_public_assets(tmp_path, monkeypatch)
        resp = client.get("/some/deep/spa/route")
        assert resp.status_code == 200 and "SPA-INDEX" in resp.text

    def test_path_traversal_does_not_escape_static_root(self, tmp_path, monkeypatch):
        """目录穿越：dist 之外的既有文件不得被读到（应回退 index.html）。"""
        outside = tmp_path / "outside.txt"
        outside.write_text("SECRET-OUTSIDE", encoding="utf-8")
        client = self._app_with_public_assets(tmp_path, monkeypatch)
        for probe in ("/../outside.txt", "/%2e%2e/outside.txt", "/..%2foutside.txt"):
            resp = client.get(probe)
            assert "SECRET-OUTSIDE" not in resp.text, f"{probe} 读到了静态根之外的文件"


class TestSpaHeadSupport:
    """HEAD 应与 GET 同样可用（HTTP 语义；供只发 HEAD 的下游健康探针）。"""

    def test_head_root_falls_back_to_index(self, tmp_path, monkeypatch):
        """HEAD / → 200（此前只判 GET，HEAD / 落到 404，下游会误判服务不可用）。"""
        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<html>SPA-INDEX</html>", encoding="utf-8")
        monkeypatch.delenv("STATIC_DIR", raising=False)
        monkeypatch.setattr(static_sites, "_REPO_ROOT", str(tmp_path))

        app = FastAPI()
        static_sites.install_spa(app)
        client = TestClient(app)
        assert client.head("/").status_code == 200

    def test_head_api_path_still_not_swallowed(self, tmp_path, monkeypatch):
        """/api 下的 HEAD 也不得被 index.html 顶掉（与 GET 同约定）。"""
        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<html>SPA-INDEX</html>", encoding="utf-8")
        monkeypatch.delenv("STATIC_DIR", raising=False)
        monkeypatch.setattr(static_sites, "_REPO_ROOT", str(tmp_path))

        app = FastAPI()
        static_sites.install_spa(app)
        client = TestClient(app)
        assert client.head("/api/definitely-not-here").status_code == 404
