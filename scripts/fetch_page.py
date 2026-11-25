"""Print the visible text of a web page (for fact-checking against official sites).

Uses a real headless browser, so JavaScript-heavy product sites work.

Usage:  .venv/bin/python scripts/fetch_page.py URL [max_chars]
"""
import sys

from playwright.sync_api import sync_playwright

url = sys.argv[1]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 900})
    # "load" + settle time: some sites keep connections open forever, so
    # waiting for network-idle would time out.
    page.goto(url, wait_until="load", timeout=60000)
    page.wait_for_timeout(3500)
    print(f"URL: {page.url}\nTITLE: {page.title()}\n")
    print(page.inner_text("body")[:limit])
    b.close()
