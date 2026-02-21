# Lambda Refactor Plan

> **Status: Proposed / Future Reference**
> This document is a reference plan only. BangaBot currently runs on EC2 with a persistent WebSocket connection via discord.py. This refactor has **not** been implemented.

## Motivation & Trade-offs

### Why consider Lambda?
- **Cost savings**: A t2.micro EC2 instance running 24/7 costs ~$100/year. Lambda's free tier (1M requests/month, 400,000 GB-seconds) would bring that to effectively $0 for a low-traffic Discord bot responding to slash commands.
- **No server management**: No EC2 instance to patch, monitor, or SSH into.
- **Auto-scaling**: Lambda handles spikes without any configuration.

### What you lose
- **`on_message` event handling**: Lambda can only respond to Discord Interactions (slash commands, buttons, modals). It cannot listen to every message in a channel. This means:
  - **URL repost detection is lost** — the core feature of BangaBot relies on `on_message` to scan every message for URLs and check them against the database.
  - **"Big oof" easter egg is lost** — triggered by detecting `big oof` in any message via `on_message`.
- **Persistent state**: No long-running process means no in-memory state, persistent DB sessions, or background tasks.
- **Cold starts**: First invocation after idle may add 1-3 seconds of latency.

### Bottom line
Lambda is a good fit **only if** you're willing to drop `on_message`-based features (repost detection, easter eggs) or find an alternative way to handle them (e.g., a separate minimal bot on a cheap VPS just for message listening).

---

## Architecture Overview

### Current (EC2)
```
Discord <--WebSocket--> EC2 (docker-compose)
                          ├── app (discord.py bot, persistent connection)
                          └── db  (PostgreSQL)
```

### Proposed (Lambda)
```
Discord --HTTPS POST--> API Gateway --> Lambda (interaction handler)
                                           └──> DynamoDB (if storage needed)
```

- **Discord sends Interactions** (slash commands) as HTTPS POST requests to a configured endpoint URL.
- **API Gateway** receives the POST and forwards it to Lambda.
- **Lambda** validates the request signature, parses the interaction, and returns a JSON response.
- **DynamoDB** replaces PostgreSQL for any data that still needs persistence (e.g., CoD API creds lookup, startup history).

---

## Command-by-Command Migration Notes

### Slash Commands (can migrate)

| Command | Current Behavior | Lambda Notes |
|---------|-----------------|--------------|
| `/hello` | Returns a time-of-day greeting with 5% easter egg chance | Straightforward. All logic is self-contained (random + time check). Return greeting as interaction response. |
| `/gif <arg>` | Sends a GIF file (`danayeah.gif`, `danabummed.gif`, `danathumbsup.gif`) | GIF files need to be bundled in the Lambda deployment package or hosted in S3. Lambda responses must return within 3 seconds; file uploads may need a deferred response. |
| `/bant` | Sends `repostBANT.png` | Same as `/gif` — bundle image or host in S3. |
| `/codtest <username>` | Looks up CoD Warzone stats via `callofduty` library | The `callofduty` library does async HTTP calls. Lambda supports `asyncio` but the library and its dependencies would need to be included in the deployment package. CoD API credentials via environment variables (same pattern). |
| `/pubg` | Generates a random PUBG loadout | Fully self-contained random logic. Easiest command to migrate. |

### Features That Cannot Migrate

| Feature | Why It Can't Migrate |
|---------|---------------------|
| **URL repost detection** | Requires `on_message` to intercept every message, extract URLs with `urlextract`, and query the database. Discord Interactions API does not deliver regular messages to a webhook endpoint. |
| **"Big oof" easter egg** | Requires `on_message` to scan message content for the phrase `big oof`. Same limitation as above. |
| **`!sync` owner command** | Prefix command (`!sync`) used to manually sync slash commands. Not applicable in Lambda model since commands are registered via the Discord API directly. |

### Database Models That Become Unnecessary

