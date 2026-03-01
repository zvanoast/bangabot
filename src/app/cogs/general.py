import datetime
import logging
import discord
import pytz
import random
from discord.ext import commands
from discord import app_commands
from database.orm import LinkExclusion

logger = logging.getLogger('bangabot')

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    commonResponses = [
        'Hello!',
        'Hello there.',
        'How''s it going?',
        'Hi.',
        'What''s up?',
        'Yo!',
        'Sup?',
        'Hey there.'
        ]

    uncommonResponses = [
        'BEEEWARE THE MILKY PIRATE!',
        'BANGA DOOTS?',
        'Piss off, innit!',
        'Oh shit waddup'
    ]

    morningResponses = [
        'Good morning!',
        'Not before my coffee...'
    ]

    afternoonResponses = [
        'Good afternoon.',
        'Is it 5 o''clock yet?'
    ]

    eveningResponses = [
        'Good evening.',
    ]

    # Commands
    @app_commands.command(
        name="hello",
        description='Say hello to BangaBot')
    async def hello(self, interaction: discord.Interaction):
        await interaction.response.send_message(self.determineGreeting())

    @app_commands.command(
        name="gif",
        description='Show a gif. Current options: yeah(y), bummed(b), thumbsup(tu). More to come')
    @app_commands.describe(arg="The gif type (y, b, tu)")
    async def gif(self, interaction: discord.Interaction, arg: str):
        if arg == 'y' or arg == 'yeah' or arg == 'yes':
            await interaction.response.send_message(file=discord.File('src/img/danayeah.gif'))
        elif arg == 'b' or arg == 'bummed':
            await interaction.response.send_message(file=discord.File('src/img/danabummed.gif'))
        elif arg == 'tu' or arg == 'thumbsup' or arg == 'thumbs up':
            await interaction.response.send_message(file=discord.File('src/img/danathumbsup.gif'))
        else:
            await interaction.response.send_message('Invalid argument passed.')

    @app_commands.command(
        name="bant",
        description='When someone reposts')
    async def bant(self, interaction: discord.Interaction):
        await interaction.response.send_message(file=discord.File('src/img/repostBANT.png'))
    
    @app_commands.command(
        name="exclude-link",
        description='Add a URL pattern to exclude from repost detection')
    @app_commands.describe(url="Base URL to exclude (e.g. giphy.com, tenor.com)")
    async def exclude_link(self, interaction: discord.Interaction, url: str):
        db = self.bot.db
        if db is None:
            await interaction.response.send_message(
                "Database not available.", ephemeral=True)
            return

        # Check if already excluded
        existing = db.query(LinkExclusion).filter(
            LinkExclusion.url == url).first()
        if existing:
            await interaction.response.send_message(
                f"`{url}` is already excluded.", ephemeral=True)
            return

        exclusion = LinkExclusion(url)
        db.add(exclusion)
        db.commit()
        logger.info(
            f"Link exclusion added by {interaction.user.name}: {url}")
        await interaction.response.send_message(
            f"Added `{url}` to repost exclusions. "
            f"URLs containing this pattern will be ignored.")

    @app_commands.command(
        name="include-link",
        description='Remove a URL pattern from the exclusion list')
    @app_commands.describe(url="The URL pattern to remove from exclusions")
    async def include_link(self, interaction: discord.Interaction, url: str):
        db = self.bot.db
        if db is None:
            await interaction.response.send_message(
                "Database not available.", ephemeral=True)
            return

        existing = db.query(LinkExclusion).filter(
            LinkExclusion.url == url).first()
        if not existing:
            await interaction.response.send_message(
                f"`{url}` is not in the exclusion list.", ephemeral=True)
            return

        db.delete(existing)
        db.commit()
        logger.info(
            f"Link exclusion removed by {interaction.user.name}: {url}")
        await interaction.response.send_message(
            f"Removed `{url}` from repost exclusions.")

    @app_commands.command(
        name="list-exclusions",
        description='Show all URL patterns excluded from repost detection')
    async def list_exclusions(self, interaction: discord.Interaction):
        db = self.bot.db
        if db is None:
            await interaction.response.send_message(
                "Database not available.", ephemeral=True)
            return

        exclusions = db.query(LinkExclusion).all()
        if not exclusions:
            await interaction.response.send_message(
                "No URL exclusions set.", ephemeral=True)
            return

        lines = [f"- `{e.url}`" for e in exclusions]
        await interaction.response.send_message(
            "**Excluded URL patterns:**\n" + "\n".join(lines))

    def determineGreeting(self):
        easterEgg = random.randint(1, 100)
        
        if easterEgg <= 5:
            return self.uncommonResponses[random.randint(0, len(self.uncommonResponses) - 1)]
        
        est = pytz.timezone('US/Eastern')
        hour = datetime.datetime.now(tz=est).hour

        if 5 <= hour < 12:
            return self.morningResponses[random.randint(0, len(self.morningResponses) - 1)]
        elif 12 <= hour < 17:
            return self.afternoonResponses[random.randint(0, len(self.afternoonResponses) - 1)]
        elif 17 <= hour < 22:
            return self.eveningResponses[random.randint(0, len(self.eveningResponses) - 1)]
        else:
            return self.commonResponses[random.randint(0, len(self.commonResponses) - 1)]

async def setup(bot):
    await bot.add_cog(General(bot))
