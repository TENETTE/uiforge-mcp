"""The game / app designer workflow: button states, rarity card template, clean multi-resolution pin check,
pixel art and a baked bitmap damage font.

Run: python examples/demo_workflow.py  ->  examples/workflow.png, examples/resolutions.png
"""

import io
import json
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from uiforge_mcp import server as ui
from uiforge_mcp.store import Store

HERE = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp())
ui.set_store(Store(TMP / "ws"))

ui.set_theme(
    colors={"bg": "#0d0f18", "ink": "#f8fafc", "muted": "#94a3b8", "violet": "#7c3aed",
            "common": "#94a3b8", "rare": "#38bdf8", "epic": "#a855f7",
            "legendary": "#f59e0b", "mythic": "#f43f5e"},
    styles={"label": {"font": "Rajdhani", "weight": 700, "size": 25, "fill": "$ink", "letter_spacing": 2}},
)

ui.create_canvas("button", 280, 84)
ui.batch("button", [
    {"op": "add_rect", "id": "face", "x": 10, "y": 10, "width": 260, "height": 60, "radius": 14,
     "style": {"material": {"name": "enamel", "color": "#6d28d9"},
               "shadow": {"color": "#000@0.55", "blur": 12, "dy": 5}}},
    {"op": "add_text", "id": "label", "text": "{label}", "x": 140, "y": 40, "anchor": "center", "style": "label"},
])
ui.update_canvas("button", vars={"label": "PLAY"})
ui.set_state("button", "hover", "face", {"style": {"material": {"name": "enamel", "color": "#8b5cf6"},
                                                   "glow": {"color": "#a78bfa@0.8", "blur": 16}}})
ui.set_state("button", "pressed", "face", {"y": 13, "style": {"material": {"name": "enamel", "color": "#4c1d95"},
                                                              "shadow": {"color": "#000@0.5", "blur": 3, "dy": 1}}})
ui.set_state("button", "pressed", "label", {"y": 43})
ui.set_state("button", "disabled", "face", {"style": {"material": "rubber"}})
ui.set_state("button", "disabled", "label", {"style": {"use": "label", "fill": "$muted"}})

ui.create_canvas("states", 1220, 100)
ui.batch("states", [
    {"op": "add_instance", "source": "button", "x": 10 + i * 300, "y": 8, "id": f"b_{st or 'normal'}",
     "vars": {"label": text}, **({"state": st} if st else {})}
    for i, (st, text) in enumerate([(None, "PLAY"), ("hover", "PLAY"), ("pressed", "PLAY"), ("disabled", "LOCKED")])
])

