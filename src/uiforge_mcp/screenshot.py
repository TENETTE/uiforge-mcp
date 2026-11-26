"""OpenCV screenshot-to-editable-canvas reconstructor (import_screenshot).

Analyzes an existing UI screenshot (PNG / JPG / WebP) with OpenCV SIMD to extract:
  1. Canvas background colour and dominant K-means palette tokens
  2. Hierarchical UI panels, cards, buttons, pills, badges and circular avatars (RETR_TREE contours)
  3. Estimated corner radius, solid vs linear gradient fill, and inner border stroke per shape
  4. Text regions via optional local OCR (rapidocr_onnxruntime or pytesseract when installed) with an
     OpenCV morphological text-line detector fallback so layouts stay editable even offline
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

try:
    import cv2
except Exception:
    cv2 = None


def _rgb_hex(rgb) -> str:
    r, g, b = (max(0, min(255, int(round(float(v))))) for v in rgb[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def _color_dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a.astype(np.float32) - b.astype(np.float32)))


def _extract_palette(rgb: np.ndarray, k: int = 6) -> tuple[str, list[str]]:
    """Return (background_hex, sorted_palette_hexes) using border sampling + OpenCV k-means."""
    h, w = rgb.shape[:2]
    border = np.concatenate([rgb[0, :], rgb[-1, :], rgb[:, 0], rgb[:, -1]], axis=0)
    bg_rgb = np.median(border, axis=0)
    bg_hex = _rgb_hex(bg_rgb)

    step = max(1, int(max(w, h) // 160))
    small = rgb[::step, ::step].reshape(-1, 3).astype(np.float32)
    if cv2 is not None and len(small) >= k * 4:
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 12, 1.0)
        _, labels, centers = cv2.kmeans(small, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
        counts = np.bincount(labels.ravel(), minlength=k)
        order = np.argsort(-counts)
        pal = [_rgb_hex(centers[i]) for i in order]
    else:
        pal = [bg_hex]
    seen: list[str] = []
    for c in [bg_hex] + pal:
        if c not in seen:
            seen.append(c)
    return bg_hex, seen[:k]


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(1, (ax1 - ax0) * (ay1 - ay0))
    area_b = max(1, (bx1 - bx0) * (by1 - by0))
    return inter / float(area_a + area_b - inter)


def _estimate_fill_and_stroke(patch: np.ndarray) -> tuple[Any, dict | None]:
    """Inspect a cropped region to classify solid vs linear gradient fill and optional border stroke."""
    ph, pw = patch.shape[:2]
    if ph < 8 or pw < 8:
        return _rgb_hex(np.median(patch.reshape(-1, 3), axis=0)), None

    ins_y = max(2, min(ph // 5, 10))
    ins_x = max(2, min(pw // 5, 10))
    core = patch[ins_y:ph - ins_y, ins_x:pw - ins_x]
    if core.size == 0:
        core = patch

    ch, cw = core.shape[:2]
    top_c = np.median(core[:max(1, ch // 4), :].reshape(-1, 3), axis=0)
    bot_c = np.median(core[max(0, ch - max(1, ch // 4)):, :].reshape(-1, 3), axis=0)
    lft_c = np.median(core[:, :max(1, cw // 4)].reshape(-1, 3), axis=0)
    rgt_c = np.median(core[:, max(0, cw - max(1, cw // 4)):].reshape(-1, 3), axis=0)

    dv = _color_dist(top_c, bot_c)
    dh = _color_dist(lft_c, rgt_c)
    if dv > 24.0 and dv >= dh:
        fill: Any = {"type": "linear", "angle": 90, "stops": [[0, _rgb_hex(top_c)], [1, _rgb_hex(bot_c)]]}
    elif dh > 24.0:
        fill = {"type": "linear", "angle": 0, "stops": [[0, _rgb_hex(lft_c)], [1, _rgb_hex(rgt_c)]]}
    else:
        fill = _rgb_hex(np.median(core.reshape(-1, 3), axis=0))

    ring = np.concatenate([patch[1, 2:-2], patch[-2, 2:-2], patch[2:-2, 1], patch[2:-2, -2]], axis=0)
    core_med = np.median(core.reshape(-1, 3), axis=0)
    ring_med = np.median(ring, axis=0)
    stroke = None
    if _color_dist(ring_med, core_med) > 26.0:
        diffs = np.linalg.norm(ring.astype(np.float32) - core_med.astype(np.float32), axis=1)
        if float(np.mean(diffs > 20.0)) >= 0.55:
            stroke = {"color": _rgb_hex(ring_med), "width": 1.5, "align": "inside"}
    return fill, stroke


def _estimate_corner_radius(mask_roi: np.ndarray, w: int, h: int) -> float:
    """Estimate rounded rectangle corner radius from empty corner triangles of a contour mask."""
    max_r = min(w, h) * 0.5
    probe = max(3, min(int(max_r), 36))
    if probe < 3 or mask_roi.shape[0] < probe * 2 or mask_roi.shape[1] < probe * 2:
        return 0.0
    corners = [
        mask_roi[:probe, :probe],
        mask_roi[:probe, -probe:],
        mask_roi[-probe:, :probe],
        mask_roi[-probe:, -probe:],
    ]
    empty_ratios = [float(np.mean(c == 0)) for c in corners]
    avg_empty = sum(empty_ratios) / 4.0
    if avg_empty < 0.03:
        return 0.0
    est = float(np.sqrt(max(0.0, avg_empty * (probe * probe) / 0.2146)))
    return round(min(max_r, max(2.0, est)), 1)


def _run_ocr(rgb: np.ndarray, mode: str = "auto") -> tuple[list[dict[str, Any]], str]:
    """Detect text regions using RapidOCR / Tesseract if installed, else OpenCV morphological text lines."""
    if mode == "off":
        return [], "off"

    try:
        from rapidocr_onnxruntime import RapidOCR
        engine = RapidOCR()
        result, _ = engine(rgb)
        texts: list[dict[str, Any]] = []
        for item in (result or []):
            pts, txt, score = item[0], str(item[1]).strip(), float(item[2])
            if not txt or score < 0.35:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            x0, y0, x1, y1 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
            texts.append({"x": x0, "y": y0, "w": max(4, x1 - x0), "h": max(8, y1 - y0), "text": txt})
        return texts, "rapidocr"
    except Exception:
        pass

    try:
        import pytesseract
        data = pytesseract.image_to_data(rgb, output_type=pytesseract.Output.DICT)
        lines: dict[tuple[int, int, int], list[tuple[int, int, int, int, str]]] = {}
        for i, raw in enumerate(data.get("text", [])):
            t = str(raw).strip()
            conf = float(data["conf"][i]) if str(data["conf"][i]).lstrip("-").isdigit() else -1.0
            if not t or conf < 40:
                continue
            key = (int(data["block_num"][i]), int(data["par_num"][i]), int(data["line_num"][i]))
            lines.setdefault(key, []).append((int(data["left"][i]), int(data["top"][i]),
                                              int(data["width"][i]), int(data["height"][i]), t))
        texts = []
        for words in lines.values():
            x0 = min(w[0] for w in words)
            y0 = min(w[1] for w in words)
            x1 = max(w[0] + w[2] for w in words)
            y1 = max(w[1] + w[3] for w in words)
            texts.append({"x": x0, "y": y0, "w": max(4, x1 - x0), "h": max(8, y1 - y0),
                          "text": " ".join(w[4] for w in words)})
        return texts, "pytesseract"
    except Exception:
        pass

    if cv2 is None:
        return [], "none"

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    abs_x = cv2.convertScaleAbs(grad_x)
    _, bw = cv2.threshold(abs_x, 38, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
    closed = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel)
    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = rgb.shape[:2]
    found: list[dict[str, Any]] = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if h < 10 or h > max(44, int(H * 0.08)) or w < 22 or w > int(W * 0.75):
            continue
        if w / float(h) < 1.6:
            continue
        found.append({"x": x, "y": y, "w": w, "h": h, "text": ""})
    found.sort(key=lambda d: (d["y"], d["x"]))
    return found[:30], "opencv_heuristic"


def _text_fg_color(patch: np.ndarray) -> str:
    """Pick the high-contrast foreground text colour inside a text bounding box."""
    if patch.size == 0:
        return "#f8fafc"
    border = np.concatenate([patch[0, :], patch[-1, :], patch[:, 0], patch[:, -1]], axis=0)
    bg = np.median(border, axis=0)
    flat = patch.reshape(-1, 3).astype(np.float32)
    dists = np.linalg.norm(flat - bg.astype(np.float32), axis=1)
    top_k = max(1, int(len(dists) * 0.12))
    idx = np.argpartition(dists, -top_k)[-top_k:]
    return _rgb_hex(np.median(flat[idx], axis=0))


def _hex_to_rgb(hx: str) -> np.ndarray:
    return np.array([int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)], dtype=np.float32)


def _infer_layout_groups(shapes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect aligned sibling rows/columns and tag them with clean group names for responsive layout."""
    rects = [s for s in shapes if s.get("type") in ("rect", "input", "toggle", "dropdown") and not s.get("group")]
    groups: list[dict[str, Any]] = []
    used: set[str] = set()
    row_idx = 0
    for i, a in enumerate(rects):
        if a["id"] in used:
            continue
        ay, ah = float(a["y"]), float(a["height"])
        row = [a]
        for b in rects[i + 1:]:
            if b["id"] in used:
                continue
            by, bh = float(b["y"]), float(b["height"])
            if abs(by - ay) <= 6.0 and abs(bh - ah) <= max(8.0, ah * 0.2):
                row.append(b)
        if len(row) >= 2:
            row.sort(key=lambda s: float(s["x"]))
            gaps = [float(row[k + 1]["x"]) - (float(row[k]["x"]) + float(row[k]["width"])) for k in range(len(row) - 1)]
            if all(-2.0 <= g <= 160.0 for g in gaps):
                row_idx += 1
                gname = f"row_{row_idx}"
                for item in row:
                    item["group"] = gname
                    used.add(item["id"])
                groups.append({"group": gname, "direction": "row",
                               "gap": round(sum(gaps) / max(1, len(gaps)), 1),
                               "members": [item["id"] for item in row]})
    col_idx = 0
    for i, a in enumerate(rects):
        if a["id"] in used:
            continue
        ax, aw = float(a["x"]), float(a["width"])
        col = [a]
        for b in rects[i + 1:]:
            if b["id"] in used:
                continue
            bx, bw = float(b["x"]), float(b["width"])
            if abs(bx - ax) <= 6.0 and abs(bw - aw) <= max(10.0, aw * 0.2):
                col.append(b)
        if len(col) >= 2:
            col.sort(key=lambda s: float(s["y"]))
            gaps = [float(col[k + 1]["y"]) - (float(col[k]["y"]) + float(col[k]["height"])) for k in range(len(col) - 1)]
            if all(-2.0 <= g <= 120.0 for g in gaps):
                col_idx += 1
                gname = f"col_{col_idx}"
                for item in col:
                    item["group"] = gname
                    used.add(item["id"])
                groups.append({"group": gname, "direction": "column",
                               "gap": round(sum(gaps) / max(1, len(gaps)), 1),
                               "members": [item["id"] for item in col]})
    return groups


