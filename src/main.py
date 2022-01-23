import discord
import requests
import os
from discord.ext import commands

#init
bot = discord.Client()
bot = commands.Bot(command_prefix='!')

@bot.event
async def on_ready():
    print('Logged in as {0.user}'.format(bot))

# Handle listening to all incoming messages
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if 'big oof' in message.content.lower():
        await message.channel.send(file=discord.File('img/OOF.png'))

    # Explicit commands will not work without the following
    await bot.process_commands(message)

bot.load_extension('cogs.general')
bot.load_extension('cogs.cod')
bot.load_extension('cogs.pubg')
bot.run(os.getenv('TOKEN'))