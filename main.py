import discord

from bot import ClanBot
from discord.ext import commands


def get_prefix(client, message):
    prefixes = ['?']
    if message.guild:
        prefixes = client.guild_prefix(message.guild.id)

    return commands.when_mentioned_or(*prefixes)(client, message)


if __name__ == '__main__':
    intents = discord.Intents.default()
    intents.members = True
    b = ClanBot(command_prefix=get_prefix, intents=intents, chunk_guilds_at_startup=False)

    b.start_up()
