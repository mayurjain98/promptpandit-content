"""Publish due items from content/queue/schedule.json to Instagram.

Runs in GitHub Actions (publish.yml) at the configured IST slots.

Rules
  * data/pause.flag exists        -> do nothing
  * an item is due when publish_at_utc <= now and it is not already in
    data/publish_log.json as "published"  (never publish twice)
  * Reel:     create REELS container -> poll until FINISHED -> publish
  * Carousel: create one child container per slide -> CAROUSEL container
              -> poll until FINISHED -> publish
  * Only container creation is retried. The publish call itself is never
    retried: if it errors, we check the account's latest posts to see
    whether it actually went live, and log that.
  * After publishing: log id, permalink, time; move the folder to
    content/published/.
  * Two consecutive failed runs -> open a GitHub Issue (you get an email).

Env: IG_ACCESS_TOKEN, IG_USER_ID, (in Actions) GITHUB_TOKEN, GITHUB_REPOSITORY

Usage:
  python scripts/publish.py                 publish everything that's due (max 2 per run)
  python scripts/publish.py --dry-run --id ITEM_ID
        create containers and wait for FINISHED, but DON'T publish (safe test)
"""
import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text())
SCHEDULE = ROOT / "content" / "queue" / "schedule.json"
LOG = ROOT / "data" / "publish_log.json"
PAUSE = ROOT / "data" / "pause.flag"
PUBLISHED_DIR = ROOT / "content" / "published"

API = f"https://graph.facebook.com/{os.getenv('IG_API_VERSION', 'v24.0')}"
TOKEN = os.getenv("IG_ACCESS_TOKEN", "")
IG_ID = os.getenv("IG_USER_ID", "")
MEDIA_BASE = CONFIG["media"]["raw_base"].rstrip("/")
MAX_PER_RUN = 2


class IGError(Exception):
    pass


# ------------------------------------------------------------------ API ----
def call(method, path, **params):
    """One Graph API call. Raises IGError with Meta's message (never the token)."""
    params["access_token"] = TOKEN
    r = requests.request(method, f"{API}/{path}", data=params if method == "POST" else None,
                         params=params if method == "GET" else None, timeout=60)
    data = r.json() if r.content else {}
    if r.status_code != 200 or "error" in data:
        err = data.get("error", {})
        raise IGError(f"{err.get('message', r.text[:200])} (code {err.get('code')}, subcode {err.get('error_subcode')})")
    return data


def create_container(retries=3, **params) -> str:
    """Create a media container. This is the only step we retry."""
    for attempt in range(1, retries + 1):
        try:
            return call("POST", f"{IG_ID}/media", **params)["id"]
        except (IGError, requests.RequestException) as e:
            print(f"    container attempt {attempt}/{retries} failed: {e}")
            if attempt == retries:
                raise
            time.sleep(15 * attempt)


def wait_finished(container_id: str, timeout_s=600):
    """Poll until Meta has fetched and processed the media."""
    start = time.time()
    while time.time() - start < timeout_s:
        st = call("GET", container_id, fields="status_code,status")
        code = st.get("status_code")
        print(f"    status: {code}")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise IGError(f"container {code}: {st.get('status')}")
        time.sleep(10)
    raise IGError("timed out waiting for container to finish processing")


def latest_post_matching(caption: str):
    """Used after an uncertain publish call: did it actually go live?"""
    media = call("GET", f"{IG_ID}/media", fields="id,caption,permalink,timestamp", limit=5)["data"]
    head = caption[:80]
    return next((m for m in media if (m.get("caption") or "").startswith(head)), None)


def publish_container(container_id: str, caption: str) -> dict:
    """Publish once. Never retried: on error, check whether it went live anyway."""
    try:
        media_id = call("POST", f"{IG_ID}/media_publish", creation_id=container_id)["id"]
    except (IGError, requests.RequestException) as e:
        print(f"    publish call errored ({e}); checking whether the post went live...")
        time.sleep(20)
        found = latest_post_matching(caption)
        if not found:
            raise
        return {"media_id": found["id"], "permalink": found.get("permalink")}
    info = call("GET", media_id, fields="permalink")
    return {"media_id": media_id, "permalink": info.get("permalink")}


# ------------------------------------------------------------ per item ----
def url_for(rel_path: str) -> str:
    return f"{MEDIA_BASE}/{rel_path}"