ICONS = {
    "sword": "M21 3L17 3.6L7.5 13L11 16.5L20.4 7ZM4.5 11.5L6 10L14 18L12.5 19.5ZM7 15.5L8.5 17L4.5 21L3 19.5Z",
    "shield": "M12 2.5L20 5.5V11.5C20 16.3 16.6 19.8 12 21.5C7.4 19.8 4 16.3 4 11.5V5.5Z",
    "potion": "M9.5 2.5H14.5V4.5H13.5V8.2C16.6 9.2 19 12 19 15.5A7 7 0 0 1 5 15.5C5 12 7.4 9.2 10.5 8.2V4.5H9.5Z",
    "bolt": "M13.5 2L4.5 13.5H11L10 22L19.5 10H13Z",
    "gem": "M6 3H18L22 9L12 21.5L2 9ZM2 9H22M9 3L7.5 9L12 21.5L16.5 9L15 3",
}
ui.create_canvas("card", 184, 248)
ui.update_canvas("card", colors={"rarity": "$common"})
ui.batch("card", [
    {"op": "add_rect", "id": "outer", "x": 8, "y": 8, "width": 168, "height": 232, "radius": 18,
     "style": {"material": "steel", "shadow": {"color": "#000@0.65", "blur": 14, "dy": 6}}},
    {"op": "add_rect", "id": "frame", "x": 13, "y": 13, "width": 158, "height": 222, "radius": 14,
     "fill": {"type": "linear", "angle": 160, "stops": [[0, "#1c1f30"], [1, "#0b0d16"]]},
     "stroke": {"color": "$rarity", "width": 2, "align": "inside"}},
    {"op": "add_rect", "id": "halo", "x": 15, "y": 15, "width": 154, "height": 132, "radius": 12,
     "fill": {"type": "radial", "cx": 0.5, "cy": 0.52, "r": 0.62, "stops": [[0, "$rarity@0.5"], [1, "$rarity@0"]]}},
    {"op": "add_path", "id": "icon", "d": ICONS["sword"], "x": 52, "y": 36, "scale": 80 / 24, "fill_rule": "nonzero",
     "fill": {"type": "linear", "angle": 90, "stops": [[0, "#ffffff"], [1, "$rarity"]]},
     "style": {"glow": {"color": "$rarity@0.5", "blur": 10}, "shadow": {"color": "#000@0.6", "blur": 6, "dy": 4}}},
    {"op": "add_text", "id": "name", "text": "{title}", "x": 92, "y": 170, "anchor": "center", "font": "Rajdhani",
     "weight": 700, "size": 20, "color": "$ink", "fit_width": 140},
    {"op": "add_text", "id": "tier", "text": "{tier}", "x": 92, "y": 196, "anchor": "center", "font": "Rajdhani",
     "weight": 700, "size": 12, "letter_spacing": 3, "color": "$rarity", "uppercase": True},
    {"op": "add_text", "id": "stat", "text": "{stat}", "x": 92, "y": 217, "anchor": "center", "font": "JetBrains Mono",
     "size": 11, "color": "$muted"},
])
rows = [
    {"name": "c1", "title": "Iron Sword", "tier": "common", "stat": "ATK +12", "colors": {"rarity": "$common"}},
    {"name": "c2", "title": "Aegis Shield", "tier": "rare", "stat": "DEF +18", "colors": {"rarity": "$rare"},
     "props": {"icon": {"d": ICONS["shield"]}}},
    {"name": "c3", "title": "Arcane Elixir", "tier": "epic", "stat": "+40 HP", "colors": {"rarity": "$epic"},
     "props": {"icon": {"d": ICONS["potion"]}}},
    {"name": "c4", "title": "Storm Core", "tier": "legendary", "stat": "SPD +25%", "colors": {"rarity": "$legendary"},
     "props": {"icon": {"d": ICONS["bolt"]}}},
    {"name": "c5", "title": "Void Heart", "tier": "mythic", "stat": "ALL +10", "colors": {"rarity": "$mythic"},
     "props": {"icon": {"d": ICONS["gem"], "fill_rule": "evenodd"}}},
]
cards = ui.generate_from_template("card", rows, name_prefix="card")["canvases"]

ui.create_canvas("hud", preset="1080p",
                 background={"type": "radial", "cx": 0.5, "cy": 0.45, "r": 0.85,
                             "stops": [[0, "#1c2640"], [1, "#090d16"]]})
ui.batch("hud", [
    {"op": "add_rect", "x": 0, "y": 0, "width": 1920, "height": 6, "fill": "#22d3ee", "id": "topline"},
    {"op": "add_rect", "x": 110, "y": 72, "width": 440, "height": 106, "radius": 18, "fill": "#0d111e@0.86",
     "stroke": {"color": "#22d3ee@0.45", "width": 2}, "group": "status"},
    {"op": "add_rect", "x": 134, "y": 124, "width": 392, "height": 20, "radius": 10, "fill": "#05070d",
     "group": "status", "id": "hp_track"},
    {"op": "add_rect", "x": 134, "y": 124, "width": 296, "height": 20, "radius": 10, "clip": "hp_track",
     "group": "status", "fill": {"type": "linear", "angle": 0, "stops": ["#fb7185", "#e11d48"]}},
    {"op": "add_text", "text": "NOVA  ·  LV 42", "x": 134, "y": 90, "size": 22, "font": "Rajdhani", "weight": 700,
     "color": "$ink", "group": "status"},
    {"op": "add_ellipse", "cx": 1700, "cy": 178, "rx": 108,
     "fill": {"type": "grid", "color": "#22d3ee@0.28", "color2": "#071019", "size": 22},
     "stroke": {"color": "#22d3ee@0.55", "width": 2.5}, "group": "map"},
    {"op": "add_polygon", "cx": 1700, "cy": 178, "radius": 12, "sides": 3, "fill": "#22d3ee", "group": "map"},
    {"op": "add_rect", "x": 660, "y": 904, "width": 600, "height": 96, "radius": 20, "fill": "#0d111e@0.86",
     "stroke": {"color": "#8b5cf6@0.5", "width": 2}, "group": "hotbar"},
    {"op": "add_text", "text": "OBJECTIVE: BREACH THE CITADEL", "x": 960, "y": 92, "anchor": "center", "size": 26,
     "font": "Rajdhani", "weight": 700, "letter_spacing": 3, "color": "$ink", "group": "objective",
     "stroke": {"color": "#000@0.75", "width": 2}},
])
for i in range(5):
    ui.add_rect("hud", 686 + i * 114, 920, 64, 64, radius=12, fill="#05070d",
                stroke={"color": "#f59e0b" if i == 0 else "#ffffff@0.2", "width": 2}, group="hotbar")
