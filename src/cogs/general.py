import datetime
import discord
import pytz
import random
from discord.ext import commands

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
        'Sup bitchtits?',
        'Piss off, innit!',
        'Oh shit waddup',
        'FUCK SALT!'
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
    @commands.command(
        brief='Say hello to BangaBot',
        description='Say hello to BangaBot')
    async def hello(self, ctx):
        await ctx.message.channel.send(self.determineGreeting())

    @commands.command(
        brief='Show a gif',
        description='Show a gif. Current options: dana yeah(y), dana bummed(b), dana thumbsup(tu)')
    async def gif(self, ctx, arg, arg2):
        if arg == 'dana':
            if arg2 == 'yeah' or arg2 == 'y':
                await ctx.message.channel.send(file=discord.File('img/danayeah.gif'))
            if arg2 == 'bummed' or arg2 == 'b':
                await ctx.message.channel.send(file=discord.File('img/danabummed.gif'))
            if arg2 == 'thumbsup' or arg2 == 'tu':
                await ctx.message.channel.send(file=discord.File('img/danathumbsup.gif'))

    @commands.command(
        brief='Repost.. BANT',
        description='Repost.. BANT')
    async def bant(self, ctx):
        await ctx.message.channel.send(file=discord.File('img/repostBANT.png'))

    # Helper functions
    def determineGreeting(self):
        responses = []
        responses.extend(self.commonResponses)

        eastern = pytz.timezone('US/Eastern')
        currentEasternTime = datetime.datetime.now(eastern).time()
        print('The current time is: ' + format(currentEasternTime))

        morningStart = datetime.time(5, 0, 0)
        morningEnd = datetime.time(11, 59, 0)
        afternoonStart = datetime.time(12, 0, 0)
        afternoonEnd = datetime.time(16, 59, 0)
        # eveningStart = datetime.time(17, 0, 0)
        # eveningEnd = datetime.time(4, 59, 00)

        if self.isTimeInRange(morningStart, morningEnd, currentEasternTime):
            responses.extend(self.morningResponses)
        elif self.isTimeInRange(afternoonStart, afternoonEnd, currentEasternTime):
            responses.extend(self.afternoonResponses)
        else:
            responses.extend(self.eveningResponses)

        rand = random.randrange(1,50)
        print('rand is ' + str(rand))
        if rand == 23:
            responses.extend(self.uncommonResponses)

        return random.choice(responses)

    def isTimeInRange(self, start, end, x):
        if start <= end:
            return start <= x <= end
        else:
            return start <= x or x <= end

def setup(bot):
    bot.add_cog(General(bot))