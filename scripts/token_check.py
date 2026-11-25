"""Weekly token health check (token.yml).

Our IG_ACCESS_TOKEN is a Meta *system-user* token that never expires, so
there is nothing to refresh. Instead we check every week that it is still
valid and still has the publish and insights permissions. If not (for example
it was revoked or permissions changed), we open a GitHub Issue, so you get an
email before posting stops.

Env: IG_ACCESS_TOKEN, IG_USER_ID, (Actions) GITHUB_TOKEN, GITHUB_REPOSITORY
"""
import os
import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(__file__))
from publish import open_issue  # noqa: E402

API = f"https://graph.facebook.com/{os.getenv('IG_API_VERSION', 'v24.0')}"
TOKEN = os.getenv("IG_ACCESS_TOKEN", "")
IG_ID = os.getenv("IG_USER_ID", "")
NEEDED = {"instagram_basic", "instagram_content_publish", "instagram_manage_insights"}


def main() -> int:
    problems = []
    dbg = requests.get(f"{API}/debug_token", params={"input_token": TOKEN, "access_token": TOKEN}, timeout=30).json()
    d = dbg.get("data", {})
    if not d.get("is_valid"):
        problems.append(f"Token is not valid: {d.get('error', dbg.get('error'))}")
    else:
        exp = d.get("expires_at", 0)
        print(f"valid: yes | type: {d.get('type')} | expires: {'never' if not exp else datetime.fromtimestamp(exp, timezone.utc)}")
        missing = NEEDED - set(d.get("scopes", []))
        if missing:
            problems.append(f"Token is missing permissions: {', '.join(sorted(missing))}")
        if exp and (exp - datetime.now(timezone.utc).timestamp()) < 14 * 86400:
            problems.append("Token expires within 14 days. Generate a new one and update the IG_ACCESS_TOKEN secret.")

    acct = requests.get(f"{API}/{IG_ID}", params={"fields": "username", "access_token": TOKEN}, timeout=30).json()
    if "error" in acct:
        problems.append(f"Cannot read the Instagram account: {acct['error'].get('message')}")
    else:
        print(f"account: @{acct.get('username')}")

    if problems:
        print("PROBLEMS:\n  " + "\n  ".join(problems))
        open_issue("Instagram token needs attention",
                   "\n".join(f"- {p}" for p in problems) +
                   "\n\nFix: Business Settings > System users > pp-publisher > Generate token, "
                   "then update the `IG_ACCESS_TOKEN` repo secret.")
        return 1
    print("Token OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
