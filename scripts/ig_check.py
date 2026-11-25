"""Phase 0 check: confirm the token works and find the Instagram user ID.

Our token is a Meta *system-user* token (Unified login, never expires).
It may work on either API host, so we try both:
  1. graph.instagram.com/me                  (Instagram-login style)
  2. graph.facebook.com  -> business -> IG    (Facebook-login style)

Reads IG_ACCESS_TOKEN (and optional IG_USER_ID) from env or .env.
Never prints the token.

Usage:  .venv/bin/python scripts/ig_check.py
"""
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

VER = os.getenv("IG_API_VERSION", "v24.0")
IG_HOST = f"https://graph.instagram.com/{VER}"
FB_HOST = f"https://graph.facebook.com/{VER}"
FIELDS = "username,name,account_type,followers_count,media_count"


def get(url, token, **params):
    """GET helper. Returns (ok, json). Errors from Meta never echo the token."""
    params["access_token"] = token
    r = requests.get(url, params=params, timeout=30)
    try:
        data = r.json()
    except ValueError:
        data = {"error": r.text[:200]}
    return r.status_code == 200 and "error" not in data, data


def try_instagram_host(token):
    ok, data = get(f"{IG_HOST}/me", token, fields="user_id," + FIELDS)
    if ok:
        return "graph.instagram.com", str(data.get("user_id") or data.get("id")), data
    print("  graph.instagram.com:", data.get("error", {}).get("message", data))
    return None


def try_facebook_host(token, ig_id=None):
    # If we already know the IG user ID, just read it.
    if ig_id:
        ok, data = get(f"{FB_HOST}/{ig_id}", token, fields="id,username,name,followers_count,media_count")  # account_type is IG-host only
        if ok:
            return "graph.facebook.com", str(data["id"]), data
        print("  graph.facebook.com:", data.get("error", {}).get("message", data))
        return None

    # Otherwise walk: system user -> businesses -> Instagram accounts.
    ok, biz = get(f"{FB_HOST}/me/businesses", token, fields="id,name")
    if not ok:
        print("  graph.facebook.com /me/businesses:", biz.get("error", {}).get("message", biz))
        return None
    for b in biz.get("data", []):
        for edge in ("owned_instagram_accounts", "instagram_accounts"):
            ok, accts = get(f"{FB_HOST}/{b['id']}/{edge}", token, fields="id,username")
            if ok and accts.get("data"):
                ig = accts["data"][0]
                return try_facebook_host(token, ig["id"])
    print("  graph.facebook.com: no Instagram account found via business portfolio")
    return None


def main() -> int:
    token = os.getenv("IG_ACCESS_TOKEN")
    if not token:
        print("IG_ACCESS_TOKEN is not set (.env or environment).")
        return 1
    known_id = os.getenv("IG_USER_ID") or None

    print("Trying API hosts...")
    result = try_instagram_host(token) or try_facebook_host(token, known_id)
    if not result:
        print("\nCould not read the account with this token.")
        return 1

    host, ig_id, data = result
    print(f"\nConnected to Instagram via {host}")
    for key in ("username", "name", "account_type", "followers_count", "media_count"):
        if key in data:
            print(f"  {key:16} {data[key]}")
    print(f"  {'IG_USER_ID':16} {ig_id}")

    if known_id and known_id != ig_id:
        print(f"WARNING: IG_USER_ID in .env ({known_id}) differs from {ig_id}.")
    elif not known_id:
        print("\nAdd this to .env:  IG_USER_ID=" + ig_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
