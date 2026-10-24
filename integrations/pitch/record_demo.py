"""Backup demo video: walks the live site in DEMO_SCRIPT.md order and records it (silent .webm, 1440x900).

  python integrations/pitch/record_demo.py [--url https://web-production-c7376.up.railway.app]

Re-record on Sunday morning, once the sealed section shows results. Add the voice-over on top (read DEMO_SCRIPT.md)
or play this while speaking live if the Wi-Fi dies. Needs `pip install playwright` and Microsoft Edge (no browser download).
"""
import argparse
import shutil
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent

# (what the script says, where to look, seconds to hold) — matches DEMO_SCRIPT.md beats.
BEATS = [
    ("hook: headline", "top", 10),
    ("time curve", "#above", 25),
    ("model + money: KPI row", "kpi", 15),
    ("decision: live cards", "#live", 15),
    ("sealed before the outcomes", "#sealed", 20),
    ("close: back to the headline", "top", 5),
]


def scroll_to(page, target):
    if target == "top":
        y = "0"
    elif target == "kpi":  # the KPI row under the hero curve; keep the curve's bottom in view
        y = ("[...document.querySelectorAll('div,p,span')].find(e => e.textContent.trim().startsWith('Return after'))"
             ".getBoundingClientRect().top + window.scrollY - 420")
    else:
        y = f"document.querySelector('{target}').getBoundingClientRect().top + window.scrollY - 24"
    page.evaluate(f"window.scrollTo({{top: {y}, behavior: 'smooth'}})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://web-production-c7376.up.railway.app")
    a = ap.parse_args()
    tmp = OUT / "_video"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                                  record_video_dir=str(tmp), record_video_size={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(a.url, wait_until="networkidle")
        page.wait_for_selector("#live")
        time.sleep(2)  # let the count-ups and curve settle
        for label, target, hold in BEATS:
            print(f"{label} ({hold}s)")
            scroll_to(page, target)
            time.sleep(hold)
        video = page.video.path()
        ctx.close()
        browser.close()
    out = OUT / "backup_demo.webm"
    shutil.move(video, out)
    shutil.rmtree(tmp, ignore_errors=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
