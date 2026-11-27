"""Parametric AAA frame & panel generator emitting 100% editable vector + PBR elements.

Produces ornate RPG metallic moldings with cubic-Bezier corner filigree scrollwork, winged gemstone
crests, forged blacksmith rivet rows, medieval iron hinge clasps, royal embossed bezels, aged fantasy
parchment scrolls, tactical sci-fi HUD telemetry frames, cyberpunk chamfered chassis, frosted glass
cards, luxury machined bezels, and chunky cartoon badges. Every call returns the exact interior safe
box for content placement.
"""

from __future__ import annotations

from typing import Any

FRAME_PRESETS = (
    "rpg_gold",
    "royal_ornate",
    "fantasy_parchment",
    "scifi_hud",
    "cyber_tech",
    "glass_card",
    "medieval_iron",
    "luxury_minimal",
    "cartoon_thick",
)


def _bracket_path(x: float, y: float, dx: float, dy: float, arm: float, thick: float) -> str:
    """Crisp L-shaped corner bracket polygon path with chamfered inner heel."""
    x0, y0 = x, y
    x1, y1 = x + dx * arm, y
    x2, y2 = x + dx * arm, y + dy * thick
    x3, y3 = x + dx * (thick * 1.45), y + dy * thick
    x4, y4 = x + dx * thick, y + dy * (thick * 1.45)
    x5, y5 = x + dx * thick, y + dy * arm
    x6, y6 = x, y + dy * arm
    return (
        f"M {x0:g} {y0:g} L {x1:g} {y1:g} L {x2:g} {y2:g} L {x3:g} {y3:g} "
        f"L {x4:g} {y4:g} L {x5:g} {y5:g} L {x6:g} {y6:g} Z"
    )


def _filigree_corner_path(cx: float, cy: float, dx: float, dy: float, s: float) -> str:
    """Symmetrical baroque/RPG corner filigree flourish built from smooth cubic Beziers."""
    def p(u: float, v: float) -> str:
        return f"{cx + dx * u * s:.2f} {cy + dy * v * s:.2f}"

    return (
        f"M {p(-0.18, -0.18)} "
        f"C {p(0.22, -0.26)}, {p(0.68, -0.16)}, {p(1.18, 0.04)} "
        f"C {p(0.92, 0.14)}, {p(0.64, 0.08)}, {p(0.46, 0.19)} "
        f"C {p(0.58, 0.30)}, {p(0.76, 0.25)}, {p(0.70, 0.42)} "
        f"C {p(0.62, 0.56)}, {p(0.36, 0.48)}, {p(0.30, 0.30)} "
        f"C {p(0.24, 0.38)}, {p(0.38, 0.24)}, {p(0.30, 0.30)} "
        f"C {p(0.48, 0.36)}, {p(0.56, 0.62)}, {p(0.42, 0.70)} "
        f"C {p(0.25, 0.76)}, {p(0.30, 0.58)}, {p(0.19, 0.46)} "
        f"C {p(0.08, 0.64)}, {p(0.14, 0.92)}, {p(0.04, 1.18)} "
        f"C {p(-0.16, 0.68)}, {p(-0.26, 0.22)}, {p(-0.18, -0.18)} Z"
    )


def _winged_crest_path(cx: float, cy: float, half_w: float, h: float) -> str:
    """Symmetrical royal winged centerpiece escutcheon crest."""
    hw, hh = half_w, h
    return (
        f"M {cx:.2f} {cy - hh * 0.95:.2f} "
        f"C {cx + hw * 0.18:.2f} {cy - hh * 0.42:.2f}, {cx + hw * 0.44:.2f} {cy - hh * 0.68:.2f}, {cx + hw:.2f} {cy - hh * 0.08:.2f} "
        f"C {cx + hw * 0.74:.2f} {cy + hh * 0.28:.2f}, {cx + hw * 0.42:.2f} {cy + hh * 0.16:.2f}, {cx + hw * 0.24:.2f} {cy + hh * 0.58:.2f} "
        f"L {cx:.2f} {cy + hh * 0.95:.2f} "
        f"L {cx - hw * 0.24:.2f} {cy + hh * 0.58:.2f} "
        f"C {cx - hw * 0.42:.2f} {cy + hh * 0.16:.2f}, {cx - hw * 0.74:.2f} {cy + hh * 0.28:.2f}, {cx - hw:.2f} {cy - hh * 0.08:.2f} "
        f"C {cx - hw * 0.44:.2f} {cy - hh * 0.68:.2f}, {cx - hw * 0.18:.2f} {cy - hh * 0.42:.2f}, {cx:.2f} {cy - hh * 0.95:.2f} Z"
    )


