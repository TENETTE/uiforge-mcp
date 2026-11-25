"""Image vectorising and vector PDF export."""
import numpy as np
import pytest
from PIL import Image, ImageDraw

from uiforge_mcp import server as s
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def test_vectorize_keeps_colours_holes_and_small_details(ws, tmp_path):
    img = Image.new("RGBA", (120, 80), (20, 20, 30, 255))
    d = ImageDraw.Draw(img)
    d.ellipse((20, 10, 80, 70), fill=(240, 180, 40, 255))
    d.ellipse((40, 30, 60, 50), fill=(20, 20, 30, 255))
    d.rectangle((95, 35, 100, 40), fill=(255, 255, 255, 255))
    src = tmp_path / "logo.png"
    img.save(src)
    s.create_canvas("c", 240, 160)
    res = s.vectorize_image("c", str(src), width=240, colors=3)
    assert len(res["paths"]) == 3 and "#ffffff" in res["colors"] or any(c.startswith("#f") for c in res["colors"])
    st = s.store()
    px = np.asarray(st.renderer(st.get("c")).render(include_background=False))
    assert px[80, 60, 0] > 200 and px[80, 100, 0] < 60
    assert px[75, 195, 0] > 200


def test_pdf_has_vector_pages_and_fallbacks(ws):
    s.create_canvas("a", 200, 100, background="#101018")
    s.add_rect("a", 10, 10, 100, 50, radius=8, style={"fill": {"type": "linear", "stops": [[0, "#ff0000"], [1, "#0000ff"]]},
                                                     "stroke": {"color": "#ffffff", "width": 2}, "shadow": {"blur": 6}})
    s.add_text("a", "Hi", x=150, y=30, size=24, id="t")
    s.add_rect("a", 120, 60, 60, 30, id="fancy", style={"fill": {"type": "shader", "code": "r = u; g = v; b = 1"}})
    s.create_canvas("b", 100, 100)
    s.add_ellipse("b", 50, 50, 40, fill="#00ff00")
    res = s.export_pdf(["a", "b"], path=str(ws / "kit.pdf"))
    data = (ws / "kit.pdf").read_bytes()
    assert data.startswith(b"%PDF-1.7") and data.rstrip().endswith(b"%%EOF") and b"/Count 2" in data
    assert res["pages"] == 2 and "t" in res["vector"] and res["embedded_as_image"] == ["fancy"]
    pdfium = pytest.importorskip("pypdfium2")
    page = pdfium.PdfDocument(str(ws / "kit.pdf"))[1].render(scale=1).to_pil().convert("RGB")
    assert page.getpixel((50, 50))[1] > 200
