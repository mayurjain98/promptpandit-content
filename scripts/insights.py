"""Fetch post metrics into data/insights.json (runs daily in insights.yml).

For every published post (from data/publish_log.json) we save two snapshots:
  "24h"  first run at least 24 hours after publishing
  "7d"   first run at least 7 days after publishing
Metrics: reach, views, likes, comments, saved, shares, follows, plus total
interactions and (for Reels) average watch time, where Instagram provides them.
Meta doesn't offer every metric for every media type, so unsupported metrics
are skipped.

/weekly reads this file to favour the formats, hooks and topics that work.

Usage:
  python scripts/insights.py            normal daily run
  python scripts/insights.py --now      also take a "latest" snapshot of every post (testing)
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "publish_log.json"
HISTORY = ROOT / "data" / "history.json"
OUT = ROOT / "data" / "insights.json"
API = f"https://graph.facebook.com/{os.getenv('IG_API_VERSION', 'v24.0')}"
TOKEN = os.getenv("IG_ACCESS_TOKEN", "")

METRICS = {
    "reel": ["reach", "views", "likes", "comments", "saved", "shares", "total_interactions",
             "ig_reels_avg_watch_time", "follows"],
    "carousel": ["reach", "views", "likes", "comments", "saved", "shares", "total_interactions",
                 "follows", "profile_visits"],
}
WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7)}


def get_insights(media_id: str, metrics: list) -> dict:
    """Ask for all metrics at once; if Meta rejects one, fall back to one at a time."""
    def ask(ms):
        r = requests.get(f"{API}/{media_id}/insights",
                         params={"metric": ",".join(ms), "access_token": TOKEN}, timeout=30)
        d = r.json()
        if "error" in d:
            raise ValueError(d["error"].get("message"))
        return {m["name"]: (m.get("values") or [{}])[0].get("value", m.get("total_value", {}).get("value"))
                for m in d.get("data", [])}
    try:
        return ask(metrics)
    except ValueError:
        out = {}
        for m in metrics:
            try:
                out |= ask([m])
            except ValueError:
                pass   # not available for this media type
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", action="store_true", help="also save a 'latest' snapshot (testing)")
    a = ap.parse_args()
    if not TOKEN:
        sys.exit("IG_ACCESS_TOKEN missing")

    log = json.loads(LOG.read_text()) if LOG.exists() else []
    data = json.loads(OUT.read_text()) if OUT.exists() and OUT.read_text().strip() else {}
    if isinstance(data, list) or "posts" not in data:
        data = {"posts": {}}
    hist = {h["id"]: h for h in (json.loads(HISTORY.read_text()) if HISTORY.exists() else [])}
    now = datetime.now(timezone.utc)

    for e in log:
        if e.get("status") != "published":
            continue
        post = data["posts"].setdefault(e["id"], {
            "media_id": e["media_id"], "type": e["type"], "permalink": e.get("permalink"),
            "published_at": e["published_at"],
            # copied from history so /weekly can compare series / style / hook
            **{k: hist.get(e["id"], {}).get(k) for k in ("series", "topic", "hook", "style")},
            "snapshots": {},
        })
        age = now - datetime.fromisoformat(e["published_at"])
        todo = [w for w, d in WINDOWS.items() if age >= d and w not in post["snapshots"]]
        if a.now:
            todo.append("latest")
        for w in todo:
            m = get_insights(e["media_id"], METRICS[e["type"]])
            m["fetched_at"] = now.isoformat()
            m["age_hours"] = round(age.total_seconds() / 3600, 1)
            post["snapshots"][w] = m
            print(f"{e['id']} [{w}] {m}")

    data["updated_at"] = now.isoformat()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"insights.json: {len(data['posts'])} posts")


if __name__ == "__main__":
    main()
