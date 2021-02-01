import callofduty
import discord
import os
from callofduty import Mode, Platform, Title
from discord.ext import commands

class COD(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        brief='Shows some dumb weekly warzone rebirth stats',
        description='Shows some dumb weekly warzone rebirth stats. Usage: "!codtest Username#1234"')
    async def codtest(self, ctx):
        try:
            cod = await callofduty.Login(os.getenv('CODUSER'),os.getenv('CODPASS'))
            username = ctx.message.split(' ')[1]
            result = await cod.SearchPlayers(Platform.BattleNet, username, limit=1)
            profile = await result[0].profile(Title.ModernWarfare, Mode.Warzone)

            level = profile["level"]
            kills = profile["weekly"]["mode"]["br_mini_rebirth_mini_royale_quads"]["properties"]["kills"]
            deaths = profile["weekly"]["mode"]["br_mini_rebirth_mini_royale_quads"]["properties"]["deaths"]
            kd = profile["weekly"]["mode"]["br_mini_rebirth_mini_royale_quads"]["properties"]["kdRatio"]
            killsPerGame = profile["weekly"]["mode"]["br_mini_rebirth_mini_royale_quads"]["properties"]["killsPerGame"]

            await ctx.message.channel.send(f"Zoney rebirth quads weekly stats: \n{result[0].username} ({result[0].platform.name}) Level: {level}\nKills: {kills}, Deaths: {deaths}, K/D Ratio: {kd}, Kills per game: {killsPerGame}")
        except Exception:
            await ctx.message.channel.send('The proper usage is "!codtest Username#1234"')

def setup(bot):
    bot.add_cog(COD(bot))