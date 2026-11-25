"""Realistic racing HUD drawn with the same tool calls an AI would make.

    python examples/demo_racing.py

Writes racing_hud.png and realistic_kit.png next to this file (temporary workspace).
"""

import tempfile
from pathlib import Path

from uiforge_mcp import server as ui
from uiforge_mcp.store import Store

OUT = Path(__file__).resolve().parent
ui.set_store(Store(Path(tempfile.mkdtemp()) / "ws"))

HAIRLINE = {"color": {"type": "linear", "angle": 90, "stops": ["#ffffff@0.26", "#ffffff@0.05"]}, "width": 1}

ui.set_theme(
    colors={"ink": "#07080a", "glass": "#101318", "line": "#ffffff@0.14", "text": "#f2f4f7", "muted": "#8b929c",
            "red": "#ff3b30", "amber": "#ffb020", "green": "#2bd576", "blue": "#3aa0ff", "purple": "#c77dff"},
    styles={
        "glass": {"fill": {"type": "linear", "angle": 90, "stops": ["#171a20d9", "#0b0d10d9"]}, "stroke": HAIRLINE,
                  "shadow": {"color": "#000000@0.5", "blur": 28, "dy": 12}},
        "label": {"font": "Barlow Condensed", "weight": 600, "size": 17, "fill": "$muted", "letter_spacing": 2.5,
                  "uppercase": True},
        "value": {"font": "Barlow Condensed", "weight": 700, "italic": True, "fill": "$text"},
        "mono": {"font": "JetBrains Mono", "weight": 600, "size": 22, "fill": "$text"},
    },
)

ui.create_canvas("racing_hud", 1920, 1080, {"type": "linear", "angle": 90, "stops": ["#39424d", "#20252c", "#0d0f12"]})
CX, CY = 1640, 800
SWEEP0, SWEEP1 = 135, 405
RPM = 0.74
needle_angle = SWEEP0 + (SWEEP1 - SWEEP0) * RPM

