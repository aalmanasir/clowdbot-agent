import json
import time
from datetime import datetime, timezone

import discord
from discord.ext import commands

from app.config import settings
from app.logging_config import logger
from app.openai_client import analyze_event
from app.shell_utils import run_command
from app.db import write_event, get_events, get_event_stats

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@bot.event
async def on_ready():
    logger.info("Discord bot connected as %s (guilds: %d)", bot.user, len(bot.guilds))


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"⚠️ Missing argument: `{error.param.name}`")
    elif isinstance(error, commands.CommandNotFound):
        pass  # Silently ignore unknown commands
    else:
        logger.error("Discord command error: %s", error)
        await ctx.send(f"❌ Error: `{str(error)[:200]}`")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@bot.command(name="ping")
async def ping(ctx):
    """Check bot latency."""
    latency_ms = round(bot.latency * 1000)
    await ctx.send(f"🏓 pong — {latency_ms}ms")


@bot.command(name="mode")
async def mode(ctx):
    """Show current operating mode."""
    mode_emoji = {
        "monitor": "👁️",
        "assist": "🤝",
        "execute": "⚡",
        "incident": "🚨",
    }
    emoji = mode_emoji.get(settings.BOT_MODE, "❓")
    await ctx.send(f"{emoji} Current mode: **{settings.BOT_MODE.upper()}**")


