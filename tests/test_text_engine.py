"""Multilingual text: bidi, HarfBuzz shaping, fallback fonts, missing-glyph export block, pseudo modes."""
import numpy as np
import pytest

from uiforge_mcp import server as s
from uiforge_mcp import shaping
from uiforge_mcp.fonts import FontLibrary
from uiforge_mcp.render import TextLayout, pseudo_localize
from uiforge_mcp.store import Store

FONTS = FontLibrary()


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def layout(text, lang=None, **el):
    return TextLayout({"id": "t", "text": text, "size": 40, "x": 0, "y": 0, **el}, {}, FONTS, 1.0, lang=lang)


def glyphs(text, lang=None):
    L = layout(text, lang)
    assert L.shaper is not None, "text should take the shaping path"
    return L.shaper, L.shaper.shape(text)[0]


def test_latin_keeps_pillow_path():
    assert layout("Hello İstanbul ışık").shaper is None


def test_arabic_letters_join():
    sh, isolated = glyphs("ب")
    _, joined = glyphs("ببب")
    iso = {g[1] for g in isolated}
    forms = {g[1] for g in joined} - iso
    assert len(forms) >= 3
    assert not sh.missing


def test_rtl_runs_right_to_left():
    _, g = glyphs("אב")
    sh, _ = glyphs("א")
    alef = sh.shape("א")[0][0][1]
    xs = {gid: x for _, gid, x, _ in g}
    assert xs[alef] > min(xs.values())


def test_digits_stay_left_to_right_inside_arabic():
    sh, g = glyphs("السعر 1250")
    x_of = {}
    for fi, gid, x, _ in g:
        for d in "12":
            if sh.chain[fi].font.get_nominal_glyph(ord(d)) == gid:
                x_of[d] = x
    assert x_of["1"] < x_of["2"]


def test_devanagari_conjunct_forms():
    sh, g = glyphs("क्षि")
    assert len(g) < len("क्षि") and not sh.missing


def test_thai_and_tamil_have_fonts():
    for text in ("สวัสดีครับ", "வணக்கம்"):
        sh, g = glyphs(text)
        assert g and not sh.missing


def test_han_follows_language_tag():
    ja = layout("直", "ja").shaper
    zh = layout("直", "zh-Hans").shaper
    ja.shape("直"), zh.shape("直")
    used_ja = {ja.chain[i].path for i in ja.used}
    used_zh = {zh.chain[i].path for i in zh.used}
    if not used_ja or not used_zh or ja.missing or zh.missing:
        pytest.skip("no CJK system fonts installed")
    assert used_ja != used_zh


def test_han_without_language_warns():
    assert any("language" in w for w in layout("直接", None).warnings)
    assert not layout("直接", "ja").warnings


def test_cjk_wraps_without_spaces_and_respects_kinsoku():
    L = layout("これは長い日本語の文章です。改行できますか。", "ja", max_width=200)
    if L.shaper.missing:
        pytest.skip("no Japanese system font installed")
    lines = [ln for ln, _ in L.lines]
    assert len(lines) > 1
    assert all(w <= 200 + 1 for _, w in L.lines)
    assert not any(ln.startswith("。") for ln in lines)


def test_arabic_wraps_at_spaces():
    L = layout("مرحبا بالعالم مرحبا بالعالم مرحبا بالعالم", "ar", max_width=220)
    assert len(L.lines) > 1 and all(w <= 221 for _, w in L.lines)


def test_arabic_renders_on_canvas(ws):
    s.create_canvas("c", 400, 80)
    s.add_text("c", "مرحبا بالعالم", 200, 40, size=36, anchor="center", color="#ffffff", lang="ar")
    st = s.store()
    r = st.renderer(st.get("c"))
    img = np.asarray(r.render(include_background=False))
    assert img[..., 3].max() == 255
    assert any("fallback" in w for w in r.warnings)


def test_export_refuses_missing_glyphs(ws):
    s.create_canvas("c", 200, 60)
    s.add_text("c", "OK \U000F0001", 10, 10, id="label")
    with pytest.raises(ValueError, match="label"):
        s.export_png("c", path=str(ws / "out.png"))
    s.update_element("c", "label", {"text": "OK"})
    s.export_png("c", path=str(ws / "out.png"))
    assert (ws / "out.png").is_file()


def test_pseudo_modes():
    base = pseudo_localize("Play game", "pseudo")
    long = pseudo_localize("Play game", "pseudo-long")
    rtl = pseudo_localize("Play game", "pseudo-rtl")
    assert len(long) > len(base) and rtl.startswith("‮")
    L = layout(rtl)
    assert L.shaper is not None
    g = L.shaper.shape(rtl)[0]
    assert g[0][2] < g[-1][2] and L.shaper.width(rtl) > 0


def test_engine_notes():
    assert shaping.engine_notes("unity", ["Play"]) == []
    assert any("RTLTMPro" in n for n in shaping.engine_notes("unity", ["مرحبا"]))
    assert any("Full Shaping" in n for n in shaping.engine_notes("all", ["สวัสดี"]))
    assert any("text_server_data" in n for n in shaping.engine_notes("godot", ["日本語"]))


def test_arc_with_complex_text_is_refused():
    with pytest.raises(ValueError, match="arc"):
        layout("مرحبا", "ar", arc={"cx": 100, "cy": 100, "radius": 80})