ops = [
    {"op": "add_ellipse", "cx": 960, "cy": 470, "rx": 1100, "ry": 150, "fill": "#aab7c6@0.16", "style": {"blur": 120}},
    {"op": "add_rect", "x": 0, "y": 0, "width": 1920, "height": 1080,
     "fill": {"type": "radial", "r": 0.78, "stops": [[0.45, "#000000@0"], [1, "#000000@0.62"]]}},

    {"op": "add_ellipse", "group": "dial", "cx": CX, "cy": CY, "rx": 214,
     "fill": {"type": "linear", "angle": 70, "stops": ["#7b838d", "#1b1e23", "#565d66", "#15171b"]},
     "style": {"shadow": {"color": "#000000@0.65", "blur": 44, "dy": 18}}},
    {"op": "add_ellipse", "group": "dial", "cx": CX, "cy": CY, "rx": 206,
     "fill": {"type": "radial", "stops": [[0, "#1c2026"], [0.72, "#0c0e11"], [1, "#050607"]]},
     "stroke": {"color": "#000000@0.8", "width": 2},
     "style": {"inner_shadow": {"color": "#000000@0.9", "blur": 26, "dy": 6}}},
    {"op": "add_ellipse", "group": "dial", "cx": CX, "cy": CY, "rx": 206, "clip": None,
     "fill": {"type": "carbon", "color": "#ffffff@0.05", "color2": "#ffffff@0", "size": 5}},
    {"op": "add_arc", "group": "dial", "cx": CX, "cy": CY, "radius": 186, "start_angle": SWEEP0, "end_angle": SWEEP1,
     "thickness": 12, "color": "#ffffff@0.07"},
    {"op": "add_arc", "group": "dial", "cx": CX, "cy": CY, "radius": 166, "start_angle": SWEEP0 + 270 * 7 / 9,
     "end_angle": SWEEP1, "thickness": 5, "color": "$red"},
    {"op": "add_ticks", "id": "rpm", "group": "dial", "cx": CX, "cy": CY, "radius": 176, "start_angle": SWEEP0,
     "end_angle": SWEEP1, "count": 37, "major_every": 4, "length": 8, "width": 1.5, "major_length": 17,
     "major_width": 3, "color": "#ffffff@0.42", "major_color": "#f2f4f7",
     "labels": [str(i) for i in range(10)], "label_size": 26, "label_font": "Barlow Condensed", "label_weight": 600,
     "label_italic": True, "label_color": "#d5dae1"},
    {"op": "add_text", "group": "dial", "text": "x1000 rpm", "x": CX, "y": CY - 78, "anchor": "center",
     "style": "label", "size": 15},
    {"op": "add_arc", "group": "value", "cx": CX, "cy": CY, "radius": 186, "start_angle": SWEEP0,
     "end_angle": needle_angle, "thickness": 12,
     "color": {"type": "conic", "from": SWEEP0, "to": SWEEP1,
               "stops": [[0, "#dfe6ee"], [0.62, "#f2f4f7"], [0.76, "#ffb020"], [0.9, "#ff3b30"]]},
     "style": {"glow": {"color": "#ffb020@0.55", "blur": 18}}},
    {"op": "add_polygon", "group": "needle", "origin": [CX, CY], "rotation": needle_angle,
     "points": [[CX - 34, CY - 4.5], [CX + 168, CY - 1.2], [CX + 168, CY + 1.2], [CX - 34, CY + 4.5]],
     "fill": {"type": "linear", "angle": 90, "stops": ["#ff6a60", "#ff3b30", "#b3170f"]},
     "style": {"glow": {"color": "#ff3b30@0.75", "blur": 14}, "shadow": {"color": "#000000@0.7", "blur": 8, "dy": 5}}},
    {"op": "add_ellipse", "group": "hub", "cx": CX, "cy": CY, "rx": 22,
     "fill": {"type": "conic", "stops": ["#e6eaef", "#5a616b", "#f4f6f8", "#474d55", "#cfd5dc", "#5a616b", "#e6eaef"]},
     "stroke": {"color": "#000000@0.7", "width": 1.5}, "style": {"shadow": {"color": "#000000@0.8", "blur": 10, "dy": 4}}},
    {"op": "add_ellipse", "group": "hub", "cx": CX, "cy": CY, "rx": 9,
     "fill": {"type": "radial", "stops": ["#2a2e35", "#08090b"]}},
    {"op": "add_rect", "group": "gear", "x": CX - 40, "y": CY + 92, "width": 80, "height": 92, "radius": 8,
     "skew": 8, "fill": "#050607@0.92", "stroke": {"color": "$red", "width": 2},
     "style": {"glow": {"color": "#ff3b30@0.35", "blur": 16}}},
    {"op": "add_text", "group": "gear", "text": "4", "x": CX + 1, "y": CY + 138, "anchor": "center", "style": "value",
     "size": 84},

    {"op": "add_text", "text": "187", "x": CX - 250, "y": CY + 170, "anchor": "baseline-right", "size": 150,
     "style": {"use": "value", "shadow": {"color": "#000000@0.65", "blur": 18, "dy": 6}}},
    {"op": "add_text", "text": "km/h", "x": CX - 250, "y": CY + 202, "anchor": "baseline-right", "style": "label",
     "size": 22},
    {"op": "add_line", "points": [[CX - 470, CY + 214], [CX - 250, CY + 214]], "width": 2,
     "color": {"type": "linear", "angle": 0, "stops": ["#ffffff@0", "#ffffff@0.5"]}, "cap": "butt"},

    {"op": "add_line", "points": [[744, 46], [1176, 46]], "width": 14, "cap": "butt", "dash": [30, 6],
     "color": "#ffffff@0.09"},
    {"op": "add_line", "points": [[744, 46], [1068, 46]], "width": 14, "cap": "butt", "dash": [30, 6],
     "color": {"type": "linear", "angle": 0, "stops": [[0, "#2bd576"], [0.42, "#2bd576"], [0.46, "#ffb020"],
                                                         [0.86, "#ffb020"], [0.9, "#ff3b30"], [1, "#ff3b30"]]},
     "style": {"glow": {"color": "#ffb020@0.6", "blur": 16}}},

    {"op": "add_rect", "x": 56, "y": 44, "width": 132, "height": 66, "skew": 14,
     "fill": {"type": "linear", "angle": 90, "stops": ["#ff5046", "#d92217"]},
     "style": {"shadow": {"color": "#000000@0.5", "blur": 18, "dy": 8}, "bevel": {"size": 1.5}}},
    {"op": "add_text", "text": "P3", "x": 122, "y": 77, "anchor": "center", "style": "value", "size": 50},
    {"op": "add_rect", "x": 186, "y": 44, "width": 236, "height": 66, "skew": 14, "style": "glass"},
    {"op": "add_text", "text": "lap", "x": 222, "y": 77, "anchor": "middle-left", "style": "label"},
    {"op": "add_text", "text": "4", "x": 300, "y": 77, "anchor": "center", "style": "value", "size": 46},
    {"op": "add_text", "text": "/ 12", "x": 322, "y": 80, "anchor": "middle-left", "style": "value", "size": 28,
     "color": "$muted"},

    {"op": "add_rect", "id": "timing", "x": 48, "y": 128, "width": 372, "height": 150, "radius": 6, "style": "glass"},
    {"op": "add_rect", "x": 48, "y": 128, "width": 4, "height": 150, "fill": "$red", "clip": "timing"},
    {"op": "add_text", "text": "current", "x": 72, "y": 158, "anchor": "middle-left", "style": "label"},
    {"op": "add_text", "text": "1:42.318", "x": 400, "y": 158, "anchor": "middle-right", "style": "mono"},
    {"op": "add_line", "points": [[72, 181], [400, 181]], "width": 1, "color": "$line", "cap": "butt"},
    {"op": "add_text", "text": "best", "x": 72, "y": 204, "anchor": "middle-left", "style": "label"},
    {"op": "add_text", "text": "1:41.905", "x": 400, "y": 204, "anchor": "middle-right", "style": "mono",
     "color": "$purple"},
    {"op": "add_line", "points": [[72, 227], [400, 227]], "width": 1, "color": "$line", "cap": "butt"},
    {"op": "add_text", "text": "delta", "x": 72, "y": 251, "anchor": "middle-left", "style": "label"},
    {"op": "add_rect", "id": "delta_track", "x": 160, "y": 246, "width": 150, "height": 10, "radius": 2,
     "fill": "#ffffff@0.08"},
    {"op": "add_rect", "x": 198, "y": 246, "width": 37, "height": 10, "fill": "$green", "clip": "delta_track",
     "style": {"glow": {"color": "#2bd576@0.6", "blur": 8}}},
    {"op": "add_line", "points": [[235, 242], [235, 260]], "width": 2, "color": "#ffffff@0.7", "cap": "butt"},
    {"op": "add_text", "text": "-0.213", "x": 400, "y": 251, "anchor": "middle-right", "style": "mono",
     "color": "$green"},

    {"op": "add_rect", "id": "car", "x": 48, "y": 806, "width": 372, "height": 226, "radius": 6, "style": "glass"},
    {"op": "add_rect", "x": 48, "y": 806, "width": 372, "height": 34, "clip": "car",
     "fill": {"type": "carbon", "color": "#3a3f47", "color2": "#121418", "size": 4}},
    {"op": "add_line", "points": [[48, 840], [420, 840]], "width": 1, "color": "$line", "cap": "butt"},
    {"op": "add_text", "text": "tyres °c", "x": 66, "y": 823, "anchor": "middle-left", "style": "label",
     "color": "#c3c9d1"},
    {"op": "add_text", "text": "fuel 23.4 l", "x": 402, "y": 823, "anchor": "middle-right", "style": "label",
     "color": "#c3c9d1"},
]
tyres = [("fl", 78, 862, "#3aa0ff", "#2bd576", "78"), ("fr", 168, 862, "#2bd576", "#ffb020", "91"),
         ("rl", 78, 948, "#2bd576", "#2bd576", "84"), ("rr", 168, 948, "#ffb020", "#ff3b30", "104")]
