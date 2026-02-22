import discord
import os
import time
import logging
import sys
from pytz import timezone
from urlextract import URLExtract
from discord.ext import commands
from datetime import datetime
#db
from database.database import engine, Base, Session
from database.orm import Link, LinkExclusion, StartupHistory
from database.orm import UserMemory, BotMemory  # noqa: F401 - register with Base.metadata

# Configure logging
def setup_logging():
    # Get environment variables or use defaults
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    is_test = 'PR_NUMBER' in os.environ
    env_name = f"PR#{os.getenv('PR_NUMBER')}" if is_test else "PROD"
    
    # Create logger
    logger = logging.getLogger('bangabot')
    logger.setLevel(getattr(logging, log_level))
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(
        f'%(asctime)s [{env_name}] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(console_handler)
    
    return logger

# Initialize logger
logger = setup_logging()

# Setup proper intents for the bot
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
intents.guilds = True           # For server info
intents.members = True          # For member details

# Initialize bot with proper intents and command settings for Discord.py 2.0+
bot = commands.Bot(
    command_prefix="!",  # Using a default prefix even if primarily using slash commands
    intents=intents,
    help_command=None,  # We'll use our own help command if needed
)

# Initialize database with retry logic
def initialize_database(max_retries=5, retry_interval=3):
    retries = 0
    while retries < max_retries:
        try:
            # Create tables
            Base.metadata.create_all(engine)
            db = Session()
            
            # Log startup history
            history = StartupHistory(datetime.now())
            db.add(history)
            db.commit()
            
            logger.info("Database initialized successfully!")
            return db
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            retries += 1
            logger.warning(f"Retrying in {retry_interval} seconds... (Attempt {retries}/{max_retries})")
            time.sleep(retry_interval)
    
    raise Exception(f"Failed to initialize database after {max_retries} attempts")

# Try to initialize database but don't crash the bot if it fails
try:
    db = initialize_database()
except Exception as e:
    logger.critical(f"Database initialization failed: {e}")
    logger.warning("Bot will continue without database functionality.")
    db = None

bot.db = db

@bot.event
async def on_ready():
    # Log connection details
    logger.info(f"Logged in as {bot.user.name} ({bot.user.id})")
    logger.info(f"Connected to {len(bot.guilds)} servers:")
    for guild in bot.guilds:
        logger.info(f"  - {guild.name} (ID: {guild.id}, Members: {len(guild.members)})")
    
    # Test environment info
    if 'PR_NUMBER' in os.environ:
        logger.info(f"Running in TEST environment for PR #{os.getenv('PR_NUMBER')}: {os.getenv('PR_TITLE', '')}")
    
    # Load extensions if not already loaded
    await load_extensions()
    
    # Sync commands with Discord
    try:
        logger.info("Syncing commands with Discord...")
        await bot.tree.sync()
        logger.info("Command synchronization complete!")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

# Handle listening to all incoming messages
@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    extractor = URLExtract()
    urls = extractor.find_urls(message.content, True, True, False, True)
    
    if len(urls) > 0:
        logger.debug(f'URL detected in message from {message.author.name}')
        #to support testing and the off-chance DM to BangaBot
        if isinstance(message.channel,discord.DMChannel):
            channel_name = 'DM with ' + message.channel.me.name
        else:
            channel_name = message.channel.mention

        user = message.author.name
        datetime = message.created_at.replace(tzinfo = timezone('UTC'))
        jump_url = message.jump_url

        for url in urls:
            # Skip database operations if db initialization failed
            if db is None:
                logger.warning("Skipping URL processing - database not available")
                break
                
            matched_links = db.query(Link) \
                .filter(Link.url == str(url)) \
                .all()
            
            if len(matched_links) > 0:
                logger.info(f"URL matched: {url[:50]}...")
                # should never be > 1
                matched_link : Link = matched_links[0]

                exclusions : list[LinkExclusion] = db.query(LinkExclusion).all()

                excluded_urls : list = []
                for exclusion in exclusions:
                    excluded_urls.append(exclusion.url)

                exclusion_found = False
                for e in excluded_urls:
                    if e in matched_link.url:
                        exclusion_found = True
                        logger.debug(f"Matched url skipped due to exception: {e}")

                if exclusion_found:
                    break

                matched_link_datetime = matched_link.date.astimezone(timezone('US/Eastern'))
                date = matched_link_datetime.strftime("%m/%d/%Y")
                time = matched_link_datetime.strftime("%H:%M:%S")

                repost_details = 'BANT! This url was posted by ' + matched_link.user + ' in ' + matched_link.channel + ' on ' + date + ' at ' + time + '\n' \
                    + matched_link.jump_url
                await message.channel.send(file=discord.File('src/img/repostBANT.png'))
                await message.channel.send(repost_details)
                logger.info(f"Repost detected from {user} - URL previously posted by {matched_link.user}")
            else:
                link = Link(url, user, channel_name, datetime, jump_url)
                db.add(link)
                db.commit()
                logger.debug(f"New URL saved: {url[:50]}... by {user}")

        logger.debug(f"Message details: {user}, {channel_name}, {datetime}, {jump_url}")

    if 'big oof' in message.content.lower():
        await message.channel.send(file=discord.File('src/img/OOF.png'))
        logger.debug(f"'Big oof' detected from {message.author.name}")

    # Explicit commands will not work without the following
    await bot.process_commands(message)

# Add error handling for commands
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        logger.debug(f"Command not found: {ctx.message.content}")
        return
        
    logger.error(f"Command error: {error} (Command: {ctx.command})")
    await ctx.send(f"Error executing command: {error}")

@bot.command(name='sync')
@commands.is_owner()
async def sync(ctx, guild_id: int = None):
    """Syncs slash commands to a specific guild or globally"""
    logger.info(f"Syncing slash commands requested by {ctx.author}")
    
    if guild_id:
        guild = discord.Object(id=guild_id)
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        await ctx.send(f"Synced commands to guild {guild_id}")
        logger.info(f"Synced commands to guild {guild_id}")
    else:
        await bot.tree.sync()
        await ctx.send("Synced commands globally")
        logger.info("Synced commands globally")

# Load extensions with error handling
async def load_extensions():
    for extension in ['cogs.general', 'cogs.cod', 'cogs.pubg', 'cogs.chat']:
        try:
            await bot.load_extension(extension)
            logger.info(f"Loaded extension: {extension}")
        except Exception as e:
            logger.error(f"Failed to load extension {extension}: {e}")

# Log that we're starting the bot
logger.info("Starting BangaBot...")
token = os.getenv('TOKEN')
if not token:
    logger.critical("TOKEN environment variable not set! Bot cannot start.")
    sys.exit(1)
else:
    logger.info("Discord token found, connecting to Discord...")
    bot.run(token)