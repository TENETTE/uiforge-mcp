"""Draws an AAA game UI kit and atmospheric HUD mockup using Cook-Torrance PBR materials and add_frame.

    python examples/demo.py

Writes kit_sheet.png and hud_mockup.png next to this file.
"""

import tempfile
from pathlib import Path

from game_ui_mcp import server as ui
from game_ui_mcp.store import Store

OUT = Path(__file__).resolve().parent
ui.set_store(Store(Path(tempfile.mkdtemp()) / "ws"))

ui.set_theme(
    colors={"bg": "#090c14", "primary": "#8b5cf6", "accent": "#22d3ee", "text": "#f8fafc", "muted": "#94a3b8",
            "danger": "#f43f5e", "gold": "#e6b038"},
    styles={
        "title": {"font": "Rajdhani", "weight": 700, "size": 28, "fill": "$text", "uppercase": "tr", "letter_spacing": 2},
    },
)

ICON = {
    "heart": "M12 21C12 21 3 15 3 9A4.5 4.5 0 0 1 12 6.5A4.5 4.5 0 0 1 21 9C21 15 12 21 12 21Z",
    "user": "M8 8A4 4 0 1 0 16 8A4 4 0 1 0 8 8ZM4 21C4 16.5 7.5 14 12 14C16.5 14 20 16.5 20 21Z",
    "sword": "M21 3L17 3.6L7.5 13L11 16.5L20.4 7ZM4.5 11.5L6 10L14 18L12.5 19.5ZM7 15.5L8.5 17L4.5 21L3 19.5Z",
    "shield": "M12 2.5L20 5.5V11.5C20 16.3 16.6 19.8 12 21.5C7.4 19.8 4 16.3 4 11.5V5.5Z",
    "potion": "M9.5 2.5H14.5V4.5H13.5V8.2C16.6 9.2 19 12 19 15.5A7 7 0 0 1 5 15.5C5 12 7.4 9.2 10.5 8.2V4.5H9.5Z",
    "bolt": "M13.5 2L4.5 13.5H11L10 22L19.5 10H13Z",
    "key": "M2.5 12A5 5 0 1 0 12.5 12A5 5 0 1 0 2.5 12ZM5.5 12A2 2 0 1 1 9.5 12A2 2 0 1 1 5.5 12Z"
           "M12 10.5V13.5H13V15H15.5V13.5H17V16H19.5V13.5H21.5V10.5Z",
}


def icon(name: str, x: float, y: float, size: float, **extra) -> dict:
    return {"op": "add_path", "d": ICON[name], "x": x, "y": y, "scale": size / 24, "fill_rule": "nonzero", **extra}


ui.create_canvas("btn_primary", 320, 96)
ui.batch("btn_primary", [
    {"op": "add_rect", "id": "bezel", "x": 14, "y": 14, "width": 292, "height": 64, "radius": 14, "corner": "cut",
     "style": {"material": "chrome", "shadow": {"color": "#000@0.65", "blur": 16, "dy": 7}}},
    {"op": "add_rect", "id": "body", "x": 19, "y": 19, "width": 282, "height": 54, "radius": 11, "corner": "cut",
     "style": {"material": {"name": "enamel", "color": "#6d28d9"},
               "glow": {"color": "$primary@0.55", "blur": 18}}},
    {"op": "add_text", "id": "label", "text": "oyuna başla", "x": 160, "y": 46, "anchor": "center", "color": "#ffffff",
     "size": 26, "style": {"use": "title", "shadow": {"color": "#1e0845@0.9", "blur": 4, "dy": 2}}},
])

ui.create_canvas("panel_rpg", 260, 260)
ui.add_frame("panel_rpg", 20, 22, 220, 216, preset="rpg_gold", title="RELICS", id_prefix="rpg")
ui.add_polygon("panel_rpg", cx=130, cy=142, radius=38, sides=6, point_rotation=30, style={"material": "emerald"})
ui.add_text("panel_rpg", "EMERALD CORE", 130, 198, anchor="center", font="Cinzel", weight=700, size=13, color="#fde68a")

