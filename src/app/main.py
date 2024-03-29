import discord
import os
from pytz import timezone
from urlextract import URLExtract
from discord.ext import commands
from datetime import datetime
#db
from database.database import engine, Base, Session
from database.orm import Link, LinkExclusion, StartupHistory

#init
bot = discord.Client()
bot = commands.Bot(command_prefix='!')

#init DB
Base.metadata.create_all(engine)
db = Session()

#log startup history
history = StartupHistory(datetime.now())
db.add(history)
db.commit()

@bot.event
async def on_ready():
    print('Logged in as {0.user}'.format(bot))

# Handle listening to all incoming messages
@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    extractor = URLExtract()
    urls = extractor.find_urls(message.content, True, True, False, True)
    
    if len(urls) > 0:
        print('URL detected..')
        #to support testing and the off-chance DM to BangaBot
        if isinstance(message.channel,discord.DMChannel):
            channel_name = 'DM with ' + message.channel.me.name
        else:
            channel_name = message.channel.mention

        user = message.author.name
        datetime = message.created_at.replace(tzinfo = timezone('UTC'))
        jump_url = message.jump_url

        for url in urls:
            matched_links = db.query(Link) \
                .filter(Link.url == str(url)) \
                .all()
            
            if len(matched_links) > 0:
                print("URL matched.")
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
                        print("Matched url (aka loan) skipped due to exception!")

                if exclusion_found:
                    break

                matched_link_datetime = matched_link.date.astimezone(timezone('US/Eastern'))
                date = matched_link_datetime.strftime("%m/%d/%Y")
                time = matched_link_datetime.strftime("%H:%M:%S")

                repost_details = 'BANT! This url was posted by ' + matched_link.user + ' in ' + matched_link.channel + ' on ' + date + ' at ' + time + '\n' \
                    + matched_link.jump_url
                await message.channel.send(file=discord.File('src/img/repostBANT.png'))
                await message.channel.send(repost_details)
            else:
                link = Link(url, user, channel_name, datetime, jump_url)
                db.add(link)
                db.commit()
                print("URL saved")

        print(user, channel_name, datetime, jump_url)

    if 'big oof' in message.content.lower():
        await message.channel.send(file=discord.File('src/img/OOF.png'))

    # Explicit commands will not work without the following
    await bot.process_commands(message)

bot.load_extension('cogs.general')
bot.load_extension('cogs.cod')
bot.load_extension('cogs.pubg')
bot.run(os.getenv('TOKEN'))