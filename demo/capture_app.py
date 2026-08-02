"""Record the live CinemaForge app running a real production.

Headless Chromium at 1080p, driven through the actual UI so the footage is
the deployed service doing real work, not a mockup. Playwright writes webm;
the assembler transcodes.
"""

import pathlib
import sys

from playwright.sync_api import sync_playwright

URL = "https://cinemaforge-384599766402.us-central1.run.app"
BRIEF = (
    "Create a 60-second explainer about observability for developers. "
    "Style: clean, modern."
)
OUT = pathlib.Path(__file__).parent / "raw"
OUT.mkdir(exist_ok=True)


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb"])
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(OUT),
            record_video_size={"width": 1920, "height": 1080},
            device_scale_factor=1,
        )
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(2500)

        # Type the brief at a human cadence so the footage reads naturally.
        page.click("#brief")
        page.type("#brief", BRIEF, delay=28)
        page.wait_for_timeout(1200)

        page.click("#produce-btn")
        print("production started, waiting for completion...")

        # Wait for the stats bar to report Complete (pipeline is ~60s).
        page.wait_for_function(
            "document.getElementById('stat-status')"
            "  && document.getElementById('stat-status').textContent.trim() === 'Complete'",
            timeout=240_000,
        )
        print("pipeline complete")
        page.wait_for_timeout(2000)

        # Walk the output tabs so each agent's real result is on screen.
        # renderTabs() rebuilds the tab strip on every click, so handles go
        # stale: re-resolve by index each time rather than holding them.
        count = len(page.query_selector_all(".output-tab"))
        print(f"{count} output tabs")
        for i in range(count):
            page.locator(".output-tab").nth(i).click()
            page.wait_for_timeout(2600)

        page.wait_for_timeout(1500)
        video = page.video
        ctx.close()
        browser.close()
        print("saved:", video.path())


if __name__ == "__main__":
    sys.exit(main())
