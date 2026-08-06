"""Assemble v4 of the CinemaForge demo.

What changed from v3, in order of what it buys:

  PUNCH-INS   a narration block can now be a sequence of shots. Block 4 cuts
              from the fresh brief being typed to a close-up of the analyst
              reporting data_source: unavailable — the thesis, finally shown
              at reading size. Punch-ins are FIXED crops: ffmpeg zoompan
              steps in integer pixels and reads as camera shake (the v2
              lesson), so movement comes from what is on screen, not from
              fake camera drift.
  CAPTIONS    full burned captions from captions.py — the script's words on
              the recording's clock. Judges watch muted.
  MUSIC ARCS  the bed lifts into the dashboard reveal and drops under the
              honest-caveat block, with linear ramps. The sidechain still
              ducks under the voice on top of that.
  NEW WORLD   every visual is the tungsten design system now: the live app,
              the re-skinned cards, the 2x dashboard.

The narration is untouched: one unbroken human take. All timing still comes
from blocks.py. Nothing here recuts audio.

App shot windows are computed from the capture's own marks JSON:
  file_time(event) = head_offset(file) + marks[event] - PAINT_DELAY
then refined by eye against extracted frames, same as every cut before it.
"""

import json
import pathlib
import subprocess
import sys

import blocks

HERE = pathlib.Path(__file__).parent
CLIPS = HERE / "clips"
RAW = HERE / "raw"
WORK = HERE / "work4"
WORK.mkdir(exist_ok=True)

FPS, W, H = 30, 1920, 1080
NARRATION = HERE / "vo3" / "narration_clean.wav"
CAPTIONS = HERE / "vo3" / "captions.ass"
FONTS = HERE / "fonts"
MUSIC = pathlib.Path(
    "/home/downoff/Desktop/Trading hack⁄setp yb i mep i cron za kdp, yt, "
    "music etc w n8n i gem i  cloud i automation/yt-pipeline/music/"
    "cinematic_piano_strings.mp3")

MAIN = RAW / "app4_main.webm"
FRESH = RAW / "app4_fresh.webm"
MARKS_MAIN = json.loads((RAW / "app4_main_marks.json").read_text())
MARKS_FRESH = json.loads((RAW / "app4_fresh_marks.json").read_text())

# Playwright's recording begins before page.goto; the first painted frame
# lands PAINT_DELAY after the goto that marks time zero.
PAINT_DELAY = 0.40

# Punch-in framings (x, y, w, h) on the 1920x1080 capture — fixed crops,
# tuned against extracted frames.
PUNCH_PAPER = (324, 360, 1280, 720)      # the paper page, reading size
PUNCH_DASH = (20, 280, 1140, 641)        # latency bars + labels; the digit
                                         # column stays out of frame - the
                                         # caption cites the earlier 24.0s
                                         # measurement, todays mean is 32.7s,
                                         # and showing both would be a lie by
                                         # juxtaposition either way


def run(cmd: list) -> None:
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode != 0:
        print(" ".join(str(c) for c in cmd[:16]), "...")
        print(r.stderr[-2000:])
        raise SystemExit(f"ffmpeg failed ({r.returncode})")