@bot.command(name="status")
async def status(ctx):
    """Show agent system status."""
    uptime_seconds = time.time() - settings.UPTIME_START
    hours, remainder = divmod(int(uptime_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)

    stats = await get_event_stats()

    lines = [
        "**🤖 ClowdBot Agent Status**",
        f"```",
        f"Version:    {settings.APP_VERSION}",
        f"Mode:       {settings.BOT_MODE.upper()}",
        f"Uptime:     {hours}h {minutes}m {seconds}s",
        f"Environment:{settings.APP_ENV}",
        f"",
        f"Events:     {stats['total_events']} total",
        f"By source:  {json.dumps(stats['by_source'])}",
        f"By status:  {json.dumps(stats['by_status'])}",
        f"Latest:     {stats['latest_event'] or 'none'}",
        f"",
        f"OpenAI:     {'configured' if settings.OPENAI_API_KEY else 'not set'}",
        f"GitHub:     {'configured' if settings.GITHUB_TOKEN else 'not set'}",
        f"Discord:    connected as {bot.user}",
        f"Shell exec: {'enabled' if settings.ALLOWED_EXECUTE else 'disabled'}",
        f"```",
    ]
    await ctx.send("\n".join(lines))


@bot.command(name="events")
async def events(ctx, count: int = 10, source: str = None):
    """Show recent events. Usage: !events [count] [source]"""
    count = min(count, 25)
    rows = await get_events(limit=count, source=source)

    if not rows:
        await ctx.send("📭 No events found.")
        return

    lines = ["**📋 Recent Events**", "```"]
    for row in rows:
        severity_icon = {"info": "ℹ️", "warning": "⚠️", "error": "❌"}.get(row["severity"], "•")
        ts = row["created_at"][:16] if row["created_at"] else "?"
        lines.append(
            f"[{row['id']}] {ts} {severity_icon} {row['source']}/{row['event_type']} "
            f"by {row['actor'] or '?'} → {row['status']}"
        )
    lines.append("```")

    msg = "\n".join(lines)
    if len(msg) > 1900:
        msg = msg[:1900] + "\n...truncated```"
    await ctx.send(msg)


@bot.command(name="analyze")
async def analyze(ctx, *, text: str):
    """Analyze text with the AI copilot. Usage: !analyze <text>"""
    async with ctx.typing():
        result = await analyze_event(f"Discord user request from {ctx.author}: {text}")

    await write_event(
        source="discord",
        event_type="command_analyze",
        actor=str(ctx.author),
        status="processed",
        raw_payload=text,
        analysis=result,
        action_taken="analysis_reply",
        result="ok",
    )

    if len(result) > 1900:
        result = result[:1900] + "\n...(truncated)"
    await ctx.send(result)


@bot.command(name="run")
async def run_cmd(ctx, *, command: str):
    """Run an allowlisted shell command. Usage: !run <command>"""
    result = run_command(command)

    status_val = "processed" if result.get("ok") else "blocked"
    await write_event(
        source="discord",
        event_type="command_run",
        actor=str(ctx.author),
        status=status_val,
        raw_payload=command,
        analysis="safe shell execution requested",
        action_taken="run_command",
        result=json.dumps(result),
    )

    if result.get("ok"):
        output = result.get("stdout", "") or "(no output)"
        if result.get("stderr"):
            output += f"\nSTDERR: {result['stderr']}"
        output += f"\nExit code: {result['returncode']}"
    else:
        output = f"Blocked: {result.get('error', 'unknown')}"

    await ctx.send(f"```\n{output[:1900]}\n```")


@bot.command(name="deploy")
async def deploy(ctx, *, target: str = ""):
    """Request a deployment (requires approval in non-execute mode)."""
    if settings.BOT_MODE != "execute":
        await write_event(
            source="discord",
            event_type="command_deploy",
            actor=str(ctx.author),
            status="pending_approval",
            raw_payload=target,
            analysis="Deployment requested but mode is not EXECUTE",
            action_taken="awaiting_approval",
            result="blocked",
            severity="warning",
        )
        await ctx.send(
            f"⚠️ Deploy requested for `{target or 'default'}` but current mode is "
            f"**{settings.BOT_MODE.upper()}**.\n"
            f"Switch to EXECUTE mode or get manual approval to proceed."
        )
        return

    # In execute mode, log and acknowledge
    await write_event(
        source="discord",
        event_type="command_deploy",
        actor=str(ctx.author),
        status="acknowledged",
        raw_payload=target,
        analysis="Deployment request acknowledged in execute mode",
        action_taken="deploy_initiated",
        result="pending",
        severity="warning",
    )
    await ctx.send(
        f"🚀 Deploy initiated for `{target or 'default'}`. Monitoring..."
    )


@bot.command(name="incident")
async def incident(ctx, *, description: str):
    """Report an incident. Usage: !incident <description>"""
    event_id = await write_event(
        source="discord",
        event_type="incident_report",
        actor=str(ctx.author),
        status="reported",
        raw_payload=description,
        analysis=None,
        action_taken="incident_logged",
        result="open",
        severity="warning",
    )

    # If OpenAI is available, analyze the incident
    analysis = ""
    async with ctx.typing():
        analysis = await analyze_event(
            f"INCIDENT REPORT from {ctx.author}:\n{description}\n\n"
            f"Provide triage assessment: severity, likely cause, immediate actions, escalation needs."
        )

    if analysis and analysis != "OpenAI not configured.":
        await write_event(
            source="system",
            event_type="incident_triage",
            actor="clowdbot",
            status="triaged",
            raw_payload=f"incident_id={event_id}",
            analysis=analysis,
            action_taken="ai_triage",
            result="ok",
        )

    response = [
        f"🚨 **Incident #{event_id} Reported**",
        f"**Reporter:** {ctx.author}",
        f"**Description:** {description[:500]}",
        f"**Status:** Open",
    ]
    if analysis and analysis != "OpenAI not configured.":
        response.append(f"\n**AI Triage:**\n{analysis[:1000]}")

    msg = "\n".join(response)
    if len(msg) > 1900:
        msg = msg[:1900] + "\n...(truncated)"
    await ctx.send(msg)


@bot.command(name="config")
async def show_config(ctx):
    """Show current configuration (secrets masked)."""
    summary = settings.masked_summary()
    lines = ["**⚙️ Configuration**", "```"]
    for k, v in summary.items():
        lines.append(f"{k:.<25} {v}")
    lines.append("```")
    await ctx.send("\n".join(lines))


@bot.command(name="help_agent")
async def help_agent(ctx):
    """Show all available commands."""
    help_text = """**🤖 ClowdBot Commands**
```
!ping           Check bot latency
!mode           Show operating mode
!status         System status and stats
!events [n]     Show last n events (default 10)
!analyze <text> AI analysis of text
!run <cmd>      Run allowlisted shell command
!deploy [tgt]   Request deployment
!incident <msg> Report an incident
!config         Show config (secrets masked)
!help_agent     This help message
```"""
    await ctx.send(help_text)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def start_discord():
    """Start the Discord bot. Blocks the calling thread."""
    if settings.DISCORD_BOT_TOKEN:
        logger.info("Starting Discord bot...")
        bot.run(settings.DISCORD_BOT_TOKEN, log_handler=None)
    else:
        logger.warning("DISCORD_BOT_TOKEN not configured — bot not started.")
