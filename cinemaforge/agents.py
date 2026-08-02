"""CinemaForge multi-agent pipeline.

Four specialized agents orchestrated by a SequentialAgent:
  1. Analyst  — queries Grafana for performance data on similar content
  2. Writer   — generates a production-ready script
  3. Director — plans visual scenes and thumbnail
  4. SEO      — optimizes metadata for discovery

The Analyst agent uses Grafana MCP tools to query real production
metrics, making content decisions data-driven rather than guesswork."""

import logging
import os

from google.adk.agents import Agent, SequentialAgent
logger = logging.getLogger(__name__)

# Import error is recorded rather than swallowed. A silently-missing MCP
# toolset is the exact failure this project already shipped once: the agent
# still runs, just without the Grafana tools, and nothing says so.
MCP_IMPORT_ERROR: str | None = None
try:
    from google.adk.tools.mcp_tool.mcp_toolset import StdioConnectionParams
    try:
        from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
    except ImportError:  # older ADK spells it MCPToolset
        from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset as McpToolset
    from mcp import StdioServerParameters
    _HAS_MCP = True
except Exception as _exc:
    _HAS_MCP = False
    MCP_IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"
    logger.error("Grafana MCP unavailable, analyst will run without it: %s", MCP_IMPORT_ERROR)

from . import tools


GRAFANA_URL = os.environ.get("GRAFANA_URL", "")
GRAFANA_TOKEN = os.environ.get("GRAFANA_SERVICE_ACCOUNT_TOKEN", "")

# Prometheus datasource backing Grafana Cloud, where this pipeline's own
# OpenTelemetry metrics land. The Analyst reads them back out.
PROM_DATASOURCE_UID = os.environ.get("GRAFANA_PROM_UID", "grafanacloud-prom")

MODEL = "gemini-3.6-flash"

# Subset of the Grafana MCP server's 73 tools that the Analyst needs. Exposing
# all of them buries the model in irrelevant choices (incidents, alerting,
# OnCall) and measurably degrades tool selection.
_GRAFANA_TOOL_FILTER = [
    "list_datasources",
    "query_prometheus",
    "list_prometheus_metric_names",
    "list_prometheus_label_names",
    "search_dashboards",
]


def grafana_toolset():
    """Grafana Cloud MCP server, or None when unconfigured.

    Uses the `mcp-grafana` console script from the official grafana/mcp-grafana
    package (a Python-wheel-packaged Go binary). The wrapper repairs the
    binary's executable bit on first run, so this works inside the container
    without uv.
    """
    if not _HAS_MCP or not GRAFANA_URL or not GRAFANA_TOKEN:
        return None
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="mcp-grafana",
                args=[],
                env={
                    "GRAFANA_URL": GRAFANA_URL,
                    "GRAFANA_SERVICE_ACCOUNT_TOKEN": GRAFANA_TOKEN,
                },
            ),
        ),
        tool_filter=_GRAFANA_TOOL_FILTER,
    )


_grafana = grafana_toolset()
GRAFANA_LIVE = _grafana is not None

_analyst_tools = [tools.analyze_content_performance, tools.log_production_event]
if _grafana is not None:
    _analyst_tools.append(_grafana)


analyst_agent = Agent(
    name="analyst",
    model=MODEL,
    description="Content performance analyst that queries Grafana dashboards.",
    instruction=f"""You are a content performance analyst for a video production studio.
You ground creative decisions in real telemetry from Grafana Cloud.

Every production this studio runs emits OpenTelemetry metrics into Grafana
Cloud's Prometheus (datasource uid `{PROM_DATASOURCE_UID}`). Your job is to
query those metrics back out and turn them into a brief the creative team
can act on.

STEP 1 - Query the real data. Use `query_prometheus` against datasource uid
`{PROM_DATASOURCE_UID}`. The pipeline's own metrics are:
  - `productions_started_total`      counter, productions initiated
  - `productions_completed_total`    counter, productions finished
  - `productions_duration_seconds`   histogram, end-to-end production time
  - `agent_calls_total`              counter, labelled by `agent`
  - `agent_duration_seconds`         histogram, labelled by `agent`
  - `tool_calls_total`               counter, labelled by `tool`
  - `production_events_total`        counter, labelled by `stage` and `status`
Useful starting queries:
  - `sum(production_events_total)  by (stage, status)`
  - `histogram_quantile(0.95, sum(rate(agent_duration_seconds_bucket[24h])) by (le, agent))`
  - `sum(rate(productions_completed_total[24h]))`
If a query returns no series, say so plainly. Do NOT invent numbers.

STEP 2 - Call `analyze_content_performance` for the topic-level view.
Read its `data_source` field. If it says `unavailable`, the studio has no
historical data for this topic yet: report that honestly and base your
recommendations on the pipeline telemetry plus general craft principles,
clearly labelled as such.

STEP 3 - Write the analytics brief:
  - Observed pipeline health (from the Prometheus queries you actually ran)
  - What the topic-level data supports, if anything
  - Recommended angle and what to avoid
  - Optimal scheduling window, only if the data supports one
  - The specific numbers that should inform the script

HARD RULE: every figure you cite must come from a tool call you actually made
in this session. If you did not measure it, do not state it. Saying "no
historical data available for this topic" is a correct and valuable answer.
Never fabricate a metric to make the brief look complete.""",
    tools=_analyst_tools,
    output_key="analytics_brief",
)