ui.create_canvas("hp_bar", 360, 72)
ui.batch("hp_bar", [
    {"op": "add_rect", "id": "bezel", "x": 52, "y": 18, "width": 294, "height": 34, "radius": 17,
     "style": {"material": "steel", "shadow": {"blur": 12, "dy": 5, "color": "#000@0.6"}}},
    {"op": "add_rect", "id": "track", "x": 56, "y": 22, "width": 286, "height": 26, "radius": 13, "fill": "#090b12",
     "style": {"inner_shadow": {"color": "#000@0.85", "blur": 8, "dy": 3}}},
    {"op": "add_rect", "id": "fill", "x": 56, "y": 22, "width": 212, "height": 26, "clip": "track",
     "fill": {"type": "linear", "angle": 90, "stops": [[0, "#fb7185"], [0.45, "#e11d48"], [1, "#9f1239"]]},
     "style": {"bevel": {"size": 3, "highlight": "#ffffff@0.5"}, "glow": {"color": "#f43f5e@0.4", "blur": 8}}},
    {"op": "add_ellipse", "id": "badge_rim", "cx": 36, "cy": 35, "rx": 26,
     "style": {"material": "gold", "shadow": {"blur": 10, "dy": 4, "color": "#000@0.65"}}},
    {"op": "add_ellipse", "id": "badge", "cx": 36, "cy": 35, "rx": 20, "style": {"material": "obsidian"}},
    icon("heart", 22, 21, 28, style={"material": "ruby", "glow": {"color": "#fb7185@0.7", "blur": 8}}),
    {"op": "add_text", "text": "74 / 100", "x": 200, "y": 35, "anchor": "center", "font": "Rajdhani", "weight": 700,
     "size": 17, "color": "#fff", "stroke": {"color": "#000@0.75", "width": 2}},
])

ui.create_canvas("slot", 112, 112)
ui.batch("slot", [
    {"op": "add_rect", "id": "rim", "x": 10, "y": 10, "width": 92, "height": 92, "radius": 16,
     "style": {"material": "gold", "shadow": {"blur": 14, "dy": 6, "color": "#000@0.65"}}},
    {"op": "add_rect", "id": "s", "x": 16, "y": 16, "width": 80, "height": 80, "radius": 11,
     "fill": {"type": "radial", "stops": [[0, "#241d38"], [1, "#0d0a16"]]},
     "style": {"inner_shadow": {"color": "#000@0.8", "blur": 12, "dy": 3}}},
    icon("sword", 30, 30, 52, style={"material": "chrome", "shadow": {"blur": 6, "dy": 3, "color": "#000@0.7"}}),
    {"op": "add_text", "text": "x3", "x": 90, "y": 90, "anchor": "bottom-right", "weight": 800, "size": 15,
     "color": "#fde68a", "stroke": {"color": "#000", "width": 2.5}},
])

ui.create_canvas("btn_cartoon", 280, 110)
ui.add_frame("btn_cartoon", 14, 14, 252, 82, preset="cartoon_thick", accent="#16a34a", id_prefix="play")
ui.add_text("btn_cartoon", "PLAY!", 140, 50, anchor="center", font="Bangers", size=44,
            color="#ffffff", stroke={"color": "#052e16", "width": 5}, letter_spacing=2,
            style={"shadow": {"color": "#052e16", "blur": 0, "dy": 4}})

ui.create_canvas("badge_scifi", 260, 120)
ui.add_frame("badge_scifi", 16, 16, 228, 88, preset="scifi_hud", accent="#22d3ee", title="SHIELD ONLINE", id_prefix="sf")
ui.add_text("badge_scifi", "98.4%", 130, 74, anchor="center", font="Barlow Condensed", weight=700,
            italic=True, size=34, color="#f8fafc")

kit = ["btn_primary", "panel_rpg", "hp_bar", "slot", "btn_cartoon", "badge_scifi"]
ui.contact_sheet(kit, columns=3, cell=300, save_path=str(OUT / "kit_sheet.png"))

ui.create_canvas("hud", 1920, 1080, {"type": "radial", "cx": 0.5, "cy": 0.42, "r": 0.9,
                                     "stops": [[0, "#1c2844"], [0.55, "#0d1324"], [1, "#06080f"]]})
