---
description: Plan, write, fact-check, render and queue next week's 7 Reels + 7 carousels
---

You are producing next week's content for **@promptpandit.in**: 7 Reels + 7 carousels.
Work through the steps in order. Do not skip fact-checking. Never set or use ANTHROPIC_API_KEY.

## Account rules (apply to everything)
- Niche: evergreen AI tools, prompts, tutorials, comparisons and productivity tips. **No breaking news.**
- Audience: Indian students and job seekers.
- Voice: friendly "guru" tone. Hinglish hooks ("Ye prompt try kiya?"), simple English or Hinglish body.
- Series (rotate across the week): **Prompt of the Day**, **Pandit ji ka Tool**, **Galat vs Sahi Prompt**.
- No fake stats, no made-up numbers, no speculation stated as fact. Hashtags: no trademarks except tool names.
- Visuals: our templates plus official tool-site screenshots only.

## 1. Learn from the past
Read `data/insights.json` and `data/history.json`.
- Favour series, Reel styles, hook patterns and topics with the best saves, shares and reach (ratios per reach, not raw counts).
- **Never repeat a topic** that's in history.json (`build_week.py` will also reject repeats).
- Week start = tomorrow, unless content is already queued for those dates in `content/queue/schedule.json`. In that case start the day after the last queued day.

## 2. Pick 14 topics
Use web search and fetch to find 7 Reel topics and 7 carousel topics, evergreen and useful for students and job seekers (exams, resumes, interviews, study, coding, English, productivity).
- Tool topics: confirm the tool exists, check its **official site** URL, and check that it has a free tier or free access if you say so.
- Rotation:

| Day | Reel series (style) | Carousel series |
|---|---|---|
| 1 | Pandit ji ka Tool (tool_demo) | Prompt of the Day |
| 2 | Galat vs Sahi Prompt (comparison) | Pandit ji ka Tool |
| 3 | Prompt of the Day (kinetic) | Galat vs Sahi Prompt |
| 4 | Pandit ji ka Tool (tool_demo) | Prompt of the Day |
| 5 | Galat vs Sahi Prompt (comparison) | Pandit ji ka Tool |
| 6 | Prompt of the Day (kinetic) | Galat vs Sahi Prompt |
| 7 | Pandit ji ka Tool (tool_demo) | Prompt of the Day |

Adjust the mix toward what insights show works, but keep all three series in the week.

## 3. Write
Create `content/plan/week_<YYYY-MM-DD>.json` (format in the `scripts/build_week.py` docstring). Copy the spec shapes from `templates/reel/sample_*.json` and `templates/carousel/sample.json`.

**Each Reel:** a hook (first line, Hinglish, under 1.5 s to read), a 20-40 s script of **60-90 words** (the voice is fast, at 1.35×), on-screen `text` for each scene, a scene plan, a caption, 5-8 hashtags and source URLs.
- Every scene needs `voice` (Roman Hinglish, which becomes the burned-in caption) **and** `voice_tts` (the same line in **Devanagari**, so the Hindi voice pronounces English words naturally: "प्रॉम्प्ट", "एआई"). Write URLs and brand names phonetically in `voice_tts` ("नोटबुक एल एम डॉट गूगल").
- tool_demo: add `tool`, `site_url` (the official site) and a `scroll` value for each scene (0-1). Check the screenshot. Scroll to sections that show real content, because animated blocks can capture as blank.
- comparison: add `title`, `galat`, `sahi`, `verdict`. Keep `sahi` under about 160 characters so it fits the panel.
- The last scene invites people to save and follow.

**Each carousel:** 7-9 slides including the CTA slide. Start with a cover; the last slide is `{"type": "cta"}`. Use `prompt` slides for copy-paste prompts and `before_after` for Galat vs Sahi. Add the caption, 5-8 hashtags and source URLs. `*word*` makes a word lime; `[placeholder]` highlights a placeholder.

**Captions:** start with a Hinglish hook line, then 2-4 short lines of value and a question to drive comments. `build_week.py` adds the CTA, a source line for tool posts, and the hashtags.

## 4. Fact-check (required)
For every factual claim (what a tool does, what's free, feature names):
- Run `.venv/bin/python scripts/fetch_page.py <official-url>` and check that the claim appears on the official page.
- Remove or soften any claim you can't verify there. Prompt-technique advice needs no source, but must not include invented numbers.
- List what you checked in a `"fact_check"` array on each item: `["claim -> url", ...]`.

## 5. Render + QA
```bash
.venv/bin/python scripts/build_week.py content/plan/week_<date>.json --validate
.venv/bin/python scripts/build_week.py content/plan/week_<date>.json      # run in the background, about 20 min
```
QA runs automatically (resolution, duration, audio, loudness, file size, slide count). Fix failures and re-run one item with `--only <date>_<type>`.
Look at 2-3 frames from each Reel and the first slide of each carousel (FFmpeg frame grab) to check layout and overflow.

## 6. Review with the owner
Show a summary table: **date, format, series, topic, hook**. Wait for **"go"**.
Then commit `content/`, `data/history.json` and the plan, and push. GitHub Actions publishes from there.
