"""CinemaForge web application.

FastAPI server with SSE streaming for real-time agent output."""

import asyncio
import json
import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from . import metrics
from .agents import production_pipeline

app = FastAPI(title="CinemaForge", version="0.1.0")

WEB_DIR = Path(__file__).parent.parent / "web"

session_service = InMemorySessionService()
runner = Runner(
    agent=production_pipeline,
    app_name="cinemaforge",
    session_service=session_service,
)


@app.get("/", response_class=HTMLResponse)
async def index():
    return (WEB_DIR / "index.html").read_text()


@app.post("/api/produce")
async def produce(request: Request):
    body = await request.json()
    brief = body.get("brief", "")
    if not brief:
        return {"error": "brief is required"}

    session_id = f"prod-{uuid.uuid4().hex[:8]}"
    user_id = "web-user"

    await session_service.create_session(
        app_name="cinemaforge", user_id=user_id, session_id=session_id
    )

    metrics.productions_started.add(1)
    start_time = time.time()

    prompt = (
        f"Production Brief:\n{brief}\n\n"
        "Run the full production pipeline: analyze performance data, "
        "write the script, plan visuals, and optimize metadata."
    )

    msg = types.Content(role="user", parts=[types.Part(text=prompt)])

    results = {}
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=msg
    ):
        if event.content and event.content.parts:
            text = "".join(p.text for p in event.content.parts if hasattr(p, "text") and p.text)
            if text and event.author:
                results[event.author] = text

    duration = time.time() - start_time
    metrics.productions_completed.add(1)
    metrics.production_duration.record(duration)

    return {
        "session_id": session_id,
        "duration_seconds": round(duration, 1),
        "stages": results,
    }


@app.post("/api/produce/stream")
async def produce_stream(request: Request):
    body = await request.json()
    brief = body.get("brief", "")
    if not brief:
        return {"error": "brief is required"}

    session_id = f"prod-{uuid.uuid4().hex[:8]}"
    user_id = "web-user"

    await session_service.create_session(
        app_name="cinemaforge", user_id=user_id, session_id=session_id
    )

    metrics.productions_started.add(1)

    prompt = (
        f"Production Brief:\n{brief}\n\n"
        "Run the full production pipeline: analyze performance data, "
        "write the script, plan visuals, and optimize metadata."
    )

    msg = types.Content(role="user", parts=[types.Part(text=prompt)])

    async def event_stream():
        start_time = time.time()
        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=msg
        ):
            if event.content and event.content.parts:
                text = "".join(
                    p.text for p in event.content.parts
                    if hasattr(p, "text") and p.text
                )
                if text and event.author:
                    data = json.dumps({
                        "agent": event.author,
                        "content": text,
                        "timestamp": time.time(),
                    })
                    yield f"data: {data}\n\n"

        duration = time.time() - start_time
        metrics.productions_completed.add(1)
        metrics.production_duration.record(duration)
        done = json.dumps({"done": True, "duration": round(duration, 1)})
        yield f"data: {done}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
