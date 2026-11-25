"""Technical QA for rendered assets. Exits non-zero if anything fails.

Reel checks (Instagram Reels API limits + our own rules):
  1080x1920, H.264 + AAC, 3-90 s (target 20-45 s), audio present and
  audible, 23-60 fps, file under 100 MB.
Carousel checks:
  2-10 slides, each a 1080x1350 JPEG under 8 MB.

Usage:
  .venv/bin/python scripts/qa.py reel  FILE.mp4
  .venv/bin/python scripts/qa.py carousel DIR
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def mean_volume(path):
    """Average loudness in dB (silence is around -91 dB)."""
    err = subprocess.run(["ffmpeg", "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.search(r"mean_volume: (-?[\d.]+) dB", err)
    return float(m.group(1)) if m else -99.0


def loudness_lufs(path):
    """Integrated loudness (EBU R128). Instagram plays at about -14 LUFS."""
    err = subprocess.run(["ffmpeg", "-i", str(path), "-af", "ebur128", "-vn", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    return float(m[-1]) if m else -99.0


def check_reel(path: Path):
    info = probe(path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])
    size_mb = path.stat().st_size / 1e6
    fps = eval(v["avg_frame_rate"]) if v else 0  # "30/1" -> 30.0
    vol = mean_volume(path) if a else -99
    return [
        ("resolution 1080x1920", v and (v["width"], v["height"]) == (1080, 1920), f"{v['width']}x{v['height']}" if v else "no video"),
        ("video codec H.264", v and v["codec_name"] == "h264", v["codec_name"] if v else "-"),
        ("pixel format yuv420p", v and v.get("pix_fmt") == "yuv420p", v.get("pix_fmt") if v else "-"),
        ("audio AAC present", a and a["codec_name"] == "aac", a["codec_name"] if a else "none"),
        ("audio audible", vol > -35, f"mean {vol:.1f} dB"),
        ("loudness -17..-10 LUFS", a and -17 <= (lufs := loudness_lufs(path)) <= -10, f"{lufs:.1f} LUFS" if a else "-"),
        ("duration 3-90 s", 3 <= dur <= 90, f"{dur:.1f}s"),
        ("duration target 20-45 s", 20 <= dur <= 45, f"{dur:.1f}s"),
        ("fps 23-60", 23 <= fps <= 60, f"{fps:g}"),
        ("size < 100 MB", size_mb < 100, f"{size_mb:.1f} MB"),
    ]


def check_carousel(folder: Path):
    slides = sorted(folder.glob("slide_*.jpg"))
    results = [("slide count 2-10", 2 <= len(slides) <= 10, str(len(slides)))]
    for s in slides:
        im = Image.open(s)
        ok = im.format == "JPEG" and im.size == (1080, 1350) and s.stat().st_size < 8e6
        results.append((f"{s.name} JPEG 1080x1350 <8MB", ok, f"{im.format} {im.size[0]}x{im.size[1]} {s.stat().st_size / 1e3:.0f} KB"))
    return results


def report(name, results):
    print(f"\nQA: {name}")
    for label, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {label:30} {detail}")
    return all(ok for _, ok, _ in results)


if __name__ == "__main__":
    kind, target = sys.argv[1], Path(sys.argv[2])
    ok = report(target, check_reel(target) if kind == "reel" else check_carousel(target))
    sys.exit(0 if ok else 1)
