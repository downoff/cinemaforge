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

**Analyst** queries Grafana dashboards for historical content performance — views, retention, CTR — so every creative decision is data-driven. **Writer** takes those insights and produces a retention-optimized script with hook/body/CTA structure. **Director** translates the script into scene-by-scene visual plans with camera, lighting, and thumbnail concepts. **SEO** optimizes title, description, tags, and scheduling using the original analytics data.

The pipeline's own health metrics (agent latency, tool calls, production throughput) are exported via OpenTelemetry to Grafana Cloud, creating a feedback loop: the same dashboards the Analyst queries also monitor the pipeline itself.

## Quick Start

```bash
# Clone and install
git clone https://github.com/davorperic/cinemaforge.git
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
| `GRAFANA_URL` | Yes | Grafana Cloud instance URL |
| `GRAFANA_SERVICE_ACCOUNT_TOKEN` | Yes | Grafana service account token |

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
- **Gemini 2.0 Flash** — LLM backbone for all four agents
- **Grafana Cloud MCP Server** — 60+ tools for querying dashboards, Prometheus, Loki
- **OpenTelemetry** — Pipeline observability exported to Grafana Cloud
- **FastAPI** — Web server with SSE streaming
- **Cloud Run** — Serverless deployment

## License

Apache 2.0
