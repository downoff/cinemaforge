"""Assemble the CinemaForge demo video.

Each narration paragraph drives one visual segment, so picture and voice stay
locked without hand-timing. Stills get a slow push so they are not dead
frames; app footage is the real recorded session.
"""

import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
AUDIO = HERE / "audio"
CARDS = HERE / "cards"
RAW = HERE / "raw"
WORK = HERE / "work"
WORK.mkdir(exist_ok=True)

FPS = 30
W, H = 1920, 1080
BG = "0x0a0a0f"
APP = RAW / "app_capture.webm"

# (narration clip index, source kind, source, start offset in source)
#   card  -> still image, slow push
#   app   -> segment of the recorded session
#   shot  -> still screenshot, slow push
PLAN = [
    (0,  "card", "card_0.png", None),
    (1,  "card", "card_1.png", None),
    (2,  "card", "card_2.png", None),
    (3,  "app",  APP,          5.5),
    (4,  "card", "card_3.png", None),
    (5,  "app",  APP,          46.0),
    (6,  "card", "card_4.png", None),
    (7,  "shot", "grafana_dash.jpg", None),
    (8,  "shot", "grafana_dash.jpg", None),
    (9,  "app",  APP,          62.0),
    (10, "card", "card_5.png", None),
]


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(" ".join(str(c) for c in cmd[:14]), "...")
        print(r.stderr[-1800:])
        raise SystemExit(f"ffmpeg failed ({r.returncode})")


def dur(path: pathlib.Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def still_segment(img: pathlib.Path, seconds: float, out: pathlib.Path,
                  zoom_to: float = 1.06) -> None:
    """Still with a slow centred push, letterboxed onto the 1080p canvas."""
    frames = max(2, int(round(seconds * FPS)))
    base = (
        f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={BG}"
    )
    if zoom_to <= 1.0:
        vf = f"{base},format=yuv420p"
    else:
        step = (zoom_to - 1.0) / frames
        vf = (
            f"{base},"
            f"zoompan=z='min(zoom+{step:.8f},{zoom_to})':d={frames}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
            f"format=yuv420p"
        )
    run(["ffmpeg", "-v", "error", "-loop", "1", "-i", str(img),
         "-t", f"{seconds:.3f}", "-vf", vf, "-r", str(FPS),
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", str(out), "-y"])


def app_segment(src: pathlib.Path, start: float, seconds: float,
                out: pathlib.Path) -> None:
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={BG},format=yuv420p"
    )
    run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", str(src),
         "-t", f"{seconds:.3f}", "-vf", vf, "-r", str(FPS),
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-an", str(out), "-y"])


def main() -> None:
    if not APP.exists():
        raise SystemExit(f"missing app capture: {APP}")

    segs, auds, total = [], [], 0.0
    for i, kind, src, start in PLAN:
        vo = AUDIO / f"vo_{i:02d}.wav"
        if not vo.exists():
            raise SystemExit(f"missing narration clip: {vo}")
        d = dur(vo) + 0.45          # small tail so cuts do not clip the voice
        out = WORK / f"seg_{i:02d}.mp4"

        if kind == "app":
            app_segment(src, start, d, out)
        else:
            # Dashboard screenshots are held flat. A push crops the outer
            # panels, and the panel values are the whole point of the shot.
            still_segment(CARDS / src, d, out,
                          zoom_to=1.0 if kind == "shot" else 1.07)

        segs.append(out)
        auds.append((vo, d))
        total += d
        print(f"seg {i:02d}  {kind:5s}  {d:5.2f}s")

    # Concat video
    lst = WORK / "segments.txt"
    lst.write_text("".join(f"file '{s}'\n" for s in segs))
    vcat = WORK / "video.mp4"
    run(["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(lst), "-c", "copy", str(vcat), "-y"])

    # Concat narration, padding each clip to its segment length
    parts = []
    for j, (vo, d) in enumerate(auds):
        p = WORK / f"a_{j:02d}.wav"
        run(["ffmpeg", "-v", "error", "-i", str(vo),
             "-af", f"apad=whole_dur={d:.3f},aresample=48000",
             "-t", f"{d:.3f}", "-ac", "2", str(p), "-y"])
        parts.append(p)
    alst = WORK / "audio.txt"
    alst.write_text("".join(f"file '{p}'\n" for p in parts))
    acat = WORK / "voice.wav"
    run(["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(alst), "-c", "copy", str(acat), "-y"])

    # Mux, normalise to broadcast-ish loudness, fade the head and tail
    final = HERE / "cinemaforge_demo.mp4"
    run(["ffmpeg", "-v", "error", "-i", str(vcat), "-i", str(acat),
         "-filter_complex",
         f"[0:v]fade=t=in:st=0:d=0.7,fade=t=out:st={total-0.9:.2f}:d=0.9[v];"
         f"[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,"
         f"afade=t=in:st=0:d=0.4,afade=t=out:st={total-0.8:.2f}:d=0.8[a]",
         "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "slow", "-crf", "19",
         "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
         "-movflags", "+faststart",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         str(final), "-y"])

    print(f"\n{final}  ({total:.1f}s / {total/60:.2f} min)")


if __name__ == "__main__":
    sys.exit(main())