writer_agent = Agent(
    name="writer",
    model=MODEL,
    description="Scriptwriter that creates production-ready video scripts.",
    instruction="""You are a professional scriptwriter for short-form video content.
You write scripts that are emotionally engaging, well-paced, and optimized for retention.

Read the analytics brief from the analyst (in session state as 'analytics_brief')
and use its insights to shape your script.

Write a complete script with:
1. HOOK (first 5 seconds) — must stop the scroll. Use the angle the analytics data says works.
2. BODY (middle section) — 3-5 beats, each building emotional momentum.
   Each beat should map to roughly one visual scene.
3. CTA (final beat) — natural call to action, not salesy.

Format the script with clear scene breaks like:
  [SCENE 1 - HOOK]
  (Visual: ...)
  Narrator: "..."

Keep the total script under 500 words for a 2-minute video.
The script must feel human — no cliches, no AI-sounding filler.""",
    tools=[tools.log_production_event],
    output_key="script",
)


director_agent = Agent(
    name="director",
    model=MODEL,
    description="Visual director that plans scenes and thumbnail concepts.",
    instruction="""You are a visual director for video content production.
Your job is to translate scripts into detailed visual plans.

Read the script from the writer (in session state as 'script') and create:

1. SCENE PLAN: For each scene in the script, provide:
   - Visual description (detailed enough for AI image generation)
   - Camera movement/angle
   - Lighting and color palette
   - Mood/atmosphere
   - Any text overlays or graphics

2. THUMBNAIL CONCEPT:
   - Describe one high-impact thumbnail frame
   - Specify the emotion it should evoke
   - Text overlay (max 4 words, bold)
   - Composition (rule of thirds, where the focus is)

3. MUSIC DIRECTION:
   - Overall mood/genre for the background score
   - Any tempo changes that match the script beats

Call build_scene_scaffold first to get consistent timings and a camera
rotation, then fill in every field it leaves null. Never return the scaffold
unchanged — the visual writing is yours.
Think cinematically — every frame should serve the story.""",
    tools=[
        tools.build_scene_scaffold,
        tools.log_production_event,
    ],
    output_key="visual_plan",
)


seo_agent = Agent(
    name="seo",
    model=MODEL,
    description="SEO specialist that optimizes video metadata for discovery.",
    instruction="""You are an SEO specialist for video content platforms.
Your job is to optimize the video's metadata so it gets discovered.

Read the analytics brief ('analytics_brief'), script ('script'),
and visual plan ('visual_plan') from session state.

Create optimized:
1. TITLE — under 60 characters, emotion-first, includes core keyword.
   Must feel like something a real person would click, not AI-generated.
2. DESCRIPTION — first 2 lines are the hook (visible before "show more").
   Include relevant links placeholder and hashtags.
3. TAGS — 8-12 specific, relevant tags (mix of broad and niche).
4. SCHEDULING — recommend publish time based on the analytics data.

Use optimize_metadata to structure your output.
The title is the single most important piece — spend most of your effort there.""",
    tools=[
        tools.optimize_metadata,
        tools.log_production_event,
    ],
    output_key="metadata",
)


production_pipeline = SequentialAgent(
    name="cinemaforge_pipeline",
    description="Full content production pipeline: analyze, write, direct, optimize.",
    sub_agents=[analyst_agent, writer_agent, director_agent, seo_agent],
)
