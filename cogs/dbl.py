import topgg
import discord
from discord.ext import commands


class TopGG(commands.Cog):
    """Handles interactions with the top.gg API"""

    def __init__(self, bot):
        self.bot = bot
        self.token = self.bot.api_data['dbl_token'] # set this to your DBL token
        self.dblpy = topgg.DBLClient(self.bot, self.token, autopost=True) # Autopost will post your guild count every 30 minutes

    async def on_autopost_success():
        self.bot.logger.info("Server count posted successfully")


def setup(bot):
    bot.add_cog(TopGG(bot))
