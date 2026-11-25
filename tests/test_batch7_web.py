"""Website export: pages, live text and fonts, CSS boxes, links / overlays, hover CSS, keyframes,
view transitions, theme variables and responsive pin anchors."""
import re

import pytest

from uiforge_mcp import server as s
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def site(ws, **kw):
    s.set_theme(colors={"accent": "#7c5cff"}, modes={"light": {"accent": "#3b82f6"}})
    s.create_canvas("home", 400, 200, background="#101018")
    s.add_rect("home", 20, 20, 120, 40, radius=10, id="btn", group="b", style={"fill": "$accent", "shadow": {"blur": 8}})
    s.add_text("home", "Play <now>", x=80, y=40, size=16, anchor="center", id="lbl", group="b")
    s.set_state("home", "hover", "btn", {"style": {"glow": {"color": "#ffffff", "blur": 10}}})
    s.add_polygon("home", cx=300, cy=100, radius=30, sides=6, id="hex", fill="#f5b83d")
    s.add_rect("home", 300, 160, 80, 30, id="corner", fill="#ffffff")
    s.set_pin(canvas="home", x="right", y="bottom", ids=["corner"])
    s.create_animation("home", "spin", duration=2, loop=True)
    s.set_keyframes("home", "spin", "hex", "rotation", [{"t": 0, "value": 0}, {"t": 2, "value": 360}])
    s.create_canvas("shop", 400, 200)
    s.add_rect("shop", 20, 20, 120, 40, id="btn", fill="#00ff00")
    s.create_canvas("menu", 200, 100)
    s.set_link("home", "btn", "shop")
    s.set_link("home", "hex", "menu", mode="overlay")
    return s.export_web(["home", "shop", "menu"], out_dir=str(ws / "site"), **kw)


def test_pages_text_fonts_links_and_states(ws):
    res = site(ws)
    assert res["pages"] == ["index.html", "shop.html", "menu.html"] and res["embedded_as_image"] == []
    page = (ws / "site" / "index.html").read_text(encoding="utf-8")
    assert "Play &lt;now&gt;" in page
    assert re.search(r"@font-face\{font-family:'Inter'", page) and list((ws / "site" / "assets" / "fonts").glob("*.ttf"))
    assert 'data-href="shop.html" data-mode="navigate"' in page and 'data-href="menu.html" data-mode="overlay"' in page
    assert ".g-b:hover #btn{" in page and "view-transition-name:v-btn" in page
    assert "@keyframes a-home-spin-hex" in page and "infinite" in page
    css = (ws / "site" / "styles.css").read_text(encoding="utf-8")
    assert "--color-accent:#7c5cff" in css and '[data-theme="light"]{--color-accent:#3b82f6}' in css
    assert "var(--color-accent, #7c5cff)" in page
    assert "<svg" in page


def test_responsive_layout_uses_pins(ws):
    site(ws, layout="responsive")
    page = (ws / "site" / "index.html").read_text(encoding="utf-8")
    corner = re.search(r'id="corner" style="([^"]+)"', page).group(1)
    assert "right:20px" in corner and "bottom:10px" in corner
    with pytest.raises(ValueError, match="layout"):
        s.export_web("home", layout="fluid")
    with pytest.raises(ValueError, match="url link"):
        s.set_link("home", "btn", "javascript:alert(1)", mode="url")


def test_font_names_cannot_break_out_of_css(ws):
    s.create_canvas("c", 100, 40)
    with pytest.raises(ValueError, match="not found"):
        s.add_text("c", "x", x=0, y=0, font="Inter'}body{display:none}", id="t")
    from uiforge_mcp.webexport import _Ctx
    import types
    lay = types.SimpleNamespace(family="Inter'}x{", path=None, var_weight=None, weight=400)
    assert "'" not in _Ctx.font_face(types.SimpleNamespace(), lay)[1:-30].replace("', system-ui", "")
