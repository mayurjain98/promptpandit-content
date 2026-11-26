# Prompt Pandit: automated Instagram content

Zero-cost system for **@promptpandit.in**: 1 Reel + 1 carousel a day on AI tools and prompts for Indian students and job seekers.
Claude Code writes and renders the week on your Mac, and GitHub Actions publishes it, tracks insights and maintains the repo.

## Your weekly routine
1. Open this folder in Claude Code and type `/weekly`.
2. Review the summary table and sample Reels and slides; ask for any changes.
3. Say **go**. Claude commits and pushes the week.
4. Do nothing else: posts go out at 13:00 IST (Reel) and 19:30 IST (carousel).
5. To pause, add an empty `data/pause.flag` and push. Delete it to resume.

## How it works
| When | Where | What |
|---|---|---|
| Weekly (you) | Mac, `/weekly` | research → write → fact-check → render → QA → `content/queue/schedule.json` |
| Every 20 min, 12:40–23:20 IST | `publish.yml` | posts due items (never twice), logs to `data/publish_log.json`, moves files to `content/published/` |
| 13:01 / 19:31 IST | backup trigger (cron-job.org) | starts `publish.yml` on time in case GitHub's own schedule is late |
| Daily 00:00 IST | `insights.yml` | 24-hour and 7-day metrics → `data/insights.json` (used by the next `/weekly`); Issue if a post is 2+ h overdue |
| Mondays | `token.yml` | checks the IG token; opens an Issue if something's wrong |
| 1st of month | `cleanup.yml` | deletes media files of posts older than 30 days (logs kept) |

Two failed publishing runs in a row open a GitHub Issue, and GitHub emails you about it.

## Backup trigger
GitHub's scheduled runs are best-effort (they can be hours late or skipped), so an outside scheduler also starts the publisher.
1. GitHub → Settings → Developer settings → Fine-grained tokens → **Generate**. Repository access: only `promptpandit-content`.
   Permissions: **Actions: Read and write** (nothing else). Note its expiry date and renew it before then.
2. On [cron-job.org](https://cron-job.org) (free), create two jobs, timezone **Asia/Kolkata**, at **13:01** and **19:31** daily:
   - URL: `https://api.github.com/repos/mayurjain98/promptpandit-content/actions/workflows/publish.yml/dispatches`
   - Method **POST**. Headers: `Authorization: Bearer <your token>`, `Accept: application/vnd.github+json`, `Content-Type: application/json`
   - Body: `{"ref":"main","inputs":{"dry_run":"false"}}`
3. "Test run" should return **HTTP 204**, and a Publish run appears in the Actions tab. If nothing is due, it just says "Nothing due".

The token lives only at cron-job.org; never put it in this repo. If it leaks, delete it on GitHub: it can only start workflows in this repo.

## Setup (already done once)
- **Local tools:** Python 3 + `.venv` (`pip install -r requirements.txt`, `playwright install chromium`), FFmpeg,
  `.venv-tts` (Python 3.12 via `uv`, `pip install -r requirements-tts.txt`).
  Models go in `models/` (git-ignored): Kokoro `kokoro-v1.0.onnx` + `voices-v1.0.bin`, and a Piper fallback voice.
- **Instagram:** Creator account, linked to the "Prompt Pandit" Meta business portfolio. Meta app "Prompt Pandit Publisher"
  (Instagram API, Unified login). System user `pp-publisher` has full access to the app and the IG account, and its token never expires.
- **Secrets:** `IG_ACCESS_TOKEN`, `IG_USER_ID` in GitHub repo secrets, plus a local `.env` (git-ignored; see `.env.example`).
  The API host is `graph.facebook.com`. There's no paid API usage and no `ANTHROPIC_API_KEY`.
- **Media hosting:** this public repo, served from `raw.githubusercontent.com`.

## Useful commands
```bash
.venv/bin/python scripts/ig_check.py                                   # is the token working?
.venv/bin/python scripts/render_reel.py SPEC.json out.mp4 [--voice hm_psi --speed 1.35 --lufs -12]
.venv/bin/python scripts/render_carousel.py SPEC.json out_dir/
.venv/bin/python scripts/build_week.py content/plan/week_DATE.json [--validate | --only DATE_reel]
.venv/bin/python scripts/qa.py reel FILE.mp4      # or: qa.py carousel DIR
```
Manual publish test (no posting): Actions → **Publish** → Run workflow → dry run ✔ + item id.

## Brand
Black with a radial spotlight (#262626 → #000), lime gradient (#EAFF7A / #C6FF00 / #8FC400), white text,
Poppins Bold for headings and Inter for body text, watermark at bottom-right (8% of the width). Shared styles: `templates/brand/brand.css`.
Voice: Kokoro `hm_psi` (Hindi male, Apache-2.0), 1.35× speed, about −12 LUFS; settings are in `config.yaml`.
Music: original synth bed in `templates/audio/`. Add any royalty-free track there to rotate it in.