def _fleur_finial_path(cx: float, cy: float, half_w: float, h: float, flip_y: float = 1.0) -> str:
    """Pointed metallic fleur-de-lis edge finial."""
    s = flip_y
    return (
        f"M {cx:.2f} {cy + s * h:.2f} "
        f"C {cx + half_w * 0.24:.2f} {cy + s * h * 0.25:.2f}, {cx + half_w * 0.68:.2f} {cy + s * h * 0.42:.2f}, {cx + half_w:.2f} {cy:.2f} "
        f"C {cx + half_w * 0.55:.2f} {cy - s * h * 0.28:.2f}, {cx + half_w * 0.22:.2f} {cy - s * h * 0.16:.2f}, {cx:.2f} {cy - s * h * 0.52:.2f} "
        f"C {cx - half_w * 0.22:.2f} {cy - s * h * 0.16:.2f}, {cx - half_w * 0.55:.2f} {cy - s * h * 0.28:.2f}, {cx - half_w:.2f} {cy:.2f} "
        f"C {cx - half_w * 0.68:.2f} {cy + s * h * 0.42:.2f}, {cx - half_w * 0.24:.2f} {cy + s * h * 0.25:.2f}, {cx:.2f} {cy + s * h:.2f} Z"
    )


def _iron_clasp_path(cx: float, cy: float, dx: float, dy: float, arm: float, w_band: float) -> str:
    """Forged medieval iron corner hinge strap with flared pointed tips."""
    def p(u: float, v: float) -> str:
        return f"{cx + dx * u:.2f} {cy + dy * v:.2f}"

    tip = arm + w_band * 0.75
    return (
        f"M {p(-w_band * 0.25, -w_band * 0.25)} "
        f"L {p(arm, -w_band * 0.18)} L {p(tip, w_band * 0.42)} L {p(arm, w_band * 1.02)} "
        f"L {p(w_band * 1.15, w_band * 0.92)} L {p(w_band * 0.92, w_band * 1.15)} "
        f"L {p(w_band * 1.02, arm)} L {p(w_band * 0.42, tip)} L {p(-w_band * 0.18, arm)} Z"
    )


def _chevron_path(x: float, y: float, w_ch: float, h_ch: float, dir_x: float = 1.0) -> str:
    """Single tactical angled chevron stripe."""
    sl = w_ch * 0.55 * dir_x
    return (
        f"M {x:.2f} {y + h_ch:.2f} L {x + sl:.2f} {y:.2f} "
        f"L {x + sl + w_ch:.2f} {y:.2f} L {x + w_ch:.2f} {y + h_ch:.2f} Z"
    )


def _diamond_points(cx: float, cy: float, rx: float, ry: float) -> list[list[float]]:
    return [[cx, cy - ry], [cx + rx, cy], [cx, cy + ry], [cx - rx, cy]]


