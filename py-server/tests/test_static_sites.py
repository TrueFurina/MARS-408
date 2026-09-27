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
