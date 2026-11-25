"""Heavy run: a 4K screen with 500 elements, 50 of them text rows in many scripts, rendered,
reviewed and exported three times in a row. Output must be identical every time."""
import hashlib
import os
import time
from pathlib import Path

import numpy as np
import pytest

from uiforge_mcp import server as s
from uiforge_mcp.store import Store

SAMPLES = [
    ("en", "Start game"), ("tr", "Oyuna başla ışık İğde"), ("de", "Spiel starten Größe"), ("ru", "Начать игру"),
    ("el", "Έναρξη παιχνιδιού"), ("vi", "Bắt đầu trò chơi"), ("ar", "ابدأ اللعبة السعر 1,250"),
    ("he", "התחל משחק"), ("fa", "شروع بازی"), ("hi", "खेल शुरू करें क्षि"), ("bn", "খেলা শুরু করুন"),
    ("ta", "விளையாட்டைத் தொடங்கு"), ("th", "เริ่มเกม"), ("ja", "ゲームを始める直"), ("zh-Hans", "开始游戏直"),
    ("zh-Hant", "開始遊戲直"), ("ko", "게임 시작"), ("pl", "Rozpocznij grę"),
]
_WIN_FONTS = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
if not all((_WIN_FONTS / f).exists() for f in ("YuGothM.ttc", "msyh.ttc", "msjh.ttc", "malgun.ttf")):
    SAMPLES = [row for row in SAMPLES if row[0] not in ("ja", "zh-Hans", "zh-Hant", "ko")]


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def build() -> None:
    s.create_canvas("big", 3840, 2160, background="#101418")
    ops = []
    for i in range(450):
        x, y = (i % 30) * 128, (i // 30) * 140
        if i % 3 == 0:
            ops.append({"op": "add_ellipse", "cx": x + 60, "cy": y + 60, "rx": 50,
                        "style": {"fill": "#3a7bd5", "shadow": {"blur": 6, "y": 3}}})
        else:
            ops.append({"op": "add_rect", "x": x + 8, "y": y + 8, "width": 110, "height": 110, "radius": 14,
                        "style": {"fill": {"type": "linear", "angle": 90, "stops": ["#2b5876", "#4e4376"]},
                                  "stroke": {"color": "#ffffff", "width": 2}}})
    for i in range(50):
        lang, text = SAMPLES[i % len(SAMPLES)]
        ops.append({"op": "add_text", "text": text, "x": 40 + (i % 2) * 1900, "y": 60 + (i // 2) * 82,
                    "size": 34, "color": "#ffffff", "max_width": 1800, "lang": lang,
                    "stroke": {"color": "#000000", "width": 2}})
    s.batch("big", ops)


def test_heavy_4k_500_elements_50_languages(ws):
    build()
    st = s.store()
    assert len(st.get("big")["elements"]) == 500
    hashes, times = [], []
    for run in range(3):
        t0 = time.perf_counter()
        img = st.renderer(st.get("big")).render()
        times.append(time.perf_counter() - t0)
        hashes.append(hashlib.sha256(np.asarray(img).tobytes()).hexdigest())
        assert img.size == (3840, 2160)
        s.export_png("big", path=str(ws / f"big_{run}.png"))
    assert len(set(hashes)) == 1, "renders differ between runs"
    for _ in range(3):
        t0 = time.perf_counter()
        assert "no glyph" not in str(s.review_canvas("big"))
        assert time.perf_counter() - t0 < 15, "review_canvas got slow again (was ~3 s, 28 s before the fix)"

    print(f"4K render seconds per run: {[round(t, 2) for t in times]}")
