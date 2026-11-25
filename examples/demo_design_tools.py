"""Design-tool features: boolean shapes, smoothed corners, fill stacks, theme modes and wrapping layout,
plus the same screen exported as an editable vector SVG.

Run: python examples/demo_design_tools.py  ->  examples/design_tools.png, examples/design_tools.svg
"""

import tempfile
from pathlib import Path

from PIL import Image

from uiforge_mcp import server as ui
from uiforge_mcp.store import Store

HERE = Path(__file__).resolve().parent
ui.set_store(Store(Path(tempfile.mkdtemp()) / "ws"))

ui.set_theme(
    colors={"bg": "#0f1117", "panel": "#1a1d27", "ink": "#f4f4f8", "muted": "#8b90a5", "accent": "#7c5cff",
            "accent2": "#22d3ee", "gold": "#f5b83d"},
    modes={"light": {"bg": "#eef0f6", "panel": "#ffffff", "ink": "#151826", "muted": "#5d6278"}},
    styles={"caption": {"font": "Inter", "weight": 600, "size": 15, "fill": "$muted", "letter_spacing": 1,
                        "uppercase": True}},
)


def screen(name: str) -> None:
    ui.create_canvas(name, 860, 620, background="$bg")
    for i, title in enumerate(("boolean", "smoothing + fills", "wrap", "background blur", "side strokes",
                               "truncate + decoration")):
        ui.add_text(name, title, x=40 + (i % 3) * 280, y=34 + (i // 3) * 310, style="caption")

    ui.add_ellipse(name, 100, 150, 70, id="moon")
    ui.add_ellipse(name, 140, 125, 58, id="bite")
    ui.boolean_elements(name, ["moon", "bite"], op="subtract", id="crescent",
                        style={"fill": {"type": "linear", "angle": 120, "stops": [[0, "$gold"], [1, "#e0731f"]]},
                               "stroke": {"color": "#fff@0.6", "width": 2}, "shadow": {"blur": 14, "dy": 6}})
    ui.add_ellipse(name, 205, 200, 22, id="head")
    ui.add_polygon(name, points=[[193, 205], [217, 205], [228, 262], [182, 262]], id="stem")
    ui.boolean_elements(name, ["head", "stem"], op="union", id="key",
                        style={"fill": "$accent2", "shadow": {"color": "$accent2@0.5", "blur": 16}})

    ui.add_rect(name, 320, 70, 150, 150, radius=40, smoothing=0.8, id="icon",
                style={"fill": [{"type": "linear", "angle": 135, "stops": [[0, "$accent"], [1, "#3b1fa8"]]},
                                {"type": "stripes", "color": "#fff@0.07", "size": 7, "angle": 45},
                                {"type": "radial", "cx": 0.3, "cy": 0.2, "r": 0.7,
                                 "stops": [[0, "#fff@0.35"], [1, "#fff@0"]]}],
                       "stroke": {"color": "#fff@0.25", "width": 1.5}, "shadow": {"blur": 22, "dy": 10}})
    ui.add_text(name, "UI", x=395, y=145, size=56, weight=800, anchor="center", style={"fill": "#ffffff"})
    ui.add_rect(name, 490, 150, 46, 46, radius=12, id="plain", style={"fill": "$panel", "stroke": "$muted"})
    ui.add_text(name, "r=12", x=513, y=212, size=11, anchor="top-center", style={"fill": "$muted"})

    ui.add_rect(name, 600, 64, 230, 200, radius=16, smoothing=0.6, id="tray",
                style={"fill": "$panel", "shadow": {"blur": 18, "dy": 8}})
    for i in range(10):
        ui.add_rect(name, 0, 0, 44, 44, radius=10, smoothing=0.6, id=f"slot{i}", group="slots",
                    style={"fill": "$bg", "stroke": {"color": "$accent@0.8" if i < 3 else "$muted@0.4", "width": 2}})
    ui.arrange_elements(name, group="slots", container="tray", gap=10, padding=14, wrap=True, hug=True,
                        align="start")

    row2 = len(ui.store().get(name)["elements"])
    for cx, cy, r, col in ((90, 400, 50, "$accent"), (170, 450, 42, "$gold"), (120, 500, 34, "$accent2")):
        ui.add_ellipse(name, cx, cy, r, fill=col)
    ui.add_rect(name, 60, 380, 170, 120, radius=20, smoothing=0.6, id="glass",
                style={"fill": "#ffffff@0.12", "backdrop_blur": 18,
                       "stroke": {"color": "#ffffff@0.35", "width": 1},
                       "shadow": {"blur": 20, "dy": 8, "knockout": True}})
    ui.add_text(name, "GLASS", x=145, y=440, size=22, weight=800, anchor="center", letter_spacing=3,
                style={"fill": "#ffffff"})

    for i, label in enumerate(("Gear", "Skills", "Map")):
        on = i == 0
        ui.add_rect(name, 320 + i * 75, 400, 70, 44, id=f"tab{i}",
                    style={"fill": "$panel" if on else "none",
                           "stroke": {"color": "$accent" if on else "$muted@0.3", "width": 3 if on else 1,
                                      "sides": ["bottom"]}})
        ui.add_text(name, label, x=355 + i * 75, y=422, size=15, weight=700 if on else 500, anchor="center",
                    style={"fill": "$ink" if on else "$muted"})

    ui.add_rect(name, 600, 380, 230, 140, radius=14, smoothing=0.6, style={"fill": "$panel"})
    ui.add_text(name, "Lady Seraphina of the Eternal Ember Throne", x=618, y=398, size=17, weight=700,
                max_width=194, max_lines=1, style={"fill": "$ink"})
    ui.add_text(name, "A blade forged in starfire, said to cut through shadow itself and the doubts of "
                "whoever holds it.", x=618, y=428, size=13, max_width=194, max_lines=2, style={"fill": "$muted"})
    ui.add_text(name, "1200", x=618, y=488, size=15, decoration="strikethrough", style={"fill": "$muted"})
    ui.add_text(name, "900", x=668, y=484, size=20, weight=800, style={"fill": "$gold"})
    ui.move_elements(name, ids=[e["id"] for e in ui.store().get(name)["elements"][row2:]], dx=0, dy=40)


screen("dark")
ui.duplicate_canvas("dark", "light")
ui.update_canvas("light", mode="light")
st = ui.store()
shots = [st.renderer(st.get(n), 1.5).render() for n in ("dark", "light")]
sheet = Image.new("RGBA", (shots[0].width, shots[0].height * 2))
for i, im in enumerate(shots):
    sheet.paste(im, (0, i * im.height))
sheet.convert("RGB").save(HERE / "design_tools.png", optimize=True)
print(ui.export_svg("dark", path=str(HERE / "design_tools.svg")))
