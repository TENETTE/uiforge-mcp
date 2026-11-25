"""Ready materials (39 built-in 2.5D PBR-lite) and design variations, drawn with uiforge-mcp itself.

Run: python examples/demo_materials.py  ->  examples/materials.png, examples/variations.png
"""

import tempfile
from pathlib import Path

from uiforge_mcp import server as ui
from uiforge_mcp import tools_design as td
from uiforge_mcp.materials import NAMES
from uiforge_mcp.store import Store

OUT = Path(__file__).resolve().parent
ui.set_store(Store(Path(tempfile.mkdtemp()) / "ws"))
ui.set_theme(colors={"bg": "#0e1016", "surface": "#1b1830", "primary": "#8b5cf6", "text": "#f4f1ff",
                     "muted": "#9a93b8"})

cols, cw, ch = 8, 160, 126
rows = (len(NAMES) + cols - 1) // cols
W, H = cols * cw + 28, rows * ch + 28
ui.create_canvas("materials", W, H, background="#181b24")
for i, name in enumerate(NAMES):
    x, y = 14 + (i % cols) * cw + 12, 14 + (i // cols) * ch + 10
    if name in ("glass", "liquid_glass", "energy_shield", "hologram", "ice", "jelly"):
        ui.add_rect("materials", x + 8, y + 8, 120, 66, radius=10,
                    style={"fill": [{"type": "linear", "angle": 35, "stops": ["#f43f5e", "#8b5cf6", "#06b6d4"]},
                                    {"type": "stripes", "color": "#ffffff@0.32", "color2": "transparent", "size": 12, "angle": 45}]})
        ui.add_ellipse("materials", x + 46, y + 41, 18, 18, style={"fill": "#fbbf24@0.9"})
        ui.add_ellipse("materials", x + 94, y + 41, 16, 16, style={"fill": "#22d3ee@0.9"})
    ui.add_rect("materials", x, y, 136, 82, radius=14, style={"material": name,
                                                              "shadow": {"blur": 14, "dy": 5, "color": "#000000@0.45"}})
    ui.add_text("materials", name.replace("_", " "), x + 68, y + 101, anchor="center", size=12, weight=600,
                color="#e6e8ee")
st = ui.store()
st.renderer(st.get("materials"), 1).render().convert("RGB").save(OUT / "materials.png", optimize=True)

ui.create_canvas("card", 360, 260, background="$bg")
ui.batch("card", [
    {"op": "add_rect", "x": 16, "y": 16, "width": 328, "height": 228, "radius": 20,
     "style": {"fill": "$surface", "stroke": {"color": "$primary@0.65", "width": 2},
               "shadow": {"blur": 22, "dy": 8, "color": "#000000@0.55"}}},
    {"op": "add_polygon", "cx": 180, "cy": 54, "radius": 20, "inner_radius": 9, "sides": 5,
     "style": {"fill": "#fbbf24", "glow": {"color": "#fbbf24@0.5", "blur": 10}}},
    {"op": "add_text", "text": "VICTORY", "x": 180, "y": 102, "anchor": "center", "size": 38, "weight": 800, "color": "$text"},
    {"op": "add_text", "text": "Rank up! +250 XP", "x": 180, "y": 138, "anchor": "center", "size": 15, "color": "$muted"},
    {"op": "add_rect", "x": 76, "y": 158, "width": 208, "height": 8, "radius": 4, "fill": "#000@0.45"},
    {"op": "add_rect", "x": 76, "y": 158, "width": 152, "height": 8, "radius": 4, "fill": "$primary"},
    {"op": "add_rect", "x": 100, "y": 182, "width": 160, "height": 42, "radius": 12,
     "style": {"fill": {"type": "linear", "angle": 90, "stops": ["$primary", "#5b21b6"]},
               "shadow": {"blur": 12, "dy": 4, "color": "#000@0.45"}}},
    {"op": "add_text", "text": "CONTINUE", "x": 180, "y": 203, "anchor": "center", "size": 15, "weight": 700, "color": "#ffffff"},
])
sheet = td.make_variations("card", count=3)
(OUT / "variations.png").write_bytes(sheet[0].data)
print("wrote", OUT / "materials.png", OUT / "variations.png")
