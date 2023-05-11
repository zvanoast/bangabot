FROM python:3

FROM gorialis/discord.py



RUN mkdir -p /usr/src/bot

WORKDIR /usr/src/bot



COPY . .



CMD [ "python3", "discord_bot.py" ]