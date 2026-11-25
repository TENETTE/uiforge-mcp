"""Values the model passes must not become code in generated engine scripts, and renders stay bounded."""
import json

import pytest

from uiforge_mcp import server as s
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


@pytest.mark.parametrize("kwargs", [
    {"unreal_content_path": '/Game/UI"\nimport os; os.system("calc")\n#'},
    {"godot_res_path": 'res://ui"]\n[ext_resource type="Script" path="res://evil.gd"'},
    {"godot_res_path": "res://../outside"},
])
def test_engine_paths_cannot_inject_code(ws, kwargs):
    with pytest.raises(ValueError, match="path"):
        s.write_engine_helpers("unreal", str(ws / "out"), **kwargs)


def test_roblox_ids_must_be_numeric(ws):
    out = ws / "out"
    out.mkdir()
    (out / "uiforge_manifest.json").write_text(json.dumps({"assets": {"btn": {"files": []}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="numeric"):
        s.write_engine_helpers("roblox", str(out), roblox_ids={"btn": '1"; game:Shutdown() --'})
    result = s.write_engine_helpers("roblox", str(out), roblox_ids={"btn": "rbxassetid://123"})
    manifest = json.loads((out / "uiforge_manifest.json").read_text(encoding="utf-8"))
    assert manifest["assets"]["btn"]["roblox_id"] == "123" and result["assets_without_id"] == []


def test_huge_render_is_refused_not_attempted(ws):
    s.create_canvas("c", 8192, 8192)
    st = s.store()
    with pytest.raises(ValueError, match="pixel limit"):
        st.renderer(st.get("c"), scale=8)
