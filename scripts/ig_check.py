"""Phase 0 check: read the Instagram account behind IG_ACCESS_TOKEN.

Reads IG_ACCESS_TOKEN (and optional IG_USER_ID) from the environment or a
local .env file. Never prints the token.

Usage:  .venv/bin/python scripts/ig_check.py
"""
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

API_VERSION = os.getenv("IG_API_VERSION", "v24.0")
BASE = f"https://graph.instagram.com/{API_VERSION}"


def main() -> int:
    token = os.getenv("IG_ACCESS_TOKEN")
    if not token:
        print("IG_ACCESS_TOKEN is not set (.env or environment).")
        return 1

    # /me returns the account the token belongs to.
    resp = requests.get(
        f"{BASE}/me",
        params={
            "fields": "user_id,username,name,account_type,followers_count,media_count",
            "access_token": token,
        },
        timeout=30,
    )
    data = resp.json()
    if resp.status_code != 200:
        # Error messages from Meta never contain the token itself.
        print("API error:", data.get("error", data))
        return 1

    print("Connected to Instagram")
    for key in ("username", "name", "account_type", "user_id", "followers_count", "media_count"):
        print(f"  {key:16} {data.get(key)}")

    expected_id = os.getenv("IG_USER_ID")
    if expected_id and expected_id != str(data.get("user_id")):
        print(f"WARNING: IG_USER_ID in .env ({expected_id}) does not match the token's user_id.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
