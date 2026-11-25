"""Animations made with the same tool calls an AI would make.

    python examples/demo_animation.py

Writes anim_button.gif, anim_gauge.gif, anim_menu.gif and their filmstrips next to this file.
"""

import tempfile
from pathlib import Path

from uiforge_mcp import server as ui
from uiforge_mcp.store import Store

OUT = Path(__file__).resolve().parent
ui.set_store(Store(Path(tempfile.mkdtemp()) / "ws"))
ui.set_theme(colors={"primary": "#8b5cf6", "text": "#f4f1ff", "muted": "#8b929c", "red": "#ff3b30", "line": "#ffffff@0.14"})


def strip(canvas, animation, name, **kw):
    image, _ = ui.preview_animation(canvas, animation, **kw)
    (OUT / name).write_bytes(image.data)


ui.create_canvas("button", 360, 130, "#0f0d18")
ui.batch("button", [
    {"op": "add_rect", "id": "body", "group": "btn", "x": 36, "y": 34, "width": 288, "height": 60, "radius": 14,
     "corner": "cut", "fill": {"type": "linear", "angle": 90, "stops": [[0, "#a78bfa"], [0.5, "#7c3aed"], [1, "#5b21b6"]]},
     "stroke": {"color": "#ddd6fe@0.9", "width": 2},
     "style": {"glow": {"color": "#8b5cf6@0.7", "blur": 14}, "shadow": {"color": "#000@0.5", "blur": 10, "dy": 6},
               "bevel": {"size": 2}}},
    {"op": "add_rect", "id": "shine", "group": "btn", "x": -40, "y": 30, "width": 46, "height": 70, "skew": 24,
     "clip": "body", "fill": {"type": "linear", "angle": 0, "stops": ["#ffffff@0", "#ffffff@0.55", "#ffffff@0"]}},
    {"op": "add_text", "id": "label", "group": "btn", "text": "OYUNA BAŞLA", "x": 180, "y": 64, "anchor": "center",
     "font": "Rajdhani", "weight": 700, "size": 28, "letter_spacing": 2, "color": "#ffffff",
     "style": {"shadow": {"color": "#2e1065@0.9", "blur": 4, "dy": 2}}},
    {"op": "create_animation", "name": "appear", "duration": 1.6},
    {"op": "set_keyframes", "animation": "appear", "target": "group:btn", "property": "scale", "pivot": [180, 64],
     "keyframes": [[0, 0.55], [0.28, 1, "back-out"]]},
    {"op": "set_keyframes", "animation": "appear", "target": "group:btn", "property": "opacity",
     "keyframes": [[0, 0], [0.14, 1, "quad-out"]]},
    {"op": "set_keyframes", "animation": "appear", "target": "shine", "property": "dx",
     "keyframes": [[0.35, 0], [0.85, 400, "quad-in-out"]]},
    {"op": "set_keyframes", "animation": "appear", "target": "body", "property": "style.glow.blur",
     "keyframes": [[0.28, 14], [0.7, 34, "sine-out"], [1.6, 14, "sine-in-out"]]},
])
strip("button", "appear", "anim_button_strip.png", frames=8, columns=4, cell=300)
ui.export_animation("button", "appear", format="gif", path=str(OUT / "anim_button.gif"), fps=20)

