import datetime
import discord
import pytz
import random
from discord.ext import commands
from discord import app_commands

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
        'Hey there.',
        'Greetings!',
        'Howdy!',
        'Salutations!',
        'What''s good?',
        'What''s poppin?',
        'What''s crackin?',
        'What''s shakin?',
        'What''s cooking?',
        'What''s the word?',
        'What''s the haps?',
        'What''s the scoop?',
        'What''s the deal?',
        'What''s the sitch?',
        'What''s the 411?',
        'What''s the vibe?',
        'What''s the buzz?',
        'What''s the lowdown?',
        'What''s the skinny?',
        'What''s the story?',
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