for name, x, y, c1, c2, temp in tyres:
    ops += [
        {"op": "add_rect", "x": x, "y": y, "width": 40, "height": 66, "radius": 9,
         "fill": {"type": "linear", "angle": 0, "stops": [c1, c2]},
         "stroke": {"color": "#000000@0.55", "width": 2},
         "style": {"inner_shadow": {"color": "#000000@0.45", "blur": 8, "dy": 3}, "glow": {"color": c2 + "@0.3", "blur": 10}}},
        {"op": "add_text", "text": temp, "x": x + 50, "y": y + 33, "anchor": "middle-left", "style": "mono", "size": 17},
    ]
ops += [
    {"op": "add_rect", "x": 100, "y": 934, "width": 86, "height": 8, "radius": 4, "fill": "#ffffff@0.12"},
    {"op": "add_rect", "x": 139, "y": 882, "width": 8, "height": 112, "radius": 4, "fill": "#ffffff@0.12"},
]
for label, x, level, color in (("thr", 286, 0.82, "$green"), ("brk", 336, 0.12, "$red"), ("clt", 386, 0.0, "$blue")):
    ops += [
        {"op": "add_rect", "id": f"{label}_track", "x": x - 9, "y": 862, "width": 18, "height": 132, "radius": 3,
         "fill": "#ffffff@0.08", "stroke": {"color": "#ffffff@0.1", "width": 1}},
        {"op": "add_text", "text": label, "x": x, "y": 1012, "anchor": "center", "style": "label", "size": 14},
    ]
    if level > 0:
        h = round(132 * level)
        ops.append({"op": "add_rect", "x": x - 9, "y": 862 + 132 - h, "width": 18, "height": h, "fill": color,
                    "clip": f"{label}_track", "style": {"glow": {"color": color + "@0.5", "blur": 10}}})

