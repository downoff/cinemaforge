"""Render the demo narration with Chirp 3 HD (Algenib).

Splits on blank lines so each paragraph becomes its own clip, which keeps
each request inside the synthesis limit and lets the assembler time video
segments against individual paragraphs.
"""

import pathlib
import sys

from google.cloud import texttospeech

OUT = pathlib.Path(__file__).parent / "audio"
OUT.mkdir(exist_ok=True)

VOICE = "en-US-Chirp3-HD-Algenib"


def main() -> None:
    script = (pathlib.Path(__file__).parent / "narration.txt").read_text()
    paras = [p.strip() for p in script.split("\n\n") if p.strip()]

    client = texttospeech.TextToSpeechClient()
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US", name=VOICE
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        sample_rate_hertz=48000,
        speaking_rate=1.0,
    )

    for i, para in enumerate(paras):
        resp = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=para),
            voice=voice,
            audio_config=audio_config,
        )
        path = OUT / f"vo_{i:02d}.wav"
        path.write_bytes(resp.audio_content)
        print(f"{path.name}  {len(para):4d} chars")

    print(f"\n{len(paras)} clips -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
