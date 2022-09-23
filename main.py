import discord

from bot import ClanBot, get_prefix
from discord.ext import commands


if __name__ == '__main__':
    intents = discord.Intents.default()
    intents.members = True
    b = ClanBot(command_prefix=get_prefix, intents=intents, chunk_guilds_at_startup=False)

    b.start_up()