def build_container(item: dict) -> str:
    if item["type"] == "reel":
        print("  creating REELS container")
        cid = create_container(media_type="REELS", video_url=url_for(item["files"][0]),
                               caption=item["caption"], share_to_feed="true")
    else:
        children = []
        for f in item["files"]:
            print(f"  child container: {Path(f).name}")
            children.append(create_container(image_url=url_for(f), is_carousel_item="true"))
        for c in children:
            wait_finished(c, timeout_s=180)
        print("  creating CAROUSEL container")
        cid = create_container(media_type="CAROUSEL", children=",".join(children), caption=item["caption"])
    wait_finished(cid)
    return cid


# ------------------------------------------------------------- logging ----
def load_json(p: Path, default):
    return json.loads(p.read_text()) if p.exists() else default


def save_json(p: Path, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def move_to_published(item_id: str):
    src = ROOT / "content" / "queue" / item_id
    if src.exists():
        PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(PUBLISHED_DIR / item_id))


def open_issue(title: str, body: str):
    repo, gh_token = os.getenv("GITHUB_REPOSITORY"), os.getenv("GITHUB_TOKEN")
    if not (repo and gh_token):
        print("  (no GITHUB_TOKEN; would open issue:", title, ")")
        return
    r = requests.post(f"https://api.github.com/repos/{repo}/issues",
                      headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"},
                      json={"title": title, "body": body, "labels": ["publish-failure"]}, timeout=30)
    print(f"  opened GitHub issue: HTTP {r.status_code}")


# ---------------------------------------------------------------- main ----
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="create containers, don't publish")
    ap.add_argument("--id", help="only this item (ignores its time)")
    a = ap.parse_args()

    if PAUSE.exists():
        print("pause.flag found: skipping.")
        return 0
    if not (TOKEN and IG_ID):
        print("IG_ACCESS_TOKEN / IG_USER_ID missing.")
        return 1

    schedule = load_json(SCHEDULE, {"items": []})
    log = load_json(LOG, [])
    done = {e["id"] for e in log if e.get("status") == "published"}
    now = datetime.now(timezone.utc)

    if a.id:
        due = [i for i in schedule["items"] if i["id"] == a.id]
    else:
        due = [i for i in schedule["items"]
               if i.get("status") == "queued" and i["id"] not in done
               and datetime.fromisoformat(i["publish_at_utc"]) <= now]
    due.sort(key=lambda i: i["publish_at_utc"])
    if not due:
        print("Nothing due.")
        return 0

    failures = 0
    for item in due[:MAX_PER_RUN]:
        if item["id"] in done:
            print(f"{item['id']}: already published, skipping.")
            continue
        if not item.get("qa_passed", False):
            print(f"{item['id']}: QA did not pass, skipping.")
            continue
        print(f"\n== {item['id']} ({item['type']}){'  [DRY RUN]' if a.dry_run else ''}")
        entry = {"id": item["id"], "type": item["type"], "time_utc": now.isoformat()}
        try:
            cid = build_container(item)
            if a.dry_run:
                print(f"  DRY RUN OK: container {cid} is FINISHED. Not published.")
                continue
            res = publish_container(cid, item["caption"])
            entry |= {"status": "published", **res, "published_at": datetime.now(timezone.utc).isoformat()}
            item["status"] = "published"
            item["permalink"] = res.get("permalink")
            print(f"  PUBLISHED: {res.get('permalink')}")
            move_to_published(item["id"])
            item["files"] = [f.replace("content/queue/", "content/published/", 1) for f in item["files"]]
        except Exception as e:  # log any failure, keep going
            failures += 1
            entry |= {"status": "failed", "error": str(e)[:500]}
            item["fail_count"] = item.get("fail_count", 0) + 1
            if item["fail_count"] >= 3:
                item["status"] = "failed"   # stop retrying this one
            print(f"  FAILED: {e}")
        if not a.dry_run:
            log.append(entry)

    if not a.dry_run:
        save_json(LOG, log)
        save_json(SCHEDULE, schedule)
        # Alert on 2 consecutive failures (only once, when the streak hits 2).
        recent = [e["status"] for e in log[-3:]]
        if recent[-2:] == ["failed", "failed"] and (len(recent) < 3 or recent[-3] != "failed"):
            last = log[-1]
            open_issue("Instagram publishing failed twice in a row",
                       f"Last item: `{last['id']}`\n\nError: {last.get('error')}\n\n"
                       "Check the Actions log. To pause publishing, add `data/pause.flag`.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
