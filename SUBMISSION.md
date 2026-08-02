# Devpost submission — CinemaForge

Track: **Grafana** · Deadline: **Sep 7 2026, 11:00pm GMT+2** (2:00pm PT)

---

## Project name

CinemaForge

## Elevator pitch (200 char max)

Four Gemini agents that plan video content from real telemetry. The analyst queries Grafana Cloud over MCP before a word is written, and refuses to cite a number it did not measure.

## Built with

`google-adk` · `google-genai` · `gemini-3.6-flash` · `mcp-grafana` · Grafana Cloud (Prometheus, MCP server) · OpenTelemetry · FastAPI · Cloud Run · Python

## Hosted project URL

https://cinemaforge-384599766402.us-central1.run.app

## Repository URL

https://github.com/downoff/cinemaforge

## Video URL

https://youtu.be/NVSdqFP61-g

(Unlisted on the Lucius Labs channel. Unlisted satisfies the "publicly visible"
requirement — anyone with the link can watch without signing in. Private would
not: judges would be locked out.)

---

## Description

### The problem

Content teams decide what to make next without evidence. Tooling in this space mostly generates confident-sounding recommendations with nothing underneath them, which is worse than no recommendation, because it looks like data.

### What CinemaForge does

CinemaForge is a production studio built as a sequential network of four Gemini agents, orchestrated with the Google Agent Development Kit:

| Agent | Role |
|---|---|
| **Analyst** | Connects to the Grafana Cloud MCP server over stdio and runs live PromQL against Grafana Cloud Prometheus |
| **Writer** | Turns the grounded brief into a hook/body/CTA script |
| **Director** | Expands the script into a shot list with camera, lighting and a thumbnail concept |
| **SEO** | Produces title, description, tags and a scheduling recommendation |

Each agent hands its output to the next through ADK session state. One line of brief in, a complete production package out, in about sixty seconds.

### How Grafana is used at runtime

The Analyst is bound to the official `grafana/mcp-grafana` server, launched as a stdio subprocess and filtered to the five tools it needs (`query_prometheus`, `list_datasources`, `list_prometheus_metric_names`, `list_prometheus_label_names`, `search_dashboards`). Exposing all 73 tools measurably degraded tool selection, so the toolset is deliberately narrowed.

Before any creative work happens, the Analyst runs real PromQL against the `grafanacloud-prom` datasource, asking how many productions this studio has run on this topic, how long they took, and which stages succeeded.

### The feedback loop

Every production emits OpenTelemetry metrics into Grafana Cloud through the OTLP gateway, tagged with a `topic` label derived from the brief:

- `productions_started_total`, `productions_completed_total`
- `productions_duration_seconds` (histogram)
- `agent_calls_total`, `agent_duration_seconds` — labelled per agent
- `tool_calls_total`, `production_events_total`

A later production on the same topic queries those series back out through MCP. The studio measures itself and the measurement feeds the next run. A dashboard for it ships in the repo at `grafana/dashboard.json`.

### What the data is, and what it is not

The Analyst reads **this pipeline's own production telemetry**. It has no viewership data — no views, retention or click-through rate — because no audience analytics source is wired in.

That constraint is enforced rather than hidden. `analyze_content_performance` returns an explicit `data_source` field of either `grafana_cloud_prometheus` or `unavailable`, and the Analyst is instructed that every figure it cites must come from a tool call it actually made in that session. On an unseen topic it reports `"data_source": "unavailable"`, `"productions_recorded": 0`, and says so in the brief instead of filling the gap. Saying "no historical data" is treated as a correct answer.

---

## Findings and learnings

**A dead integration looks exactly like a working one.** The first build defined the Grafana MCP toolset and never attached it to any agent. The app ran, the health check was green, and the briefs were full of confident numbers — all of which came from a hardcoded dict. The tell was that three different topics produced byte-identical figures: 342 views, 38.2% retention, 2.4% CTR. Plausible output is not evidence of a working data path. Checking that the numbers *change* was worth more than any amount of reading the code.

**`increase()` and `rate()` lie on a fresh counter.** They need two samples inside the window, so a topic's very first production reported zero prior runs while its own data was already sitting in Prometheus, and the duration quantile came back `NaN`. The fix is to read the counter's instant value for "has this happened before" questions and keep rate functions for genuine rates. NaN and Inf now get screened out rather than handed to the model dressed as a measurement.

**Cloud Run silently eats OpenTelemetry.** CPU is throttled the moment a request finishes, so the 30-second periodic OTLP exporter usually never fires and the run's metrics die in the container. An explicit `force_flush()` at the end of each production was the difference between an empty dashboard and a working feedback loop.

**A dependency floor is not a ceiling.** `mcp` 2.0.0 removed `mcp.shared.session`, which `google-adk` imports. ADK bounds `mcp<2` only under its `[mcp]` extra, so an unpinned `mcp>=1.0` quietly resolved to 2.x in the container and the Grafana toolset vanished at runtime while everything else kept working. It reproduced only in the deployed image, because local dev happened to be holding an older version. The lesson that stuck was not the pin itself but that the `except ImportError` around it turned a broken integration into a silent one.

**Instrument the thing that instruments.** `agent_calls_total` was named in the Analyst's own prompt and never incremented anywhere in the codebase, so that query could only ever return empty. The agent dutifully reported "no data" and was right for the wrong reason.

**Honesty is a design decision, not a disclaimer.** The interesting engineering was not making the agent cite data, it was making it comfortable reporting that there is none. That took an explicit tool contract (`data_source: unavailable`), a hard instruction that untraceable figures are forbidden, and removing the mock that made guessing easy. Once those were in place the model reported empty results plainly and labelled its fallback advice as craft judgement rather than analysis.
