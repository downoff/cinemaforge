"""Transcribe the recorded narration with word-level timestamps.

I cannot listen to the file, so this is how I verify what was actually said,
where each scripted block starts and ends, and whether any line was fumbled
and retaken. Cutting audio without this would be guessing.
"""

import json
import pathlib
import sys

from google.cloud import speech

HERE = pathlib.Path(__file__).parent
WAV = HERE / "vo3" / "clean_16k.wav"
OUT = HERE / "vo3" / "transcript_clean.json"


def main() -> None:
    client = speech.SpeechClient()
    # Inline audio is capped at 60s; anything longer must come from GCS.
    gcs_uri = sys.argv[1] if len(sys.argv) > 1 else None
    if gcs_uri:
        audio = speech.RecognitionAudio(uri=gcs_uri)
    else:
        audio = speech.RecognitionAudio(content=WAV.read_bytes())
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="en-US",
        enable_word_time_offsets=True,
        enable_automatic_punctuation=True,
        model="latest_long",
        use_enhanced=True,
        speech_contexts=[speech.SpeechContext(phrases=[
            "CinemaForge", "Grafana", "PromQL", "OpenTelemetry", "Gemini",
            "MCP", "SEO", "Prometheus", "Cloud Run", "Apache", "telemetry",
            "Agent Development Kit", "data source unavailable",
        ], boost=18.0)],
    )
    op = client.long_running_recognize(config=config, audio=audio)
    print("transcribing...")
    resp = op.result(timeout=600)

    words, text = [], []
    for result in resp.results:
        alt = result.alternatives[0]
        text.append(alt.transcript.strip())
        for w in alt.words:
            words.append({
                "w": w.word,
                "s": w.start_time.total_seconds(),
                "e": w.end_time.total_seconds(),
            })

    OUT.write_text(json.dumps({"text": " ".join(text), "words": words}, indent=1))
    print(f"{len(words)} words -> {OUT}\n")

    # Print the transcript in ~12s chunks with timestamps so the block
    # boundaries are readable at a glance.
    if not words:
        print("NO WORDS RECOGNISED")
        return
    chunk, start = [], words[0]["s"]
    for w in words:
        if w["s"] - start > 12 and chunk:
            print(f"[{start:6.2f}] {' '.join(chunk)}")
            chunk, start = [], w["s"]
        chunk.append(w["w"])
    if chunk:
        print(f"[{start:6.2f}] {' '.join(chunk)}")


if __name__ == "__main__":
    sys.exit(main())