| Model | Purpose | Lambda Status |
|-------|---------|---------------|
| `Link` | Stores URLs for repost detection | Not needed (repost detection can't work) |
| `LinkExclusion` | URL patterns to skip during repost checks | Not needed |
| `StartupHistory` | Logs bot startup timestamps | Not applicable (no persistent process) |

---

## Recommended Tech Choices

| Concern | Recommendation |
|---------|---------------|
| **Interaction handling** | [`discord-interactions`](https://github.com/discord/discord-interactions-python) — lightweight library for validating Discord interaction signatures and parsing payloads. No WebSocket, no bot token needed for basic responses. |
| **HTTP framework** | None needed if using API Gateway + Lambda directly. Alternatively, use a thin wrapper like `mangum` if you want Flask/FastAPI locally. |
| **Storage** | **DynamoDB** — serverless, pay-per-request, no provisioning. Only needed if you want to persist data (e.g., CoD stats cache). For this bot's slash commands, storage may not be needed at all. |
| **Deployment** | **AWS SAM** (Serverless Application Model) — define Lambda + API Gateway + DynamoDB in a single `template.yaml`. `sam build && sam deploy` handles packaging and CloudFormation. |
| **Image/file hosting** | **S3** — upload GIF/PNG assets to an S3 bucket. Lambda reads from S3 at runtime or embeds a public URL in the response. Alternatively, bundle small files (<50 MB total) directly in the Lambda deployment package. |

---

## Sample Lambda Handler Skeleton

```python
import json
import os
from discord_interactions import verify_key, InteractionType, InteractionResponseType

DISCORD_PUBLIC_KEY = os.environ["DISCORD_PUBLIC_KEY"]


def lambda_handler(event, context):
    # Parse the incoming request
    body = event.get("body", "")
    signature = event["headers"].get("x-signature-ed25519", "")
    timestamp = event["headers"].get("x-signature-timestamp", "")

    # Verify the request signature (required by Discord)
    if not verify_key(body.encode(), signature, timestamp, DISCORD_PUBLIC_KEY):
        return {"statusCode": 401, "body": "Invalid signature"}

    data = json.loads(body)

    # Handle Discord's PING verification (used when setting the endpoint URL)
    if data["type"] == InteractionType.PING:
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"type": InteractionResponseType.PONG}),
        }

    # Handle slash commands
    if data["type"] == InteractionType.APPLICATION_COMMAND:
        command_name = data["data"]["name"]

        if command_name == "hello":
            return _respond(determine_greeting())

        elif command_name == "pubg":
            return _respond(generate_pubg_loadout(data))

        elif command_name == "gif":
            arg = data["data"]["options"][0]["value"]
            return _respond_with_gif(arg)

        elif command_name == "bant":
            return _respond_with_file("repostBANT.png")

        elif command_name == "codtest":
            # CoD stats require async HTTP — use a deferred response
            # and follow up via the interaction webhook
            return _defer_and_process_cod(data)

    return {"statusCode": 400, "body": "Unhandled interaction type"}


def _respond(content: str):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "type": InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {"content": content},
        }),
    }


def determine_greeting():
    """Port of General.determineGreeting() — random + time-based greeting."""
    import random
    from datetime import datetime
    import pytz

    # 5% easter egg chance
    uncommon = ["BEEEWARE THE MILKY PIRATE!", "BANGA DOOTS?",
                "Piss off, innit!", "Oh shit waddup"]
    if random.randint(1, 100) <= 5:
        return random.choice(uncommon)

    est = pytz.timezone("US/Eastern")
    hour = datetime.now(tz=est).hour

    if 5 <= hour < 12:
        return random.choice(["Good morning!", "Not before my coffee..."])
    elif 12 <= hour < 17:
        return random.choice(["Good afternoon.", "Is it 5 o'clock yet?"])
    elif 17 <= hour < 22:
        return "Good evening."
    else:
        return random.choice(["Hello!", "Hello there.", "How's it going?",
                              "Hi.", "What's up?", "Yo!", "Sup?", "Hey there."])


def generate_pubg_loadout(data):
    """Port of PUBG.pubg() — random loadout generator."""
    # ... (port the logic from cogs/pubg.py)
    pass


def _respond_with_gif(arg):
    """For file responses, use a deferred response + follow-up with file upload."""
    # Discord Interactions API doesn't support file uploads in the initial response.
    # Use InteractionResponseType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE,
    # then POST the file to the follow-up webhook endpoint.
    pass


def _respond_with_file(filename):
    """Same deferred pattern as _respond_with_gif."""
    pass


def _defer_and_process_cod(data):
    """Defer response, then call CoD API and send follow-up."""
    pass
```

---

## Deployment Steps

### 1. Register slash commands with Discord

Slash commands must be registered via the Discord API (not auto-synced by a bot). Use a one-time script:

```python
import requests

APP_ID = "your-application-id"
BOT_TOKEN = "your-bot-token"

commands = [
    {"name": "hello", "description": "Say hello to BangaBot"},
    {"name": "gif", "description": "Show a gif", "options": [
        {"name": "arg", "description": "The gif type (y, b, tu)",
         "type": 3, "required": True}  # type 3 = STRING
    ]},
    {"name": "bant", "description": "When someone reposts"},
    {"name": "pubg", "description": "Bored of PUBG? Mix it up!"},
    {"name": "codtest", "description": "Shows some dumb weekly warzone rebirth stats", "options": [
        {"name": "username", "description": "Your Battle.net username",
         "type": 3, "required": False}
    ]},
]

for cmd in commands:
    r = requests.post(
        f"https://discord.com/api/v10/applications/{APP_ID}/commands",
        json=cmd,
        headers={"Authorization": f"Bot {BOT_TOKEN}"}
    )
    print(f"{cmd['name']}: {r.status_code}")
```

### 2. SAM template outline

```yaml
AWSTemplateFormatVersion: "2010-09-09"
Transform: AWS::Serverless-2016-10-31
Description: BangaBot Discord Interactions Handler

Globals:
  Function:
    Timeout: 10
    MemorySize: 128
    Runtime: python3.9

Resources:
  BangaBotFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: handler.lambda_handler
      CodeUri: src/
      Environment:
        Variables:
          DISCORD_PUBLIC_KEY: !Ref DiscordPublicKey
          CODUSER: !Ref CodUser
          CODPASS: !Ref CodPass
      Events:
        DiscordInteraction:
          Type: Api
          Properties:
            Path: /interactions
            Method: POST

  # Optional: DynamoDB table (only if you need storage)
  # BangaBotTable:
  #   Type: AWS::DynamoDB::Table
  #   Properties:
  #     TableName: bangabot
  #     AttributeDefinitions:
  #       - AttributeName: pk
  #         AttributeType: S
  #     KeySchema:
  #       - AttributeName: pk
  #         KeyType: HASH
  #     BillingMode: PAY_PER_REQUEST

Parameters:
  DiscordPublicKey:
    Type: String
  CodUser:
    Type: String
  CodPass:
    Type: String
    NoEcho: true

Outputs:
  InteractionEndpoint:
    Description: "Set this as your Discord Application Interactions Endpoint URL"
    Value: !Sub "https://${ServerlessRestApi}.execute-api.${AWS::Region}.amazonaws.com/Prod/interactions"
```

### 3. Deploy

```bash
sam build
sam deploy --guided  # First time — sets up S3 bucket, stack name, parameters
sam deploy           # Subsequent deploys
```

### 4. Configure Discord

1. Go to [Discord Developer Portal](https://discord.com/developers/applications) > your application.
2. Under **General Information**, set **Interactions Endpoint URL** to the API Gateway URL from the SAM output.
3. Discord will send a PING to verify — your Lambda must respond with a PONG (handled in the skeleton above).

---

## Cost Comparison

| Item | EC2 (current) | Lambda (proposed) |
|------|--------------|-------------------|
| Compute | t2.micro ~$8.50/month ($102/year) | Free tier: 1M requests + 400K GB-sec/month. A low-traffic bot likely stays at **$0/month**. |
| Database | PostgreSQL in Docker (no extra cost, runs on same EC2) | DynamoDB free tier: 25 GB storage + 25 read/write capacity units. **$0/month** for this use case. |
| Storage | EBS volume included with EC2 | S3 for assets: negligible (<$0.01/month). |
| **Total** | **~$102/year** | **~$0/year** (within free tier) |

**Note**: Lambda free tier is per-account. If you run other Lambda functions, the free tier is shared.

---

## Summary

This refactor would save ~$100/year by moving from EC2 to Lambda, but at the cost of losing BangaBot's primary feature: URL repost detection. The slash commands (`/hello`, `/gif`, `/bant`, `/pubg`, `/codtest`) can all be ported to Lambda with moderate effort. The `on_message`-based features (repost detection, "big oof") cannot work under the Discord Interactions model.

**Recommendation**: Keep the current EC2 setup as long as repost detection is a valued feature. Revisit this plan if:
- Repost detection is no longer needed
- Discord adds a way to forward message events to webhooks
- A hybrid approach becomes viable (Lambda for commands + cheap VPS for message listening)
