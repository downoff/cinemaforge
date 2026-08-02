"""Record each animated card as a video clip.

The motion is CSS transform/opacity, composited by Chromium, so it is
continuous. This replaces the ffmpeg zoompan approach, which stepped in
integer pixels on static stills and read on screen as camera shake.
"""

import pathlib
import subprocess
import sys

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
AUDIO = HERE / "audio"
OUT = HERE / "clips"
OUT.mkdir(exist_ok=True)

# narration clip index -> card id
CARD_FOR = {0: "c0", 1: "c1", 2: "c2", 4: "c3", 6: "c4", 10: "c5"}


def dur(p: pathlib.Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(p)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def main() -> None:
    tmp = OUT / "_raw"
    tmp.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(args=[
            "--force-color-profile=srgb",
            "--disable-lcd-text",              # grayscale AA, cleaner on video
            "--font-render-hinting=none",
        ])
        for idx, card in CARD_FOR.items():
            seconds = dur(AUDIO / f"vo_{idx:02d}.wav") + 0.45
            ctx = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                record_video_dir=str(tmp),
                record_video_size={"width": 1920, "height": 1080},
                device_scale_factor=1,
            )
            page = ctx.new_page()
            page.goto(f"file://{HERE / 'cards_anim.html'}?card={card}")
            page.wait_for_timeout(int(seconds * 1000) + 700)
            video = page.video
            ctx.close()
            src = pathlib.Path(video.path())
            dst = OUT / f"card_{idx:02d}.webm"
            src.replace(dst)
            print(f"card {card} (vo_{idx:02d})  {seconds:5.2f}s  -> {dst.name}")
        browser.close()

    print(f"\n{len(CARD_FOR)} card clips -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
