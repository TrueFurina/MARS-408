# ============================================================
# WS1 覆盖率补全 — shared/kg_search.py（已保存知识图谱的实体/关系检索）
#
# 此前在测试套件中零引用（grep shared.<mod> 无命中），却被 engines/frugal_rag
# 用于「KG 增强查询」。仅依赖 json/os，用 tmp_path + monkeypatch 隔离文件系统，
# 可脱离 conftest 独立运行：
#   py-server/.venv/Scripts/python.exe -m pytest tests/test_shared_kg_search.py --noconftest -q
#
# 覆盖：目录缺失返回空 / 实体命中(大小写不敏感) / 关系按 type 命中 /
#       subject 过滤 / 结果各封顶 10 条 / 坏 JSON 文件跳过不崩
# ================================================================

import json


def _write(kg_dir, name, payload):
    (kg_dir / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_missing_dir_returns_empty(monkeypatch):
    import shared.kg_search as kgs

    monkeypatch.setattr(kgs, "_KG_DIR", "/nonexistent/kg/dir/xyz")
    assert kgs.search_kg_entities("anything") == {"entities": [], "relationships": []}


def test_finds_entity_case_insensitive(monkeypatch, tmp_path):
    import shared.kg_search as kgs

    _write(tmp_path, "a.json", {
        "subject": "computer_network",
        "entities": [{"name": "TCP", "description": "传输控制协议"}],
        "relationships": [{"type": "uses"}],
    })
    monkeypatch.setattr(kgs, "_KG_DIR", str(tmp_path))
    out = kgs.search_kg_entities("tcp")
    assert len(out["entities"]) == 1
    assert out["entities"][0]["name"] == "TCP"


def test_matches_entity_description(monkeypatch, tmp_path):
    import shared.kg_search as kgs

    _write(tmp_path, "a.json", {
        "subject": "os",
        "entities": [{"name": "进程", "description": "Process Scheduling"}],
        "relationships": [],
    })
    monkeypatch.setattr(kgs, "_KG_DIR", str(tmp_path))
    assert len(kgs.search_kg_entities("scheduling")["entities"]) == 1


def test_matches_relationship_by_type(monkeypatch, tmp_path):
    import shared.kg_search as kgs

    _write(tmp_path, "a.json", {
        "subject": "ds",
        "entities": [],
        "relationships": [{"type": "DEPENDS_ON"}],
    })
    monkeypatch.setattr(kgs, "_KG_DIR", str(tmp_path))
    assert len(kgs.search_kg_entities("depends")["relationships"]) == 1


def test_subject_filter_excludes_other_subjects(monkeypatch, tmp_path):
    import shared.kg_search as kgs

    _write(tmp_path, "cn.json", {
        "subject": "computer_network",
        "entities": [{"name": "TCP", "description": ""}], "relationships": [],
    })
    _write(tmp_path, "os.json", {
        "subject": "operating_system",
        "entities": [{"name": "TCP-like", "description": ""}], "relationships": [],
    })
    monkeypatch.setattr(kgs, "_KG_DIR", str(tmp_path))
    # subject="general" 不过滤，两个都命中
    assert len(kgs.search_kg_entities("tcp")["entities"]) == 2
    # 指定 subject 后只命中该科
    out = kgs.search_kg_entities("tcp", subject="computer_network")
    assert len(out["entities"]) == 1
    assert out["entities"][0]["name"] == "TCP"


def test_results_capped_at_10(monkeypatch, tmp_path):
    import shared.kg_search as kgs

    entities = [{"name": f"E{i}", "description": "match"} for i in range(15)]
    relations = [{"type": "match"} for _ in range(15)]
    _write(tmp_path, "big.json", {
        "subject": "general", "entities": entities, "relationships": relations,
    })
    monkeypatch.setattr(kgs, "_KG_DIR", str(tmp_path))
    out = kgs.search_kg_entities("match")
    assert len(out["entities"]) == 10
    assert len(out["relationships"]) == 10


def test_malformed_json_file_skipped(monkeypatch, tmp_path):
    import shared.kg_search as kgs

    (tmp_path / "bad.json").write_text("{ this is not json", encoding="utf-8")
    _write(tmp_path, "good.json", {
        "subject": "general",
        "entities": [{"name": "Good", "description": "ok"}], "relationships": [],
    })
    monkeypatch.setattr(kgs, "_KG_DIR", str(tmp_path))
    out = kgs.search_kg_entities("good")
    assert len(out["entities"]) == 1, "坏文件应被跳过而非让整个检索崩掉"


def test_non_json_files_ignored(monkeypatch, tmp_path):
    import shared.kg_search as kgs

    (tmp_path / "readme.txt").write_text('{"name": "Nope"}', encoding="utf-8")
    monkeypatch.setattr(kgs, "_KG_DIR", str(tmp_path))
    assert kgs.search_kg_entities("nope")["entities"] == []
