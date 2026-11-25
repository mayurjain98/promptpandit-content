"""Monthly cleanup (cleanup.yml): delete media of posts published more than
30 days ago. meta.json and spec.json stay, and so do all logs in data/.

Instagram keeps its own copy once a post is published, so the repo copy
is only needed until then.

Usage:  python scripts/cleanup.py [--days 30] [--dry-run]
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "publish_log.json"
PUBLISHED = ROOT / "content" / "published"
MEDIA = {".mp4", ".jpg", ".jpeg", ".png"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cutoff = datetime.now(timezone.utc) - timedelta(days=a.days)
    log = json.loads(LOG.read_text()) if LOG.exists() else []
    freed = 0
    for e in log:
        if e.get("status") != "published" or datetime.fromisoformat(e["published_at"]) > cutoff:
            continue
        folder = PUBLISHED / e["id"]
        for f in folder.glob("*"):
            if f.suffix.lower() in MEDIA:
                freed += f.stat().st_size
                print(("would delete " if a.dry_run else "delete ") + str(f.relative_to(ROOT)))
                if not a.dry_run:
                    f.unlink()
    print(f"{'Would free' if a.dry_run else 'Freed'} {freed / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
