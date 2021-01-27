import discord
import os
import requests

from keep_alive import keep_alive

client = discord.Client()

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('!hello'):
        await message.channel.send('Hello!')

    if message.content.startswith('big oof'):
        await message.channel.send(file=discord.File('img/OOF.png'))

keep_alive()
client.run(os.getenv('TOKEN'))