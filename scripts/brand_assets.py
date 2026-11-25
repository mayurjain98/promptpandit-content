"""Build derived brand assets (safe to re-run).

1. templates/brand/watermark_trimmed.png
   The watermark PNG has lots of empty padding. We crop to the visible logo
   so "8% of width" means the logo itself, not the padding.

2. templates/audio/pad_lofi_01.m4a
   An ORIGINAL ambient chord bed synthesised with FFmpeg (sine waves +
   filters). Because we generate it ourselves it is royalty-free by
   construction. Drop any other royalty-free tracks into templates/audio/
   and the Reel renderer will rotate through them.

Usage:  .venv/bin/python scripts/brand_assets.py
"""
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "templates" / "brand"
AUDIO = ROOT / "templates" / "audio"


def trim_watermark():
    src = BRAND / "promptpandit_final_watermark_transparent.png"
    dst = BRAND / "watermark_trimmed.png"
    img = Image.open(src).convert("RGBA")
    # Ignore the faint outer glow when finding the edges (alpha > 40).
    alpha = img.getchannel("A").point(lambda a: 255 if a > 40 else 0)
    bbox = alpha.getbbox()
    pad = 12  # keep a little glow around the bubble
    bbox = (max(bbox[0] - pad, 0), max(bbox[1] - pad, 0),
            min(bbox[2] + pad, img.width), min(bbox[3] + pad, img.height))
    img.crop(bbox).save(dst)
    print(f"watermark_trimmed.png  {img.crop(bbox).size}")


# Chord progression (Am - F - C - G), frequencies in Hz, 4 s per chord.
CHORDS = [
    [220.00, 261.63, 329.63],   # A minor
    [174.61, 220.00, 261.63],   # F major
    [196.00, 261.63, 329.63],   # C major (C4 E4 + G3)
    [196.00, 246.94, 293.66],   # G major
]
CHORD_SEC = 4
LOOPS = 4  # 4 x 16 s = 64 s, longer than any Reel


def make_pad():
    out = AUDIO / "pad_lofi_01.m4a"
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, chord in enumerate(CHORDS):
            # Each note: sine with a slow tremolo; summed and scaled down.
            notes = "+".join(
                f"0.25*sin(2*PI*{f}*t)*(0.85+0.15*sin(2*PI*0.5*t))" for f in chord
            )
            part = Path(tmp) / f"c{i}.wav"
            subprocess.run([
                "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                "-i", f"aevalsrc={notes}:s=44100:d={CHORD_SEC}",
                # Soft attack/release so chords blend without clicks.
                "-af", f"afade=t=in:d=0.8,afade=t=out:st={CHORD_SEC - 0.8}:d=0.8",
                str(part)])
            parts.append(part)
        listfile = Path(tmp) / "list.txt"
        listfile.write_text("".join(f"file '{p}'\n" for p in parts * LOOPS))
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listfile),
            # Warm it up: low-pass, gentle echo for space, stereo, normalise.
            "-af", "lowpass=f=1800,aecho=0.8:0.6:120|240:0.25|0.15,"
                   "pan=stereo|c0=c0|c1=c0,loudnorm=I=-24",
            "-c:a", "aac", "-b:a", "128k", str(out)])
    print(f"{out.name}  created")


if __name__ == "__main__":
    trim_watermark()
    make_pad()
