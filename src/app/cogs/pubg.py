import random
from discord.ext import commands
from discord import app_commands
import discord

# Guns
normalGuns = [
    'AR',
    'Sniper',
    'SMG',
    'DMR'
]

rareGuns = [
    'Crossbow',
    'EMT Gear',
    'LMG'
]

# Gun loadout "overrides"
normalOverrides = [
    'Keep the first guns you find.',
    'Shotty snipes!'
]

rareOverrides = [
    'Pistols ONLY.'
]

# Modifiers
mods = [
    'You must keep guns you get a kill with.',
    'Crate hunter.',
    'MAD MAX!',
    'GO BANGA!',
    'Demolitions EXPERT.'
]

class PUBG(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @app_commands.command(
        name="pubg",
        description='Bored of PUBG? Mix it up!')
    async def pubg(self, interaction: discord.Interaction):
        msg = interaction.user.name + '\'s loadout:\n'
        chosenGuns = []

        # 20% chance to override guns
        if random.randrange(1,5) == 1:
            overrides = normalOverrides
        
            if random.randrange(1,5) == 1:
                overrides += rareOverrides

            msg += random.choice(overrides)
        else:
            # 5% chance for each rare gun to be selected
            availableRareGuns = rareGuns[:]
            random.shuffle(availableRareGuns)
            for gun in availableRareGuns:
                if len(chosenGuns) == 2:
                    break
                if random.randrange(1,20) == 1:
                    chosenGuns.append(gun)
                    availableRareGuns.remove(gun)

            # Then fill in empty guns with normal guns
            availableGuns = normalGuns[:]
            random.shuffle(availableGuns)
            while len(chosenGuns) < 2:
                randomGun = random.choice(availableGuns)
                chosenGuns.append(randomGun)
                availableGuns.remove(randomGun)

            msg += chosenGuns[0] + ' + ' + chosenGuns[1]
        
        # Each mod has less of a chance, starting at 10%
        modChance = 15
        activeMods = []
        random.shuffle(mods)
        for mod in mods:
            if random.randrange(1,modChance) == 1:
                activeMods.append(mod)
                modChance *= 2
        
        if len(activeMods) >= 1:
            msg += '\n\nActive mods:\n' +  ' '.join(activeMods)

        await interaction.response.send_message(msg)

async def setup(bot):
    await bot.add_cog(PUBG(bot))