ui.set_pin("hud", "left", "top", group="status")
ui.set_pin("hud", "right", "top", group="map")
ui.set_pin("hud", "center", "bottom", group="hotbar")
ui.set_pin("hud", "center", "top", group="objective")
ui.set_pin("hud", "stretch", "top", ids=["topline"])
res = ui.preview_resolutions("hud", sizes=[[1920, 1080], [2560, 1080], [1280, 800], "mobile-game-landscape"],
                             cell=460, guides=None)
Image.open(io.BytesIO(res[0].data)).save(HERE / "resolutions.png")

ui.create_canvas("pixel_potion", 16, 16)
ui.batch("pixel_potion", [
    {"op": "add_path", "d": ICONS["potion"], "x": 0, "y": 0, "scale": 16 / 24, "fill": "#e11d48",
     "stroke": {"color": "#3b0718", "width": 1, "align": "outside"}},
    {"op": "add_rect", "x": 5, "y": 9, "width": 2, "height": 3, "fill": "#fda4af"},
])
ui.update_canvas("pixel_potion", pixel_art={"palette": ["#e11d48", "#3b0718", "#fda4af", "#9f1239"]})

font_out = ui.export_bitmap_font("damage", "0123456789!", size=56, font="Bangers",
                                 fill={"type": "linear", "angle": 90, "stops": ["#fff7c2", "#f59e0b", "#b45309"]},
                                 stroke={"color": "#2a1003", "width": 5},
                                 style={"shadow": {"color": "#000@0.6", "blur": 0, "dy": 4}},
                                 out_dir=str(TMP / "font"), preview_text="1250!")


def render(cid: str, scale: float = 1.0) -> Image.Image:
    st = ui.store()
    return st.renderer(st.get(cid), scale).render()


W = 1260
sheet = Image.new("RGB", (W, 560), (13, 15, 24))
d = ImageDraw.Draw(sheet)
states_img = render("states")
sheet.paste(states_img, (20, 42), states_img)
for i, lbl in enumerate(["NORMAL", "HOVER", "PRESSED", "DISABLED"]):
    d.text((40 + i * 300, 18), lbl, fill=(148, 163, 184))
x = 20
for cid in cards:
    img = render(cid)
    sheet.paste(img, (x, 180), img)
    x += 196
pix = render("pixel_potion", 8)
sheet.paste(pix, (1046, 198), pix)
d.text((1030, 342), "Pixel art 16x16 (4 colours)", fill=(148, 163, 184))
font_img = Image.open(io.BytesIO(font_out[0].data))
sheet.paste(font_img, (1016, 426))
d.text((1016, 404), "Baked BMFont damage text", fill=(148, 163, 184))
d.text((24, 156), "ONE CARD TEMPLATE  +  5 DATA ROWS", fill=(148, 163, 184))
d.text((24, 462), "All rendered natively from live instances, templates, pixel-art quantization & BMFont.", fill=(100, 116, 139))
sheet.save(HERE / "workflow.png")
print("wrote", HERE / "workflow.png", "and", HERE / "resolutions.png")
print(json.dumps(ui.review_canvas("hud")["issues"][:3], ensure_ascii=False))
