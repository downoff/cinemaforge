"""Edit the recorded narration into a broadcast-ready track.

Three things happen here:

1. Surgical removal of the fumbles found in the transcript. These timings
   come from word-level STT, not guesswork, because I cannot hear the file.
2. Long pauses are compressed to a consistent beat. The raw take is 3:05.7,
   over the contest's 3 minute ceiling, and the reclaimed time comes from
   dead air rather than from anything spoken.
3. A conservative cleanup chain. The recording peaks at 0 dBFS with 447
   clipped samples, so everything is attenuated before processing and
   brought back up at the end.
"""

import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
VO3 = HERE / "vo3"
# The master take, kept in the repo. It was recorded once by hand and cannot
# be regenerated, so it does not live in ~/Downloads where a cleanup would
# take it. Everything else under vo3/ is derived from this file and is
# gitignored; delete that and re-run to rebuild.
SRC = VO3 / "narration_raw.m4a"
TRANSCRIPT = VO3 / "transcript.json"
OUT = VO3 / "narration_clean.wav"

# (start, end) spans to delete, from the word-level transcript.
#  49.20-51.50  duplicate second take of "and it runs real PromQL"
# 109.75-111.00  the fumbled "and and" where "end to end" was intended
# 131.15-132.50  the first of the doubled "because it is". The end here comes
#                from the RMS envelope, not from the word timings: there is a
#                silence trough at 132.42-132.57 between the two takes, while
#                STT places the second "because" at 132.40. Trusting the word
#                timing cut 0.3s early and left an audible "is" behind.
CUTS = [(49.20, 51.50), (109.75, 111.00), (131.15, 132.50)]

MAX_GAP = 0.95      # any silence longer than this is pulled back to it
LEAD = 0.30         # silence kept before the first word
TAIL = 0.60         # silence kept after the last word


def run(cmd: list) -> None:
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode != 0:
        print(" ".join(str(c) for c in cmd[:14]), "...")
        print(r.stderr[-1500:])
        raise SystemExit(f"ffmpeg failed ({r.returncode})")


def dur(p: pathlib.Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def main() -> None:
    words = json.loads(TRANSCRIPT.read_text())["words"]

    def cut(t: float) -> bool:
        return any(a <= t < b for a, b in CUTS)

    # Keep only words outside the cut spans, then rebuild the timeline with
    # every inter-word gap clamped.
    kept = [w for w in words if not cut(w["s"])]
    if not kept:
        raise SystemExit("no words survived the cuts")

    # Group consecutive kept words into runs of continuous speech, splitting
    # wherever the gap exceeds MAX_GAP or a cut span intervenes. Each boundary
    # records whether it abuts a cut, because padding must not be applied
    # there.
    segs, cur_s, prev_e = [], kept[0]["s"], kept[0]["e"]
    for w in kept[1:]:
        gap = w["s"] - prev_e
        crossed = any(prev_e <= a and b <= w["s"] for a, b in CUTS)
        if gap > MAX_GAP or crossed:
            segs.append((cur_s, prev_e))
            cur_s = w["s"]
        prev_e = w["e"]
    segs.append((cur_s, prev_e))

    # Pad the joins so consonants are not clipped, but never let the padding
    # reach into a cut: doing so pulls the deleted audio straight back in,
    # which is what left a stutter on the doubled "because it is". Clamping
    # against the cut spans is safer than trusting the split reason, because
    # a boundary can be produced by the gap rule while still sitting flush
    # against a cut.
    PAD = 0.12
    SNAP = 0.50   # a boundary this close to a cut belongs to that cut

    def pad_start(a: float) -> float:
        # A segment resuming just after a cut must resume exactly at the cut
        # edge. The edge was chosen from the waveform, whereas the word
        # timings lag it, so honouring the word would clip the first syllable.
        for c0, c1 in CUTS:
            if c1 <= a < c1 + SNAP:
                return c1
        t = max(0.0, a - PAD)
        for c0, c1 in CUTS:
            if c0 < t < c1:
                return c1
        return t

    def pad_end(b: float) -> float:
        for c0, c1 in CUTS:
            if c0 - SNAP < b <= c0:
                return c0
        t = b + PAD
        for c0, c1 in CUTS:
            if c0 < t < c1:
                return c0
        return t

    segs = [(pad_start(a), pad_end(b)) for a, b in segs]

    print(f"{len(words)} words -> {len(kept)} kept, {len(segs)} speech runs")

    tmp = VO3 / "_parts"
    tmp.mkdir(exist_ok=True)
    for f in tmp.glob("*.wav"):
        f.unlink()

    parts, speech = [], 0.0
    for i, (a, b) in enumerate(segs):
        p = tmp / f"p{i:03d}.wav"
        # -6 dB on the way in: the source clips, so leave headroom for the
        # filter chain and restore level at the loudnorm stage.
        run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}",
             "-i", SRC, "-ac", "1", "-ar", "48000",
             "-af", "volume=-6dB", "-c:a", "pcm_s24le", p, "-y"])
        parts.append(p)
        speech += b - a
        if i < len(segs) - 1:
            gap = tmp / f"g{i:03d}.wav"
            run(["ffmpeg", "-v", "error", "-f", "lavfi",
                 "-i", f"anullsrc=r=48000:cl=mono", "-t", f"{MAX_GAP:.3f}",
                 "-c:a", "pcm_s24le", gap, "-y"])
            parts.append(gap)

    lead = tmp / "lead.wav"
    tail = tmp / "tail.wav"
    run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
         "-t", f"{LEAD}", "-c:a", "pcm_s24le", lead, "-y"])
    run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
         "-t", f"{TAIL}", "-c:a", "pcm_s24le", tail, "-y"])
    parts = [lead] + parts + [tail]

    lst = tmp / "parts.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    joined = VO3 / "_joined.wav"
    run(["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
         "-c", "copy", joined, "-y"])

    # Cleanup chain, deliberately gentle:
    #   highpass  - phone proximity rumble
    #   equalizer - tame the 5-7k sibilance range a touch
    #   acompressor - even out the level between blocks
    #   alimiter  - catch what was clipping
    #   loudnorm  - land on the -16 LUFS the video expects
    chain = (
        "highpass=f=85,"
        "equalizer=f=250:t=q:w=1.2:g=-2,"
        "equalizer=f=6000:t=q:w=2.0:g=-3,"
        "acompressor=threshold=-20dB:ratio=3:attack=12:release=180:makeup=2,"
        "alimiter=limit=0.93,"
        "loudnorm=I=-16:TP=-2.0:LRA=11"
    )
    run(["ffmpeg", "-v", "error", "-i", joined, "-af", chain,
         "-ac", "1", "-ar", "48000", "-c:a", "pcm_s24le", OUT, "-y"])

    total = dur(OUT)
    print(f"\nspeech {speech:6.2f}s   final {total:6.2f}s "
          f"({int(total//60)}:{total%60:04.1f})   was 185.7s")
    if total > 178:
        print("WARNING: still close to the 3 minute ceiling")


if __name__ == "__main__":
    sys.exit(main())
