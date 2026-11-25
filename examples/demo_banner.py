"""The README hero banner, drawn entirely with uiforge-mcp (Cook-Torrance PBR, Liquid Glass, gauges & frames).

Run: python examples/demo_banner.py  ->  docs/banner.png
"""

import tempfile
from pathlib import Path

from uiforge_mcp import server as ui
from uiforge_mcp.store import Store

DOCS = Path(__file__).resolve().parent.parent / "docs"
ui.set_store(Store(Path(tempfile.mkdtemp()) / "ws"))
ui.set_theme(colors={"bg": "#090b12", "ink": "#f8fafc", "muted": "#94a3b8",
                     "violet": "#8b5cf6", "cyan": "#22d3ee", "gold": "#f5b83d", "rose": "#f43f5e"})

c = "banner"
ui.create_canvas(c, 1280, 420, background={"type": "radial", "cx": 0.72, "cy": 0.45, "r": 0.85,
                                           "stops": [[0, "#1c1542"], [0.55, "#0d111e"], [1, "$bg"]]})
ui.batch(c, [
    {"op": "add_rect", "x": 0, "y": 0, "width": 1280, "height": 420,
     "fill": {"type": "grid", "color": "#ffffff@0.03", "size": 36, "line_width": 1}},
    {"op": "add_ellipse", "cx": 870, "cy": 165, "rx": 180, "ry": 130,
     "fill": {"type": "radial", "stops": [[0, "#8b5cf6@0.42"], [1, "#8b5cf6@0"]]}},
    {"op": "add_ellipse", "cx": 1090, "cy": 290, "rx": 160, "ry": 120,
     "fill": {"type": "radial", "stops": [[0, "#06b6d4@0.38"], [1, "#06b6d4@0"]]}},
    {"op": "add_ellipse", "cx": 745, "cy": 295, "rx": 120, "ry": 95,
     "fill": {"type": "radial", "stops": [[0, "#f43f5e@0.32"], [1, "#f43f5e@0"]]}},
    {"op": "add_rect", "x": 68, "y": 76, "width": 208, "height": 28, "radius": 14,
     "style": {"fill": "#8b5cf6@0.16", "stroke": {"color": "#a78bfa@0.45", "width": 1}}},
    {"op": "add_text", "text": "OPEN SOURCE · MIT · 100% LOCAL", "x": 172, "y": 90, "anchor": "center",
     "size": 10.5, "weight": 700, "letter_spacing": 1.4, "color": "#c4b5fd"},
    {"op": "add_text", "text": "uiforge-mcp", "x": 66, "y": 124, "size": 74, "weight": 800,
     "color": {"type": "linear", "angle": 0, "stops": [[0, "#ffffff"], [0.65, "#e2e8f0"], [1, "#a78bfa"]]}},
    {"op": "add_text", "text": "Blender-grade PBR materials, live studio & engine-ready UI for AI agents.",
     "x": 70, "y": 218, "size": 19, "weight": 500, "color": "$muted", "max_width": 560},
    {"op": "add_rect", "x": 70, "y": 290, "width": 148, "height": 34, "radius": 9,
     "style": {"material": "gold", "shadow": {"blur": 14, "dy": 5, "color": "#000@0.5"}}},
    {"op": "add_text", "text": "39 PBR MATERIALS", "x": 144, "y": 307, "anchor": "center",
     "size": 11, "weight": 800, "letter_spacing": 1, "color": "#1c1205"},
    {"op": "add_rect", "x": 230, "y": 290, "width": 134, "height": 34, "radius": 9,
     "style": {"material": "chrome", "shadow": {"blur": 14, "dy": 5, "color": "#000@0.5"}}},
    {"op": "add_text", "text": "NORMAL MAPS", "x": 297, "y": 307, "anchor": "center",
     "size": 11, "weight": 800, "letter_spacing": 1, "color": "#0f172a"},
    {"op": "add_rect", "x": 376, "y": 290, "width": 162, "height": 34, "radius": 9,
     "style": {"fill": {"type": "linear", "angle": 135, "stops": [[0, "#151c2e"], [1, "#0b0f1b"]]},
               "stroke": {"color": "$cyan@0.75", "width": 1.4},
               "glow": {"color": "$cyan@0.25", "blur": 12},
               "shadow": {"blur": 14, "dy": 5, "color": "#000@0.5"}}},
    {"op": "add_text", "text": "GAME · .NET · C++ · REACT", "x": 457, "y": 307, "anchor": "center",
     "size": 10.5, "weight": 700, "letter_spacing": 0.9, "color": "#e0f2fe"},

    {"op": "add_rect", "x": 728, "y": 54, "width": 440, "height": 290, "radius": 24,
     "fill": [{"type": "linear", "angle": 30, "stops": ["#f43f5e@0.42", "#8b5cf6@0.48", "#06b6d4@0.42"]},
              {"type": "stripes", "color": "#ffffff@0.12", "color2": "transparent", "size": 18, "angle": 45}]},
    {"op": "add_ellipse", "cx": 820, "cy": 130, "rx": 46, "ry": 46, "fill": "#fbbf24@0.65"},
    {"op": "add_ellipse", "cx": 1085, "cy": 255, "rx": 54, "ry": 54, "fill": "#22d3ee@0.58"},

    {"op": "add_rect", "id": "glass_card", "x": 712, "y": 46, "width": 472, "height": 306, "radius": 26,
     "smoothing": 0.6, "style": {"material": "liquid_glass"}},
    {"op": "add_rect", "x": 726, "y": 60, "width": 444, "height": 278, "radius": 20, "smoothing": 0.6,
     "fill": "#090c14@0.72", "stroke": {"color": "#ffffff@0.14", "width": 1}},

    {"op": "add_ellipse", "cx": 792, "cy": 124, "rx": 38, "ry": 38,
     "style": {"material": "gold", "shadow": {"blur": 16, "dy": 6, "color": "#000@0.65"}}},
    {"op": "add_ellipse", "cx": 792, "cy": 124, "rx": 28, "ry": 28,
     "style": {"material": "obsidian"}},
    {"op": "add_polygon", "cx": 792, "cy": 124, "radius": 18, "sides": 6, "point_rotation": 30,
     "style": {"material": "ruby", "glow": {"color": "#f43f5e@0.55", "blur": 12}}},

    {"op": "add_text", "text": "VALKYRIE MK-IV", "x": 848, "y": 98, "size": 22, "weight": 700,
     "font": "Rajdhani", "letter_spacing": 2, "color": "$ink"},
    {"op": "add_text", "text": "LV 42  ·  TACTICAL VANGUARD", "x": 848, "y": 126, "size": 12, "weight": 600,
     "letter_spacing": 1.5, "color": "$cyan"},

    {"op": "add_rect", "id": "hp_tr", "x": 848, "y": 149, "width": 298, "height": 14, "radius": 7,
     "fill": "#05070c@0.85", "stroke": {"color": "#ffffff@0.15", "width": 1}},
    {"op": "add_rect", "x": 848, "y": 149, "width": 232, "height": 14, "radius": 7, "clip": "hp_tr",
     "fill": {"type": "linear", "angle": 0, "stops": ["#fb7185", "#e11d48"]},
     "style": {"bevel": {"size": 2, "highlight": "#ffffff@0.45"}, "glow": {"color": "#f43f5e@0.45", "blur": 8}}},
    {"op": "add_rect", "id": "sh_tr", "x": 848, "y": 170, "width": 298, "height": 8, "radius": 4,
     "fill": "#05070c@0.85"},
    {"op": "add_rect", "x": 848, "y": 170, "width": 178, "height": 8, "radius": 4, "clip": "sh_tr",
     "fill": {"type": "linear", "angle": 0, "stops": ["#38bdf8", "#22d3ee"]},
     "style": {"glow": {"color": "#22d3ee@0.65", "blur": 8}}},

    {"op": "add_ellipse", "cx": 1104, "cy": 266, "rx": 54, "ry": 54,
     "style": {"material": "radial_metal", "shadow": {"blur": 14, "dy": 5, "color": "#000@0.65"}}},
    {"op": "add_ellipse", "cx": 1104, "cy": 266, "rx": 44, "ry": 44,
     "fill": {"type": "radial", "stops": [[0, "#1c2028"], [1, "#090b0f"]]}},
    {"op": "add_arc", "cx": 1104, "cy": 266, "radius": 36, "start_angle": 135, "end_angle": 405,
     "thickness": 5, "color": "#ffffff@0.12"},
    {"op": "add_arc", "cx": 1104, "cy": 266, "radius": 36, "start_angle": 135, "end_angle": 340,
     "thickness": 5, "color": {"type": "conic", "from": 135, "to": 405,
                               "stops": [[0, "#22d3ee"], [0.65, "#f59e0b"], [1, "#f43f5e"]]},
     "style": {"glow": {"color": "#f59e0b@0.5", "blur": 8}}},
    {"op": "add_text", "text": "284", "x": 1104, "y": 261, "anchor": "center", "font": "Barlow Condensed",
     "weight": 700, "italic": True, "size": 26, "color": "#ffffff"},
    {"op": "add_text", "text": "KM/H", "x": 1104, "y": 284, "anchor": "center", "font": "Barlow Condensed",
     "weight": 600, "size": 10, "letter_spacing": 1.5, "color": "$muted"},
])

