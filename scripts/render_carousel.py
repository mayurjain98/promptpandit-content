"""Render a carousel spec (JSON) to 1080x1350 slide images.

Instagram's publishing API only accepts JPEG for image posts, so we capture
each slide losslessly and save a high-quality JPEG (q=95). Pass --png to
also keep PNG copies for review.

Spec format (see templates/carousel/sample.json):
  { "id": "...", "series": "Prompt of the Day", "slides": [ {type: ...}, ... ] }

Usage:
  .venv/bin/python scripts/render_carousel.py SPEC.json OUT_DIR [--png]
"""
import argparse
import io
import json
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates" / "carousel" / "carousel.html"
CTA_TEXT = "Save karo, follow karo @promptpandit.in"


def render(spec: dict, out_dir: Path, keep_png: bool = False) -> list:
    slides = spec["slides"]
    # Rule: every carousel ends with the CTA slide. Add one if missing.
    if slides[-1]["type"] != "cta":
        slides = slides + [{"type": "cta"}]
    if not 2 <= len(slides) <= 10:
        raise ValueError(f"Instagram allows 2-10 carousel items, got {len(slides)}")

    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1350})
        page.goto(TEMPLATE.as_uri())
        for i, slide in enumerate(slides, start=1):
            page.evaluate("([s, i, n, series]) => window.renderSlide(s, i, n, series)",
                          [slide, i, len(slides), spec.get("series")])
            png = page.locator("#slide").screenshot(type="png")
            img = Image.open(io.BytesIO(png)).convert("RGB")
            path = out_dir / f"slide_{i:02d}.jpg"
            img.save(path, "JPEG", quality=95, subsampling=0, optimize=True)
            if keep_png:
                img.save(out_dir / f"slide_{i:02d}.png")
            files.append(path)
        browser.close()
    return files


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("out_dir")
    ap.add_argument("--png", action="store_true", help="also save PNG copies")
    a = ap.parse_args()
    spec = json.loads(Path(a.spec).read_text())
    for f in render(spec, Path(a.out_dir), a.png):
        print(f)
