# clowdbot-agent

Autonomous operations & engineering copilot. Coordinates GitHub webhooks, Discord commands, OpenAI analysis, and safe shell execution from a single FastAPI server.

## Features

- **4 Operating Modes** — Monitor, Assist, Execute, Incident
- **GitHub Webhook Processing** — Push, PR, issues, releases, CI events with AI analysis
- **Discord Bot** — 10 commands: `!ping`, `!status`, `!events`, `!analyze`, `!run`, `!deploy`, `!incident`, `!mode`, `!config`, `!help_agent`
- **OpenAI Integration** — Structured event analysis with the full operations prompt
- **Safe Shell Execution** — Allowlisted commands only, disabled by default
- **SQLite Event Log** — All events tracked with severity, analysis, and outcomes
- **Health Monitoring** — Periodic self-checks for API, DB, and integration health
- **Docker Ready** — Dockerfile + docker-compose included
- **CI Pipeline** — GitHub Actions with lint, test, and Docker build stages

## Quick Start

```bash
git clone https://github.com/aalmanasir/clowdbot-agent.git
cd clowdbot-agent

cp .env.example .env
# Edit .env with your API keys

pip install -r requirements.txt
python3 main.py
```

Server starts on `http://localhost:8080`.

## Docker

```bash
# Build and run
docker-compose up -d

# Or standalone
docker build -t clowdbot-agent .
docker run -p 8080:8080 --env-file .env clowdbot-agent
```

## Configuration

All config via environment variables (`.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `clowdbot-agent` | Application name |
| `APP_ENV` | `development` | Environment (`development`/`production`) |
| `APP_PORT` | `8080` | HTTP port |
| `APP_VERSION` | `0.2.0` | Version string |
| `LOG_LEVEL` | `INFO` | Logging level |
| `BOT_MODE` | `assist` | Operating mode: `monitor`/`assist`/`execute`/`incident` |
| `OPENAI_API_KEY` | | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model to use for analysis |
| `DISCORD_BOT_TOKEN` | | Discord bot token |
| `DISCORD_CHANNEL_ID` | | Primary Discord channel |
| `GITHUB_TOKEN` | | GitHub personal access token |
| `GITHUB_WEBHOOK_SECRET` | | HMAC secret for webhook verification |
| `SQLITE_PATH` | `./agent.db` | SQLite database path |
| `ALLOWED_EXECUTE` | `false` | Enable shell command execution |
| `HEALTH_CHECK_INTERVAL` | `60` | Seconds between health checks |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Basic health check |
| `GET` | `/status` | Detailed system status with event stats |
| `GET` | `/config` | Configuration (secrets masked) |
| `GET` | `/events` | List events (filterable: `source`, `event_type`, `status`, `severity`, `since`) |
| `GET` | `/events/{id}` | Get single event |
| `GET` | `/events/stats/summary` | Aggregate event statistics |
| `POST` | `/webhook/github` | GitHub webhook receiver |
| `POST` | `/analyze` | Manual AI analysis (`{"text": "...", "source": "api"}`) |
| `POST` | `/events/manual` | Create manual event entry |
| `GET` | `/monitoring/health` | Run all health checks now |
| `GET` | `/monitoring/last` | Last periodic health check result |

## Discord Commands

| Command | Description |
|---------|-------------|
| `!ping` | Bot latency |
| `!mode` | Show operating mode |
| `!status` | Full system status |
| `!events [n] [source]` | Show last n events |
| `!analyze <text>` | AI analysis |
| `!run <command>` | Run allowlisted shell command |
| `!deploy [target]` | Request deployment (gated by mode) |
| `!incident <description>` | Report and triage an incident |
| `!config` | Show config (secrets masked) |
| `!help_agent` | List all commands |

## GitHub Webhook Events

Supported event types with structured extraction:

- **push** — branch, commit count, commit messages
- **pull_request** — PR number, title, state, merge status
- **issues** — issue number, title, labels, state
- **release** — tag, name, prerelease/draft flags
- **check_run / check_suite** — CI name, conclusion, status
- **workflow_run** — workflow name, conclusion, branch
- **create / delete** — ref type and name
- **issue_comment** — issue context with comment body
- **star** — starred/unstarred

All events are classified by severity (info/warning) and analyzed by OpenAI when available.

## Project Structure

```
clowdbot-agent/
├── main.py                    # FastAPI app + lifecycle management
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .env.example
├── .gitignore
├── .github/
│   └── workflows/
│       └── ci.yml             # Lint → Test → Docker build
└── app/
    ├── __init__.py
    ├── config.py              # Settings from environment
    ├── logging_config.py      # Structured logging setup
    ├── prompt.py              # Full operations system prompt
    ├── db.py                  # SQLite with queries and stats
    ├── openai_client.py       # OpenAI integration (graceful fallback)
    ├── shell_utils.py         # Safe shell execution
    ├── github_handler.py      # Webhook processing + event extraction
    ├── discord_bot.py         # Discord bot with 10 commands
    ├── routes.py              # API endpoints
    └── monitoring.py          # Health checks and monitoring loop
```

## Operating Modes

| Mode | Behavior |
|------|----------|
| **Monitor** | Observe and summarize — no actions taken |
| **Assist** | Recommend actions, require human approval |
| **Execute** | Automatically perform safe, reversible operations |
| **Incident** | Priority triage, containment, and escalation |

## License

MIT
