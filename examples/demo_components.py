"""Components, arrays, arc text, cut-outs and SVG import: a ranked-season emblem and a quick-slot ring.

Run: python examples/demo_components.py  ->  examples/components.png
"""

import json
import tempfile
from pathlib import Path

from game_ui_mcp import server as ui
from game_ui_mcp.store import Store

HERE = Path(__file__).resolve().parent
ui.set_store(Store(Path(tempfile.mkdtemp()) / "ws"))

ui.set_theme(colors={"gold": "hsl(42, 90%, 58%)", "gold_dk": "hsl(32, 80%, 28%)", "gold_md": "hsl(38, 78%, 46%)", "ink": "#0c1018",
                     "steel": "#8b98ab", "accent": "hsl(190, 95%, 55%)"})

ui.create_canvas("gem", 64, 64)
ui.batch("gem", [
    {"op": "add_polygon", "id": "cut", "cx": 32, "cy": 32, "radius": 28, "sides": 6, "point_rotation": 30,
     "style": {"material": {"name": "gem", "color": "#0ea5e9"},
               "stroke": {"color": "#e8fbff@0.8", "width": 1.5, "join": "miter"}}},
])

ui.create_canvas("emblem", 360, 360)
ui.batch("emblem", [
    {"op": "add_ellipse", "id": "rim", "cx": 180, "cy": 180, "rx": 150,
     "style": {"material": "gold", "shadow": {"color": "#000@0.65", "blur": 24, "dy": 10}}},
    {"op": "add_ellipse", "id": "face", "cx": 180, "cy": 180, "rx": 116,
     "style": {"material": "obsidian", "inner_shadow": {"blur": 16, "dy": 6, "color": "#000@0.85"}}},
    {"op": "add_ellipse", "id": "track", "cx": 180, "cy": 180, "rx": 144, "fill": "none",
     "stroke": {"color": "#00000055", "width": 2, "dash": [3, 5], "align": "center"}},
    {"op": "add_text", "id": "title", "text": "GRAND CHAMPION", "x": 0, "y": 0, "size": 19, "font": "Rajdhani",
     "weight": 700, "letter_spacing": 3, "anchor": "middle-center",
     "arc": {"cx": 180, "cy": 180, "radius": 132, "angle": -90},
     "fill": "#1e1204", "style": {"shadow": {"color": "#fff@0.4", "blur": 0, "dy": 1}}},
    {"op": "add_text", "id": "season", "text": "SEASON 07", "x": 0, "y": 0, "size": 16, "font": "Rajdhani",
     "weight": 700, "letter_spacing": 4, "anchor": "middle-center",
     "arc": {"cx": 180, "cy": 180, "radius": 132, "side": "inner"}, "fill": "#1e1204"},
    {"op": "create_layer", "name": "star", "style": {"shadow": {"color": "#000@0.7", "blur": 12, "dy": 5}}},
    {"op": "add_polygon", "id": "star", "cx": 180, "cy": 172, "radius": 78, "inner_radius": 34, "sides": 5,
     "style": {"material": "gold"}},
    {"op": "add_ellipse", "id": "hole", "cx": 180, "cy": 180, "rx": 26, "style": {"blend": "erase"}},
    {"op": "add_instance", "id": "gem", "source": "gem", "x": 156, "y": 156, "width": 48,
     "style": {"glow": {"color": "$accent@0.6", "blur": 14}}},
])
ui.add_ellipse("emblem", 180, 35, 2.5, fill={"type": "radial", "cx": 0.35, "cy": 0.3, "stops": [[0, "#fff"], [1, "$gold_dk"]]}, id="rivet")
ui.duplicate_element("emblem", "rivet", count=23, rotate=15, pivot=[180, 180], new_id="rivet")

ui.create_canvas("ring", 360, 360)
ui.add_ellipse("ring", 180, 180, 120, fill="none", stroke={"color": "$steel@0.5", "width": 2, "dash": [10, 6]})
ui.add_rect("ring", 160, 38, 40, 40, radius=8, fill="#151b26", stroke={"color": "$steel", "width": 2}, id="slot")
ui.duplicate_element("ring", "slot", count=7, rotate=45, pivot=[180, 180], new_id="slot")
ui.add_instance("ring", "gem", 166, 44, width=28, id="g")
ui.duplicate_element("ring", "g", count=7, rotate=45, pivot=[180, 180], new_id="g")
ui.add_svg("ring", '<svg viewBox="0 0 24 24"><path d="M4 12h12M11 6l6 6-6 6" fill="none" stroke="currentColor" '
                   'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
           196, 162, 36, 36, color="#e6edf7", id_prefix="arrow_r")
ui.add_svg("ring", '<svg viewBox="0 0 24 24"><path d="M4 12h12M11 6l6 6-6 6" fill="none" stroke="currentColor" '
                   'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
           128, 162, 36, 36, color="#e6edf7", id_prefix="arrow_l")
ui.update_element("ring", "arrow_l_1", {"flip_x": True})

print("fit:", ui.fit_canvas("emblem", padding=4))
for name in ("emblem", "ring"):
    print(name, json.dumps(ui.review_canvas(name)["issues"], ensure_ascii=False))

sheet = ui.contact_sheet(["emblem", "ring", "gem"], columns=3, cell=360, background="dark")
from PIL import Image
import io
Image.open(io.BytesIO(sheet[0].data)).save(HERE / "components.png")
print("wrote", HERE / "components.png")