def _bind_palette_tokens(shapes: list[dict[str, Any]], texts: list[dict[str, Any]],
                         token_map: dict[str, str], max_dist: float = 24.0) -> int:
    """Replace matching raw hex fills/strokes/text colors with $ss_* theme tokens."""
    if not token_map:
        return 0
    tok_rgbs = [(f"${name}", _hex_to_rgb(hx)) for name, hx in token_map.items() if isinstance(hx, str) and len(hx) == 7 and hx.startswith("#")]
    bound = 0

    def match(val: Any) -> Any:
        nonlocal bound
        if isinstance(val, str) and len(val) == 7 and val.startswith("#"):
            rgb = _hex_to_rgb(val)
            best_tok, best_d = None, max_dist
            for tname, trgb in tok_rgbs:
                d = _color_dist(rgb, trgb)
                if d <= best_d:
                    best_d, best_tok = d, tname
            if best_tok:
                bound += 1
                return best_tok
        return val

    for s in shapes:
        st = s.get("style")
        if isinstance(st, dict):
            if "fill" in st:
                st["fill"] = match(st["fill"])
            if isinstance(st.get("stroke"), dict) and "color" in st["stroke"]:
                st["stroke"]["color"] = match(st["stroke"]["color"])
    for t in texts:
        if "color" in t:
            t["color"] = match(t["color"])
    return bound


