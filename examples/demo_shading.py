"""Layers, lighting and shading: the same shapes drawn flat and then built up in passes.

    python examples/demo_shading.py

Writes shading_kit.png (contact sheet), orb_layers.png (the orb's layers side by side) and orb.psd.
"""

import tempfile
from pathlib import Path

from uiforge_mcp import server as ui
from uiforge_mcp.store import Store

OUT = Path(__file__).resolve().parent
ui.set_store(Store(Path(tempfile.mkdtemp()) / "ws"))

ui.create_canvas("orb_flat", 240, 240)
ui.batch("orb_flat", [
    {"op": "add_ellipse", "cx": 120, "cy": 116, "rx": 80, "fill": "#c81e3a"},
    {"op": "add_arc", "cx": 120, "cy": 116, "radius": 86, "start_angle": 0, "end_angle": 360, "thickness": 12,
     "color": "#b9902f"},
])

ui.create_canvas("orb", 240, 240)
ui.batch("orb", [
    {"op": "create_layer", "name": "ground"},
    {"op": "add_ellipse", "cx": 120, "cy": 214, "rx": 74, "ry": 12, "fill": "#000000@0.55", "style": {"blur": 14}},

    {"op": "create_layer", "name": "body"},
    {"op": "add_ellipse", "id": "glass", "cx": 120, "cy": 116, "rx": 80,
     "fill": {"type": "radial", "cx": 0.42, "cy": 0.38, "r": 0.7, "space": "oklab",
              "stops": [[0, "#ff5b6e"], [0.55, "#c81e3a"], [1, "#5c0a1c"]]}},

    {"op": "create_layer", "name": "shade", "clip": True, "blend": "multiply"},
    {"op": "add_ellipse", "cx": 120, "cy": 116, "rx": 82,
     "fill": {"type": "radial", "cx": 0.3, "cy": 0.28, "r": 0.98,
              "stops": [[0, "#3b0613@0"], [0.42, "#3b0613@0"], [1, "#22030b@0.92"]]}},
    {"op": "add_ellipse", "cx": 120, "cy": 196, "rx": 70, "ry": 26, "fill": "#2a0410@0.7", "style": {"blur": 22}},
    {"op": "add_ellipse", "cx": 120, "cy": 116, "rx": 80,
     "fill": {"type": "clouds", "color": "#40000f@0.55", "color2": "#40000f@0", "size": 46, "octaves": 4,
              "seed": 7, "contrast": 1.7}},

    {"op": "create_layer", "name": "light", "clip": True, "blend": "screen"},
    {"op": "add_ellipse", "cx": 92, "cy": 84, "rx": 52, "ry": 40, "rotation": -28, "fill": "#ffd9de@0.55",
     "style": {"blur": 26}},
    {"op": "add_ellipse", "cx": 88, "cy": 76, "rx": 22, "ry": 11, "rotation": -32, "fill": "#ffffff@0.95",
     "style": {"blur": 3, "mask": {"type": "linear", "angle": 90, "stops": ["#000000", "#000000@0.25"]}}},
    {"op": "add_ellipse", "cx": 112, "cy": 62, "rx": 5, "ry": 3.5, "fill": "#ffffff", "style": {"blur": 1.5}},
    {"op": "add_arc", "cx": 120, "cy": 116, "radius": 72, "start_angle": 20, "end_angle": 110, "thickness": 7,
     "cap": "round", "color": "#ff9aa6@0.75", "style": {"blur": 7}},

    {"op": "create_layer", "name": "ring",
     "style": {"light": {"angle": 225, "size": 5, "depth": 1.4, "gloss": 0.8, "highlight": "#fff6d8@0.85",
                         "shadow": "#2a1a00@0.75"},
               "stroke": {"color": "#2b1c05", "width": 1.5, "align": "outside"},
               "shadow": {"color": "#000000@0.6", "blur": 10, "dy": 5}}},
    {"op": "add_arc", "cx": 120, "cy": 116, "radius": 86, "start_angle": 0, "end_angle": 360, "thickness": 13,
     "color": {"type": "conic", "from": 200, "space": "oklab",
               "stops": ["#f6d98a", "#a9781c", "#ffe9a8", "#8a5e12", "#e9c463", "#9a6c18", "#f6d98a"]}},
    {"op": "add_ticks", "cx": 120, "cy": 116, "radius": 91, "start_angle": 0, "end_angle": 360, "count": 12,
     "length": 10, "width": 5, "cap": "round", "color": "#d9ae4b"},
])

