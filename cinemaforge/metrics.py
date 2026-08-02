"""OpenTelemetry metrics for production pipeline observability.

Emits metrics to Grafana Cloud via OTLP. These metrics power the
production health dashboards that the Analyst agent queries."""

import os

from opentelemetry import metrics as otel_metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource

resource = Resource.create({"service.name": "cinemaforge", "service.version": "0.1.0"})

_exporter = ConsoleMetricExporter()
_reader = PeriodicExportingMetricReader(_exporter, export_interval_millis=60_000)
provider = MeterProvider(resource=resource, metric_readers=[_reader])
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