slots = [("gold", "ruby"), ("chrome", "emerald"), ("steel", "gem"), ("copper", "jade")]
for i, (frame_m, gem_m) in enumerate(slots):
    sx = 754 + i * 70
    ui.batch(c, [
        {"op": "add_rect", "x": sx, "y": 222, "width": 58, "height": 58, "radius": 13,
         "style": {"material": frame_m, "shadow": {"blur": 10, "dy": 4, "color": "#000@0.55"}}},
        {"op": "add_rect", "x": sx + 4, "y": 226, "width": 50, "height": 50, "radius": 9,
         "fill": "#0d1018", "style": {"inner_shadow": {"blur": 8, "dy": 2, "color": "#000@0.8"}}},
        {"op": "add_polygon", "cx": sx + 29, "cy": 251, "radius": 15, "sides": 6, "point_rotation": 30,
         "style": {"material": gem_m}},
    ])

ui.add_text(c, "LIVE STUDIO  ·  WEBGPU + CUDA  ·  DOTLOTTIE V2", 754, 304,
            size=10, weight=700, letter_spacing=1.1, color="#94a3b8")

st = ui.store()
st.renderer(st.get(c), 1).render().convert("RGB").save(DOCS / "banner.png", optimize=True)
print("wrote", DOCS / "banner.png")
