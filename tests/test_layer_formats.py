"""export_layers writes jpg/webp pieces or one layered svg into the folder the model picks."""
import xml.etree.ElementTree as ET

from PIL import Image
import pytest

from uiforge_mcp import server as s
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    s.create_canvas("hud", 200, 100)
    s.add_rect("hud", 0, 0, 200, 100, group="panel", style={"fill": "#224488"})
    s.add_ellipse("hud", 150, 50, 20, 20, group="badge", style={"fill": "#ff3300"})
    yield tmp_path
    s.set_store(None)


def test_layers_as_jpg_in_chosen_folder(ws):
    out = ws / "my" / "folder"
    res = s.export_layers("hud", out_dir=str(out), format="jpeg")
    files = sorted(p.name for p in out.glob("*.jpg"))
    assert files == ["hud_badge.jpg", "hud_panel.jpg"]
    assert Image.open(out / "hud_panel.jpg").format == "JPEG"
    assert any("jpg has no transparency" in n for n in res["notes"])


def test_layers_as_one_layered_svg(ws):
    res = s.export_layers("hud", out_dir=str(ws / "svg"), format="svg", scales=[1, 2])
    root = ET.parse(ws / "svg" / "hud.svg").getroot()
    ns = "{http://www.inkscape.org/namespaces/inkscape}"
    groups = [g for g in root if g.get(ns + "groupmode") == "layer"]
    assert [g.get(ns + "label") for g in groups] == ["panel", "badge"]
    badge = groups[1][0]
    assert float(badge.get("x")) == pytest.approx(128, abs=2)
    assert badge.get("href").startswith("data:image/png;base64,")
    assert [l["file"] for l in res["layers"]] == ["hud.svg", "hud.svg"]


def test_bad_layer_format_is_explained(ws):
    with pytest.raises(ValueError, match="png, webp, jpg or svg"):
        s.export_layers("hud", format="gif")
