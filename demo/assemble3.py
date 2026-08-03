"""Assemble v3 of the CinemaForge demo.

The change from v2 is the narration: it is one continuous human take rather
than eleven separate TTS files stitched end to end. That inverts how timing
works. v2 cut the audio to fit the picture; v3 cuts the picture to fit the
audio, because the delivery is fixed and the visuals are not.

So the audio here is laid down as a single unbroken track and never spliced.
Every join in the finished video is a picture cut over continuous sound,
which is also why nothing needs a crossfade to hide a seam.
"""

import pathlib
import subprocess
import sys

import blocks

HERE = pathlib.Path(__file__).parent
CLIPS = HERE / "clips"
RAW = HERE / "raw"
WORK = HERE / "work3"
WORK.mkdir(exist_ok=True)

FPS, W, H = 30, 1920, 1080
APP = RAW / "app_capture.webm"
NARRATION = HERE / "vo3" / "narration_clean.wav"
MUSIC = pathlib.Path(
    "/home/downoff/Desktop/Trading hack⁄setp yb i mep i cron za kdp, yt, "
    "music etc w n8n i gem i  cloud i automation/yt-pipeline/music/"
    "cinematic_piano_strings.mp3")

CLIP_FILE = {0: "card_00", 1: "card_01", 2: "card_02", 4: "card_04",
             6: "card_06", 7: "dash_07", 8: "dash_08", 10: "card_10"}


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
    """Seconds of blank white to skip at the head of a recording.

    Playwright starts recording when the context is created, which is before
    page.goto, so the first frames are the white about:blank. They read as a
    hard flash on the cut. The entrance animations only begin once the page
    paints, so trimming to the first painted frame loses nothing.
    """
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "info", "-i", str(src),
         "-t", "1.5", "-vf",
         "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
         "-an", "-f", "null", "-"],
        capture_output=True, text=True)
    # Playwright writes variable-frame-rate webm, so the frame index cannot be
    # divided by FPS to get a time. Take pts_time from the metadata dump.
    pts = None
    for line in r.stderr.splitlines():
        if "pts_time:" in line:
            pts = float(line.rsplit("pts_time:", 1)[1].split()[0])
        elif "YAVG=" in line and pts is not None:
            if float(line.rsplit("YAVG=", 1)[1]) < 120:   # backdrop sits ~33
                return pts
    return 0.0


def clip_segment(src: pathlib.Path, seconds: float, out: pathlib.Path) -> None:
    skip = head_offset(src)
    have = dur(src) - skip
    if have < seconds - 0.05:
        raise SystemExit(f"{src.name} has {have:.2f}s after the {skip:.2f}s "
                         f"white head but needs {seconds:.2f}s "
                         f"- re-run record_cards.py / record_dash.py")
    run(["ffmpeg", "-v", "error", "-i", src,
         "-ss", f"{skip:.3f}", "-t", f"{seconds:.3f}",
         "-vf", f"scale={W}:{H}:flags=lanczos,fps={FPS},format=yuv420p",
         "-c:v", "libx264", "-preset", "slow", "-crf", "17",
         "-pix_fmt", "yuv420p", "-an", out, "-y"])
    if skip:
        print(f"       trimmed {skip * FPS:.0f} white frames "
              f"({skip:.2f}s) from {src.name}")


def app_segment(src: pathlib.Path, start: float, seconds: float,
                out: pathlib.Path) -> None:
    """App capture inset on the brand backdrop.

    The page only fills ~1560x1052 of the 1920x1080 capture, so presenting it
    framed turns what was dead black into deliberate composition.
    """
    if start + seconds > dur(src) + 0.05:
        raise SystemExit(f"app capture is {dur(src):.2f}s, segment wants "
                         f"{start:.2f}+{seconds:.2f}")
    inset_w = 1660
    grad = (
        f"color=c=0x0a0f1a:s={W}x{H}:r={FPS},format=rgb24,"
        f"geq=r='0x0a+(0x0e-0x0a)*Y/{H}':g='0x0f+(0x14-0x0f)*Y/{H}':"
        f"b='0x1a+(0x22-0x1a)*Y/{H}'"
    )
    vf = (
        f"[1:v]crop=1560:1052:20:28,scale={inset_w}:-2:flags=lanczos[app];"
        f"[0:v][app]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p[v]"
    )
    run(["ffmpeg", "-v", "error",
         "-f", "lavfi", "-t", f"{seconds:.3f}", "-i", grad,
         "-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", src,
         "-filter_complex", vf, "-map", "[v]",
         "-r", str(FPS), "-c:v", "libx264", "-preset", "slow", "-crf", "17",
         "-pix_fmt", "yuv420p", "-an", out, "-y"])


def main() -> None:
    segs = blocks.segments()
    total = dur(NARRATION)
    built = []

    for idx, a, b, d in segs:
        kind, arg = blocks.PLAN[idx]
        out = WORK / f"seg_{idx:02d}.mp4"
        if kind == "app":
            app_segment(APP, float(arg), d, out)
        else:
            clip_segment(CLIPS / f"{CLIP_FILE[idx]}.webm", d, out)
        built.append(out)
        print(f"  seg {idx:02d}  {kind:4s}  {a:7.2f} -> {b:7.2f}  {d:6.2f}s")

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

    final = HERE / "cinemaforge_demo_v3.mp4"
    # [0]=video, [1]=narration, [2]=music
    af = (
        "[2:a]aformat=sample_rates=48000:channel_layouts=stereo,"
        f"aloop=loop=-1:size=2e9,atrim=0:{total:.3f},"
        "volume=0.20,"
        f"afade=t=in:st=0:d=2.5,afade=t=out:st={total - 4:.2f}:d=4[mus];"
        "[1:a]aformat=sample_rates=48000:channel_layouts=stereo[vox];"
        "[vox]asplit=2[vox1][key];"
        "[mus][key]sidechaincompress=threshold=0.03:ratio=9:attack=8:"
        "release=420:makeup=1[duck];"
        "[vox1][duck]amix=inputs=2:duration=first:weights=1 0.9,"
        "loudnorm=I=-16:TP=-1.5:LRA=11,"
        f"afade=t=in:st=0:d=0.4,afade=t=out:st={total - 1.0:.2f}:d=1.0[a]"
    )
    run(["ffmpeg", "-v", "error", "-i", vcat, "-i", NARRATION, "-i", MUSIC,
         "-filter_complex",
         f"[0:v]fade=t=in:st=0:d=0.8,fade=t=out:st={total - 1.2:.2f}:d=1.2[v];"
         + af,
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