MX, MY = 1764, 176
ops += [
    {"op": "add_ellipse", "cx": MX, "cy": MY, "rx": 118, "style": "glass"},
    {"op": "add_arc", "cx": MX, "cy": MY, "radius": 108, "start_angle": 0, "end_angle": 360, "thickness": 1,
     "dash": [3, 9], "color": "#ffffff@0.3"},
    {"op": "add_path", "x": MX - 72, "y": MY - 62, "scale": 1.2,
     "d": "M20 20C40 4 86 2 104 22C120 40 100 58 84 62C66 67 70 88 88 92C108 96 104 112 80 108"
          "C52 104 22 100 12 76C4 56 6 32 20 20Z",
     "fill": "none", "stroke": {"color": "#f2f4f7@0.85", "width": 3.5, "align": "center"},
     "style": {"shadow": {"color": "#000000@0.6", "blur": 6, "dy": 2}}},
    {"op": "add_ellipse", "cx": MX + 28, "cy": MY - 55, "rx": 6, "fill": "$red", "stroke": {"color": "#ffffff", "width": 2},
     "style": {"glow": {"color": "#ff3b30", "blur": 10}}},
    {"op": "add_ellipse", "cx": MX - 20, "cy": MY + 62, "rx": 4.5, "fill": "$blue"},
    {"op": "add_ellipse", "cx": MX + 50, "cy": MY + 4, "rx": 4.5, "fill": "$amber"},
]
ui.batch("racing_hud", ops)
ui.export_png("racing_hud", str(OUT / "racing_hud.png"), scales=[0.5], include_background=True)
(OUT / "racing_hud_0_5x.png").replace(OUT / "racing_hud.png")

ui.create_canvas("btn_carbon", 360, 104)
ui.batch("btn_carbon", [
    {"op": "add_rect", "id": "body", "x": 24, "y": 18, "width": 312, "height": 60, "radius": 4, "skew": 12,
     "fill": {"type": "carbon", "color": "#3b4048", "color2": "#111317", "size": 4},
     "stroke": {"color": {"type": "linear", "angle": 90, "stops": ["#ffffff@0.4", "#ffffff@0.06"]}, "width": 1.5},
     "style": {"shadow": {"color": "#000000@0.6", "blur": 16, "dy": 8}}},
    {"op": "add_rect", "x": 24, "y": 18, "width": 312, "height": 30, "skew": 12, "clip": "body",
     "fill": {"type": "linear", "angle": 90, "stops": ["#ffffff@0.14", "#ffffff@0"]}},
    {"op": "add_rect", "x": 24, "y": 72, "width": 312, "height": 6, "skew": 12, "clip": "body", "fill": "$red",
     "style": {"glow": {"color": "#ff3b30@0.7", "blur": 12}}},
    {"op": "add_text", "text": "start race", "x": 180, "y": 46, "anchor": "center", "size": 32, "letter_spacing": 3,
     "uppercase": True, "style": {"use": "value", "shadow": {"color": "#000000@0.8", "blur": 6, "dy": 2}}},
])

