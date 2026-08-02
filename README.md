# CinemaForge

AI-powered multi-agent content production studio. Four specialized Gemini agents collaborate through a sequential pipeline — analyst, writer, director, SEO optimizer — to produce complete video content packages from a single brief.

Built with **Google ADK** + **Grafana Cloud MCP** + **OpenTelemetry** for the [Agentic Cinema](https://agentic-cinema.devpost.com/) hackathon.

## Architecture

```
Production Brief
      │
      ▼
┌─────────────┐    Grafana MCP    ┌─────────────┐
│   Analyst   │◄─────────────────►│ Grafana Cloud│
│  (Gemini)   │    query_prom,    │  Dashboards  │
└──────┬──────┘    query_loki     └─────────────┘
       │ analytics_brief
       ▼
┌─────────────┐
│   Writer    │
│  (Gemini)   │
└──────┬──────┘
       │ script
       ▼
┌─────────────┐
│  Director   │
│  (Gemini)   │
└──────┬──────┘
       │ visual_plan
       ▼
┌─────────────┐
│    SEO      │
│  (Gemini)   │
└──────┬──────┘
       │ metadata
       ▼
  Complete Package

All stages emit OTel metrics ──► Grafana Cloud
```

**Analyst** connects to the [Grafana Cloud MCP Server](https://github.com/grafana/mcp-grafana) over stdio and runs live PromQL against Grafana Cloud Prometheus. **Writer** takes the resulting brief and produces a retention-optimized script with hook/body/CTA structure. **Director** translates the script into scene-by-scene visual plans with camera, lighting, and thumbnail concepts. **SEO** optimizes title, description, tags, and scheduling.

### The feedback loop

Every production emits OpenTelemetry metrics — agent latency, tool calls, stage events, throughput — into Grafana Cloud, tagged with a `topic` label derived from the brief. A later production on the same topic queries those metrics back out through MCP. The studio measures itself, and the measurements feed the next run.

### What the data is, and isn't

The Analyst reads **this pipeline's own production telemetry** — how many prior runs on a topic, how long they took, which stages succeeded. It does **not** have viewership data: no views, retention, or CTR, because the studio does not ingest an audience analytics source. `analyze_content_performance` returns an explicit `data_source` field of either `grafana_cloud_prometheus` or `unavailable`, and the Analyst is instructed to report "no historical data" rather than fill the gap with plausible numbers. Every figure in a brief traces to a tool call that actually ran.

## Quick Start

```bash
# Clone and install
git clone https://github.com/downoff/cinemaforge.git
cd cinemaforge
pip install .

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run
uvicorn cinemaforge.app:app --reload --port 8080
# Open http://localhost:8080
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | Yes | Gemini API key |
| `GRAFANA_URL` | Yes | Grafana Cloud instance URL, e.g. `https://yourstack.grafana.net` |
| `GRAFANA_SERVICE_ACCOUNT_TOKEN` | Yes | Grafana service account token (`glsa_…`), Editor role. Used by the MCP server to **read**. |
| `GRAFANA_PROM_UID` | No | Prometheus datasource uid (default `grafanacloud-prom`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | Grafana Cloud OTLP gateway. Without it, metrics fall back to the console exporter and the feedback loop stays open. |
| `OTEL_EXPORTER_OTLP_HEADERS` | No | `Authorization=Basic <base64 of instanceID:token>`. Must be a **Cloud Access Policy token** with `metrics:write` — a `glsa_` service-account token is rejected by the OTLP gateway. |

> The read path and the write path use **different credentials**. The service-account token reads through MCP; OTLP ingestion needs a Cloud Access Policy token. Configuring only the first gives you a working Analyst that correctly reports having no data to read.

Check what is actually live at `/api/health` — it performs a real authenticated round-trip to Grafana rather than just checking that variables are set:

```json
{
  "grafana_configured": true,
  "grafana_reachable": true,
  "grafana_mcp_attached": true,
  "otel_export_configured": false
}
```

## Deploy to Cloud Run

```bash
gcloud run deploy cinemaforge \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_API_KEY=$GOOGLE_API_KEY,GRAFANA_URL=$GRAFANA_URL,GRAFANA_SERVICE_ACCOUNT_TOKEN=$GRAFANA_SERVICE_ACCOUNT_TOKEN
```

## Tech Stack

- **Google ADK 2.6** — Multi-agent orchestration (SequentialAgent)
- **Gemini 3.6 Flash** — LLM backbone for all four agents
- **Grafana Cloud MCP Server** — 60+ tools for querying dashboards, Prometheus, Loki
- **OpenTelemetry** — Pipeline observability exported to Grafana Cloud
- **FastAPI** — Web server with SSE streaming
- **Cloud Run** — Serverless deployment

## License

Apache 2.0