def dur(p: pathlib.Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(p)], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def head_offset(src: pathlib.Path) -> float:
    """Seconds of blank white at the head of a Playwright recording.

    VFR, so pts_time from the metadata dump — never frame index / FPS."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "info", "-i", str(src),
         "-t", "2.5", "-vf",
         "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
         "-an", "-f", "null", "-"],
        capture_output=True, text=True)
    pts = None
    for line in r.stderr.splitlines():
        if "pts_time:" in line:
            pts = float(line.rsplit("pts_time:", 1)[1].split()[0])
        elif "YAVG=" in line and pts is not None:
            if float(line.rsplit("YAVG=", 1)[1]) < 120:
                return pts
    return 0.0


_heads: dict = {}


def ft(src: pathlib.Path, marks: dict, event: str, slack: float = 0.0) -> float:
    """marks-event -> absolute time in the recorded file."""
    if src not in _heads:
        _heads[src] = head_offset(src)
        print(f"       {src.name}: {_heads[src]:.2f}s white head")
    return max(0.0, _heads[src] + marks[event] - PAINT_DELAY + slack)


def encode(out: pathlib.Path, args_in: list, vf: str, seconds: float) -> None:
    run(["ffmpeg", "-v", "error", *args_in,
         "-t", f"{seconds:.3f}", "-vf", vf,
         "-r", str(FPS), "-c:v", "libx264", "-preset", "slow", "-crf", "17",
         "-pix_fmt", "yuv420p", "-an", out, "-y"])


def clip_shot(card: str, seconds: float, out: pathlib.Path) -> None:
    src = CLIPS / f"{card}.webm"
    if src not in _heads:
        _heads[src] = head_offset(src)
    skip = _heads[src]
    have = dur(src) - skip
    if have < seconds - 0.05:
        raise SystemExit(f"{src.name}: {have:.2f}s after white head, "
                         f"need {seconds:.2f}s — re-run record_cards.py")
    encode(out, ["-ss", f"{skip:.3f}", "-i", src],
           f"scale={W}:{H}:flags=lanczos,fps={FPS},format=yuv420p", seconds)


def app_shot(src: pathlib.Path, start: float, seconds: float,
             out: pathlib.Path, punch=None) -> None:
    """A window of the live capture — full-frame inset, or a punch-in crop."""
    if start + seconds > dur(src) + 0.05:
        raise SystemExit(f"{src.name} is {dur(src):.2f}s, shot wants "
                         f"{start:.2f}+{seconds:.2f}")
    if punch:
        x, y, cw, ch = punch
        vf = (f"crop={cw}:{ch}:{x}:{y},scale={W}:{H}:flags=lanczos,"
              f"fps={FPS},format=yuv420p")
        encode(out, ["-ss", f"{start:.3f}", "-i", src], vf, seconds)
        return
    # full frame: inset on the brand backdrop, warm gradient
    grad = (
        f"color=c=0x14120F:s={W}x{H}:r={FPS},format=rgb24,"
        f"geq=r='0x14+(0x18-0x14)*Y/{H}':g='0x12+(0x15-0x12)*Y/{H}':"
        f"b='0x0F+(0x10-0x0F)*Y/{H}'"
    )
    vf = (
        f"[1:v]crop=1840:1035:40:12,scale=1700:-2:flags=lanczos[app];"
        f"[0:v][app]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p[v]"
    )
    run(["ffmpeg", "-v", "error",
         "-f", "lavfi", "-t", f"{seconds:.3f}", "-i", grad,
         "-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", src,
         "-filter_complex", vf, "-map", "[v]",
         "-r", str(FPS), "-c:v", "libx264", "-preset", "slow", "-crf", "17",
         "-pix_fmt", "yuv420p", "-an", out, "-y"])


def dash_shot(phase: str, seconds: float, out: pathlib.Path, punch=None) -> None:
    src = CLIPS / f"dash_{phase}.webm"  # recorder names: dash_07 / dash_08
    if src not in _heads:
        _heads[src] = head_offset(src)
    skip = _heads[src]
    if punch:
        x, y, cw, ch = punch
        vf = (f"scale={W}:{H}:flags=lanczos,crop={cw}:{ch}:{x}:{y},"
              f"scale={W}:{H}:flags=lanczos,fps={FPS},format=yuv420p")
    else:
        vf = f"scale={W}:{H}:flags=lanczos,fps={FPS},format=yuv420p"
    encode(out, ["-ss", f"{skip:.3f}", "-i", src], vf, seconds)


# ————— the cut —————
# Each narration block is a list of shots; shot durations are fractions of
# the block, the last one absorbs rounding.

def plan(segs):
    """[(idx, [(kind, args, dur), ...])] for the whole narration."""
    out = []
    for idx, a, b, d in segs:
        if idx == 0:
            shots = [("card", "card_00", d)]
        elif idx == 1:
            shots = [("card", "card_01", d)]
        elif idx == 2:
            shots = [("card", "card_02", d)]
        elif idx == 3:
            # the roll: click and a beat of the leader — then cut to the
            # analyst's brief landing, so "those numbers come back from
            # Grafana" plays over the numbers, not over a countdown. (The
            # first cut held the leader for the full 19s, and block 4 then
            # opened on a second leader. Two dials in a row reads as filler.)
            s = ft(MAIN, MARKS_MAIN, "rolled", -2.5)
            t_brief = ft(MAIN, MARKS_MAIN, "analyst_out", 0.4)
            d1 = min(8.0, d * 0.42)
            shots = [("app", (MAIN, s, None), d1),
                     ("app", (MAIN, t_brief, None), d - d1)]
        elif idx == 4:
            # fresh topic: type + roll, then punch in on the honest brief
            t_type = ft(FRESH, MARKS_FRESH, "settled", 0.3)
            t_brief = ft(FRESH, MARKS_FRESH, "honesty_framed", 0.4)
            d1 = min(8.4, d * 0.45)
            shots = [("app", (FRESH, t_type, None), d1),
                     ("app", (FRESH, t_brief, PUNCH_PAPER), d - d1)]
        elif idx == 5:
            # the handoffs, then the screenplay at reading size
            t_hand = ft(MAIN, MARKS_MAIN, "writer_out", -1.2)
            t_scr = ft(MAIN, MARKS_MAIN, "tab_screenplay", 0.6)
            d1 = min(9.0, d * 0.56)
            shots = [("app", (MAIN, t_hand, None), d1),
                     ("app", (MAIN, t_scr, PUNCH_PAPER), d - d1)]
        elif idx == 6:
            shots = [("card", "card_06", d)]
        elif idx == 7:
            shots = [("dash", ("07", None), d)]
        elif idx == 8:
            # the latency panel, close enough to read the analyst bar
            shots = [("dash", ("08", PUNCH_DASH), d)]
        elif idx == 9:
            # the last handoff riding into WRAPPED: four printed tallies and
            # the final timecode, the caveat spoken over a finished studio.
            # (-5.0 rather than -1.5: the capture's tail is only ~14s past
            # seo_out, and an 18.5s window must not run off the file.)
            s = ft(MAIN, MARKS_MAIN, "seo_out", -5.0)
            shots = [("app", (MAIN, s, None), d)]
        elif idx == 10:
            shots = [("card", "card_10", d)]
        out.append((idx, shots))
    return out


def main() -> None:
    segs = blocks.segments()
    total = dur(NARRATION)
    built = []

    for idx, shots in plan(segs):
        for j, (kind, args, d) in enumerate(shots):
            out = WORK / f"seg_{idx:02d}_{j}.mp4"
            if kind == "card":
                clip_shot(args, d, out)
            elif kind == "app":
                src, start, punch = args
                app_shot(src, start, d, out, punch)
            elif kind == "dash":
                phase, punch = args
                dash_shot(phase, d, out, punch)
            built.append(out)
            tag = "punch" if (kind == "app" and args[2]) or \
                             (kind == "dash" and args[1]) else kind
            print(f"  seg {idx:02d}.{j}  {tag:5s}  {d:6.2f}s")

    lst = WORK / "segments.txt"
    lst.write_text("".join(f"file '{s}'\n" for s in built))
    vcat = WORK / "video.mp4"
    run(["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", lst, "-c", "copy", vcat, "-y"])

    vlen = dur(vcat)
    print(f"\n  video {vlen:.2f}s   narration {total:.2f}s   "
          f"drift {vlen - total:+.2f}s")
    if abs(vlen - total) > 0.30:
        print("  WARNING: picture and narration have drifted apart")

    # music arcs, anchored to the narration's own block starts
    starts = json.loads((HERE / "vo3" / "blocks.json").read_text())["starts"]
    t_dash = starts[7] - 0.3          # lift into the dashboard reveal
    t_dash_end = starts[8] + 6.0
    t_cav = starts[9] - 0.3           # drop under the honest caveat
    t_cav_end = starts[10] - 0.3      # swell back for the close
    RAMP = 1.4

    def ramp(t0, t1, v0, v1):
        return (f"if(between(t,{t0:.2f},{t0+RAMP:.2f}),"
                f"{v0}+({v1}-{v0})*(t-{t0:.2f})/{RAMP},"
                f"if(between(t,{t0+RAMP:.2f},{t1:.2f}),{v1},")

    # piecewise: 1.0 -> 1.32 (dashboard) -> 1.0 -> 0.55 (caveat) -> 1.12 (close)
    # each ramp() opens two if( branches, so the tail closes 2 per ramp.
    pieces = [
        ramp(t_dash, t_dash_end, 1.0, 1.32),
        ramp(t_dash_end, t_cav, 1.32, 1.0),
        ramp(t_cav, t_cav_end, 1.0, 0.55),
        ramp(t_cav_end, total, 0.55, 1.12),
    ]
    vol = "".join(pieces) + "1.0" + ")" * (2 * len(pieces))

    final = HERE / "cinemaforge_demo_v4.mp4"
    af = (
        "[2:a]aformat=sample_rates=48000:channel_layouts=stereo,"
        f"aloop=loop=-1:size=2e9,atrim=0:{total:.3f},"
        "volume=0.20,"
        f"volume=volume='{vol}':eval=frame,"
        f"afade=t=in:st=0:d=2.5,afade=t=out:st={total - 4:.2f}:d=4[mus];"
        "[1:a]aformat=sample_rates=48000:channel_layouts=stereo[vox];"
        "[vox]asplit=2[vox1][key];"
        "[mus][key]sidechaincompress=threshold=0.03:ratio=9:attack=8:"
        "release=420:makeup=1[duck];"
        "[vox1][duck]amix=inputs=2:duration=first:weights=1 0.9,"
        "loudnorm=I=-16:TP=-1.5:LRA=11,"
        f"afade=t=in:st=0:d=0.4,afade=t=out:st={total - 1.0:.2f}:d=1.0[a]"
    )
    subs = (f"subtitles={CAPTIONS.as_posix()}:fontsdir={FONTS.as_posix()}"
            .replace(":", "\\:").replace("\\:", ":", 1))
    # ffmpeg filter escaping: the option separators must stay literal ':'
    subs = f"subtitles='{CAPTIONS.as_posix()}':fontsdir='{FONTS.as_posix()}'"
    run(["ffmpeg", "-v", "error", "-i", vcat, "-i", NARRATION, "-i", MUSIC,
         "-filter_complex",
         f"[0:v]{subs},fade=t=in:st=0:d=0.8,"
         f"fade=t=out:st={total - 1.2:.2f}:d=1.2[v];" + af,
         "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
         "-c:v", "libx264", "-preset", "slow", "-crf", "19",
         "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
         "-movflags", "+faststart",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         final, "-y"])

    got = dur(final)
    print(f"\n  {final}")
    print(f"  {got:.2f}s  ({int(got // 60)}:{got % 60:04.1f})   "
          f"ceiling 180s  ->  {'OK' if got <= 180 else 'OVER'}")


if __name__ == "__main__":
    sys.exit(main())
