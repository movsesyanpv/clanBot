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
        available_types = ['notifiers', 'seasonal', 'updates']
        notifier_type = 'notifiers'
        if len(args) > 0:
            if args[0] in available_types:
                notifier_type = args[0]
        if await ctx.bot.check_ownership(message, is_silent=True, admin_check=True):
            ctx.bot.guild_cursor.execute('''INSERT or IGNORE into {} values (?,?)'''.format(notifier_type),
                                        (message.channel.id, message.guild.id))
            ctx.bot.guild_db.commit()
            ctx.bot.get_channels()
            msg = 'Got it, {}'.format(message.author.mention)
            await message.channel.send(msg, delete_after=10)
        if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
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
        if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
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
        if ctx.guild.me.guild_permissions.change_nickname:
            await ctx.guild.me.edit(nick=ctx.bot.translations[lang]['nick'], reason='language change')
        await message.channel.send(msg, delete_after=10)
        if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
            await message.delete()
        return

    @commands.command()
    async def update(self, ctx, *args):
        get = True
        channels = None
        if ctx.message.guild is not None:
            if await ctx.bot.check_ownership(ctx.message, is_silent=True, admin_check=True):
                if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
                    await ctx.message.delete()
                get = False
                channels = [ctx.message.channel.id]
            else:
                if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
                    await ctx.message.delete()
                return
        else:
            if not await ctx.bot.check_ownership(ctx.message):
                return
        await ctx.bot.force_update(args, get=get, channels=channels)
        return


def setup(bot):
    bot.add_cog(Updates(bot))
