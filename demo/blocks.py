"""Segment boundaries for v3, derived from the recorded narration.

v2 timed the visuals from eleven separate TTS files, one per script block.
v3 has a single continuous human take, so the boundaries come from where each
scripted block actually starts in that take. Those word times are produced by
`edit_vo.py` -> `transcribe.py` -> `vo3/blocks.json`; this module only turns
them into cut points.

Cuts land LEAD_IN before the first word of a block, so the picture changes on
the breath rather than a beat into the sentence.
"""

import json
import pathlib

HERE = pathlib.Path(__file__).parent
NARRATION = HERE / "vo3" / "narration_clean.wav"
LEAD_IN = 0.30

# narration block index -> what fills it.
#   ("clip", card-id)  a recorded CSS card
#   ("dash", delay)    the dashboard shot at a given animation phase
#   ("app",  start)    the live app capture, from this offset
PLAN = {
    0:  ("clip", "c0"),
    1:  ("clip", "c1"),
    2:  ("clip", "c2"),
    # The capture is one run: idle 8-28s, analyst 30-42, writer 42-50,
    # director 50-62, seo 62-70, finished 70-81. Offset 5.5 sat in the idle
    # stretch, so the screen read "Waiting for production to start" while the
    # narration said the analyst was querying. 29 opens just as it starts.
    3:  ("app", 29.0),
    4:  ("clip", "c3"),
    5:  ("app", 46.0),
    6:  ("clip", "c4"),
    7:  ("dash", "0s"),
    8:  ("dash", "-14s"),
    # 62.5 not 66.0: the block grew to 18.5s in the human take and the capture
    # is only 81.5s long, so the old offset ran off the end.
    9:  ("app", 62.5),
    10: ("clip", "c5"),
}


def _total() -> float:
    import subprocess
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(NARRATION)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def segments() -> list:
    """[(idx, start, end, duration)] covering the whole narration."""
    starts = json.loads((HERE / "vo3" / "blocks.json").read_text())["starts"]
    total = _total()
    cuts = [max(0.0, s - LEAD_IN) for s in starts]
    cuts[0] = 0.0
    out = []
    for i, a in enumerate(cuts):
        b = cuts[i + 1] if i + 1 < len(cuts) else total
        out.append((i, a, b, b - a))
    return out


def duration(idx: int) -> float:
    return segments()[idx][3]


if __name__ == "__main__":
    tot = 0.0
    for idx, a, b, d in segments():
        kind, arg = PLAN[idx]
        print(f"  {idx:2d}  {kind:4s} {str(arg):6s}  {a:7.2f} -> {b:7.2f}  {d:6.2f}s")
        tot += d
    print(f"\n  total {tot:.2f}s  ({int(tot // 60)}:{tot % 60:04.1f})")