ui.create_canvas("title", 560, 170)
ui.batch("title", [
    {"op": "create_layer", "name": "letters",
     "style": {"shadow": [{"color": "#000000@0.7", "blur": 14, "dy": 8}, {"color": "#ff9d00@0.35", "blur": 30}]}},
    {"op": "add_text", "text": "VICTORY", "x": 280, "y": 84, "anchor": "center", "font": "Cinzel", "weight": 900,
     "size": 96, "letter_spacing": 4,
     "color": {"type": "linear", "angle": 90, "space": "oklab",
               "stops": [[0, "#fff3c4"], [0.45, "#f2c14a"], [0.5, "#b07a14"], [0.56, "#e9b93f"], [1, "#8a5a0c"]]},
     "stroke": [{"color": "#5a3605", "width": 2.5}, {"color": "#ffe9a6", "width": 1.5, "offset": 2.5},
                {"color": "#2c1802", "width": 3, "offset": 4}],
     "style": {"light": {"angle": 240, "size": 4, "depth": 1.6, "profile": "chisel", "gloss": 0.9,
                         "highlight": "#ffffff@0.8", "shadow": "#3a2200@0.7"}}},
    {"op": "create_layer", "name": "glint", "clip": True, "blend": "screen"},
    {"op": "add_rect", "x": 330, "y": -20, "width": 34, "height": 220, "skew": 28,
     "fill": {"type": "linear", "angle": 0, "stops": ["#ffffff@0", "#ffffff@0.45", "#ffffff@0"]}},
])

ui.create_canvas("button_flat", 380, 130)
ui.batch("button_flat", [
    {"op": "add_rect", "x": 30, "y": 26, "width": 320, "height": 70, "radius": 16, "fill": "#2f7de0"},
    {"op": "add_text", "text": "CONTINUE", "x": 190, "y": 61, "anchor": "center", "font": "Rajdhani", "weight": 700,
     "size": 34, "letter_spacing": 2, "color": "#ffffff"},
])
ui.create_canvas("button", 380, 130)
ui.batch("button", [
    {"op": "create_layer", "name": "plate",
     "style": {"shadow": [{"color": "#000000@0.55", "blur": 4, "dy": 3}, {"color": "#0a2a5e@0.6", "blur": 22, "dy": 12}]}},
    {"op": "add_rect", "id": "plate", "x": 30, "y": 26, "width": 320, "height": 70, "radius": 16,
     "fill": {"type": "linear", "angle": 90, "space": "oklab", "stops": [[0, "#63b0ff"], [0.5, "#2f7de0"], [1, "#1b4fa6"]]},
     "stroke": [{"color": "#0d2c66", "width": 2, "align": "outside"},
                {"color": "#bfe0ff@0.55", "width": 1.5, "align": "inside", "offset": 1}],
     "style": {"light": {"angle": 250, "size": 9, "depth": 1.2, "gloss": 0.5, "highlight": "#ffffff@0.55",
                         "shadow": "#06204f@0.65"}}},
    {"op": "create_layer", "name": "surface", "clip": True, "blend": "soft-light"},
    {"op": "add_rect", "x": 30, "y": 26, "width": 320, "height": 70,
     "fill": {"type": "hex", "color": "#ffffff@0.5", "size": 14, "line_width": 1}},
    {"op": "add_ellipse", "cx": 120, "cy": 30, "rx": 150, "ry": 40, "fill": "#ffffff@0.6", "style": {"blur": 26}},
    {"op": "create_layer", "name": "label",
     "style": {"shadow": {"color": "#06204f@0.8", "blur": 3, "dy": 2}}},
    {"op": "add_text", "text": "CONTINUE", "x": 190, "y": 61, "anchor": "center", "font": "Rajdhani", "weight": 700,
     "size": 34, "letter_spacing": 2,
     "color": {"type": "linear", "angle": 90, "stops": ["#ffffff", "#d6ebff"]}},
])

