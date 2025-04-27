import callofduty
import discord
import os
from callofduty import Mode, Platform, Title
from discord.ext import commands
from discord import app_commands

class COD(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="codtest",
        description='Shows some dumb weekly warzone rebirth stats')
    @app_commands.describe(username="Your Battle.net username (format: Username#1234)")
    async def codtest(self, interaction: discord.Interaction, username: str = None):
        try:
            if not username:
                await interaction.response.send_message('The proper usage is "/codtest Username#1234"')
                return
                
            cod = await callofduty.Login(os.getenv('CODUSER'),os.getenv('CODPASS'))
            result = await cod.SearchPlayers(Platform.BattleNet, username, limit=1)
            profile = await result[0].profile(Title.ModernWarfare, Mode.Warzone)

            level = profile["level"]
            kills = profile["weekly"]["mode"]["br_mini_rebirth_mini_royale_quads"]["properties"]["kills"]
            deaths = profile["weekly"]["mode"]["br_mini_rebirth_mini_royale_quads"]["properties"]["deaths"]
            kd = profile["weekly"]["mode"]["br_mini_rebirth_mini_royale_quads"]["properties"]["properties"]["kdRatio"]
            killsPerGame = profile["weekly"]["mode"]["br_mini_rebirth_mini_royale_quads"]["properties"]["killsPerGame"]

            await interaction.response.send_message(f"Zoney rebirth quads weekly stats: \n{result[0].username} ({result[0].platform.name}) Level: {level}\nKills: {kills}, Deaths: {deaths}, K/D Ratio: {kd}, Kills per game: {killsPerGame}")
        except Exception as e:
            await interaction.response.send_message(f'Error: {str(e)}. The proper usage is "/codtest Username#1234"')

async def setup(bot):
    await bot.add_cog(COD(bot))