ui.create_canvas("panel_glass", 256, 256)
ui.batch("panel_glass", [
    {"op": "add_rect", "id": "p", "x": 44, "y": 36, "width": 168, "height": 168, "radius": 8,
     "fill": "#12151ad9", "stroke": HAIRLINE, "style": {"shadow": {"color": "#000000@0.5", "blur": 26, "dy": 12},
                                                         "inner_glow": {"color": "#ffffff@0.05", "blur": 22}}},
    {"op": "add_line", "points": [[44, 52], [44, 84]], "width": 3, "color": "$red", "cap": "butt"},
])

ui.create_canvas("knob_metal", 160, 160)
ui.batch("knob_metal", [
    {"op": "add_ellipse", "cx": 80, "cy": 76, "rx": 58,
     "fill": {"type": "conic", "stops": ["#eef1f4", "#646b75", "#f7f9fa", "#4c525a", "#dfe4e9", "#5c636d", "#eef1f4"]},
     "stroke": {"color": "#000000@0.6", "width": 1.5},
     "style": {"shadow": {"color": "#000000@0.6", "blur": 18, "dy": 10}, "bevel": {"size": 2}}},
    {"op": "add_ellipse", "cx": 80, "cy": 76, "rx": 44,
     "fill": {"type": "brushed", "color": "#b9c0c8", "color2": "#6d747d", "angle": 0, "amount": 0.7},
     "stroke": {"color": "#000000@0.45", "width": 1.5}, "style": {"inner_shadow": {"color": "#000000@0.5", "blur": 6, "dy": 2}}},
    {"op": "add_line", "points": [[80, 40], [80, 58]], "width": 4, "color": "$red", "cap": "round",
     "style": {"glow": {"color": "#ff3b30@0.7", "blur": 6}}},
    {"op": "add_ticks", "cx": 80, "cy": 76, "radius": 74, "start_angle": 135, "end_angle": 405, "count": 13,
     "length": 6, "width": 1.5, "color": "#ffffff@0.55"},
])

ui.create_canvas("boost_gauge", 220, 220)
ui.batch("boost_gauge", [
    {"op": "add_ellipse", "cx": 110, "cy": 108, "rx": 92, "fill": {"type": "radial", "stops": ["#1b1f25", "#060708"]},
     "stroke": {"color": {"type": "linear", "angle": 70, "stops": ["#8a929c", "#22262c", "#6a727c"]}, "width": 5},
     "style": {"shadow": {"color": "#000000@0.6", "blur": 18, "dy": 8}}},
    {"op": "add_arc", "cx": 110, "cy": 108, "radius": 70, "start_angle": 150, "end_angle": 390, "thickness": 10,
     "dash": [9, 3.2], "color": "#ffffff@0.1"},
    {"op": "add_arc", "cx": 110, "cy": 108, "radius": 70, "start_angle": 150, "end_angle": 318, "thickness": 10,
     "dash": [9, 3.2], "color": {"type": "conic", "from": 150, "to": 390, "stops": ["#3aa0ff", "#2bd576", "#ffb020", "#ff3b30"]},
     "style": {"glow": {"color": "#2bd576@0.5", "blur": 10}}},
    {"op": "add_text", "text": "1.4", "x": 110, "y": 106, "anchor": "center", "style": "value", "size": 54},
    {"op": "add_text", "text": "bar", "x": 110, "y": 142, "anchor": "center", "style": "label", "size": 15},
])

ui.create_canvas("tab_position", 220, 96)
ui.batch("tab_position", [
    {"op": "add_rect", "x": 26, "y": 16, "width": 168, "height": 56, "skew": 14,
     "fill": {"type": "linear", "angle": 90, "stops": ["#ff5046", "#d92217"]},
     "style": {"shadow": {"color": "#000000@0.5", "blur": 14, "dy": 7}, "bevel": {"size": 1.5}}},
    {"op": "add_text", "text": "P3", "x": 78, "y": 44, "anchor": "center", "style": "value", "size": 44},
    {"op": "add_text", "text": "/ 20", "x": 112, "y": 47, "anchor": "middle-left", "style": "value", "size": 26,
     "color": "#ffffff@0.75"},
])

ui.contact_sheet(["btn_carbon", "panel_glass", "boost_gauge", "knob_metal", "tab_position"], columns=3, cell=300,
                 save_path=str(OUT / "realistic_kit.png"))
print("written: racing_hud.png, realistic_kit.png")