SHIELD = "M100 14L176 40V104C176 156 142 192 100 212C58 192 24 156 24 104V40Z"
ui.create_canvas("shield", 200, 230)
ui.batch("shield", [
    {"op": "create_layer", "name": "plate",
     "style": {"stroke": [{"color": "#e8c66a", "width": 5, "align": "inside"},
                          {"color": "#3a2606", "width": 2.5, "align": "outside"}],
               "light": {"angle": 225, "size": 7, "depth": 1.3, "gloss": 0.6},
               "shadow": {"color": "#000000@0.6", "blur": 12, "dy": 7}}},
    {"op": "add_path", "d": SHIELD, "fill": {"type": "linear", "angle": 90, "space": "oklab",
                                               "stops": ["#3d7bd9", "#1f3f8f"]}},
    {"op": "create_layer", "name": "half", "clip": True, "blend": "multiply"},
    {"op": "add_rect", "x": 100, "y": 0, "width": 100, "height": 230, "fill": "#0c1b46@0.55"},
    {"op": "add_rect", "x": 0, "y": 120, "width": 200, "height": 110,
     "fill": {"type": "linear", "angle": 90, "stops": ["#081235@0", "#081235@0.75"]}},
    {"op": "create_layer", "name": "sheen", "clip": True, "blend": "screen"},
    {"op": "add_ellipse", "cx": 66, "cy": 56, "rx": 62, "ry": 40, "rotation": -20, "fill": "#bcd8ff@0.5",
     "style": {"blur": 20}},
    {"op": "create_layer", "name": "emblem",
     "style": {"light": {"angle": 225, "size": 4, "depth": 1.5, "gloss": 1.0},
               "stroke": {"color": "#3a2606", "width": 2, "align": "outside"},
               "shadow": {"color": "#000000@0.5", "blur": 5, "dy": 3}}},
    {"op": "add_polygon", "cx": 100, "cy": 106, "radius": 46, "sides": 5, "inner_radius": 19,
     "fill": {"type": "linear", "angle": 90, "space": "oklab", "stops": ["#fff0b8", "#e3ad2f", "#9a6a10"]}},
])

sheet, _ = ui.contact_sheet(["orb_flat", "orb", "button_flat", "button", "title", "shield"], columns=3, cell=320,
                            background="dark", save_path=str(OUT / "shading_kit.png"))

parts = ui.export_layers("orb", out_dir=str(OUT / "_orb_layers"), merge_clipped=False, trim=False)
from PIL import Image  # noqa: E402

tiles = [Image.open(OUT / "_orb_layers" / layer["file"]) for layer in parts["layers"]]
strip = Image.new("RGBA", (len(tiles) * 250 + 10, 280), (24, 24, 30, 255))
from PIL import ImageDraw, ImageFont  # noqa: E402

draw = ImageDraw.Draw(strip)
for i, (tile, layer) in enumerate(zip(tiles, parts["layers"])):
    strip.alpha_composite(tile, (10 + i * 250, 8))
    draw.text((10 + i * 250 + 6, 254), layer["name"] + (f"  ({layer['blend']})" if layer.get("blend") else ""),
              fill="#ffffff", font=ImageFont.load_default(14))
strip.convert("RGB").save(OUT / "orb_layers.png")
for f in (OUT / "_orb_layers").iterdir():
    f.unlink()
(OUT / "_orb_layers").rmdir()

psd = ui.export_psd("orb", str(OUT / "orb.psd"))
print("written: shading_kit.png, orb_layers.png, orb.psd", [layer["name"] for layer in psd["layers_bottom_to_top"]])
