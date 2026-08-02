"""Render each .card in cards.html to a 1920x1080 PNG."""

import pathlib
import sys

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
OUT = HERE / "cards"
OUT.mkdir(exist_ok=True)


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1920, "height": 1080}, device_scale_factor=1
        )
        page.goto(f"file://{HERE / 'cards.html'}")
        page.wait_for_timeout(900)

        cards = page.query_selector_all(".card")
        for i, c in enumerate(cards):
            path = OUT / f"card_{i}.png"
            c.screenshot(path=str(path))
            print(f"{path.name}")
        browser.close()
        print(f"\n{len(cards)} cards -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
