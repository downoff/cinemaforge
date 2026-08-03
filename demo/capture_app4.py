"""Capture the redesigned app running two real productions, for demo v4.

Run 1 — the main brief. The full arc: idle, roll, leader, analyst rolling,
        three handoffs, screenplay printing, wrapped.
Run 2 — a topic this studio has never produced, so the analyst genuinely
        reports data_source: unavailable. That beat carries the narration's
        thesis and must be real model output, not a mock.

Playwright starts recording before page.goto, so each file opens on white
about:blank frames — assemble trims them via pts_time (head_offset), never
by frame index, because the webm is variable-frame-rate.

State changes are logged as seconds since goto; they are starting points for
the edit, refined against extracted frames as always.
"""

import json
import pathlib
import time

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
RAW = HERE / "raw"
RAW.mkdir(exist_ok=True)

APP = "https://cinemaforge-384599766402.us-central1.run.app"

BRIEF_MAIN = ("Create a 2-minute motivational video about overcoming creative "
              "burnout, for independent filmmakers. Style: cinematic, warm, personal.")
# The fresh topic must be genuinely unproduced EVERY capture: re-running the
# same brief gives its topic label history, and the analyst then honestly
# reports that history instead of data_source: unavailable (learned when
# the tide-pool topic stopped being fresh on the second take).
BRIEF_FRESH = ("Create a 2-minute history feature about the Great Emu War of "
               "1932, for trivia lovers. Style: witty, deadpan.")


def wait_state(page, js, timeout_s, label, t0, marks):
    """Poll a JS condition, record when it flips."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if page.evaluate(js):
            marks[label] = round(time.time() - t0, 2)
            print(f"   {marks[label]:7.2f}s  {label}")
            return True
        page.wait_for_timeout(250)
    print(f"   !! timeout waiting for {label}")
    return False


def capture(name: str, brief: str, tail_tab: str | None) -> None:
    print(f"\n=== {name} ===")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=[
            "--force-color-profile=srgb", "--disable-lcd-text",
            "--font-render-hinting=none"])
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(RAW),
            record_video_size={"width": 1920, "height": 1080},
            device_scale_factor=1,
        )
        page = ctx.new_page()
        marks = {}
        t0 = time.time()
        page.goto(APP)
        page.wait_for_timeout(2400)          # fonts + entrance animation
        marks["settled"] = round(time.time() - t0, 2)

        if brief != BRIEF_MAIN:
            # retype the brief on camera — the act of briefing is part of the story
            page.fill("#brief", "")
            page.wait_for_timeout(700)
            page.type("#brief", brief, delay=16)
            page.wait_for_timeout(900)
        marks["typed"] = round(time.time() - t0, 2)

        page.click("#produce-btn")
        marks["rolled"] = round(time.time() - t0, 2)
        print(f"   {marks['rolled']:7.2f}s  rolled")

        wait_state(page, "!!outputs.analyst", 90, "analyst_out", t0, marks)
        wait_state(page,
                   "document.querySelector('#stage-analyst').classList.contains('printed')",
                   120, "analyst_printed", t0, marks)
        wait_state(page, "!!outputs.writer", 90, "writer_out", t0, marks)
        wait_state(page, "!!outputs.director", 90, "director_out", t0, marks)
        wait_state(page, "!!outputs.seo", 90, "seo_out", t0, marks)
        wait_state(page,
                   "document.getElementById('stat-status').textContent === 'WRAPPED'",
                   90, "wrapped", t0, marks)

        # For the honesty beat: bring the analyst's own admission into view
        # and hold it — the edit punches in on exactly this framing.
        if tail_tab is not None:
            page.evaluate("""() => {
                const page = document.getElementById('page');
                const el = document.getElementById('page-body');
                const needle = /unavailable|no historical|no prior/i;
                const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
                let n;
                while ((n = walk.nextNode())) {
                    if (needle.test(n.textContent)) {
                        n.parentElement.scrollIntoView({block: 'center'});
                        return n.textContent.slice(0, 60);
                    }
                }
                page.scrollTop = 0;
                return null;
            }""")
            marks["honesty_framed"] = round(time.time() - t0, 2)
            page.wait_for_timeout(11500)

        # hold the wrapped state, then walk the tabs so the edit can cut to
        # any page. The screenplay gets the long dwell — the edit reads it.
        page.wait_for_timeout(1500)
        dwell = {"Analytics brief": 3000, "Screenplay": 9000,
                 "Shot list": 3000, "Metadata": 3000}
        for label in (["Analytics brief", "Screenplay", "Shot list", "Metadata"]
                      if tail_tab is None else [tail_tab]):
            tabs = page.locator(".reel-tab", has_text=label)
            if tabs.count():
                tabs.first.click()
                marks[f"tab_{label.split()[0].lower()}"] = round(time.time() - t0, 2)
                page.wait_for_timeout(dwell.get(label, 2600))

        page.wait_for_timeout(1200)
        video = page.video
        ctx.close()
        src = pathlib.Path(video.path())
        dst = RAW / f"{name}.webm"
        src.replace(dst)
        browser.close()

    (RAW / f"{name}_marks.json").write_text(json.dumps(marks, indent=1))
    print(f"   -> {dst.name}")
    # keep the agent output too — the edit needs to know what the analyst said
    return


if __name__ == "__main__":
    import sys
    if "--fresh-only" not in sys.argv:
        capture("app4_main", BRIEF_MAIN, None)
    capture("app4_fresh", BRIEF_FRESH, "Analytics brief")
    print("\ndone")
