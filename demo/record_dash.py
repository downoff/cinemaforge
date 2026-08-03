"""Record the Grafana dashboard shot with continuous CSS drift.

Segments 7 and 8 previously held one identical still for ~24s combined.
Two clips are recorded at different phase offsets so the pair does not
visibly loop.
"""

import pathlib
import subprocess
import sys

from playwright.sync_api import sync_playwright

import blocks

HERE = pathlib.Path(__file__).parent
OUT = HERE / "clips"
OUT.mkdir(exist_ok=True)

# narration index -> css animation-delay so the two clips differ
DASH = {7: "0s", 8: "-14s"}


def main() -> None:
    tmp = OUT / "_raw"
    tmp.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb"])
        for idx, delay in DASH.items():
            seconds = blocks.duration(idx) + 1.0
            ctx = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                record_video_dir=str(tmp),
                record_video_size={"width": 1920, "height": 1080},
            )
            page = ctx.new_page()
            page.goto(f"file://{HERE / 'dash_motion.html'}")
            page.eval_on_selector(
                ".shot", "(el, d) => { el.style.animationDelay = d; }", delay)
            page.wait_for_timeout(int(seconds * 1000) + 700)
            video = page.video
            ctx.close()
            pathlib.Path(video.path()).replace(OUT / f"dash_{idx:02d}.webm")
            print(f"dash vo_{idx:02d}  {seconds:5.2f}s  delay={delay}")
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