def _rivet_ring(x: float, y: float, w: float, h: float, inset: float, spacing: float, skip_top_center: float = 0.0) -> list[tuple[float, float]]:
    """Compute evenly spaced perimeter rivets skipping corners and optional top crest span."""
    pts: list[tuple[float, float]] = []
    span_x = w - inset * 2
    nx = max(2, int(span_x // spacing))
    if nx >= 2:
        for i in range(1, nx):
            rx = x + inset + span_x * (i / nx)
            if skip_top_center <= 0 or abs(rx - (x + w * 0.5)) > skip_top_center:
                pts.append((rx, y + inset * 0.58))
            pts.append((rx, y + h - inset * 0.58))
    span_y = h - inset * 2
    ny = max(2, int(span_y // spacing))
    if ny >= 2:
        for j in range(1, ny):
            ry = y + inset + span_y * (j / ny)
            pts.append((x + inset * 0.58, ry))
            pts.append((x + w - inset * 0.58, ry))
    return pts


def frame_operations(x: float, y: float, width: float, height: float, preset: str = "rpg_gold",
                     ornament: str = "auto", material: str | None = None, accent: str | None = None,
                     title: str | None = None, group: str | None = None, id_prefix: str | None = None,
                     layer: str | None = None, quality: str | None = None) -> tuple[list[dict[str, Any]], list[float]]:
    """Generate a list of canvas element specs and the inner safe content box [ix, iy, iw, ih]."""
    p = str(preset or "rpg_gold").lower().strip()
    if p not in FRAME_PRESETS:
        raise ValueError(f"preset must be one of {', '.join(FRAME_PRESETS)}")
    orn = str(ornament or "auto").lower().strip()
    if orn not in ("auto", "none", "rivets", "brackets", "filigree", "notches"):
        raise ValueError("ornament must be auto, none, rivets, brackets, filigree or notches")
    q_eff = str(quality or "advanced").lower().strip()
    if q_eff == "simple" and orn == "auto":
        orn = "none"
    x, y, w, h = float(x), float(y), float(width), float(height)
    if w < 48 or h < 36:
        raise ValueError("frame width must be >= 48 and height >= 36")

    pfx = id_prefix or group or p
    grp = group or pfx
    base: dict[str, Any] = {"group": grp}
    if layer:
        base["layer"] = layer
    ops: list[dict[str, Any]] = []

    def add(etype: str, suffix: str, **props) -> None:
        item = {"type": etype, "id": f"{pfx}_{suffix}", **base, **props}
        if etype != "text":
            item["_decor"] = True
        ops.append(item)

    def add_rivet(suffix: str, rx: float, ry: float, rad: float, mat_name: str = "steel") -> None:
        add("ellipse", f"{suffix}_sock", cx=rx, cy=ry, rx=rad + 1.4, ry=rad + 1.4,
            style={"fill": "#090a0f@0.75"})
        add("ellipse", suffix, cx=rx, cy=ry, rx=rad, ry=rad,
            style={"material": mat_name, "shadow": {"color": "#000000@0.65", "blur": 2.5, "dy": 1.2}})

    if p == "rpg_gold":
        mat = material or "gold"
        acc = accent or "#e11d48"
        pad = max(14.0, min(22.0, min(w, h) * 0.085))
        fil_s = max(18.0, min(32.0, min(w, h) * 0.145))
        add("rect", "outer", x=x, y=y, width=w, height=h, radius=12,
            style={"material": mat,
                   "shadow": [{"color": "#000000@0.72", "blur": 26, "dy": 12},
                              {"color": "#000000@0.55", "blur": 5, "dy": 2}]})
        add("rect", "step_groove", x=x + 5, y=y + 5, width=w - 10, height=h - 10, radius=9,
            style={"fill": "#191108", "stroke": {"color": "#452c0c@0.9", "width": 1.5, "align": "inside"}})
        add("rect", "inner_bezel", x=x + 8, y=y + 8, width=w - 16, height=h - 16, radius=7,
            style={"material": "hammered_gold" if mat == "gold" else mat,
                   "inner_shadow": {"color": "#000000@0.55", "blur": 4, "dy": 1}})
        add("rect", "recess", x=x + 13, y=y + 13, width=w - 26, height=h - 26, radius=5,
            style={"fill": {"type": "radial", "cx": 0.5, "cy": 0.32, "r": 0.88,
                            "stops": [[0, "#241d31"], [0.65, "#14101e"], [1, "#09070f"]]},
                   "stroke": {"color": "#2d1d0c@0.9", "width": 2, "align": "inside"},
                   "inner_shadow": {"color": "#000000@0.9", "blur": 18, "dy": 5}})
        add("rect", "filigree_rule", x=x + 18, y=y + 18, width=w - 36, height=h - 36, radius=3,
            style={"fill": None, "stroke": {"color": "#f6d379@0.42", "width": 1.1}})
        if orn in ("auto", "filigree", "brackets"):
            for ci, (cx, cy, dx, dy) in enumerate(((x + 4, y + 4, 1, 1), (x + w - 4, y + 4, -1, 1),
                                                   (x + 4, y + h - 4, 1, -1), (x + w - 4, y + h - 4, -1, -1))):
                add("path", f"filigree_{ci}", d=_filigree_corner_path(cx, cy, dx, dy, fil_s),
                    style={"material": mat, "shadow": {"color": "#000000@0.75", "blur": 5, "dy": 2.5}})
                add("ellipse", f"corner_boss_{ci}", cx=cx + dx * 6.5, cy=cy + dy * 6.5, rx=3.6, ry=3.6,
                    style={"material": {"name": "gem", "color": acc},
                           "shadow": {"color": "#000000@0.65", "blur": 3, "dy": 1}})
            crest_w = max(24.0, min(46.0, w * 0.16))
            add("path", "crest_wings", d=_winged_crest_path(x + w * 0.5, y + 4, crest_w, 12.5),
                style={"material": mat, "shadow": {"color": "#000000@0.75", "blur": 6, "dy": 3}})
            add("polygon", "crest_gem", points=_diamond_points(x + w * 0.5, y + 4, 8.5, 6.5),
                style={"material": {"name": "gem", "color": acc}})
            add("path", "bot_finial", d=_fleur_finial_path(x + w * 0.5, y + h - 3, 18.0, 7.5, 1.0),
                style={"material": mat, "shadow": {"color": "#000000@0.65", "blur": 4, "dy": 2}})
        if orn in ("rivets",):
            for ri, (rx, ry) in enumerate(_rivet_ring(x, y, w, h, 14.0, 44.0)):
                add_rivet(f"rivet_{ri}", rx, ry, 3.0, mat)
        inner = [round(x + pad + 10, 2), round(y + pad + (34 if title else 10), 2),
                 round(w - (pad + 10) * 2, 2), round(h - (pad + 10) * 2 - (24 if title else 0), 2)]
        if title:
            add("rect", "title_plate", x=x + w * 0.5 - min(w * 0.34, 110), y=y + 18,
                width=min(w * 0.68, 220), height=24, radius=4,
                style={"fill": {"type": "linear", "angle": 90, "stops": [[0, "#1c1428@0.0"], [0.5, "#2b1d3a@0.75"], [1, "#1c1428@0.0"]]},
                       "stroke": {"color": "#f6d379@0.3", "width": 1}})
            add("text", "title", text=title, x=x + w * 0.5, y=y + 30, anchor="center",
                size=16, weight=700, font="Cinzel", letter_spacing=1.6, color="#fde68a",
                style={"shadow": {"color": "#000000@0.9", "blur": 4, "dy": 2}})

    elif p == "royal_ornate":
        mat = material or "hammered_gold"
        acc = accent or "#3b82f6"
        fil_s = max(22.0, min(38.0, min(w, h) * 0.165))
        add("rect", "outer_plinth", x=x, y=y, width=w, height=h, radius=14,
            style={"material": "bronze",
                   "shadow": [{"color": "#000000@0.78", "blur": 28, "dy": 14},
                              {"color": "#000000@0.6", "blur": 6, "dy": 2}]})
        add("rect", "molding_gold", x=x + 4, y=y + 4, width=w - 8, height=h - 8, radius=11,
            style={"material": mat, "inner_shadow": {"color": "#000000@0.5", "blur": 4, "dy": 1}})
        add("rect", "inlay_channel", x=x + 11, y=y + 11, width=w - 22, height=h - 22, radius=7,
            style={"fill": "#120c18", "stroke": {"color": "#d4af37@0.7", "width": 1.2}})
        add("rect", "velvet_bed", x=x + 16, y=y + 16, width=w - 32, height=h - 32, radius=5,
            style={"material": {"name": "fabric", "color": "#1d122d"},
                   "stroke": {"color": "#000000@0.75", "width": 2, "align": "inside"},
                   "inner_shadow": {"color": "#000000@0.88", "blur": 20, "dy": 6}})
        add("rect", "inner_hairline", x=x + 22, y=y + 22, width=w - 44, height=h - 44, radius=3,
            style={"fill": None, "stroke": {"color": "#f6d379@0.5", "width": 1.0}})
        if orn != "none":
            for ci, (cx, cy, dx, dy) in enumerate(((x + 3, y + 3, 1, 1), (x + w - 3, y + 3, -1, 1),
                                                   (x + 3, y + h - 3, 1, -1), (x + w - 3, y + h - 3, -1, -1))):
                add("path", f"scroll_{ci}", d=_filigree_corner_path(cx, cy, dx, dy, fil_s),
                    style={"material": "gold", "shadow": {"color": "#000000@0.8", "blur": 6, "dy": 3}})
                add("polygon", f"corner_gem_{ci}", points=_diamond_points(cx + dx * 7.5, cy + dy * 7.5, 4.5, 4.5),
                    style={"material": {"name": "gem", "color": acc}})
            crest_w = max(30.0, min(58.0, w * 0.21))
            add("path", "crown_crest", d=_winged_crest_path(x + w * 0.5, y + 3, crest_w, 15.0),
                style={"material": "gold", "shadow": {"color": "#000000@0.8", "blur": 7, "dy": 3}})
            add("polygon", "crown_jewel", points=_diamond_points(x + w * 0.5, y + 3, 10.5, 7.8),
                style={"material": {"name": "gem", "color": acc}})
            add("path", "bot_crest", d=_fleur_finial_path(x + w * 0.5, y + h - 3, 24.0, 9.5, 1.0),
                style={"material": "gold", "shadow": {"color": "#000000@0.75", "blur": 5, "dy": 2}})
            for ri, (rx, ry) in enumerate(_rivet_ring(x, y, w, h, 14.0, 48.0, skip_top_center=crest_w + 10)):
                add("ellipse", f"bead_{ri}", cx=rx, cy=ry, rx=2.2, ry=2.2,
                    style={"material": "gold", "shadow": {"color": "#000000@0.65", "blur": 2, "dy": 1}})
        inner = [round(x + 28, 2), round(y + (52 if title else 28), 2),
                 round(w - 56, 2), round(h - (80 if title else 56), 2)]
        if title:
            add("text", "title", text=title, x=x + w * 0.5, y=y + 34, anchor="center",
                size=16, weight=700, font="Cinzel", letter_spacing=2.2, color="#fef3c7",
                style={"shadow": {"color": "#000000@0.9", "blur": 5, "dy": 2}})

    elif p == "fantasy_parchment":
        mat = material or "aged_parchment"
        acc = accent or "#991b1b"
        cap_h = max(14.0, min(20.0, h * 0.085))
        add("rect", "scroll_body", x=x + 8, y=y + cap_h * 0.55, width=w - 16, height=h - cap_h * 1.1, radius=6,
            style={"material": mat,
                   "stroke": {"color": "#6b4423@0.65", "width": 2, "align": "inside"},
                   "inner_shadow": {"color": "#3d220a@0.55", "blur": 18, "dy": 0},
                   "shadow": {"color": "#000000@0.65", "blur": 22, "dy": 10}})
        add("rect", "ink_rule", x=x + 17, y=y + cap_h + 6, width=w - 34, height=h - cap_h * 2 - 12, radius=3,
            style={"fill": None, "stroke": {"color": "#5c3415@0.55", "width": 1.3}})
        add("rect", "roller_top", x=x, y=y, width=w, height=cap_h, radius=cap_h * 0.5,
            style={"material": {"name": "wood", "color": "#4e2f19"},
                   "shadow": {"color": "#000000@0.7", "blur": 10, "dy": 4}})
        add("rect", "roller_bot", x=x, y=y + h - cap_h, width=w, height=cap_h, radius=cap_h * 0.5,
            style={"material": {"name": "wood", "color": "#4e2f19"},
                   "shadow": {"color": "#000000@0.7", "blur": 10, "dy": 4}})
        if orn != "none":
            for si, sx in enumerate((x - 3, x + w - 13)):
                add("rect", f"cap_t_{si}", x=sx, y=y - 2, width=16, height=cap_h + 4, radius=4,
                    style={"material": "bronze", "shadow": {"color": "#000000@0.6", "blur": 4, "dy": 2}})
                add("rect", f"cap_b_{si}", x=sx, y=y + h - cap_h - 2, width=16, height=cap_h + 4, radius=4,
                    style={"material": "bronze", "shadow": {"color": "#000000@0.6", "blur": 4, "dy": 2}})
            seal_x, seal_y = x + w - 34, y + h - cap_h - 20
            add("ellipse", "wax_seal_outer", cx=seal_x, cy=seal_y, rx=13.5, ry=13.5,
                style={"material": {"name": "wax_seal", "color": acc},
                       "shadow": {"color": "#000000@0.55", "blur": 5, "dy": 2}})
            add("ellipse", "wax_seal_ring", cx=seal_x, cy=seal_y, rx=9.0, ry=9.0,
                style={"fill": None, "stroke": {"color": "#fca5a5@0.45", "width": 1.3}})
        inner = [round(x + 26, 2), round(y + cap_h + (36 if title else 14), 2),
                 round(w - 52, 2), round(h - cap_h * 2 - (50 if title else 28), 2)]
        if title:
            add("text", "title", text=title, x=x + w * 0.5, y=y + cap_h + 22, anchor="center",
                size=16, weight=700, font="Cinzel", letter_spacing=1.5, color="#3b1d08")

    elif p == "scifi_hud":
        acc = accent or "#22d3ee"
        cut = float(round(max(14.0, min(26.0, min(w, h) * 0.115))))
        arm = float(round(max(16.0, min(28.0, min(w, h) * 0.14))))
        add("rect", "body", x=x, y=y, width=w, height=h, radius=cut, corner="cut",
            style={"fill": {"type": "linear", "angle": 160, "stops": [[0, "#101b2e@0.93"], [1, "#060b14@0.96"]]},
                   "backdrop_blur": 14,
                   "stroke": {"color": f"{acc}@0.48", "width": 1.5, "align": "inside"},
                   "inner_glow": {"color": f"{acc}@0.14", "blur": 16},
                   "shadow": {"color": "#000000@0.6", "blur": 26, "dy": 10, "knockout": True}})
        add("rect", "sub_bezel", x=x + 6, y=y + 6, width=w - 12, height=h - 12, radius=max(6.0, cut - 4), corner="cut",
            style={"fill": None, "stroke": {"color": f"{acc}@0.22", "width": 1.0, "align": "inside"}})
        add("rect", "topbar", x=round(x + cut + 6), y=round(y + 2), width=round(max(28.0, w * 0.28)), height=4, radius=2,
            style={"fill": acc, "glow": {"color": f"{acc}@0.8", "blur": 10}})
        if orn in ("auto", "brackets", "notches"):
            th = 3.2
            for ci, (bx, by, dx, dy) in enumerate(((x - 2, y - 2, 1, 1), (x + w + 2, y - 2, -1, 1),
                                                   (x - 2, y + h + 2, 1, -1), (x + w + 2, y + h + 2, -1, -1))):
                add("path", f"bracket_{ci}", d=_bracket_path(bx, by, dx, dy, arm, th),
                    style={"fill": acc, "glow": {"color": f"{acc}@0.65", "blur": 8}})
            n_ticks = max(4, min(14, int((w - cut * 2 - 40) // 14)))
            tx0 = round(x + w - cut - 14 - n_ticks * 10)
            for ti in range(n_ticks):
                th_t = 6 if ti % 4 == 0 else 3
                add("rect", f"tick_{ti}", x=tx0 + ti * 10, y=round(y + h - 8 - th_t), width=2, height=th_t,
                    style={"fill": f"{acc}@0.55" if ti % 4 else acc})
            for di in range(3):
                add("ellipse", f"led_{di}", cx=round(x + w - cut - 8 - di * 10), cy=round(y + 12), rx=2.2, ry=2.2,
                    style={"fill": acc if di == 0 else f"{acc}@0.35",
                           "glow": {"color": f"{acc}@0.8", "blur": 5} if di == 0 else None})
        inner = [round(x + 20, 2), round(y + (44 if title else 20), 2),
                 round(w - 40, 2), round(h - (66 if title else 40), 2)]
        if title:
            title_x = round(x + (max(24.0, arm + 6.0) if orn in ("auto", "brackets", "notches") else 22.0))
            title_col = acc
            try:
                from .colors import parse_color
                tr, tg, tb, _ = parse_color(acc)
                lum = (0.2126 * tr + 0.7152 * tg + 0.0722 * tb) / 255.0
                if lum < 0.35:
                    mr = int(round(tr * 0.4 + 248 * 0.6))
                    mg = int(round(tg * 0.4 + 250 * 0.6))
                    mb = int(round(tb * 0.4 + 252 * 0.6))
                    title_col = f"#{mr:02x}{mg:02x}{mb:02x}"
            except Exception:
                pass
            add("line", "hdr_rule", points=[[round(x + 18), round(y + 34)], [round(x + w - 18), round(y + 34)]],
                width=1, color=f"{acc}@0.28")
            add("text", "title", text=title.upper(), x=title_x, y=round(y + 21), anchor="middle-left",
                size=14, weight=700, font="Rajdhani", letter_spacing=2.6, color=title_col)

    elif p == "cyber_tech":
        acc = accent or "#f43f5e"
        acc2 = "#22d3ee"
        cut = float(round(max(12.0, min(24.0, min(w, h) * 0.105))))
        add("rect", "chassis", x=x, y=y, width=w, height=h, radius=cut, corner="cut",
            style={"material": material or "carbon_twill",
                   "stroke": {"color": f"{acc2}@0.58", "width": 1.6, "align": "inside"},
                   "shadow": {"color": "#000000@0.68", "blur": 24, "dy": 11}})
        add("rect", "screen", x=x + 9, y=y + 9, width=w - 18, height=h - 18, radius=max(6.0, cut - 5), corner="cut",
            style={"fill": {"type": "linear", "angle": 165, "stops": [[0, "#101727@0.94"], [1, "#070b14@0.97"]]},
                   "stroke": {"color": "#ffffff@0.14", "width": 1, "align": "inside"},
                   "inner_shadow": {"color": "#000000@0.88", "blur": 14, "dy": 4}})
        add("rect", "rail_l", x=round(x + 2), y=round(y + cut + 6), width=4, height=round(max(16.0, h - cut * 2 - 12)), radius=2,
            style={"fill": acc, "glow": {"color": f"{acc}@0.85", "blur": 12}})
        add("rect", "rail_r", x=round(x + w - 6), y=round(y + cut + 6), width=4, height=round(max(16.0, h - cut * 2 - 12)), radius=2,
            style={"fill": acc2, "glow": {"color": f"{acc2}@0.85", "blur": 12}})
        if orn in ("auto", "notches", "rivets", "brackets"):
            for ci, (cx, cy) in enumerate(((x + cut + 8, y + 6), (x + w - cut - 8, y + 6),
                                           (x + cut + 8, y + h - 6), (x + w - cut - 8, y + h - 6))):
                add_rivet(f"bolt_{ci}", cx, cy, 2.6, "steel")
            chev_x0 = x + w - cut - 52
            for hi in range(4):
                add("path", f"chev_{hi}", d=_chevron_path(chev_x0 + hi * 11, y + h - 10, 6.0, 5.5, 1.0),
                    style={"fill": acc if hi % 2 == 0 else f"{acc}@0.45"})
        inner = [round(x + 22, 2), round(y + (42 if title else 20), 2),
                 round(w - 44, 2), round(h - (62 if title else 40), 2)]
        if title:
            add("rect", "title_tag", x=round(x + 18), y=round(y + 14), width=6, height=18, radius=2,
                style={"fill": acc, "glow": {"color": f"{acc}@0.7", "blur": 6}})
            add("text", "title", text=title.upper(), x=round(x + 34), y=round(y + 23), anchor="middle-left",
                size=15, weight=700, font="Barlow Condensed", italic=True, letter_spacing=2.2, color="#f8fafc")

    elif p == "glass_card":
        acc = accent or "#e0f2fe"
        add("rect", "glass", x=x, y=y, width=w, height=h, radius=22, smoothing=0.6,
            style={"material": {"name": "liquid_glass", "color": f"{acc}@0.12"}})
        add("rect", "top_sheen", x=x + 16, y=y + 2, width=w - 32, height=2.5, radius=1.2,
            style={"fill": {"type": "linear", "angle": 0, "stops": [[0, "#ffffff@0.0"], [0.5, "#ffffff@0.65"], [1, "#ffffff@0.0"]]}})
        if title:
            add("line", "divider", points=[[x + 20, y + 46], [x + w - 20, y + 46]],
                width=1, color="#ffffff@0.20")
            add("text", "title", text=title, x=x + 22, y=y + 26, anchor="middle-left",
                size=16, weight=700, font="Inter", color="#ffffff")
        inner = [round(x + 20, 2), round(y + (56 if title else 20), 2),
                 round(w - 40, 2), round(h - (76 if title else 40), 2)]

    elif p == "medieval_iron":
        mat = material or "iron"
        clasp_arm = max(18.0, min(32.0, min(w, h) * 0.145))
        add("rect", "frame", x=x, y=y, width=w, height=h, radius=9,
            style={"material": mat,
                   "shadow": [{"color": "#000000@0.74", "blur": 24, "dy": 11},
                              {"color": "#000000@0.55", "blur": 4, "dy": 2}]})
        add("rect", "bevel_slot", x=x + 9, y=y + 9, width=w - 18, height=h - 18, radius=6,
            style={"fill": "#090b10", "stroke": {"color": "#334155@0.55", "width": 1.2}})
        add("rect", "bed", x=x + 12, y=y + 12, width=w - 24, height=h - 24, radius=5,
            style={"material": "stone",
                   "stroke": {"color": "#000000@0.75", "width": 2, "align": "inside"},
                   "inner_shadow": {"color": "#000000@0.88", "blur": 16, "dy": 5}})
        if orn in ("auto", "rivets", "brackets"):
            for ci, (cx, cy, dx, dy) in enumerate(((x + 2, y + 2, 1, 1), (x + w - 2, y + 2, -1, 1),
                                                   (x + 2, y + h - 2, 1, -1), (x + w - 2, y + h - 2, -1, -1))):
                add("path", f"clasp_{ci}", d=_iron_clasp_path(cx, cy, dx, dy, clasp_arm, 9.0),
                    style={"material": "steel", "shadow": {"color": "#000000@0.78", "blur": 4, "dy": 2}})
                add_rivet(f"c_stud_{ci}", cx + dx * 7.5, cy + dy * 7.5, 3.5, "chrome")
            for ri, (rx, ry) in enumerate(_rivet_ring(x, y, w, h, 14.0, 56.0)):
                add_rivet(f"stud_{ri}", rx, ry, 2.9, "steel")
        inner = [round(x + 24, 2), round(y + (46 if title else 24), 2),
                 round(w - 48, 2), round(h - (70 if title else 48), 2)]
        if title:
            add("text", "title", text=title, x=x + w * 0.5, y=y + 30, anchor="center",
                size=17, weight=700, font="Cinzel", letter_spacing=1.5, color="#f1f5f9",
                style={"shadow": {"color": "#000000@0.9", "blur": 4, "dy": 2}})

    elif p == "luxury_minimal":
        mat = material or "chrome"
        acc = accent or "#e6b038"
        add("rect", "bezel", x=x, y=y, width=w, height=h, radius=16, smoothing=0.5,
            style={"material": mat, "shadow": {"color": "#000000@0.58", "blur": 28, "dy": 13}})
        add("rect", "inlay", x=round(x + 5), y=round(y + 5), width=round(w - 10), height=round(h - 10), radius=12, smoothing=0.5,
            style={"fill": {"type": "linear", "angle": 145, "stops": [[0, "#151923"], [1, "#0a0c12"]]},
                   "stroke": {"color": "#ffffff@0.08", "width": 1, "align": "inside"},
                   "inner_shadow": {"color": "#000000@0.75", "blur": 12, "dy": 3}})
        if orn in ("auto", "brackets", "notches"):
            add("rect", "accent_rule", x=round(x + 22), y=round(y + 5), width=round(min(72.0, w * 0.26)), height=3, radius=1.5,
                style={"fill": acc, "glow": {"color": f"{acc}@0.45", "blur": 6}})
            bot_w = round(min(44.0, w * 0.16))
            add("rect", "bot_rule", x=round(x + w - 22 - bot_w), y=round(y + h - 7),
                width=bot_w, height=2, radius=1, style={"fill": f"{acc}@0.65"})
        inner = [round(x + 20, 2), round(y + (44 if title else 20), 2),
                 round(w - 40, 2), round(h - (64 if title else 40), 2)]
        if title:
            add("text", "title", text=title, x=round(x + 22), y=round(y + 26), anchor="middle-left",
                size=15, weight=700, font="Inter", letter_spacing=1.2, color="#f8fafc")

    else:
        acc = accent or "#3b82f6"
        add("rect", "depth", x=x, y=y + 8, width=w, height=h - 4, radius=20,
            style={"fill": "#0f172a", "stroke": {"color": "#020617", "width": 4, "align": "outside"},
                   "shadow": {"color": "#000000@0.48", "blur": 14, "dy": 6}})
        add("rect", "face", x=x, y=y, width=w, height=h - 8, radius=20,
            style={"material": {"name": material or "candy_gloss", "color": acc},
                   "stroke": {"color": "#020617", "width": 4, "align": "outside"}})
        add("rect", "gloss_bar", x=x + 14, y=y + 7, width=w - 28, height=max(10.0, (h - 8) * 0.22), radius=8,
            style={"fill": {"type": "linear", "angle": 90, "stops": [[0, "#ffffff@0.52"], [1, "#ffffff@0"]]}})
        add("ellipse", "spark_dot", cx=x + 20, cy=y + 15, rx=4.2, ry=2.6,
            style={"fill": "#ffffff@0.78"})
        inner = [round(x + 18, 2), round(y + (42 if title else 18), 2),
                 round(w - 36, 2), round(h - (66 if title else 42), 2)]
        if title:
            add("text", "title", text=title, x=x + w * 0.5, y=y + 26, anchor="center",
                size=22, weight=700, font="Fredoka", color="#ffffff",
                style={"stroke": {"color": "#020617", "width": 4, "align": "outside"},
                       "shadow": {"color": "#020617@0.7", "blur": 0, "dy": 3}})

    return ops, inner
