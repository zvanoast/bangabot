# BangaBot

A Discord bot for the boys. Detects reposts, roasts people, and develops opinions about everyone in the server.

## Features

**Repost Detection** — Tracks every URL shared in the server. Post a duplicate and BangaBot will call you out with the original poster, date, and a link to the original message.

**AI Chat** — Powered by Claude (Haiku). BangaBot has a personality: dry, well-read, a little full of himself. He randomly chimes into conversations, responds when mentioned, and stays engaged in active threads. Sometimes he just reacts with an emoji when he has nothing to add — like a real person would.

**Memory System** — Remembers facts about users and the server across conversations. Personal details, preferences, inside jokes — anything worth recalling weeks later. Memories are stored in PostgreSQL and injected into the system prompt when relevant.

**User Sentiment** — Develops persistent opinions about each user on a -5.0 to +5.0 scale. Sentiment shifts slowly over many interactions: favorites get warmth, nemeses get roasted. The bot never mentions scores — it just embodies the attitude naturally.

**Fun Commands**
- `/wz` — Call of Duty stats lookup
- `/pubg` — Random PUBG loadout generator
- `/hello` — Greeting
- `/gif` — GIF response
- `/bant` — You know what this is

## Running Locally

```bash
# Start bot + PostgreSQL with Docker Compose
cd src/app && docker-compose up -d --build

# Check logs
docker logs app-app-1 --tail 50
```

Requires a `.env` file in `src/app/` with:
- `TOKEN` — Discord bot token
- `ANTHROPIC_API_KEY` — For AI chat features
- `DBUSER`, `DBPASS`, `DBNAME`, `DBHOST`, `DBPORT` — PostgreSQL connection
- `CODUSER`, `CODPASS` — Call of Duty API credentials (optional)

## Deployment

Push to `master` triggers automatic deployment to EC2 via GitHub Actions. PR branches get ephemeral test environments with their own bot instance and database.

## Tech Stack

- Python 3.9 / discord.py 2.3.2
- PostgreSQL + SQLAlchemy 1.4
- Claude Haiku (via Anthropic API) for chat, memory extraction, and sentiment evaluation
- Docker Compose for local dev and production
- GitHub Actions for CI/CD
