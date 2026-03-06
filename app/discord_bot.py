import discord
from discord.ext import commands
from app.config import settings
from app.openai_client import analyze_event
from app.shell_utils import run_command
from app.db import write_event

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Discord bot connected as {bot.user}")

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send("pong")

@bot.command(name="mode")
async def mode(ctx):
    await ctx.send(f"Current mode: {settings.BOT_MODE}")

@bot.command(name="analyze")
async def analyze(ctx, *, text: str):
    result = await analyze_event(f"Discord user request from {ctx.author}: {text}")
    await write_event(
        source="discord",
        event_type="command_analyze",
        actor=str(ctx.author),
        status="processed",
        raw_payload=text,
        analysis=result,
        action_taken="analysis_reply",
        result="ok"
    )
    # Discord hard limit is 2000 chars; keep some room for formatting
    if len(result) > 1900:
        result = result[:1900]
    await ctx.send(result)

@bot.command(name="run")
async def run(ctx, *, command: str):
    result = run_command(command)
    await write_event(
        source="discord",
        event_type="command_run",
        actor=str(ctx.author),
        status="processed" if result.get("ok") else "blocked",
        raw_payload=command,
        analysis="safe shell execution requested",
        action_taken="run_command",
        result=str(result)
    )
    await ctx.send(f"```{str(result)[:1900]}```")

def start_discord():
    if settings.DISCORD_BOT_TOKEN:
        bot.run(settings.DISCORD_BOT_TOKEN)
    else:
        raise RuntimeError("DISCORD_BOT_TOKEN not configured.")
