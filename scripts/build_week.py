"""Build a week's queue from a plan file written by /weekly.

Plan file: content/plan/week_YYYY-MM-DD.json
{
  "week_start": "2026-11-26",                 # first publish day (IST)
  "items": [
    { "day": 1, "type": "reel" | "carousel",
      "series": "Pandit ji ka Tool", "topic": "Perplexity: cited answers",
      "hook": "...", "caption": "...", "hashtags": ["#aitools", ...],
      "sources": ["https://..."],
      "spec": { ...reel or carousel spec... } }
  ]
}

What it does:
  1. Validates the plan (7 reels + 7 carousels, 5-8 hashtags, 7-9 slides,
     no topic already in data/history.json).
  2. Renders every item into content/queue/<date>_<type>_<slug>/.
  3. Runs technical QA on each item. Stops on failures.
  4. Writes content/queue/schedule.json (reel 13:00 IST, carousel 19:30 IST).
  5. Adds the topics to data/history.json so they're never repeated.

Usage:
  .venv/bin/python scripts/build_week.py content/plan/week_2026-11-26.json
  ... --only 2026-11-27_reel        re-render one item
  ... --validate                    check the plan only, no rendering
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from render_carousel import render as render_carousel  # noqa: E402
from render_reel import render as render_reel  # noqa: E402

CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text())
QUEUE = ROOT / "content" / "queue"
HISTORY = ROOT / "data" / "history.json"
IST = timezone(timedelta(hours=5, minutes=30))
CTA = CONFIG["account"]["cta"]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def norm(topic: str) -> str:
    """Topic key used for the never-repeat check."""
    return re.sub(r"[^a-z0-9 ]", "", topic.lower()).strip()


# ------------------------------------------------------------ validation ---
def validate(plan: dict) -> list:
    errors = []
    items = plan["items"]
    history = {norm(h["topic"]) for h in json.loads(HISTORY.read_text())}
    for kind in ("reel", "carousel"):
        days = sorted(i["day"] for i in items if i["type"] == kind)
        if days != list(range(1, 8)):
            errors.append(f"need one {kind} for each day 1-7, got days {days}")
    seen = set()
    for it in items:
        tag = f"day {it['day']} {it['type']}"
        key = norm(it["topic"])
        if key in history:
            errors.append(f"{tag}: topic already used before: {it['topic']}")
        if key in seen:
            errors.append(f"{tag}: duplicate topic this week: {it['topic']}")
        seen.add(key)
        if not 5 <= len(it["hashtags"]) <= 8:
            errors.append(f"{tag}: needs 5-8 hashtags, has {len(it['hashtags'])}")
        if not it.get("sources"):
            errors.append(f"{tag}: no source URLs")
        if len(full_caption(it)) > 2200:
            errors.append(f"{tag}: caption over 2200 characters")
        spec = it["spec"]
        if it["type"] == "carousel":
            n = len(spec["slides"]) + (0 if spec["slides"][-1]["type"] == "cta" else 1)
            if not 7 <= n <= 9:
                errors.append(f"{tag}: needs 7-9 slides incl. CTA, has {n}")
        else:
            if spec["style"] not in ("kinetic", "comparison", "tool_demo"):
                errors.append(f"{tag}: unknown reel style {spec['style']}")
            words = sum(len(s["voice"].split()) for s in spec["scenes"])
            if not 45 <= words <= 110:   # ~20-40 s at our voice speed
                errors.append(f"{tag}: script has {words} words, aim for 45-110")
    return errors


def full_caption(it: dict) -> str:
    """Final caption: text + CTA + source line (tool posts) + hashtags."""
    parts = [it["caption"].strip()]
    if CTA.lower() not in it["caption"].lower():
        parts.append(CTA)
    if it["series"] == "Pandit ji ka Tool":
        hosts = sorted({re.sub(r"^www\.", "", s.split("/")[2]) for s in it["sources"]})
        parts.append("Source: " + ", ".join(hosts) + " (official site)")
    parts.append(" ".join(it["hashtags"]))
    return "\n\n".join(parts)


# -------------------------------------------------------------- building ---
def publish_time(week_start: date, day: int, kind: str) -> datetime:
    hh, mm = map(int, CONFIG["slots"][kind].split(":"))
    d = week_start + timedelta(days=day - 1)
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=IST)


def qa(kind: str, target: Path) -> bool:
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "qa.py"), kind, str(target)],
                       capture_output=True, text=True)
    print(r.stdout.rstrip())
    return r.returncode == 0


def build_item(it: dict, week_start: date) -> dict:
    when = publish_time(week_start, it["day"], it["type"])
    item_id = f"{when:%Y-%m-%d}_{it['type']}_{slug(it['topic'])}"
    out = QUEUE / item_id
    out.mkdir(parents=True, exist_ok=True)
    print(f"\n== {item_id}")
    if it["type"] == "reel":
        spec = {**it["spec"], "id": item_id, "series": it["series"]}
        render_reel(spec, out / "reel.mp4")
        files, ok = ["reel.mp4"], qa("reel", out / "reel.mp4")
    else:
        spec = {**it["spec"], "id": item_id, "series": it["series"]}
        paths = render_carousel(spec, out)
        files, ok = [p.name for p in paths], qa("carousel", out)
    meta = {
        "id": item_id, "type": it["type"], "series": it["series"], "topic": it["topic"],
        "hook": it["hook"], "caption": full_caption(it), "sources": it["sources"],
        "files": [f"content/queue/{item_id}/{f}" for f in files],
        "publish_at_ist": when.isoformat(), "publish_at_utc": when.astimezone(timezone.utc).isoformat(),
        "qa_passed": ok,
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    (out / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2))
    return meta


def write_schedule():
    """Rebuild schedule.json from every meta.json in the queue."""
    metas = [json.loads(p.read_text()) for p in sorted(QUEUE.glob("*/meta.json"))]
    metas.sort(key=lambda m: m["publish_at_utc"])
    schedule = {"items": [{k: m[k] for k in ("id", "type", "publish_at_ist", "publish_at_utc",
                                              "files", "caption", "qa_passed")} | {"status": "queued"}
                          for m in metas]}
    (QUEUE / "schedule.json").write_text(json.dumps(schedule, ensure_ascii=False, indent=2))
    return metas


def add_history(plan: dict, metas: list):
    history = json.loads(HISTORY.read_text())
    known = {h["id"] for h in history}
    by_topic = {m["topic"]: m for m in metas}
    for it in plan["items"]:
        m = by_topic.get(it["topic"])
        if m and m["id"] not in known:
            history.append({"id": m["id"], "type": it["type"], "series": it["series"], "topic": it["topic"],
                            "hook": it["hook"], "style": it["spec"].get("style", "carousel"),
                            "planned_for": m["publish_at_ist"]})
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2))


def summary(metas: list):
    print(f"\n{'Date (IST)':17} {'Format':9} {'Series':22} {'Topic':40} QA")
    for m in metas:
        t = datetime.fromisoformat(m["publish_at_ist"])
        print(f"{t:%a %d %b %H:%M}  {m['type']:9} {m['series']:22} {m['topic'][:40]:40} {'ok' if m['qa_passed'] else 'FAIL'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--only", help="re-render items whose id starts with this")
    ap.add_argument("--validate", action="store_true")
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text())
    week_start = date.fromisoformat(plan["week_start"])

    errors = [] if a.only else validate(plan)
    if errors:
        print("Plan problems:\n  " + "\n  ".join(errors))
        sys.exit(1)
    if a.validate:
        print("Plan OK")
        sys.exit(0)

    for it in sorted(plan["items"], key=lambda i: (i["day"], i["type"])):
        prefix = f"{publish_time(week_start, it['day'], it['type']):%Y-%m-%d}_{it['type']}"
        if a.only and not prefix.startswith(a.only):
            continue
        build_item(it, week_start)

    metas = write_schedule()
    if not a.only:
        add_history(plan, metas)
    summary(metas)
    if not all(m["qa_passed"] for m in metas):
        print("\nSome items FAILED QA. Fix and re-run with --only.")
        sys.exit(1)
