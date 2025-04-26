# BangaBot Log Monitoring Guide

This document explains how to effectively monitor logs for BangaBot in both production and test environments.

## Monitoring Options

### 1. Using the Monitor Script (Recommended)

The `monitor-logs.sh` script provides an easy way to monitor logs from both production and test environments:

```bash
# Make the script executable (first time only)
chmod +x monitor-logs.sh

# Monitor production bot logs
./monitor-logs.sh prod

# Monitor a specific PR test bot (e.g., PR #21)
./monitor-logs.sh test 21

# Show only the last 500 lines
./monitor-logs.sh prod --tail=500

# Show database logs instead of bot logs
./monitor-logs.sh prod --db

# Show all container logs
./monitor-logs.sh prod --all

# View logs without following (show and exit)
./monitor-logs.sh prod --no-follow
```

### 2. Using Docker Compose Directly

If you prefer using Docker commands directly:

```bash
# Production logs
sudo docker compose -f ~/bangabot/src/app/docker-compose.yml logs -f app

# Test environment logs (for PR #21)
sudo docker compose -f ~/bangabot_test/pr21/docker-compose.pr21.yml logs -f bangabot_pr21

# Database logs
sudo docker compose -f ~/bangabot/src/app/docker-compose.yml logs -f db
```

## Log Levels

The bot's logging level can be controlled by setting the `LOG_LEVEL` environment variable:

- `ERROR`: Only errors and critical issues
- `WARNING`: Errors and warnings
- `INFO` (default): General information plus warnings and errors
- `DEBUG`: Verbose output including all operations

### Changing Log Level

For production:
```bash
# Edit .env file
echo "LOG_LEVEL=DEBUG" >> ~/bangabot/src/app/.env

# Restart the container to apply change
sudo docker compose -f ~/bangabot/src/app/docker-compose.yml restart app
```

For test environments:
```bash
# Edit .env file
echo "LOG_LEVEL=DEBUG" >> ~/bangabot_test/pr21/.env

# Restart the container to apply change
sudo docker compose -f ~/bangabot_test/pr21/docker-compose.pr21.yml restart bangabot_pr21
```

## Log Format

Logs are formatted as:
```
YYYY-MM-DD HH:MM:SS [ENV] [LEVEL] Message
```

Where:
- `ENV` is either "PROD" or "PR#xx" for test environments
- `LEVEL` is the log level (INFO, DEBUG, WARNING, ERROR, CRITICAL)

## Understanding Common Log Messages

### Bot Startup
```
[INFO] Starting BangaBot...
[INFO] Logged in as BangaBot (123456789)
[INFO] Connected to 3 servers
[INFO] Loaded extension: cogs.general
```

### Database Operations
```
[INFO] Database initialized successfully!
[DEBUG] New URL saved: https://example.com... by User123
[INFO] URL matched: https://example.com...
[INFO] Repost detected from User456 - URL previously posted by User123
```

### Command Processing
```
[DEBUG] Command not found: !invalidcommand
[ERROR] Command error: Command raised an exception: ValueError: Invalid argument
```

## Log Rotation

Both production and test environments use Docker's built-in log rotation with:
- Maximum size of 20MB per log file
- Maximum of 5 log files kept

This prevents logs from consuming too much disk space on the server.

## Troubleshooting

If you need more detailed logs:
1. Set `LOG_LEVEL=DEBUG` in the environment
2. Restart the bot container
3. Monitor logs with `./monitor-logs.sh prod` or appropriate command
4. Return to `INFO` level once troubleshooting is complete