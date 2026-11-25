"""Kokoro TTS worker (runs in .venv-tts, Python 3.12).

Kokoro is free and Apache-2.0 licensed (commercial use OK). Its Hindi voices
read Devanagari Hinglish naturally, e.g. "ये प्रॉम्प्ट ट्राई किया?".

render_reel.py calls this once per Reel and passes all lines as JSON on
stdin, so the model loads only once:
  [{"text": "...", "out": "/tmp/v00.wav"}, ...]
Prints each clip's duration (seconds) as a JSON list.

Usage (manual test):
  echo '[{"text":"नमस्ते","out":"t.wav"}]' | .venv-tts/bin/python scripts/tts_kokoro.py --voice hf_alpha --speed 1.2
"""
import argparse
import json
import sys
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "kokoro" / "kokoro-v1.0.onnx"
VOICES = ROOT / "models" / "kokoro" / "voices-v1.0.bin"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="hf_alpha")
    ap.add_argument("--speed", type=float, default=1.2)
    ap.add_argument("--lang", default="hi")
    a = ap.parse_args()

    jobs = json.load(sys.stdin)
    k = Kokoro(str(MODEL), str(VOICES))
    durations = []
    for job in jobs:
        audio, sr = k.create(job["text"], voice=a.voice, speed=a.speed, lang=a.lang)
        # 16-bit PCM so Python's wave module can read it in the renderer.
        sf.write(job["out"], audio, sr, subtype="PCM_16")
        durations.append(round(len(audio) / sr, 3))
    print(json.dumps(durations))


if __name__ == "__main__":
    main()
