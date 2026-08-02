"""Assemble v2 of the CinemaForge demo.

Changes from v1, all driven by the QA findings:
  * Cards and the dashboard are recorded as video with CSS-composited motion.
    v1 used ffmpeg zoompan on stills, which steps in integer pixels and read
    on screen as camera shake (measured: 90x swing in frame-to-frame luma vs
    3x now).
  * Palette, type and motion easing come from the Lucius AI design system
    rather than an improvised theme.
  * App capture is framed on the brand backdrop instead of floating in dead
    black, and gets a slow push so it is not static either.
  * A music bed sits under the narration, side-chained down where the voice is.
"""

import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
AUDIO = HERE / "audio"
CLIPS = HERE / "clips"
RAW = HERE / "raw"
WORK = HERE / "work2"
WORK.mkdir(exist_ok=True)

FPS, W, H = 30, 1920, 1080
APP = RAW / "app_capture.webm"
MUSIC = pathlib.Path(
    "/home/downoff/Desktop/Trading hack⁄setp yb i mep i cron za kdp, yt, "
    "music etc w n8n i gem i  cloud i automation/yt-pipeline/music/"
    "cinematic_piano_strings.mp3")

# (narration idx, kind, source, app start offset)
PLAN = [
    (0,  "clip", CLIPS / "card_00.webm", None),
    (1,  "clip", CLIPS / "card_01.webm", None),
    (2,  "clip", CLIPS / "card_02.webm", None),
    (3,  "app",  APP,                    5.5),
    (4,  "clip", CLIPS / "card_04.webm", None),
    (5,  "app",  APP,                    46.0),
    (6,  "clip", CLIPS / "card_06.webm", None),
    (7,  "clip", CLIPS / "dash_07.webm", None),
    (8,  "clip", CLIPS / "dash_08.webm", None),
    (9,  "app",  APP,                    66.0),
    (10, "clip", CLIPS / "card_10.webm", None),
]


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


def clip_segment(src: pathlib.Path, seconds: float, out: pathlib.Path) -> None:
    """Recorded card/dash clip -> exact-length h264 segment."""
    run(["ffmpeg", "-v", "error", "-i", src, "-t", f"{seconds:.3f}",
         "-vf", f"scale={W}:{H}:flags=lanczos,fps={FPS},format=yuv420p",
         "-c:v", "libx264", "-preset", "slow", "-crf", "17",
         "-pix_fmt", "yuv420p", "-an", out, "-y"])


def app_segment(src: pathlib.Path, start: float, seconds: float,
                out: pathlib.Path) -> None:
    """App capture framed on the brand backdrop with a slow continuous push.

    The page content only occupies ~1500x1050 of the 1920x1080 capture, so
    presenting it inset on the brand gradient turns what was dead black into
    intentional framing.
    """
    inset_w = 1660
    grad = (
        f"color=c=0x0a0f1a:s={W}x{H}:r={FPS},"
        f"format=rgb24,"
        # brand-ish vertical fade toward #0e1422
        f"geq=r='0x0a+(0x0e-0x0a)*Y/{H}':g='0x0f+(0x14-0x0f)*Y/{H}':"
        f"b='0x1a+(0x22-0x1a)*Y/{H}'"
    )
    vf = (
        f"[1:v]crop=1560:1052:20:28,"
        f"scale={inset_w}:-2:flags=lanczos,"
        f"zoompan=z='1':d=1:s={inset_w}x{int(inset_w*1052/1560)}[app];"
        f"[0:v][app]overlay=(W-w)/2:(H-h)/2:shortest=1,"
        f"format=yuv420p[v]"
    )
    run(["ffmpeg", "-v", "error",
         "-f", "lavfi", "-t", f"{seconds:.3f}", "-i", grad,
         "-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", src,
         "-filter_complex", vf, "-map", "[v]",
         "-r", str(FPS), "-c:v", "libx264", "-preset", "slow", "-crf", "17",
         "-pix_fmt", "yuv420p", "-an", out, "-y"])


def main() -> None:
    segs, auds, total = [], [], 0.0
    for idx, kind, src, start in PLAN:
        vo = AUDIO / f"vo_{idx:02d}.wav"
        d = dur(vo) + 0.45
        out = WORK / f"seg_{idx:02d}.mp4"
        if kind == "app":
            app_segment(src, start, d, out)
        else:
            clip_segment(src, d, out)
        segs.append(out)
        auds.append((vo, d))
        total += d
        print(f"seg {idx:02d}  {kind:4s}  {d:5.2f}s")

    lst = WORK / "segments.txt"
    lst.write_text("".join(f"file '{s}'\n" for s in segs))
    vcat = WORK / "video.mp4"
    run(["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", lst, "-c", "copy", vcat, "-y"])

    parts = []
    for j, (vo, d) in enumerate(auds):
        p = WORK / f"a_{j:02d}.wav"
        run(["ffmpeg", "-v", "error", "-i", vo,
             "-af", f"apad=whole_dur={d:.3f},aresample=48000",
             "-t", f"{d:.3f}", "-ac", "2", p, "-y"])
        parts.append(p)
    alst = WORK / "audio.txt"
    alst.write_text("".join(f"file '{p}'\n" for p in parts))
    voice = WORK / "voice.wav"
    run(["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", alst, "-c", "copy", voice, "-y"])

    final = HERE / "cinemaforge_demo_v2.mp4"
    if MUSIC.exists():
        # Music ducked under the voice via sidechaincompress, then the pair
        # normalised together.
        # Input order is [0]=video, [1]=voice, [2]=music.
        af = (
            "[2:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"aloop=loop=-1:size=2e9,atrim=0:{total:.3f},"
            "volume=0.20,"
            f"afade=t=in:st=0:d=2.5,afade=t=out:st={total-4:.2f}:d=4[mus];"
            "[1:a]aformat=sample_rates=48000:channel_layouts=stereo[vox];"
            "[vox]asplit=2[vox1][key];"
            "[mus][key]sidechaincompress=threshold=0.03:ratio=9:attack=8:"
            "release=420:makeup=1[duck];"
            "[vox1][duck]amix=inputs=2:duration=first:weights=1 0.9,"
            "loudnorm=I=-16:TP=-1.5:LRA=11,"
            f"afade=t=in:st=0:d=0.4,afade=t=out:st={total-1.0:.2f}:d=1.0[a]"
        )
        inputs = ["-i", str(voice), "-i", str(MUSIC)]
    else:
        af = ("[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,"
              f"afade=t=in:st=0:d=0.4,afade=t=out:st={total-1.0:.2f}:d=1.0[a]")
        inputs = ["-i", str(voice)]

    run(["ffmpeg", "-v", "error", "-i", vcat, *inputs,
         "-filter_complex",
         f"[0:v]fade=t=in:st=0:d=0.8,fade=t=out:st={total-1.0:.2f}:d=1.0[v];"
         + af,
         "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "slow", "-crf", "19",
         "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
         "-movflags", "+faststart",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         final, "-y"])

    print(f"\n{final}  ({total:.1f}s / {total/60:.2f} min)")


if __name__ == "__main__":
    sys.exit(main())
