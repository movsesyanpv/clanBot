from discord.ext import commands
import discord


class Updates(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.guild_only()
    async def regnotifier(self, ctx, *args):
        message = ctx.message
        content = message.content.lower().split()
        notifier_type = 'notifiers'
        if len(content) >= 3 and 'seasonal' in message.content.lower():
            notifier_type = content[2]
        if await ctx.bot.check_ownership(message, is_silent=True, admin_check=True):
            ctx.bot.guild_cursor.execute('''INSERT or IGNORE into {} values (?,?)'''.format(notifier_type),
                                        (message.channel.id, message.guild.id))
            ctx.bot.guild_db.commit()
            ctx.bot.get_channels()
            msg = 'Got it, {}'.format(message.author.mention)
            await message.channel.send(msg, delete_after=10)
        await message.delete()
        return

    @commands.command()
    @commands.guild_only()
    async def rmnotifier(self, ctx, *args):
        message = ctx.message
        content = message.content.lower().split()
        notifier_type = 'notifiers'
        if len(content) >= 3 and 'seasonal' in message.content.lower():
            notifier_type = content[2]
        if await ctx.bot.check_ownership(message, is_silent=True, admin_check=True):
            ctx.bot.guild_cursor.execute('''DELETE FROM {} WHERE channel_id=?'''.format(notifier_type),
                                        (message.channel.id,))
            ctx.bot.guild_db.commit()
            ctx.bot.get_channels()
            msg = 'Got it, {}'.format(message.author.mention)
            await message.channel.send(msg, delete_after=10)
        await message.delete()
        return

    @commands.command()
    @commands.guild_only()
    async def setlang(self, ctx, lang):
        message = ctx.message
        if await ctx.bot.check_ownership(message, is_silent=True, admin_check=True):
            ctx.bot.guild_cursor.execute('''UPDATE language SET lang=? WHERE server_id=?''', (lang, ctx.message.guild.id))
            ctx.bot.guild_db.commit()
        msg = 'Got it, {}'.format(message.author.mention)
        await message.channel.send(msg, delete_after=10)
        await message.delete()
        return

    @commands.command()
    @commands.is_owner()
    async def update(self, ctx, *args):
        if ctx.message.guild is not None:
            await ctx.message.delete()
        for upd_type in args:
            await ctx.bot.force_update(upd_type)
        return

def setup(bot):
    bot.add_cog(Updates(bot))
