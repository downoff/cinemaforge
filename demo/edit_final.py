"""Remove ", at twenty four seconds," from the finished narration.

Why: the phrase cites the analyst's mean latency as measured on 08-02. The
live dashboard — which judges can open — now reads 32.7s and will keep
moving. The sentence is grammatically whole without the clause ("The analyst
is the slowest agent, because it is the one doing the Grafana queries"), and
the film stops carrying a number that time falsifies. Framing the digits out
of shot was tried first and rejected: the number is legible in the full
dashboard shot anyway, and a cropped-out truth is still a dodge.

Method, all learned on v3:
  - STT places "agent" end at 119.10 and "Because" start at 121.70, but word
    timings lag the audio by ~0.3s, so both boundaries are refined from the
    RMS envelope: the cut starts in the silence right after "agent" and ends
    just before the "Because" onset, keeping ~0.3s of natural pause.
  - The splice lands trough-to-trough, so no crossfade is needed.

Because a cut shifts everything after it by exactly its length, the
transcript and blocks.json are shifted arithmetically — no re-transcription.
Originals are kept as *_pre24 backups.
"""

import json
import pathlib
import struct
import subprocess
import wave

HERE = pathlib.Path(__file__).parent
VO3 = HERE / "vo3"
WAV = VO3 / "narration_clean.wav"

# STT anchors (lagging, refined below)
AGENT_END = 119.10
BECAUSE_START = 121.70
KEEP_PAUSE = 0.30            # natural comma-pause retained before "Because"


def rms_envelope(path: pathlib.Path, t0: float, t1: float):
    """(times, rms) at 10ms hop over [t0, t1), mono-folded.

    The clean narration is 24-bit PCM, so the window is decoded through a
    16-bit ffmpeg tap rather than read raw."""
    tap = path.parent / "_rms_tap.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}",
                    "-t", f"{t1 - t0:.3f}", "-i", str(path),
                    "-ac", "1", "-c:a", "pcm_s16le", str(tap), "-y"],
                   check=True)
    with wave.open(str(tap), "rb") as w:
        rate, ch = w.getframerate(), w.getnchannels()
        raw = w.readframes(w.getnframes())
    tap.unlink()
    samples = struct.unpack(f"<{len(raw)//2}h", raw)
    hop = int(0.010 * rate)
    out = []
    for i in range(0, len(samples) - hop, hop):
        win = samples[i:i + hop]
        out.append((t0 + i / rate,
                    (sum(s * s for s in win) / len(win)) ** 0.5))
    return out


def main() -> None:
    env = rms_envelope(WAV, 118.2, 122.6)
    floor = sorted(r for _, r in env)[len(env) // 10]      # 10th percentile
    loud = max(3 * floor, 120)

    # He does NOT pause at the first comma — "agent at twenty-four seconds"
    # is one continuous phrase. The only usable seam on the left is the
    # ~40ms stop-closure of the /t/ in "agent": the deepest short dip near
    # the STT boundary. The splice is crossfaded below, so a mid-flow cut
    # at a closure is safe.
    lo = int((AGENT_END - 0.30 - 118.2) / 0.010)
    hi = int((AGENT_END + 0.35 - 118.2) / 0.010)
    dips = [(max(r for _, r in env[i:i + 4]), env[i][0])
            for i in range(lo, hi)]
    _, start = min(dips)

    # "Because" onset: first sustained-loud after the "seconds." tail has
    # fully decayed (search from 121.05, inside the 0.9s comma pause).
    onset = None
    for i, (t, r) in enumerate(env):
        if t < 121.05:
            continue
        window = [x for _, x in env[i:i + 8]]              # 80ms
        if window and min(window) > loud:
            onset = t
            break
    assert onset, "no Because onset found"
    end = onset - KEEP_PAUSE
    assert end > start + 1.0, f"cut window collapsed: {start:.2f}..{end:.2f}"
    delta = end - start
    print(f"cut {start:.3f} -> {end:.3f}  (removes {delta:.3f}s; "
          f"'Because' onset {onset:.3f}, floor {floor:.0f}, loud {loud:.0f})")

    # back up, then splice trough-to-trough
    backup = VO3 / "narration_clean_pre24.wav"
    if not backup.exists():
        backup.write_bytes(WAV.read_bytes())
    # 20ms crossfade at the joint: the left edge is a stop-closure inside
    # continuous speech, not silence, and a butt splice there could click.
    tmp = VO3 / "_final.wav"
    subprocess.run([
        "ffmpeg", "-v", "error", "-i", str(backup),
        "-filter_complex",
        f"[0:a]atrim=0:{start + 0.010:.4f},asetpts=PTS-STARTPTS[a];"
        f"[0:a]atrim={end - 0.010:.4f},asetpts=PTS-STARTPTS[b];"
        f"[a][b]acrossfade=d=0.020:c1=tri:c2=tri[out]",
        "-map", "[out]", str(tmp), "-y"], check=True)
    tmp.replace(WAV)

    # shift the derived timing files by the same delta
    tj = VO3 / "transcript_clean.json"
    (VO3 / "transcript_clean_pre24.json").write_text(tj.read_text())
    doc = json.loads(tj.read_text())
    kept = []
    for w in doc["words"]:
        if start <= w["s"] < end:
            continue                                        # the removed words
        if w["s"] >= end:
            w = {"w": w["w"], "s": round(w["s"] - delta, 2),
                 "e": round(w["e"] - delta, 2)}
        kept.append(w)
    tj.write_text(json.dumps({"text": doc["text"], "words": kept}, indent=1))

    bj = VO3 / "blocks.json"
    (VO3 / "blocks_pre24.json").write_text(bj.read_text())
    blocks = json.loads(bj.read_text())
    blocks["starts"] = [round(s - delta, 1) if s >= end else s
                        for s in blocks["starts"]]
    blocks["last_end"] = round(blocks["last_end"] - delta, 1)
    bj.write_text(json.dumps(blocks, indent=1))

    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", str(WAV)],
                       capture_output=True, text=True)
    print(f"narration now {float(r.stdout):.2f}s "
          f"(was {float(r.stdout) + delta:.2f}s)")
    print("blocks starts:", blocks["starts"])


if __name__ == "__main__":
    main()
