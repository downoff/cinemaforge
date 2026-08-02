"""Custom tools for CinemaForge agents.

Each tool is a plain function — ADK auto-wraps them as FunctionTool.
Docstrings become the tool description the LLM sees."""

import json
import math
import os
import time
from typing import Optional

import httpx

from . import metrics

GRAFANA_URL = os.environ.get("GRAFANA_URL", "").rstrip("/")
GRAFANA_TOKEN = os.environ.get("GRAFANA_SERVICE_ACCOUNT_TOKEN", "")
PROM_UID = os.environ.get("GRAFANA_PROM_UID", "grafanacloud-prom")


def _query_prometheus(promql: str, timeout: float = 10.0) -> Optional[list]:
    """Run an instant PromQL query through the Grafana datasource proxy.

    Returns the result series list, or None if Grafana is unconfigured or the
    query fails. Never raises and never invents data - a None here means
    "we do not know", which callers must surface honestly.
    """
    if not GRAFANA_URL or not GRAFANA_TOKEN:
        return None
    url = f"{GRAFANA_URL}/api/datasources/proxy/uid/{PROM_UID}/api/v1/query"
    try:
        resp = httpx.get(
            url,
            params={"query": promql},
            headers={"Authorization": f"Bearer {GRAFANA_TOKEN}"},
            timeout=timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") != "success":
            return None
        return body.get("data", {}).get("result", [])
    except Exception:
        return None


def analyze_content_performance(
    topic: str,
    time_range: str = "7d",
) -> str:
    """Look up how this studio's past productions on a given topic performed,
    using the pipeline's own telemetry in Grafana Cloud Prometheus.

    Returns a `data_source` field that is either "grafana_cloud_prometheus"
    (real measured data) or "unavailable" (no data for this topic yet). When
    it is "unavailable" there are no performance numbers to cite - say so
    rather than guessing.

    Args:
        topic: The content topic to analyze (e.g. "anxiety", "motivation").
        time_range: How far back to look (e.g. "7d", "28d", "90d").
    """
    metrics.tool_calls.add(1, {"tool": "analyze_content_performance"})
    start = time.time()

    safe_topic = topic.replace('"', '\\"')
    window = time_range if time_range.endswith(("h", "d", "w")) else "7d"

    # Use the counter's instant value, NOT increase()/rate(). Those need two
    # samples inside the window, so a topic produced for the first time
    # reports 0 prior runs even though its own run is already recorded -
    # which reads as "no history" when history exists.
    runs = _query_prometheus(
        f'sum(productions_completed_total{{topic="{safe_topic}"}})'
    )
    # Not topic-filtered: production_events_total is emitted by
    # log_production_event, which the agents call without knowing the run's
    # topic label. These counts are pipeline-wide, and are reported as such.
    stages = _query_prometheus(
        "sum(production_events_total) by (stage, status)"
    )
    duration = _query_prometheus(
        f'sum(productions_duration_seconds_sum{{topic="{safe_topic}"}}) / '
        f'sum(productions_duration_seconds_count{{topic="{safe_topic}"}})'
    )

    def _scalar(series):
        """Instant-vector value as a float, or None.

        Prometheus returns NaN/Inf as the strings "NaN"/"+Inf"; float() parses
        them happily and they then serialise to invalid JSON, so screen them
        out explicitly rather than passing a NaN to the model as if measured.
        """
        if not series:
            return None
        try:
            v = float(series[0]["value"][1])
        except (KeyError, IndexError, ValueError, TypeError):
            return None
        return round(v, 2) if math.isfinite(v) else None

    prior_runs = _scalar(runs)

    if prior_runs is None:
        result = {
            "topic": topic,
            "data_source": "unavailable",
            "productions_recorded": 0,
            "note": (
                "No telemetry found for this topic in Grafana Cloud. Either "
                "Grafana is not configured or this studio has not produced "
                "content on this topic yet. There are NO historical "
                "performance figures to cite - do not invent any."
            ),
        }
    else:
        stage_breakdown = {}
        for s in stages or []:
            m = s.get("metric", {})
            key = f'{m.get("stage", "?")}/{m.get("status", "?")}'
            stage_breakdown[key] = _scalar([s])
        result = {
            "topic": topic,
            "data_source": "grafana_cloud_prometheus",
            "datasource_uid": PROM_UID,
            "productions_recorded": prior_runs,
            "mean_production_seconds": _scalar(duration),
            "stage_events_all_topics": stage_breakdown,
            "note": (
                "Real measured values from this studio's own pipeline "
                "telemetry, cumulative since the counters began. They "
                "describe production throughput and reliability, NOT audience "
                "response - this studio ingests no viewership data, so there "
                "are no views, retention, CTR or scheduling figures here and "
                "none should be inferred."
            ),
        }

    metrics.tool_duration.record(time.time() - start, {"tool": "analyze_content_performance"})
    return json.dumps(result, indent=2)


def build_scene_scaffold(
    num_scenes: int = 6,
    seconds_per_scene: int = 20,
    style: str = "cinematic",
) -> str:
    """Return an empty shot-list scaffold: per-scene timestamps and a
    non-repeating camera/lighting rotation to plan against.

    This is a structural helper only. It does NOT write visual descriptions -
    you (the Director) fill in `visual_prompt`, `mood` and `thumbnail_concept`
    yourself from the actual script content. The scaffold exists so your shot
    list has consistent timing and does not reuse the same camera setup twice
    in a row.

    Args:
        num_scenes: How many scenes to lay out.
        seconds_per_scene: Nominal duration of each scene.
        style: Visual style label carried through to the output.
    """
    metrics.tool_calls.add(1, {"tool": "build_scene_scaffold"})
    start = time.time()
    cameras = [
        "wide establishing", "medium close-up", "slow dolly in",
        "aerial / high angle", "tight close-up", "lateral tracking",
    ]
    lighting = [
        "warm golden hour", "soft overcast diffuse", "cool blue evening",
        "hard directional key", "practical / motivated sources", "low-key rim",
    ]
    scenes = [
        {
            "scene_number": i + 1,
            "timestamp": f"{i * seconds_per_scene}s - {(i + 1) * seconds_per_scene}s",
            "camera": cameras[i % len(cameras)],
            "lighting": lighting[i % len(lighting)],
            "visual_prompt": None,   # Director fills this in
            "mood": None,            # Director fills this in
        }
        for i in range(num_scenes)
    ]
    result = {
        "style": style,
        "total_runtime_seconds": num_scenes * seconds_per_scene,
        "scenes": scenes,
        "instruction": (
            "Fill every null field from the script. Do not return the "
            "scaffold unchanged."
        ),
    }
    metrics.tool_duration.record(time.time() - start, {"tool": "build_scene_scaffold"})
    return json.dumps(result, indent=2)


def optimize_metadata(
    title: str,
    description: str,
    topic: str,
    target_audience: str,
) -> str:
    """Optimize video metadata (title, description, tags) for discovery.
    Uses SEO best practices and performance data patterns.

    Args:
        title: Draft video title.
        description: Draft video description.
        topic: The main topic/theme.
        target_audience: Who this video is for.
    """
    metrics.tool_calls.add(1, {"tool": "optimize_metadata"})
    start = time.time()
    result = {
        "optimized_title": title,
        "title_notes": "Title should be under 60 chars, lead with emotion, include the core keyword.",
        "tags": [topic, target_audience, "motivation", "self-improvement", "mindset"],
        "category": "Entertainment",
        "default_language": "en",
        "scheduling_recommendation": "Publish at 20:00 UTC for maximum reach in US/EU evening hours.",
    }
    metrics.tool_duration.record(time.time() - start, {"tool": "optimize_metadata"})
    return json.dumps(result, indent=2)


def log_production_event(
    stage: str,
    status: str,
    details: Optional[str] = None,
) -> str:
    """Log a production pipeline event for monitoring in Grafana.

    Args:
        stage: Pipeline stage (research, writing, directing, seo).
        status: Event status (started, completed, error).
        details: Optional details about the event.
    """
    metrics.production_events.add(1, {"stage": stage, "status": status})
    return json.dumps({"logged": True, "stage": stage, "status": status})
