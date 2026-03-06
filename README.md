# clowdbot-agent

Autonomous operations & engineering copilot running on Linux. Coordinates GitHub webhooks, Discord commands, OpenAI analysis, and safe shell execution.

## Features

- **GitHub Webhook Processing** — Receives events, analyzes them with GPT, logs results
- **Discord Bot** — `!ping`, `!mode`, `!analyze <text>`, `!run <command>`
- **OpenAI Integration** — Event analysis with structured operational guidance
- **Safe Shell Execution** — Allowlisted commands only, disabled by default
- **SQLite Event Log** — All events tracked with analysis and outcomes
- **FastAPI Server** — Health checks and webhook endpoints

## Quick Start

```bash
# Clone
git clone https://github.com/aalmanasir/clowdbot-agent.git
cd clowdbot-agent

# Configure
cp .env.example .env
# Edit .env with your API keys

# Install
pip install -r requirements.txt

# Run
python3 main.py
```

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for event analysis |
| `DISCORD_BOT_TOKEN` | Discord bot token |
| `DISCORD_CHANNEL_ID` | Discord channel ID |
| `GITHUB_TOKEN` | GitHub personal access token |
| `GITHUB_WEBHOOK_SECRET` | Secret for verifying GitHub webhooks |
| `BOT_MODE` | `assist` (default) or `execute` |
| `ALLOWED_EXECUTE` | `true` to enable shell commands (default: `false`) |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/webhook/github` | GitHub webhook receiver |

## Discord Commands

| Command | Description |
|---------|-------------|
| `!ping` | Pong |
| `!mode` | Show current bot mode |
| `!analyze <text>` | Analyze text with OpenAI |
| `!run <command>` | Run an allowlisted shell command |

## Project Structure

```
clowdbot-agent/
├── main.py                 # FastAPI entrypoint + Discord bot startup
├── requirements.txt
├── .env.example
├── .gitignore
└── app/
    ├── config.py           # Settings from environment
    ├── prompt.py           # System prompt for OpenAI
    ├── db.py               # SQLite event logging
    ├── openai_client.py    # OpenAI integration
    ├── shell_utils.py      # Safe shell execution
    ├── github_handler.py   # GitHub webhook processing
    └── discord_bot.py      # Discord bot commands
```

## License

MIT
