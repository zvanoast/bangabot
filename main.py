import asyncio
import discord
import os
import requests
import callofduty
from callofduty import Mode, Platform, Title
from keep_alive import keep_alive

#init
client = discord.Client()
#cod = await callofduty.Login(os.getenv('CODUSER'),os.getenv('CODPASS'))
#cod = await callofduty.Login('***REMOVED***','***REMOVED***')


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

    if message.content.startswith('!codtest'):
        try:
            cod = await callofduty.Login(os.getenv('CODUSER'),os.getenv('CODPASS'))
            username = message.content.split(' ')[1]
            result = await cod.SearchPlayers(Platform.BattleNet, username, limit=1)
            profile = await result[0].profile(Title.ModernWarfare, Mode.Warzone)

            level = profile["level"]
            kills = profile["weekly"]["mode"]["br_rebirth_rbrthquad"]["properties"]["kills"]
            deaths = profile["weekly"]["mode"]["br_rebirth_rbrthquad"]["properties"]["deaths"]
            kd = profile["weekly"]["mode"]["br_rebirth_rbrthquad"]["properties"]["kdRatio"]

            #wl = profile["weekly"]["mode"]["br_rebirth_rbrthquad"]["properties"]["wins"] / profile["lifetime"]["mode"]["br_all"]["properties"]["gamesPlayed"]

            await message.channel.send(f"Zoney rebirth quads weekly stats: \n{result[0].username} ({result[0].platform.name}) Level: {level}\nKills: {kills}, Deaths: {deaths}, K/D Ratio: {kd}")
            #await message.
        except ValueError:
            await message.channel.send("The proper usage is '!codtest USERNAME#1111'")

keep_alive()
client.run(os.getenv('TOKEN'))