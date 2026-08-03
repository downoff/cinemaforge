"""Build burn-in captions: the script's words on the recording's clock.

The narration was read from SCRIPT_v3.md, so that file is the ground truth
for WHAT was said — the STT transcript exists only to know WHEN. Burning the
STT text directly would caption the accent's mistranscriptions ("a gas
dressed up as recommendation"), which is worse than no captions at all.

So: align script words to STT words with SequenceMatcher, take timings from
the matched STT words, interpolate across the mismatches, and group the
script text into captions on its own punctuation.
"""

import difflib
import json
import pathlib
import re

HERE = pathlib.Path(__file__).parent
STT = json.loads((HERE / "vo3" / "transcript_clean.json").read_text())["words"]
SCRIPT = (HERE / "SCRIPT_v3.md").read_text()
OUT = HERE / "vo3" / "captions.ass"

GAP = 0.60
MAX_WORDS = 10
MIN_DUR = 0.8


def script_words():
    """The spoken text: every '> ' line, in order, tokenised with display form."""
    spoken = []
    for line in SCRIPT.splitlines():
        if line.startswith("> "):
            spoken.append(line[2:].strip())
        elif line.strip() == ">":
            continue
    text = " ".join(spoken)
    # Spoken-out spellings in the script read badly as captions.
    text = (text.replace("S E O", "SEO").replace("M C P", "MCP")
                .replace("two point zero", "2.0"))
    # edit_final.py removed this clause from the audio (the live dashboard
    # outdates any fixed number); the captions must not resurrect it.
    text = text.replace("at twenty four seconds, ", "")
    words = []
    for tok in text.split():
        norm = re.sub(r"[^a-z0-9]", "", tok.lower())
        if norm:
            words.append((tok, norm))
    return words


def stt_norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def main() -> None:
    script = script_words()
    s_norm = [n for _, n in script]
    t_norm = [stt_norm(w["w"]) for w in STT]

    sm = difflib.SequenceMatcher(a=s_norm, b=t_norm, autojunk=False)
    times = [None] * len(script)          # (start, end) per script word
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            times[a + k] = (STT[b + k]["s"], STT[b + k]["e"])

    matched = sum(t is not None for t in times)
    print(f"aligned {matched}/{len(script)} script words to STT times")

    # Interpolate the unmatched stretches between their anchored neighbours.
    for i, t in enumerate(times):
        if t is not None:
            continue
        lo = next((j for j in range(i - 1, -1, -1) if times[j]), None)
        hi = next((j for j in range(i + 1, len(times)) if times[j]), None)
        if lo is None and hi is None:
            times[i] = (0.0, 0.5)
        elif lo is None:
            times[i] = (max(0.0, times[hi][0] - 0.4), times[hi][0])
        elif hi is None:
            times[i] = (times[lo][1], times[lo][1] + 0.4)
        else:
            a, b = times[lo][1], times[hi][0]
            span = max(b - a, 0.15)
            n = hi - lo - 1
            k = i - lo - 1
            times[i] = (a + span * k / n, a + span * (k + 1) / n)

    # Group into captions on script punctuation / silence / length.
    evs, cur, start = [], [], None
    for i, (disp, _) in enumerate(script):
        ws, we = times[i]
        if cur and (
            ws - times[i - 1][1] > GAP
            or len(cur) >= MAX_WORDS
            or cur[-1].rstrip()[-1:] in ".?!"
        ):
            evs.append((start, times[i - 1][1], " ".join(cur)))
            cur, start = [], None
        if start is None:
            start = ws
        cur.append(disp)
    if cur:
        evs.append((start, times[-1][1], " ".join(cur)))

    # Clamp: no overlaps, no blink-length captions.
    fixed, prev_end = [], 0.0
    for a, b, text in evs:
        a = max(a, prev_end)
        b = max(b, a + MIN_DUR)
        prev_end = b
        fixed.append((a, b, text))

    def ts(t):
        h = int(t // 3600); m = int(t // 60) % 60
        s = int(t) % 60; cs = int((t - int(t)) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Archivo,40,&H00E8E2D6,&H00E8E2D6,&H00141210,&H96000000,0,0,0,0,100,100,0.4,0,1,1.6,0,2,140,140,52,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for a, b, text in fixed:
        lines.append(f"Dialogue: 0,{ts(a)},{ts(b)},Cap,,0,0,0,,{text}\n")
    OUT.write_text("".join(lines))
    print(f"{len(fixed)} captions -> {OUT}")
    for a, b, t in fixed[:8]:
        print(f"  {a:6.2f}-{b:6.2f}  {t}")


if __name__ == "__main__":
    main()
