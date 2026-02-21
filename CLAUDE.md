# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BangaBot is a Discord bot built with discord.py 2.3.2 (Python 3.9). Its primary feature is repost detection — tracking URLs shared in Discord channels and alerting when duplicates are posted. It also includes fun commands (CoD stats, PUBG loadout randomizer, greetings, GIFs).

## Build & Run Commands

```bash
# Run locally with Docker Compose (starts bot + PostgreSQL)
cd src/app && docker-compose up -d --build

# Lint (matches CI config — critical errors only)
flake8 src/app --count --select=E9,F63,F7,F82 --show-source --statistics

# Lint (warnings — max complexity 10, line length 127)
flake8 src/app --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

# Monitor logs
./monitor-logs.sh prod                # production app logs
./monitor-logs.sh test <PR_NUMBER>    # PR test environment logs
```

There are no unit tests. Testing is done via ephemeral PR test environments on EC2.

## Architecture

### Entry Point & Bot Setup
`src/app/main.py` — Bot initialization, logging config, slash command sync, and the core `on_message` listener that handles URL repost detection.

### Cogs (Command Modules)
Located in `src/app/cogs/`. Loaded dynamically on startup from `main.py`:
- `general.py` — `/hello`, `/gif`, `/bant` commands
- `cod.py` — `/wz` Call of Duty stats lookup
- `pubg.py` — `/pubg` random loadout generator

### Database Layer
`src/app/database/`:
- `database.py` — SQLAlchemy engine setup, PostgreSQL connection with retry logic (30 attempts), auto-creates database if missing
- `orm.py` — Three models: `Link` (URL tracking), `LinkExclusion` (URL patterns to skip), `StartupHistory` (boot timestamps)

### Environment Variables
- `TOKEN` — Discord bot token
- `CODUSER` / `CODPASS` — Call of Duty API credentials
- `DBUSER`, `DBPASS`, `DBNAME`, `DBHOST`, `DBPORT` — PostgreSQL connection
- `LOG_LEVEL` — Logging level (default: INFO)
- `PR_NUMBER`, `PR_TITLE`, `PR_URL` — Set automatically in PR test environments

## Deployment

- **Production**: Push to `master` triggers GitHub Actions (`deploy-to-ec2.yml`) which builds a Docker image, SCPs files to EC2, and runs `docker-compose up -d --build`.
- **PR Testing**: Opening a PR triggers `pull-request-test.yml`, which deploys an isolated bot+db instance per PR on a test server. Containers are named `bangabot_pr<N>` and auto-cleaned on PR close.
- **Docker**: App uses `gorialis/discord.py` base image. Compose runs two services: `app` (bot) and `db` (PostgreSQL with health checks).

## Key Patterns

- Slash commands use `@app_commands.command()` decorator pattern
- URL extraction uses the `urlextract` library in the `on_message` event
- Logging format: `YYYY-MM-DD HH:MM:SS [ENV] [LEVEL] Message` where ENV is `PROD` or `PR#xx`
- Database init retries with 2-second intervals; bot startup retries DB connection up to 5 times
