"""CinemaForge web application.

FastAPI server with SSE streaming for real-time agent output."""

import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from . import agents, metrics
from .agents import production_pipeline

app = FastAPI(title="CinemaForge", version="0.1.0")

WEB_DIR = Path(__file__).parent.parent / "web"

_STOPWORDS = {
    "create", "make", "a", "an", "the", "for", "about", "video", "minute",
    "second", "targeting", "target", "style", "on", "of", "to", "and", "with",
}


def _topic_from_brief(brief: str, max_words: int = 3) -> str:
    """Derive a low-cardinality topic label from a production brief.

    This label is attached to every metric the run emits, so a later
    production on the same topic can query its own history back out of
    Grafana. Kept short and normalised to avoid a cardinality explosion.
    """
    words = re.findall(r"[a-z]+", brief.lower())
    keep = [w for w in words if w not in _STOPWORDS and len(w) > 3]
    return "-".join(keep[:max_words]) or "untitled"

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

    topic = _topic_from_brief(brief)
    labels = {"topic": topic}
    metrics.productions_started.add(1, labels)
    start_time = time.time()

    prompt = (
        f"Production Brief:\n{brief}\n\n"
        f"Topic label for telemetry lookups: {topic}\n\n"
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
    metrics.productions_completed.add(1, labels)
    metrics.production_duration.record(duration, labels)
    metrics.flush()

    return {
        "session_id": session_id,
        "topic": topic,
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

    topic = _topic_from_brief(brief)
    labels = {"topic": topic}
    metrics.productions_started.add(1, labels)

    prompt = (
        f"Production Brief:\n{brief}\n\n"
        f"Topic label for telemetry lookups: {topic}\n\n"
        "Run the full production pipeline: analyze performance data, "
        "write the script, plan visuals, and optimize metadata."
    )

    msg = types.Content(role="user", parts=[types.Part(text=prompt)])

    async def event_stream():
        start_time = time.time()
        # Each sub-agent emits several events; count it once, and treat the
        # gap since the previous agent finished as its wall-clock duration.
        seen_agents: set[str] = set()
        last_agent_ts = start_time
        try:
            async for event in runner.run_async(
                user_id=user_id, session_id=session_id, new_message=msg
            ):
                if event.content and event.content.parts:
                    text = "".join(
                        p.text for p in event.content.parts
                        if hasattr(p, "text") and p.text
                    )
                    if text and event.author:
                        now = time.time()
                        if event.author not in seen_agents:
                            seen_agents.add(event.author)
                            metrics.agent_calls.add(
                                1, {**labels, "agent": event.author}
                            )
                            metrics.agent_duration.record(
                                now - last_agent_ts,
                                {**labels, "agent": event.author},
                            )
                            last_agent_ts = now
                        data = json.dumps({
                            "agent": event.author,
                            "content": text,
                            "timestamp": now,
                        })
                        yield f"data: {data}\n\n"
        except Exception as exc:
            err = json.dumps({"error": str(exc)})
            yield f"data: {err}\n\n"

        duration = time.time() - start_time
        metrics.productions_completed.add(1, labels)
        metrics.production_duration.record(duration, labels)
        metrics.flush()
        done = json.dumps({
            "done": True, "duration": round(duration, 1), "topic": topic,
        })
        yield f"data: {done}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/health")
async def health():
    """Report what is actually reachable, not merely what is configured.

    `grafana_reachable` is a live authenticated round-trip to the Grafana
    Cloud API, so a green health check means the Analyst can really query it.
    """
    has_gemini = bool(os.environ.get("GOOGLE_API_KEY"))
    grafana_url = os.environ.get("GRAFANA_URL", "").rstrip("/")
    grafana_token = os.environ.get("GRAFANA_SERVICE_ACCOUNT_TOKEN", "")
    grafana_configured = bool(grafana_url and grafana_token)

    grafana_reachable = False
    grafana_error = None
    if grafana_configured:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    f"{grafana_url}/api/datasources",
                    headers={"Authorization": f"Bearer {grafana_token}"},
                )
            grafana_reachable = r.status_code == 200
            if not grafana_reachable:
                grafana_error = f"HTTP {r.status_code}"
        except Exception as exc:
            grafana_error = type(exc).__name__

    return {
        "status": "ok",
        "version": "0.2.0",
        "model": agents.MODEL,
        "gemini_configured": has_gemini,
        "grafana_configured": grafana_configured,
        "grafana_reachable": grafana_reachable,
        "grafana_error": grafana_error,
        "grafana_mcp_attached": agents.GRAFANA_LIVE,
        "mcp_import_error": agents.MCP_IMPORT_ERROR,
        "otel_export_configured": bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")),
    }
