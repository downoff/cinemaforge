"""OpenTelemetry metrics for production pipeline observability."""

import os

from opentelemetry import metrics as otel_metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource

resource = Resource.create({"service.name": "cinemaforge", "service.version": "0.1.0"})

_readers = []

_otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
if _otlp_endpoint:
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    _readers.append(PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{_otlp_endpoint}/v1/metrics"),
        export_interval_millis=30_000,
    ))
else:
    _readers.append(PeriodicExportingMetricReader(
        ConsoleMetricExporter(), export_interval_millis=60_000,
    ))

provider = MeterProvider(resource=resource, metric_readers=_readers)
otel_metrics.set_meter_provider(provider)

meter = otel_metrics.get_meter("cinemaforge.pipeline")

productions_started = meter.create_counter("productions.started", description="Total productions initiated")
productions_completed = meter.create_counter("productions.completed", description="Total productions completed")
production_duration = meter.create_histogram("productions.duration_seconds", description="End-to-end production time")
agent_calls = meter.create_counter("agent.calls", description="Agent invocations by agent name")
agent_duration = meter.create_histogram("agent.duration_seconds", description="Per-agent execution time")
tool_calls = meter.create_counter("tool.calls", description="Tool invocations by tool name")
tool_duration = meter.create_histogram("tool.duration_seconds", description="Per-tool execution time")
production_events = meter.create_counter("production.events", description="Pipeline events by stage and status")
token_usage = meter.create_counter("llm.tokens", description="LLM token usage by type")


def flush(timeout_millis: int = 10_000) -> bool:
    """Force-export buffered metrics.

    Cloud Run throttles a container's CPU once a request finishes, so the
    30s periodic exporter frequently never runs and the run's metrics are
    lost. Call this at the end of a production so the data actually reaches
    Grafana Cloud.
    """
    try:
        return provider.force_flush(timeout_millis=timeout_millis)
    except Exception:
        return False
