# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BangaBot is a Discord bot built with discord.py 2.3.2 (Python 3.9). Core features: repost detection, AI-powered chat with persistent memory and user sentiment, and fun commands (CoD stats, PUBG loadout randomizer, greetings, GIFs).

## Build & Run Commands

```bash
# Run locally with Docker Compose (starts bot + PostgreSQL)
cd src/app && docker-compose up -d --build

# Lint (matches CI config — critical errors only)
flake8 src/app --count --select=E9,F63,F7,F82 --show-source --statistics

# Lint (warnings — max complexity 10, line length 127)
flake8 src/app --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

# Monitor logs
./monitor-logs.sh prod                # production app logs (run on EC2)
./monitor-logs.sh test <PR_NUMBER>    # PR test environment logs (run on test server)
docker logs app-app-1 --tail 50       # local dev logs
```

There are no unit tests. Testing is done via ephemeral PR test environments on EC2.

## Architecture

### Entry Point & Bot Setup
`src/app/main.py` — Bot initialization, logging config, slash command sync, database init with migration runner, and the core `on_message` listener that handles URL repost detection.

### Cogs (Command Modules)
Located in `src/app/cogs/`. Loaded dynamically on startup from `main.py`:
- `general.py` — `/hello`, `/gif`, `/bant` commands
- `cod.py` — `/wz` Call of Duty stats lookup
- `pubg.py` — `/pubg` random loadout generator
- `chat.py` — AI chat, memory extraction, sentiment tracking, emoji reactions

### Database Layer
`src/app/database/`:
- `database.py` — SQLAlchemy engine setup, PostgreSQL connection with retry logic (30 attempts), auto-creates database if missing
- `orm.py` — Models: `Link` (URL tracking), `LinkExclusion` (URL patterns to skip), `StartupHistory` (boot timestamps), `UserMemory` (per-user facts), `BotMemory` (server/relationship facts), `UserSentiment` (opinion scores per user)
- `migrations.py` — Lightweight migration runner. Migrations are registered functions tracked in a `schema_migrations` table. Runs automatically on startup after `create_all`.

### Chat Cog (`cogs/chat.py`) — Key Design Decisions

**Response flow**: `on_message` → engagement check → `_generate_response` → optional `[REACT]` conversion → split & send with typing delays → background memory/sentiment extraction.

**Engagement modes**:
- Direct mention: always responds
- Engagement mode: if bot recently responded in a channel, uses a quick Haiku call to decide if the next message warrants a reply
- Random chime-in: small chance (2% base, 15% with keywords) with per-channel cooldown

**Humanizing behaviors**:
- Typing indicator shown per-chunk, not wrapping the whole response
- Responses split into natural chat-sized chunks (1-2 sentences) with random delays between them
- Bot can choose to react with an emoji instead of responding (LLM-driven, via `[REACT]` token in system prompt). Prefers custom server emojis inferred by name.

**Memory system**:
- Single background Claude Haiku call per response extracts both memories and sentiment updates
- User memories: 50 stored per user, 30 queried per call
- Bot memories: 100 stored total, 30 queried per call
- Extraction prompt is deliberately restrictive — most conversations produce no memories. Only facts useful weeks later are stored.
- Memories injected into system prompt alongside sentiment for context-aware responses

**Sentiment system**:
- `UserSentiment` row auto-created (score 0.0) on first interaction — deterministic, not LLM-dependent
- Score range: -5.0 (nemesis) to +5.0 (best friend), stored as float
- Delta per interaction clamped to [-1.0, +1.0], with guidance to default to 0
- First impressions (score at 0) shift more easily; established scores resist change
- Score thresholds map to behavioral instructions in system prompt (dismissive, curt, warm, favorite)
- Bot never mentions scores or rating systems

**Single API call principle**: Memory extraction and sentiment evaluation happen in a single background Haiku call, not separate calls. This keeps cost low and latency minimal.

### Environment Variables
- `TOKEN` — Discord bot token
- `ANTHROPIC_API_KEY` — Anthropic API key for Claude
- `CODUSER` / `CODPASS` — Call of Duty API credentials
- `DBUSER`, `DBPASS`, `DBNAME`, `DBHOST`, `DBPORT` — PostgreSQL connection
- `LOG_LEVEL` — Logging level (default: INFO)
- `PR_NUMBER`, `PR_TITLE`, `PR_URL` — Set automatically in PR test environments

## Deployment

- **Production**: Push to `master` triggers GitHub Actions (`deploy-to-ec2.yml`) which builds a Docker image, SCPs files to EC2, and runs `docker-compose up -d --build`. Migrations run automatically on startup.
- **PR Testing**: Opening a PR triggers `pull-request-test.yml`, which deploys an isolated bot+db instance per PR on a test server. Containers are named `bangabot_pr<N>` and auto-cleaned on PR close.
- **Docker**: App uses `gorialis/discord.py` base image. Compose runs two services: `app` (bot) and `db` (PostgreSQL with health checks).

## Key Patterns

- Slash commands use `@app_commands.command()` decorator pattern
- URL extraction uses the `urlextract` library in the `on_message` event
- Logging format: `YYYY-MM-DD HH:MM:SS [ENV] [LEVEL] Message` where ENV is `PROD` or `PR#xx`
- Database init retries with 2-second intervals; bot startup retries DB connection up to 5 times
- SQLAlchemy 1.4 (legacy mode) — use `engine.begin()` for transactional blocks, not `engine.connect()` with manual commit
- Adding new DB migrations: create a function in `migrations.py`, add it to the `MIGRATIONS` list. Idempotent checks recommended.

## Session Continuity

You are working on a long-running project across multiple sessions. At the start of every session, read `claude-progress.txt` before doing anything else to understand the current state of work.

At the end of every session, or before your context window fills, update `claude-progress.txt` with the following structure:

```
---
Last updated: [date and time]
Last completed task: [what you just finished]
Current status: [one sentence on where things stand]

### Completed
- [bullet list of finished work, newest first]

### In Progress
- [anything partially done, with notes on where you left off]

### Up Next
- [the next 2-3 tasks in priority order]

### Blockers / Notes
- [anything a future session needs to know: decisions made, weird bugs, workarounds used]
---
```

Rules:
- Never overwrite the file — always prepend a new entry so history is preserved.
- Be specific. "Fixed collision detection" is useless. "Fixed AABB collision in Player.ts — entities were tunneling at high velocity, clamped delta to max 8px per frame" is useful.
- If you are mid-task when context runs low, write your exact stopping point so the next session can resume without backtracking.
