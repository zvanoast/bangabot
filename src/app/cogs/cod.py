import callofduty
import discord
import os
from callofduty import Mode, Platform, Title
from discord.ext import commands

class COD(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(
        brief='Shows some dumb weekly warzone rebirth stats',
        description='Shows some dumb weekly warzone rebirth stats. Usage: "!codtest Username#1234"')
    async def codtest(self, ctx, username=None):
        try:
            if not username:
                await ctx.send('The proper usage is "!codtest Username#1234"')
                return
                
            cod = await callofduty.Login(os.getenv('CODUSER'),os.getenv('CODPASS'))
            result = await cod.SearchPlayers(Platform.BattleNet, username, limit=1)
            profile = await result[0].profile(Title.ModernWarfare, Mode.Warzone)

            level = profile["level"]
            kills = profile["weekly"]["mode"]["br_mini_rebirth_mini_royale_quads"]["properties"]["kills"]
            deaths = profile["weekly"]["mode"]["br_mini_rebirth_mini_royale_quads"]["properties"]["deaths"]
            kd = profile["weekly"]["mode"]["br_mini_rebirth_mini_royale_quads"]["properties"]["kdRatio"]
            killsPerGame = profile["weekly"]["mode"]["br_mini_rebirth_mini_royale_quads"]["properties"]["killsPerGame"]

            await ctx.send(f"Zoney rebirth quads weekly stats: \n{result[0].username} ({result[0].platform.name}) Level: {level}\nKills: {kills}, Deaths: {deaths}, K/D Ratio: {kd}, Kills per game: {killsPerGame}")
        except Exception as e:
            await ctx.send(f'Error: {str(e)}. The proper usage is "!codtest Username#1234"')

def setup(bot):
    bot.add_cog(COD(bot))