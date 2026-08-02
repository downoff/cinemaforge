"""CinemaForge multi-agent pipeline.

Four specialized agents orchestrated by a SequentialAgent:
  1. Analyst  — queries Grafana for performance data on similar content
  2. Writer   — generates a production-ready script
  3. Director — plans visual scenes and thumbnail
  4. SEO      — optimizes metadata for discovery

The Analyst agent uses Grafana MCP tools to query real production
metrics, making content decisions data-driven rather than guesswork."""

import os

from google.adk.agents import Agent, SequentialAgent
try:
    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioConnectionParams
    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False

from . import tools


GRAFANA_URL = os.environ.get("GRAFANA_URL", "")
GRAFANA_TOKEN = os.environ.get("GRAFANA_SERVICE_ACCOUNT_TOKEN", "")

MODEL = "gemini-3.6-flash"


def _grafana_toolset():
    if not _HAS_MCP or not GRAFANA_URL or not GRAFANA_TOKEN:
        return None
    return MCPToolset(
        connection_params=StdioConnectionParams(
            command="uvx",
            args=["mcp-grafana"],
            env={
                "GRAFANA_URL": GRAFANA_URL,
                "GRAFANA_SERVICE_ACCOUNT_TOKEN": GRAFANA_TOKEN,
            },
        ),
    )


analyst_agent = Agent(
    name="analyst",
    model=MODEL,
    description="Content performance analyst that queries Grafana dashboards.",
    instruction="""You are a content performance analyst for a video production studio.
Your job is to analyze past content performance data and provide actionable insights
to guide the creative team.

When given a production brief:
1. Use analyze_content_performance to check how similar topics have performed
2. If Grafana MCP tools are available, query production dashboards for deeper metrics
3. Summarize your findings as a concise analytics brief:
   - What worked well for this topic historically
   - What angles/formats to avoid
   - Optimal scheduling window
   - Specific data points that should inform the script

Store your analysis in the output. Be specific and data-driven, not generic.
Your recommendations directly shape the script and visuals.""",
    tools=[
        tools.analyze_content_performance,
        tools.log_production_event,
    ],
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

Use generate_scene_descriptions to structure your output.
Think cinematically — every frame should serve the story.""",
    tools=[
        tools.generate_scene_descriptions,
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
