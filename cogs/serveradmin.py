from discord.ext import commands
import importlib
import discord
import json
from tabulate import tabulate
from datetime import datetime, timedelta, timezone
import updater
import os
import sqlite3


class ServerAdmin(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        description='Delete groups that are unavailable or inactive'
    )
    async def lfgcleanup(self, ctx, days=0):
        msg = 'Done, removed {} entries.'
        if ctx.guild is None:
            if await ctx.bot.check_ownership(ctx.message, is_silent=False, admin_check=False):
                n = await ctx.bot.lfg_cleanup(days, ctx.guild)
                await ctx.message.channel.send(msg.format(n))
        else:
            if await ctx.bot.check_ownership(ctx.message, is_silent=False, admin_check=True):
                n = await ctx.bot.lfg_cleanup(days, ctx.guild)
                await ctx.message.channel.send(msg.format(n), delete_after=30)
            if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
                await ctx.message.delete()

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
        if lang.lower() not in ctx.bot.langs:
            msg = 'The language you\'ve entered (`{}`) is not available. Available languages are `{}`.'.format(
                lang, str(ctx.bot.langs).replace('[', '').replace(']', '').replace('\'', ''))
            await message.channel.send(msg)
            return
        if await ctx.bot.check_ownership(message, is_silent=True, admin_check=True):
            ctx.bot.guild_cursor.execute('''UPDATE language SET lang=? WHERE server_id=?''',
                                         (lang.lower(), ctx.message.guild.id))
            ctx.bot.guild_db.commit()
        msg = 'Got it, {}'.format(message.author.mention)
        if ctx.guild.me.guild_permissions.change_nickname:
            await ctx.guild.me.edit(nick=ctx.bot.translations[lang.lower()]['nick'], reason='language change')
        await message.channel.send(msg, delete_after=10)
        if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
            await message.delete()
        return

    @commands.command()
    @commands.guild_only()
    async def setclan(self, ctx, clan_id, *args):
        lang = ctx.bot.guild_lang(ctx.message.guild.id)
        try:
            url = 'https://www.bungie.net/Platform/GroupV2/{}/'.format(int(clan_id))
        except ValueError:
            for arg in args:
                clan_id = '{} {}'.format(clan_id, arg)
            url = 'https://www.bungie.net/Platform/GroupV2/Name/{}/1/'.format(clan_id)
        clan_resp = await ctx.bot.data.get_bungie_json('clan'.format(clan_id), url, string='clan {}'.format(clan_id), change_msg=False)
        clan_json = clan_resp
        try:
            code = clan_json['ErrorCode']
        except KeyError:
            code = 0
        except TypeError:
            await ctx.channel.send('{}: {}'.format(clan_id, ctx.bot.translations[lang]['msg']['clan_search_error']), delete_after=60)
            if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
                await ctx.message.delete()
            return
        if code == 1:
            await ctx.channel.send('{}\nid: {}'.format(clan_json['Response']['detail']['name'],
                                                       clan_json['Response']['detail']['groupId']), delete_after=60)
            if await ctx.bot.check_ownership(ctx.message, is_silent=True, admin_check=True):
                ctx.bot.guild_cursor.execute('''UPDATE clans SET clan_name=?, clan_id=? WHERE server_id=?''',
                                             (clan_json['Response']['detail']['name'],
                                              clan_json['Response']['detail']['groupId'], ctx.guild.id))
                ctx.bot.guild_db.commit()
                if ctx.guild.me.guild_permissions.change_nickname:
                    try:
                        await ctx.guild.me.edit(
                            nick='{}bot'.format(clan_json['Response']['detail']['clanInfo']['clanCallsign']),
                            reason='clan setup')
                    except KeyError:
                        pass
        else:
            await ctx.channel.send('{}: {}'.format(clan_id, clan_json['Message']), delete_after=60)
        if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
            await ctx.message.delete()

    @commands.command()
    async def update(self, ctx, *args):
        if ctx.message.guild is not None:
            lang = ctx.bot.guild_lang(ctx.message.guild.id)
        else:
            lang = 'en'
        get = True
        channels = None
        if not list(set(ctx.bot.all_types).intersection(args)):
            if ctx.guild is not None:
                if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
                    await ctx.message.delete()
            await ctx.channel.send(ctx.bot.translations[lang]['msg']['invalid_type'])
            return
        if ctx.message.guild is not None:
            if await ctx.bot.check_ownership(ctx.message, is_silent=False, admin_check=True):
                if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
                    await ctx.message.delete()
                get = False
                channels = [ctx.message.channel.id]
                reg_ch_c = ctx.bot.guild_cursor.execute('''SELECT channel_id FROM notifiers WHERE server_id=?
                                                        UNION ALL
                                                        SELECT channel_id FROM seasonal WHERE server_id=?''',
                                                        (ctx.guild.id, ctx.guild.id))
                reg_ch_c = reg_ch_c.fetchall()
                reg_ch = []
                for ch in reg_ch_c:
                    reg_ch.append(ch[0])
                if len(reg_ch) == 0:
                    await ctx.channel.send(ctx.bot.translations[lang]['msg']['no_notifiers'])
                else:
                    notifiers_c = ctx.bot.guild_cursor.execute('''SELECT channel_id FROM notifiers WHERE server_id=?''',
                                                               (ctx.guild.id,))
                    notifiers_c = notifiers_c.fetchall()
                    notifiers = []
                    for ch in notifiers_c:
                        notifiers.append(ch[0])

                    correct_ch = False
                    regular_types = ctx.bot.all_types.copy()
                    if not list(set(notifiers).intersection(channels)):
                        if list(set(regular_types).intersection(args)):
                            await ctx.channel.send(ctx.bot.translations[lang]['msg']['no_regular_reg'])
                    else:
                        if list(set(regular_types).intersection(args)):
                            correct_ch = True
                    if correct_ch:
                        await ctx.channel.send(ctx.bot.translations[lang]['msg']['in_progress'])
            else:
                if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
                    await ctx.message.delete()
                return
        else:
            if not await ctx.bot.check_ownership(ctx.message):
                return
        await ctx.bot.force_update(args, get=get, channels=channels, forceget=get)
        return

    @commands.command()
    @commands.guild_only()
    async def setprefix(self, ctx, prefix, *prefixes):
        prefix = [prefix, *prefixes]
        if await ctx.bot.check_ownership(ctx.message, is_silent=True, admin_check=True):
            if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
                await ctx.message.delete()
            if prefix[0].lower() == 'none':
                prefix = []
            ctx.bot.guild_cursor.execute('''UPDATE prefixes SET prefix=? WHERE server_id=?''',
                                         (str(list(prefix)), ctx.message.guild.id))
            ctx.bot.guild_db.commit()
            msg = 'Got it, {}'.format(ctx.message.author.mention)
            await ctx.message.channel.send(msg, delete_after=10)


def setup(bot):
    bot.add_cog(ServerAdmin(bot))