ui.batch("hud", [
    {"op": "add_rect", "x": 0, "y": 0, "width": 1920, "height": 1080,
     "fill": {"type": "grid", "color": "#22d3ee@0.035", "size": 60, "line_width": 1}},
    {"op": "add_ellipse", "cx": 960, "cy": 540, "rx": 64, "ry": 64, "fill": None,
     "stroke": {"color": "#22d3ee@0.28", "width": 1.5, "dash": [14, 10]}},
    {"op": "add_ellipse", "cx": 960, "cy": 540, "rx": 3.5, "ry": 3.5, "fill": "#22d3ee",
     "style": {"glow": {"color": "#22d3ee", "blur": 8}}},
    {"op": "add_frame", "x": 54, "y": 46, "width": 520, "height": 144, "preset": "scifi_hud",
     "accent": "#22d3ee", "id_prefix": "status"},
    {"op": "add_ellipse", "cx": 122, "cy": 118, "rx": 44, "style": {"material": "gold"}},
    {"op": "add_ellipse", "cx": 122, "cy": 118, "rx": 36, "style": {"material": "obsidian"}},
    icon("user", 98, 94, 48, style={"material": "chrome"}),
    {"op": "add_text", "text": "NOVA  ·  LV 42", "x": 184, "y": 72, "style": "title", "size": 26},
    {"op": "add_rect", "id": "hpt", "x": 184, "y": 110, "width": 356, "height": 20, "radius": 10,
     "fill": "#05070d@0.85", "stroke": {"color": "#ffffff@0.18", "width": 1.2}},
    {"op": "add_rect", "x": 184, "y": 110, "width": 274, "height": 20, "clip": "hpt",
     "fill": {"type": "linear", "angle": 90, "stops": [[0, "#fb7185"], [0.5, "#e11d48"], [1, "#9f1239"]]},
     "style": {"bevel": {"size": 2, "highlight": "#ffffff@0.45"}}},
    {"op": "add_rect", "id": "sht", "x": 184, "y": 138, "width": 356, "height": 11, "radius": 5.5,
     "fill": "#05070d@0.85"},
    {"op": "add_rect", "x": 184, "y": 138, "width": 220, "height": 11, "clip": "sht",
     "fill": {"type": "linear", "angle": 0, "stops": ["#38bdf8", "#22d3ee"]},
     "style": {"glow": {"color": "#22d3ee@0.6", "blur": 8}}},
    {"op": "add_text", "text": "HP 770 / 1000", "x": 184, "y": 156, "size": 12, "weight": 700,
     "font": "JetBrains Mono", "color": "#fda4af"},
    {"op": "add_text", "text": "SHIELD 62%", "x": 448, "y": 156, "size": 12, "weight": 700,
     "font": "JetBrains Mono", "color": "#67e8f9"},

    {"op": "add_frame", "x": 700, "y": 46, "width": 520, "height": 68, "preset": "luxury_minimal",
     "accent": "#22d3ee", "id_prefix": "obj"},
    {"op": "add_text", "text": "OBJECTIVE  ·  BREACH THE CITADEL CORE", "x": 960, "y": 80, "anchor": "center",
     "font": "Rajdhani", "weight": 700, "size": 21, "letter_spacing": 2.5, "color": "#f8fafc"},

    {"op": "add_ellipse", "cx": 1744, "cy": 176, "rx": 126, "style": {"material": "steel",
     "shadow": {"blur": 24, "dy": 10, "color": "#000@0.65"}}},
    {"op": "add_ellipse", "cx": 1744, "cy": 176, "rx": 114,
     "fill": {"type": "grid", "color": "$accent@0.22", "color2": "#061018", "size": 22}},
    {"op": "add_ellipse", "cx": 1744, "cy": 176, "rx": 64, "fill": None,
     "stroke": {"color": "#22d3ee@0.25", "width": 1}},
    {"op": "add_arc", "cx": 1744, "cy": 176, "radius": 52, "start_angle": 230, "end_angle": 310,
     "thickness": 46, "color": "#22d3ee@0.12"},
    {"op": "add_polygon", "cx": 1744, "cy": 176, "radius": 11, "sides": 3, "fill": "$accent",
     "style": {"glow": {"color": "$accent", "blur": 10}}},
    {"op": "add_ellipse", "cx": 1788, "cy": 134, "rx": 5, "fill": "#f43f5e",
     "style": {"glow": {"color": "#f43f5e", "blur": 8}}},
    {"op": "add_ellipse", "cx": 1708, "cy": 212, "rx": 4.5, "fill": "#fbbf24",
     "style": {"glow": {"color": "#fbbf24", "blur": 8}}},

    {"op": "add_frame", "x": 632, "y": 914, "width": 656, "height": 116, "preset": "cyber_tech",
     "accent": "#8b5cf6", "id_prefix": "hotbar"},
])
slot_mats = [("gold", "sword", "1"), ("steel", "shield", "2"), ("steel", "potion", "3"),
             ("steel", "bolt", "4"), ("steel", "key", "5")]
for i, (m, ic, num) in enumerate(slot_mats):
    sx = 668 + i * 122
    ui.batch("hud", [
        {"op": "add_rect", "x": sx, "y": 932, "width": 84, "height": 80, "radius": 14,
         "style": {"material": m, "shadow": {"blur": 10, "dy": 4, "color": "#000@0.55"}}},
        {"op": "add_rect", "x": sx + 4, "y": 936, "width": 76, "height": 72, "radius": 10,
         "fill": "#0a0e18", "style": {"inner_shadow": {"blur": 8, "dy": 2, "color": "#000@0.85"}}},
        icon(ic, sx + 20, 950, 44, style={"material": "gold" if i == 0 else "chrome"}),
        {"op": "add_text", "text": num, "x": sx + 10, "y": 941, "size": 12, "weight": 800,
         "font": "JetBrains Mono", "color": "#fde68a" if i == 0 else "#94a3b8"},
    ])
ui.export_png("hud", str(OUT / "hud_mockup.png"), scales=[0.5], include_background=True)
(OUT / "hud_mockup_0_5x.png").replace(OUT / "hud_mockup.png")
print("wrote kit_sheet.png and hud_mockup.png")