def analyze_screenshot(path: str | Path, max_width: int = 1280, max_elements: int = 60,
                       ocr: str = "auto", classify_widgets: bool = True,
                       infer_layout: bool = True) -> dict[str, Any]:
    """Analyze a UI screenshot into structured editable canvas elements, layout groups + palette tokens."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise ValueError(f"screenshot file not found: {p}")
    pil = Image.open(p).convert("RGB")
    orig_w, orig_h = pil.size
    if orig_w > max_width and max_width >= 160:
        scale = max_width / float(orig_w)
        pil = pil.resize((int(round(orig_w * scale)), max(1, int(round(orig_h * scale)))), Image.LANCZOS)
    rgb = np.asarray(pil, dtype=np.uint8)
    H, W = rgb.shape[:2]

    bg_hex, palette = _extract_palette(rgb, k=6)
    bg_rgb = np.array([int(bg_hex[1:3], 16), int(bg_hex[3:5], 16), int(bg_hex[5:7], 16)], dtype=np.float32)

    raw_texts, ocr_engine = _run_ocr(rgb, mode=str(ocr or "auto").lower())
    text_boxes = [(td["x"], td["y"], td["x"] + td["w"], td["y"] + td["h"]) for td in raw_texts]

    shapes: list[dict[str, Any]] = []
    if cv2 is not None:
        dist_bg = np.linalg.norm(rgb.astype(np.float32) - bg_rgb[None, None, :], axis=2)
        fg_mask = (dist_bg > 18.0).astype(np.uint8) * 255
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 32, 110)
        k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        edges_closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, k_close)

        raw_boxes: list[tuple[int, int, int, int, float, np.ndarray]] = []
        for src_bin in (fg_mask, edges_closed):
            cnts, _ = cv2.findContours(src_bin, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                area = cv2.contourArea(c)
                if area < 280 or area > W * H * 0.92:
                    continue
                x, y, w, h = cv2.boundingRect(c)
                if w < 18 or h < 14:
                    continue
                if w > W * 0.96 and h > H * 0.96:
                    continue
                fill_ratio = area / float(w * h)
                if fill_ratio < 0.52:
                    continue
                if h < 34 and any(_iou((x, y, x + w, y + h), tb) > 0.32 for tb in text_boxes):
                    continue
                if h < 34:
                    inner_e = edges[y + 2:max(y + 3, y + h - 2), x + 2:max(x + 3, x + w - 2)]
                    if inner_e.size > 0 and float(np.mean(inner_e > 0)) > 0.12:
                        continue
                perim = max(1.0, cv2.arcLength(c, True))
                circ = 4.0 * np.pi * area / (perim * perim)
                raw_boxes.append((x, y, x + w, y + h, float(circ), c))

        raw_boxes.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
        kept: list[tuple[int, int, int, int, float, np.ndarray]] = []
        for cand in raw_boxes:
            box4 = cand[:4]
            if any(_iou(box4, k[:4]) > 0.82 for k in kept):
                continue
            kept.append(cand)
            if len(kept) >= max_elements:
                break

        for idx, (x0, y0, x1, y1, circ, cnt) in enumerate(kept):
            w, h = x1 - x0, y1 - y0
            patch = rgb[y0:y1, x0:x1]
            fill, stroke = _estimate_fill_and_stroke(patch)
            if isinstance(fill, str) and _color_dist(
                np.array([int(fill[1:3], 16), int(fill[3:5], 16), int(fill[5:7], 16)], dtype=np.float32), bg_rgb
            ) < 12.0 and stroke is None:
                continue
            aspect = w / float(h)
            is_circle = circ > 0.78 and 0.82 <= aspect <= 1.22
            st_obj: dict[str, Any] = {"fill": fill}
            if stroke:
                st_obj["stroke"] = stroke
            if is_circle:
                shapes.append({
                    "type": "ellipse",
                    "id": f"circle_{idx + 1}",
                    "cx": round(x0 + w * 0.5, 1),
                    "cy": round(y0 + h * 0.5, 1),
                    "rx": round(w * 0.5, 1),
                    "ry": round(h * 0.5, 1),
                    "style": st_obj,
                })
            else:
                roi_mask = np.zeros((h, w), dtype=np.uint8)
                shifted = cnt - np.array([[[x0, y0]]], dtype=cnt.dtype)
                cv2.drawContours(roi_mask, [shifted], -1, 255, thickness=-1)
                rad = _estimate_corner_radius(roi_mask, w, h)
                role = "card" if (w * h > W * H * 0.08) else ("button" if (26 <= h <= 64 and w >= 72) else "box")
                if classify_widgets and 18 <= h <= 34 and 1.65 <= aspect <= 2.35 and rad >= h * 0.42:
                    shapes.append({
                        "type": "toggle",
                        "id": f"toggle_{idx + 1}",
                        "x": float(x0),
                        "y": float(y0),
                        "width": float(w),
                        "height": float(h),
                        "variant": "switch",
                        "checked": False,
                        "note": "imported:toggle",
                    })
                else:
                    shapes.append({
                        "type": "rect",
                        "id": f"{role}_{idx + 1}",
                        "x": float(x0),
                        "y": float(y0),
                        "width": float(w),
                        "height": float(h),
                        "radius": rad,
                        "style": st_obj,
                        "note": f"imported:{role}",
                    })

    texts: list[dict[str, Any]] = []
    for ti, td in enumerate(raw_texts):
        if len(shapes) + len(texts) >= max_elements + 25:
            break
        tx, ty, tw, th = td["x"], td["y"], td["w"], td["h"]
        txt = td["text"]
        if not txt:
            if ocr_engine == "opencv_heuristic":
                if any(_iou((tx, ty, tx + tw, ty + th), (int(s.get("x", 0)), int(s.get("y", 0)),
                                                         int(s.get("x", 0) + s.get("width", 0)),
                                                         int(s.get("y", 0) + s.get("height", 0)))) > 0.72
                       for s in shapes if s["type"] == "rect"):
                    continue
                txt = f"Label {ti + 1}"
            else:
                continue
        patch = rgb[max(0, ty - 2):min(H, ty + th + 2), max(0, tx - 2):min(W, tx + tw + 2)]
        fg_col = _text_fg_color(patch)
        fsize = round(max(10.0, min(64.0, th * 0.80)), 1)
        texts.append({
            "type": "text",
            "id": f"text_{ti + 1}",
            "text": txt,
            "x": float(tx),
            "y": round(ty + th * 0.5, 1),
            "anchor": "middle-left",
            "size": fsize,
            "font": "Inter",
            "weight": 700 if fsize >= 20 else 500,
            "color": fg_col,
        })

    layout_groups = _infer_layout_groups(shapes) if infer_layout else []
    token_map: dict[str, str] = {"ss_bg": bg_hex}
    for i, hx in enumerate(palette[1:], 1):
        token_map[f"ss_c{i}"] = hx

    return {
        "width": W,
        "height": H,
        "background": bg_hex,
        "palette": palette,
        "token_map": token_map,
        "shapes": shapes,
        "texts": texts,
        "layout_groups": layout_groups,
        "ocr_engine": ocr_engine,
    }
