"""Render a Reel spec (JSON) to a 1080x1920 MP4.

Pipeline
  1. Voice:    each scene's "voice" line -> Piper TTS -> WAV clip
  2. Timeline: scene start/end times come from the clip lengths
  3. Frames:   templates/reel/<style>.html is opened in Playwright; for each
               frame we call window.seek(t) and screenshot it
  4. Encode:   frames are piped into FFmpeg -> H.264, then mixed with the
               voice track and a royalty-free music bed at low volume (AAC)

Captions are drawn inside the HTML frames, so they are burned in.

Styles (templates/reel/): kinetic | comparison | tool_demo
Each style has <style>.json with render settings (fps, music volume...).

Usage:
  .venv/bin/python scripts/render_reel.py SPEC.json OUT.mp4
"""
import argparse
import json
import random
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
REEL_DIR = ROOT / "templates" / "reel"
AUDIO_DIR = ROOT / "templates" / "audio"
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text())
TTS = CONFIG["tts"]
W, H = 1080, 1920


# ---------------------------------------------------------------- voice ----
def tts_batch(texts, outs) -> list:
    """Synthesise all lines. Returns each clip's duration in seconds.

    Engine is set in config.yaml (tts.engine):
      kokoro  Hindi voice reading Devanagari Hinglish (default, Apache-2.0)
      piper   fallback English voice
    """
    # Strip our *emphasis* / [placeholder] markers so they are not read aloud.
    clean = [re.sub(r"[*\[\]]", "", t) for t in texts]
    if TTS["engine"] == "kokoro":
        jobs = [{"text": t, "out": str(o)} for t, o in zip(clean, outs)]
        res = subprocess.run(
            [str(ROOT / ".venv-tts" / "bin" / "python"), str(ROOT / "scripts" / "tts_kokoro.py"),
             "--voice", TTS["voice"], "--speed", str(TTS["speed"]), "--lang", TTS["lang"]],
            input=json.dumps(jobs).encode(), check=True, capture_output=True)
        return json.loads(res.stdout.decode().strip().splitlines()[-1])
    durs = []
    for t, o in zip(clean, outs):
        subprocess.run(
            [str(ROOT / ".venv" / "bin" / "piper"), "-m", str(ROOT / TTS["piper_model"]), "-f", str(o),
             "--length-scale", str(1 / TTS["speed"]), "--sentence-silence", "0.15"],
            input=t.encode(), check=True, capture_output=True)
        with wave.open(str(o)) as w:
            durs.append(w.getnframes() / w.getframerate())
    return durs


def build_voice_track(clips, starts, total, out: Path):
    """Place each clip at its start time on one silent track."""
    with wave.open(str(clips[0])) as w:
        params = w.getparams()
        rate, width = w.getframerate(), w.getsampwidth()
    track = bytearray(int(total * rate) * width)
    for clip, start in zip(clips, starts):
        with wave.open(str(clip)) as w:
            data = w.readframes(w.getnframes())
        offset = int(start * rate) * width
        track[offset:offset + len(data)] = data[: len(track) - offset]
    with wave.open(str(out), "wb") as w:
        w.setparams(params)
        w.writeframes(bytes(track))


# ------------------------------------------------------------- timeline ----
def make_timeline(durations, cfg):
    """Scene i runs from start to end; the voice clip starts at `start`."""
    t = cfg["lead_in"]
    scenes = []
    for d in durations:
        length = max(d + cfg["gap"], cfg["min_scene"])
        scenes.append({"start": round(t, 3), "end": round(t + length, 3), "voice": round(d, 3)})
        t += length
    outro_start = t
    total = t + cfg["outro"]
    return {"fps": cfg["fps"], "scenes": scenes, "outroStart": round(outro_start, 3), "total": round(total, 3)}


# --------------------------------------------------------- site capture ----
def capture_site(url: str, out: Path, max_height: int = 7000):
    """Full-page screenshot of a tool's official site (for tool_demo)."""
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 900, "height": 900}, device_scale_factor=2)  # narrower = bigger text in frame; 2x = crisp
        page.goto(url, wait_until="networkidle", timeout=60000)
        # Prefer declining cookie banners; if there's no decline option, hide them.
        for label in ("Reject all", "Reject", "Decline", "Only necessary", "No thanks"):
            btn = page.get_by_role("button", name=re.compile(label, re.I))
            if btn.count():
                try:
                    btn.first.click(timeout=2000)
                    break
                except Exception:
                    pass
        page.add_style_tag(content="[id*=cookie i],[class*=cookie i],[id*=consent i],[class*=consent i]{display:none!important}")
        # Scroll through once so lazy-loaded images appear.
        page.evaluate("""async () => { for (let y = 0; y < document.body.scrollHeight; y += 600) {
                         window.scrollTo(0, y); await new Promise(r => setTimeout(r, 120)); } window.scrollTo(0, 0); }""")
        page.wait_for_timeout(1500)
        height = min(page.evaluate("document.body.scrollHeight"), max_height)
        page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": 900, "height": height}, full_page=True)
        b.close()


