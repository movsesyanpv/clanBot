from discord.ext import commands
import discord
from tabulate import tabulate
import sqlite3


class Updates(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.guild_only()
    async def regnotifier(self, ctx, upd_type='notifiers'):
        message = ctx.message
        available_types = ['notifiers', 'seasonal', 'updates']
        notifier_type = 'notifiers'
        if upd_type in available_types:
            notifier_type = upd_type
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
    async def rmnotifier(self, ctx, upd_type='notifiers'):
        message = ctx.message
        available_types = ['notifiers', 'seasonal', 'updates']
        notifier_type = 'notifiers'
        if upd_type in available_types:
            notifier_type = upd_type
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
    @commands.guild_only()
    async def setclan(self, ctx, clan_id, *args):
        try:
            url = 'https://www.bungie.net/Platform/GroupV2/{}/'.format(int(clan_id))
        except ValueError:
            for arg in args:
                clan_id = '{} {}'.format(clan_id, arg)
            url = 'https://www.bungie.net/Platform/GroupV2/Name/{}/1/'.format(clan_id)
        clan_json = ctx.bot.data.get_bungie_json('clan'.format(clan_id), url, string='clan {}'.format(clan_id)).json()
        try:
            code = clan_json['ErrorCode']
        except KeyError:
            code = 0
        if code != 0:
            await ctx.channel.send('{}\nid: {}'.format(clan_json['Response']['detail']['name'], clan_json['Response']['detail']['groupId']), delete_after=10)
            if await ctx.bot.check_ownership(ctx.message, is_silent=True, admin_check=True):
                ctx.bot.guild_cursor.execute('''UPDATE clans SET clan_name=?, clan_id=? WHERE server_id=?''',
                                             (clan_json['Response']['detail']['name'], clan_json['Response']['detail']['groupId'], ctx.guild.id))
                ctx.bot.guild_db.commit()
        else:
            await ctx.channel.send('{}: {}'.format(clan_id, clan_json['Message']), delete_after=10)
        if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
            await ctx.message.delete()

    @commands.command()
    @commands.guild_only()
    async def top(self, ctx, metric, number=10):
        ctx.bot.guild_cursor.execute('''SELECT clan_id FROM clans WHERE server_id=?''', (ctx.guild.id,))
        clan_id = ctx.bot.guild_cursor.fetchone()
        if len(clan_id) > 0:
            clan_id = clan_id[0]
            try:
                int(metric)
            except ValueError:
                try:
                    internal_db = sqlite3.connect('internal.db')
                    internal_cursor = internal_db.cursor()
                    internal_cursor.execute('''SELECT hash FROM metrics WHERE name=?''', (metric.lower(), ))
                    metric_id = internal_cursor.fetchone()
                    if metric_id is not None:
                        if len(metric_id) > 0:
                            metric = metric_id[0]
                        else:
                            raise sqlite3.OperationalError
                    else:
                        raise sqlite3.OperationalError
                except sqlite3.OperationalError:
                    await ctx.channel.send('Unknown metric.', delete_after=10)
                    if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
                        await ctx.message.delete()
                    return
            await ctx.channel.send('Getting the leaderboard, could take a long time.', delete_after=30)
            top_list = await ctx.bot.data.get_clan_leaderboard(clan_id, metric, number)
            lang = ctx.bot.guild_lang(ctx.message.guild.id)
            top_name = await ctx.bot.data.destiny.decode_hash(metric, 'DestinyMetricDefinition', language=lang)
            max_len = min(number, len(top_list))
            await ctx.channel.send('{}```{}```'.format(top_name['displayProperties']['description'], tabulate(top_list, tablefmt='plain', colalign=('left', 'left'), showindex=range(1, max_len+1))))
        else:
            await ctx.channel.send('Clan not found or not registered.', delete_after=10)
        if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
            await ctx.message.delete()

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
