"""PBR texture map baking showcase & parametric AAA frame gallery, rendered by uiforge-mcp itself.

Run: python examples/demo_pbr_maps.py  ->  examples/pbr_maps.png, examples/frames.png
"""

import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from uiforge_mcp import server as ui
from uiforge_mcp import tools_delivery as td
from uiforge_mcp.frames import FRAME_PRESETS
from uiforge_mcp.store import Store

OUT = Path(__file__).resolve().parent
tmp = Path(tempfile.mkdtemp())
ui.set_store(Store(tmp / "ws"))

ui.create_canvas("crest", 260, 260)
ui.batch("crest", [
    {"op": "add_ellipse", "id": "ring_out", "cx": 130, "cy": 130, "rx": 108, "ry": 108,
     "style": {"material": "hammered_gold", "shadow": {"blur": 22, "dy": 10, "color": "#000@0.65"}}},
    {"op": "add_ellipse", "id": "bed", "cx": 130, "cy": 130, "rx": 82, "ry": 82,
     "style": {"material": "obsidian", "inner_shadow": {"blur": 16, "dy": 5, "color": "#000@0.85"}}},
    {"op": "add_polygon", "id": "star", "cx": 130, "cy": 130, "radius": 68, "inner_radius": 32, "sides": 8,
     "style": {"material": "gold", "shadow": {"blur": 10, "dy": 4, "color": "#000@0.6"}}},
    {"op": "add_polygon", "id": "jewel", "cx": 130, "cy": 130, "radius": 34, "sides": 6, "point_rotation": 30,
     "style": {"material": "ruby", "shadow": {"blur": 8, "dy": 3, "color": "#000@0.65"}}},
])
for i in range(12):
    import math
    ang = math.radians(i * 30)
    ui.add_ellipse("crest", 130 + 95 * math.cos(ang), 130 + 95 * math.sin(ang), 5.5, 5.5,
                   style={"material": "chrome"})

res = td.export_pbr_maps("crest", out_dir=str(tmp / "pbr"), engine="godot")
pbr_dir = Path(res["folder"])

panels = [
    ("FINAL PBR RENDER", "beauty"),
    ("ALBEDO", "albedo"),
    ("TANGENT NORMAL", "normal"),
    ("ROUGHNESS", "roughness"),
    ("METALLIC", "metallic"),
    ("AMBIENT OCCLUSION", "ao"),
]
cw, ch = 220, 256
sheet = Image.new("RGB", (len(panels) * cw + 32, ch + 28), (16, 19, 27))
draw = ImageDraw.Draw(sheet)
for idx, (label, key) in enumerate(panels):
    im = Image.open(pbr_dir / res["files"][key]).convert("RGBA").resize((200, 200), Image.LANCZOS)
    x0 = 16 + idx * cw + 10
    card = Image.new("RGBA", (200, 200), (24, 28, 40, 255))
    card.alpha_composite(im)
    sheet.paste(card.convert("RGB"), (x0, 18))
    draw.rectangle([x0, 18, x0 + 200, 218], outline=(52, 60, 82), width=1)
    tw = draw.textlength(label)
    draw.text((x0 + (200 - tw) / 2, 230), label, fill=(226, 232, 240))
sheet.save(OUT / "pbr_maps.png", optimize=True)

ui.create_canvas("frames_demo", 1040, 810, background="#0f121b")
titles = {
    "rpg_gold": "Inventory",
    "royal_ornate": "Royal Decree",
    "fantasy_parchment": "Quest Scroll",
    "scifi_hud": "Telemetry",
    "cyber_tech": "Override",
    "glass_card": "Liquid Card",
    "medieval_iron": "Armory",
    "luxury_minimal": "Profile",
    "cartoon_thick": "QUESTS!",
}
fw, fh, gx, gy = 312, 236, 26, 26
for idx, preset in enumerate(FRAME_PRESETS):
    col, row = idx % 3, idx // 3
    fx = 26 + col * (fw + gx)
    fy = 26 + row * (fh + gy)
    if preset in ("glass_card", "scifi_hud"):
        ui.add_rect("frames_demo", fx + 20, fy + 26, fw - 40, fh - 48, radius=18,
                    style={"fill": [{"type": "linear", "angle": 35, "stops": ["#f43f5e@0.75", "#7c3aed@0.75", "#06b6d4@0.75"]},
                                    {"type": "stripes", "color": "#ffffff@0.22", "color2": "transparent", "size": 14, "angle": 45}]})
    f = ui.add_frame("frames_demo", fx, fy, fw, fh, preset=preset, title=titles[preset], id_prefix=preset)
    ix, iy, iw, ih = f["inner_box"]
    dark_text = preset in ("cartoon_thick", "fantasy_parchment")
    txt_col = "#1c130a" if preset == "fantasy_parchment" else ("#0f172a" if preset == "cartoon_thick" else "#e2e8f0")
    sub_col = "#4a2e16" if preset == "fantasy_parchment" else ("#1e293b" if preset == "cartoon_thick" else "#94a3b8")
    ui.add_text("frames_demo", f"preset: {preset}", ix + iw / 2, iy + ih / 2 - 8, anchor="center",
                size=14, weight=700, color=txt_col)
    ui.add_text("frames_demo", "100% editable vector + PBR", ix + iw / 2, iy + ih / 2 + 14, anchor="center",
                size=11, color=sub_col)

st = ui.store()
st.renderer(st.get("frames_demo"), 1).render().convert("RGB").save(OUT / "frames.png", optimize=True)
print("wrote", OUT / "pbr_maps.png", OUT / "frames.png")