# ---------------------------------------------------------------- render ---
def grab(page, tries: int = 3) -> bytes:
    """Screenshot one frame; retry if headless Chrome stalls for a moment."""
    for attempt in range(tries):
        try:
            return page.screenshot(type="jpeg", quality=92, timeout=15000)
        except Exception:
            if attempt == tries - 1:
                raise
            page.wait_for_timeout(500)

def pick_music(seed: str):
    tracks = sorted(p for p in AUDIO_DIR.iterdir() if p.suffix in (".mp3", ".m4a", ".wav", ".aac"))
    return random.Random(seed).choice(tracks) if tracks else None


def render(spec: dict, out_mp4: Path, lufs: float = None):
    style = spec["style"]
    cfg = json.loads((REEL_DIR / f"{style}.json").read_text())
    if lufs is not None:
        cfg["voice_lufs"] = lufs
    html = REEL_DIR / f"{style}.html"
    out_mp4.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # 1. Voice clips
        # `voice_tts` = what is spoken (Devanagari Hinglish for Kokoro);
        # `voice` = Roman Hinglish used for captions.
        clips = [tmp / f"v{i:02d}.wav" for i in range(len(spec["scenes"]))]
        durs = tts_batch([sc.get("voice_tts") or sc["voice"] for sc in spec["scenes"]], clips)

        # 2. Timeline + voice track
        tl = make_timeline(durs, cfg)
        voice = tmp / "voice.wav"
        build_voice_track(clips, [s["start"] for s in tl["scenes"]], tl["total"], voice)
        print(f"  timeline: {len(clips)} scenes, {tl['total']:.1f}s")

        # Optional site capture for tool demos (served as a local file to the page).
        if style == "tool_demo":
            shot = tmp / "site.png"
            capture_site(spec["site_url"], shot)
            spec = {**spec, "site_image": shot.as_uri()}

        # 3 + 4. Frames -> FFmpeg (video only, encoded on the fly)
        silent = tmp / "video.mp4"
        n_frames = int(round(tl["total"] * tl["fps"]))
        ff = subprocess.Popen([
            "ffmpeg", "-y", "-v", "error",
            "-f", "image2pipe", "-framerate", str(tl["fps"]), "-c:v", "mjpeg", "-i", "-",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-profile:v", "high",
            # JPEG frames are full-range; convert to standard TV-range yuv420p for Instagram.
            "-vf", "scale=in_range=full:out_range=tv,format=yuv420p", "-color_range", "tv",
            "-r", str(tl["fps"]), str(silent)], stdin=subprocess.PIPE)
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--allow-file-access-from-files"])
            page = b.new_page(viewport={"width": W, "height": H})
            page.goto(html.as_uri())
            page.evaluate("([s, t]) => window.setup(s, t)", [spec, tl])
            for f in range(n_frames):
                page.evaluate(f"window.seek({f / tl['fps']:.4f})")
                ff.stdin.write(grab(page))
                if f % (tl["fps"] * 5) == 0:
                    print(f"  frames {f}/{n_frames}", end="\r", flush=True)
            b.close()
        ff.stdin.close()
        if ff.wait() != 0:
            sys.exit("FFmpeg video encode failed")

        # 5. Mux: loud, punchy voice + low music bed, fade music at the end.
        #    Voice: compressor (evens out quiet syllables) then loudness-normalised
        #    to -14 LUFS, the level Instagram/YouTube play at, so it sounds loud.
        voice_fx = (f"aresample=44100,pan=stereo|c0=c0|c1=c0,"
                    f"acompressor=threshold=-22dB:ratio=3:attack=5:release=80:makeup=3,"
                    f"loudnorm=I={cfg['voice_lufs']}:TP=-1.5:LRA=7,aresample=44100")
        music = pick_music(spec.get("id", "x"))
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(silent), "-i", str(voice)]
        if music:
            fade_at = max(tl["total"] - 1.5, 0)
            cmd += ["-stream_loop", "-1", "-i", str(music), "-filter_complex",
                    f"[1:a]{voice_fx}[v];"
                    f"[2:a]aresample=44100,volume={cfg['music_volume']},afade=t=out:st={fade_at}:d=1.5[m];"
                    f"[v][m]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]",
                    "-map", "0:v", "-map", "[a]"]
        else:
            cmd += ["-filter_complex", f"[1:a]{voice_fx},alimiter=limit=0.95[a]", "-map", "0:v", "-map", "[a]"]
        cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
                "-t", str(tl["total"]), "-movflags", "+faststart", str(out_mp4)]
        subprocess.run(cmd, check=True)
    print(f"  done: {out_mp4}  ({tl['total']:.1f}s, music: {music.name if music else 'none'})")
    return tl


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("out")
    # Optional one-off overrides (default: values from config.yaml / style json)
    ap.add_argument("--voice", help="Kokoro voice, e.g. hf_alpha, hm_psi")
    ap.add_argument("--speed", type=float, help="speech speed, e.g. 1.35")
    ap.add_argument("--lufs", type=float, help="voice loudness target, e.g. -12")
    a = ap.parse_args()
    if a.voice: TTS["voice"] = a.voice
    if a.speed: TTS["speed"] = a.speed
    render(json.loads(Path(a.spec).read_text()), Path(a.out), lufs=a.lufs)