CX = CY = 220
ui.create_canvas("gauge", 440, 440, "#0b0c0f")
ui.batch("gauge", [
    {"op": "add_ellipse", "group": "dial", "cx": CX, "cy": CY, "rx": 206,
     "fill": {"type": "radial", "stops": [[0, "#1c2026"], [0.72, "#0c0e11"], [1, "#050607"]]},
     "stroke": {"color": {"type": "linear", "angle": 70, "stops": ["#7b838d", "#1b1e23", "#565d66"]}, "width": 6},
     "style": {"inner_shadow": {"color": "#000000@0.9", "blur": 26, "dy": 6}}},
    {"op": "add_arc", "group": "dial", "cx": CX, "cy": CY, "radius": 186, "start_angle": 135, "end_angle": 405,
     "thickness": 12, "color": "#ffffff@0.07"},
    {"op": "add_arc", "group": "dial", "cx": CX, "cy": CY, "radius": 166, "start_angle": 345, "end_angle": 405,
     "thickness": 5, "color": "$red"},
    {"op": "add_ticks", "id": "rpm", "group": "dial", "cx": CX, "cy": CY, "radius": 176, "start_angle": 135,
     "end_angle": 405, "count": 37, "major_every": 4, "length": 8, "width": 1.5, "major_length": 17, "major_width": 3,
     "color": "#ffffff@0.42", "major_color": "#f2f4f7", "labels": [str(i) for i in range(10)], "label_size": 26,
     "label_font": "Barlow Condensed", "label_weight": 600, "label_italic": True, "label_color": "#d5dae1"},
    {"op": "add_arc", "id": "value", "group": "value", "cx": CX, "cy": CY, "radius": 186, "start_angle": 135,
     "end_angle": 135, "thickness": 12,
     "color": {"type": "conic", "from": 135, "to": 405,
               "stops": [[0, "#dfe6ee"], [0.62, "#f2f4f7"], [0.76, "#ffb020"], [0.9, "#ff3b30"]]},
     "style": {"glow": {"color": "#ffb020@0.55", "blur": 18}}},
    {"op": "add_polygon", "id": "needle", "group": "needle", "origin": [CX, CY], "rotation": 135,
     "points": [[CX - 34, CY - 4.5], [CX + 168, CY - 1.2], [CX + 168, CY + 1.2], [CX - 34, CY + 4.5]],
     "fill": {"type": "linear", "angle": 90, "stops": ["#ff6a60", "#ff3b30", "#b3170f"]},
     "style": {"glow": {"color": "#ff3b30@0.75", "blur": 14}, "shadow": {"color": "#000000@0.7", "blur": 8, "dy": 5}}},
    {"op": "add_ellipse", "group": "hub", "cx": CX, "cy": CY, "rx": 22,
     "fill": {"type": "conic", "stops": ["#e6eaef", "#5a616b", "#f4f6f8", "#474d55", "#cfd5dc", "#5a616b", "#e6eaef"]},
     "stroke": {"color": "#000000@0.7", "width": 1.5}},
    {"op": "add_text", "id": "gear", "text": "1", "x": CX, "y": CY + 128, "anchor": "center",
     "font": "Barlow Condensed", "weight": 700, "italic": True, "size": 76, "color": "#f2f4f7"},
    {"op": "create_animation", "name": "rev", "duration": 2.4, "loop": True},
])
rev = [[0, 135], [0.9, 372, "quad-in"], [1.05, 262, "quad-out"], [1.9, 380, "quad-in"], [2.4, 135, "cubic-in-out"]]
ui.batch("gauge", [
    {"op": "set_keyframes", "animation": "rev", "target": "needle", "property": "rotation", "keyframes": rev},
    {"op": "set_keyframes", "animation": "rev", "target": "value", "property": "end_angle",
     "keyframes": rev},
    {"op": "set_keyframes", "animation": "rev", "target": "gear", "property": "text",
     "keyframes": [[0, "1"], [0.9, "2", "step"], [2.25, "1", "step"]]},
    {"op": "set_keyframes", "animation": "rev", "target": "gear", "property": "scale",
     "keyframes": [[0.88, 1], [0.94, 1.35, "quad-out"], [1.1, 1, "quad-in-out"]]},
    {"op": "set_keyframes", "animation": "rev", "target": "gear", "property": "style.fill",
     "keyframes": [[0.88, "#f2f4f7"], [0.94, "#ff3b30", "quad-out"], [1.25, "#f2f4f7", "quad-in-out"]]},
])
strip("gauge", "rev", "anim_gauge_strip.png", frames=8, columns=4, cell=260)
ui.export_animation("gauge", "rev", format="gif", path=str(OUT / "anim_gauge.gif"), fps=15, scale=0.5)

ui.create_canvas("menu", 420, 320, {"type": "linear", "angle": 90, "stops": ["#1a1e25", "#0b0c0f"]})
items = ["CAREER", "QUICK RACE", "GARAGE", "SETTINGS"]
ops = [{"op": "add_rect", "id": "bar", "x": 40, "y": 44, "width": 5, "height": 44, "fill": "$red",
        "style": {"glow": {"color": "#ff3b30@0.7", "blur": 12}}},
       {"op": "add_rect", "id": "hl", "x": 45, "y": 44, "width": 320, "height": 44,
        "fill": {"type": "linear", "angle": 0, "stops": ["#ffffff@0.12", "#ffffff@0"]}}]
for i, text in enumerate(items):
    ops.append({"op": "add_text", "id": f"item{i}", "text": text, "x": 64, "y": 66 + i * 60, "anchor": "middle-left",
                "font": "Barlow Condensed", "weight": 700, "italic": True, "size": 36, "letter_spacing": 1.5,
                "color": "#f2f4f7" if i == 0 else "#8b929c"})
ops.append({"op": "create_animation", "name": "enter", "duration": 1.9})
for i in range(len(items)):
    ops += [
        {"op": "set_keyframes", "animation": "enter", "target": f"item{i}", "property": "dx", "offset": i * 0.07,
         "keyframes": [[0, -70], [0.32, 0, "expo-out"]]},
        {"op": "set_keyframes", "animation": "enter", "target": f"item{i}", "property": "opacity", "offset": i * 0.07,
         "keyframes": [[0, 0], [0.2, 1, "quad-out"]]},
    ]
ops += [
    {"op": "set_keyframes", "animation": "enter", "target": "bar", "property": "height",
     "keyframes": [[0, 0], [0.3, 44, "back-out"]]},
    {"op": "set_keyframes", "animation": "enter", "target": "hl", "property": "opacity",
     "keyframes": [[0.1, 0], [0.4, 1, "quad-out"]]},
    {"op": "set_keyframes", "animation": "enter", "target": "bar", "property": "dy",
     "keyframes": [[1.0, 0], [1.28, 120, "back-out"]]},
    {"op": "set_keyframes", "animation": "enter", "target": "hl", "property": "dy",
     "keyframes": [[1.0, 0], [1.24, 120, "cubic-out"]]},
    {"op": "set_keyframes", "animation": "enter", "target": "item0", "property": "style.fill",
     "keyframes": [[1.0, "#f2f4f7"], [1.2, "#8b929c", "quad-out"]]},
    {"op": "set_keyframes", "animation": "enter", "target": "item2", "property": "style.fill",
     "keyframes": [[1.05, "#8b929c"], [1.25, "#f2f4f7", "quad-out"]]},
]
ui.batch("menu", ops)
strip("menu", "enter", "anim_menu_strip.png", frames=8, columns=4, cell=300)
ui.export_animation("menu", "enter", format="gif", path=str(OUT / "anim_menu.gif"), fps=24, scale=0.85)
print("written:", ", ".join(p.name for p in sorted(OUT.glob("anim_*"))))
