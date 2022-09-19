import aiosqlite

from discord.ext import commands
from discord.commands import Option, option, SlashCommandGroup, slash_command
import importlib
import discord
import json
from tabulate import tabulate
from datetime import datetime, timedelta, timezone
import updater
import os
from cogs.utils.views import UpdateTypes, BotLangs, AutopostSettings
from cogs.utils.converters import locale_2_lang
from cogs.utils.checks import message_permissions
import dateparser


class ServerAdmin(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    autopost = SlashCommandGroup("autopost", "Autopost channel settings", guild_only=True,
                                 default_member_permissions=discord.Permissions(administrator=True))

    register = autopost.create_subgroup(
        "start", "Register this channel for automatic posts"
    )

    @autopost.command(
        description_localizations={
            'ru': "Прекратить автоматические посты бота в этом канале",
            'fr': 'Forcer le Bot a ne plus poster de mise a jour dans ce canal'
        },
        description='Make the bot stop posting updates in this channel',
        guild_only=True,
        default_member_permissions=discord.Permissions(administrator=True)
    )
    async def remove(self, ctx):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        await ctx.bot.remove_channel(ctx.channel.id)
        await ctx.interaction.edit_original_message(content=ctx.bot.translations[lang]['msg']['command_is_done'], view=None)

    @staticmethod
    async def post_selection(ctx, registration=False):
        converter = {
            'nightmares': 'nightmares',
            'crucible': 'cruciblerotators',
            'raids': 'raids',
            'ordeal': 'ordeal',
            'empire': 'empire_hunts',
            'strikes': 'vanguardstrikes',
            'spider': 'spider',
            'mods': 'daily_mods',
            'xur': 'xur',
            'osiris': 'osiris',
            'alerts': 'alerts',
            'gambit': 'gambit',
            'lostsector': 'lostsector'
        }

        lang = await locale_2_lang(ctx)
        data_cursor = await ctx.bot.guild_db.cursor()
        channels = [ctx.channel.id]
        reg_ch_c = await data_cursor.execute('''SELECT channel_id FROM notifiers WHERE server_id=?
                                                                    UNION ALL
                                                                    SELECT channel_id FROM seasonal WHERE server_id=?''',
                                                (ctx.guild.id, ctx.guild.id))
        reg_ch_c = await reg_ch_c.fetchall()
        reg_ch = []
        for ch in reg_ch_c:
            reg_ch.append(ch[0])
        if len(reg_ch) == 0:
            await ctx.respond(ctx.bot.translations[lang]['msg']['no_notifiers'])
            await data_cursor.close()
            return 0
        else:
            notifiers_c = await data_cursor.execute('''SELECT channel_id FROM notifiers WHERE server_id=?''',
                                                       (ctx.guild.id,))
            notifiers_c = await notifiers_c.fetchall()
            notifiers = []
            for ch in notifiers_c:
                notifiers.append(ch[0])

            if not list(set(notifiers).intersection(channels)):
                await ctx.interaction.edit_original_message(
                    content=ctx.bot.translations[lang]['msg']['no_regular_reg'], view=None)
                await data_cursor.close()
                return 0

            view = AutopostSettings(ctx, lang, registration)
            await ctx.respond(ctx.bot.translations[lang]['msg']['update_types'], view=view)
            await view.wait()
            args = view.value

            if args is None:
                await ctx.interaction.edit_original_message(
                    content=ctx.bot.translations[lang]['msg']['timed_out'], view=None)
                await data_cursor.close()
                return 1
            if args == 'cancel':
                await ctx.interaction.edit_original_message(
                    content=ctx.bot.translations[lang]['msg']['command_is_done'], view=None)
                await data_cursor.close()
                return -1
            if args == 'all':
                args = set(ctx.bot.translations[lang]['update_types']).intersection(set(ctx.bot.all_types))

            variants = set(ctx.bot.translations[lang]['update_types']).intersection(set(ctx.bot.all_types))
            for upd_type in variants:
                if upd_type in args:
                    value = 1
                else:
                    value = 0
                try:
                    await data_cursor.execute('''UPDATE post_settings SET {}=? WHERE channel_id=?'''.
                                              format(converter[upd_type]), (value, ctx.channel.id))
                except aiosqlite.OperationalError:
                    await data_cursor.execute(
                        '''ALTER TABLE post_settings ADD COLUMN {} INTEGER'''.format(converter[upd_type]))
                    await data_cursor.execute('''UPDATE post_settings SET {}=? WHERE channel_id=?'''.
                                              format(converter[upd_type]), (value, ctx.channel.id))
                await ctx.bot.guild_db.commit()
        await data_cursor.close()

    @autopost.command(
        description_localizations={
            'ru': 'Выбрать обновления в этом канале'
        },
        description='Choose update types to post in this channel',
        guild_only=True,
        default_member_permissions=discord.Permissions(administrator=True)
    )
    async def settings(self, ctx):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)

        status = await self.post_selection(ctx)

        if status is None:
            await ctx.interaction.edit_original_message(content=ctx.bot.translations[lang]['msg']['command_is_done'], view=None)

    @register.command(
        description_localizations={
            'ru': "Начать автоматические посты об обновлениях игры в этом канале",
            'fr': 'Autorisez le bot à poster la mise a jour des rotations dans ce canal'
        },
        description='Make the bot start posting rotation updates in this channel',
        guild_only=True,
        default_member_permissions=discord.Permissions(administrator=True)
    )
    async def rotations(self, ctx):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        if not await message_permissions(ctx, lang):
            return
        await ctx.bot.register_channel(ctx, 'notifiers')

        await self.post_selection(ctx, True)

        await ctx.interaction.edit_original_message(content=ctx.bot.translations[lang]['msg']['command_is_done'], view=None)
        await ctx.bot.force_update(['daily', 'weekly'], get=False, channels=[ctx.channel.id], forceget=False)
        return

    @register.command(
        description_localizations={
            'ru': "Начать автоматические посты об обновлениях бота в этом канале",
            'fr': 'Autorisez le bot à poster les changelogs dans ce canal'
        },
        description='Make the bot start posting changelogs in this channel',
        guild_only=True,
        default_member_permissions=discord.Permissions(administrator=True)
    )
    async def changelogs(self, ctx):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        if not await message_permissions(ctx, lang):
            return
        await ctx.bot.register_channel(ctx, 'updates')
        await ctx.interaction.edit_original_message(content=ctx.bot.translations[lang]['msg']['command_is_done'], view=None)
        return

    @slash_command(name='lfgcleanup',
                   description='Delete groups that are unavailable or inactive',
                   default_member_permissions=discord.Permissions(administrator=True))
    async def sl_lfgcleanup(self, ctx,
                            days: Option(int, "Days since the activity was finished", required=False, default=0)):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        msg = ctx.bot.translations[lang]['msg']['lfg_cleanup']
        if ctx.guild is None:
            if await ctx.bot.check_ownership(ctx, is_silent=True, admin_check=False):
                n = await ctx.bot.lfg_cleanup(days, ctx.guild)
                await ctx.respond(msg.format(n))
            else:
                await ctx.respond(ctx.bot.translations[lang]['msg']['no_admin'])
        else:
            n = await ctx.bot.lfg_cleanup(days, ctx.guild)
            await ctx.respond(msg.format(n))

    @slash_command(name='regnotifier',
                description='Register notifier channel',
                   guild_only=True,
                   default_member_permissions=discord.Permissions(administrator=True))
    async def sl_regnotifier(self, ctx,
                             upd_type: Option(str, "The type of notifier", required=False, default='notifiers',
                                              choices=[discord.OptionChoice('Rotations', value='notifiers',
                                                                            name_localizations={
                                                                                'ru': 'Обновления игры',
                                                                                'fr': 'Rotations'
                                                                            }),
                                                       discord.OptionChoice('Changelogs', value='updates',
                                                                            name_localizations={
                                                                                'ru': 'Обновления бота',
                                                                                'fr': 'Logs des modifications'
                                                                            })])
                             ):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        if not await message_permissions(ctx, lang):
            return
        await ctx.bot.register_channel(ctx, upd_type)
        await ctx.respond(ctx.bot.translations[lang]['msg']['command_is_done'])
        return

    @slash_command(name='rmnotifier',
                   description='Deregister notifier channel',
                   guild_only=True,
                   default_member_permissions=discord.Permissions(administrator=True))
    async def sl_rmnotifier(self, ctx):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        if not await message_permissions(ctx, lang):
            return
        await ctx.bot.remove_channel(ctx.channel.id)
        await ctx.interaction.edit_original_message(content=ctx.bot.translations[lang]['msg']['command_is_done'],
                                                    view=None)

    @slash_command(
        name='setlang',
        description='Tell the bot the server\'s language',
        guild_only=True,
        default_member_permissions=discord.Permissions(administrator=True)
    )
    async def sl_setlang(self, ctx):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        view = BotLangs(ctx.author, self.bot)
        await ctx.respond(ctx.bot.translations[lang]['msg']['language_select'], view=view)
        await view.wait()
        args = view.value

        msg = ctx.bot.translations[lang]['msg']['command_is_done']

        data_cursor = await ctx.bot.guild_db.cursor()
        await data_cursor.execute('''UPDATE language SET lang=? WHERE server_id=?''',
                                  (args[0].lower(), ctx.guild.id))
        await ctx.bot.guild_db.commit()
        await data_cursor.close()
        if ctx.guild.me.guild_permissions.change_nickname:
            await ctx.guild.me.edit(nick=ctx.bot.translations[args[0].lower()]['nick'], reason='language change')
        await ctx.interaction.edit_original_message(content=msg, view=None)

    @slash_command(name='setclan',
                   description='Set a Destiny 2 clan for the server',
                   guild_only=True,
                   default_member_permissions=discord.Permissions(administrator=True)
                   )
    async def sl_setclan(self, ctx, clan_id: Option(str, "Name or id of a clan", required=True)):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        try:
            url = 'https://www.bungie.net/Platform/GroupV2/{}/'.format(int(clan_id))
        except ValueError:
            url = 'https://www.bungie.net/Platform/GroupV2/Name/{}/1/'.format(clan_id)
        clan_resp = await ctx.bot.data.get_bungie_json('clan'.format(clan_id), url, string='clan {}'.format(clan_id),
                                                       change_msg=False)
        clan_json = clan_resp
        try:
            code = clan_json['ErrorCode']
        except KeyError:
            code = 0
        except TypeError:
            await ctx.respond('{}: {}'.format(clan_id, ctx.bot.translations[lang]['msg']['clan_search_error']))
            return
        if code == 1:
            translations = ctx.bot.translations[lang]['clan_info']
            clan_embed = discord.Embed(title='{} [{}]'.format(clan_json['Response']['detail']['name'], clan_json['Response']['detail']['clanInfo']['clanCallsign']),
                                       description=clan_json['Response']['detail']['about'])
            clan_embed.add_field(name=translations['motto'], value=clan_json['Response']['detail']['motto'])
            clan_embed.add_field(name=translations['member_count'], value=clan_json['Response']['detail']['memberCount'])
            clan_embed.add_field(name=translations['creation_date'], value=discord.utils.format_dt(dateparser.parse(clan_json['Response']['detail']['creationDate']), style='D'))
            clan_embed.add_field(name=translations['id'], value=clan_json['Response']['detail']['groupId'])
            clan_embed.add_field(name=translations['founder'], value=clan_json['Response']['founder']['destinyUserInfo']['LastSeenDisplayName'])
            await ctx.respond(embed=clan_embed)
            data_cursor = await ctx.bot.data.bot_data_db.cursor()
            guild_cursor = await ctx.bot.guild_db.cursor()
            try:
                await data_cursor.execute('''INSERT or IGNORE INTO clans VALUES (?,?)''', (clan_json['Response']['detail']['name'], clan_json['Response']['detail']['groupId']))
                await ctx.bot.data.bot_data_db.commit()
            except aiosqlite.OperationalError:
                pass
            await data_cursor.close()
            await guild_cursor.execute('''UPDATE clans SET clan_name=?, clan_id=? WHERE server_id=?''',
                                         (clan_json['Response']['detail']['name'],
                                          clan_json['Response']['detail']['groupId'], ctx.guild.id))
            await ctx.bot.guild_db.commit()
            await guild_cursor.close()
            if ctx.guild.me.guild_permissions.change_nickname:
                try:
                    await ctx.guild.me.edit(
                        nick='{}bot'.format(clan_json['Response']['detail']['clanInfo']['clanCallsign']),
                        reason='clan setup')
                except KeyError:
                    pass
        else:
            await ctx.respond('{}: {}'.format(clan_id, clan_json['Message']))

    @commands.command()
    async def update(self, ctx, *args):
        if ctx.message.guild is not None:
            lang = ctx.bot.guild_lang(ctx.message.guild.id)
        else:
            lang = 'en'
        get = True
        channels = None
        if len(args) == 0:
            view = UpdateTypes(ctx.message.author, lang=lang)
            await ctx.channel.send('Select update types', view=view)
            await view.wait()
            args = view.value
        if not list(set(ctx.bot.all_types).intersection(args)):
            if ctx.guild is not None:
                if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                    await ctx.message.delete()
            await ctx.channel.send(ctx.bot.translations[lang]['msg']['invalid_type'])
            return
        if ctx.message.guild is not None:
            if await ctx.bot.check_ownership(ctx.message, is_silent=False, admin_check=True):
                if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                    await ctx.message.delete()
                await ctx.channel.send(ctx.bot.translations[lang]['msg']['deprecation_warning'], delete_after=60)
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
                if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                    await ctx.message.delete()
                return
        else:
            if not await ctx.bot.check_ownership(ctx.message):
                return
        await ctx.bot.force_update(args, get=get, channels=channels, forceget=get)
        return

    @slash_command(
        name='update',
        description='Get updates from Bungie',
        guild_only=True,
        default_member_permissions=discord.Permissions(administrator=True)
    )
    async def sl_update(self, ctx):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        if not await message_permissions(ctx, lang):
            return
        get = True
        channels = None

        get = False
        channels = [ctx.channel.id]
        data_cursor = await ctx.bot.guild_db.cursor()
        reg_ch_c = await data_cursor.execute('''SELECT channel_id FROM notifiers WHERE server_id=?
                                                UNION ALL
                                                SELECT channel_id FROM seasonal WHERE server_id=?''',
                                             (ctx.guild.id, ctx.guild.id))
        reg_ch_c = await reg_ch_c.fetchall()
        reg_ch = []
        for ch in reg_ch_c:
            reg_ch.append(ch[0])
        if len(reg_ch) == 0:
            await ctx.respond(ctx.bot.translations[lang]['msg']['no_notifiers'])
            return
        else:
            view = UpdateTypes(ctx, lang)
            await ctx.respond(ctx.bot.translations[lang]['msg']['update_types'], view=view)
            await view.wait()
            args = view.value

            if args is None:
                await ctx.interaction.edit_original_message(
                    content=ctx.bot.translations[lang]['msg']['timed_out'], view=None)
                return

            notifiers_c = await data_cursor.execute('''SELECT channel_id FROM notifiers WHERE server_id=?''',
                                                    (ctx.guild.id,))
            notifiers_c = await notifiers_c.fetchall()
            notifiers = []
            for ch in notifiers_c:
                notifiers.append(ch[0])

            correct_ch = False
            regular_types = ctx.bot.all_types.copy()
            if not list(set(notifiers).intersection(channels)):
                if list(set(regular_types).intersection(args)):
                    await ctx.interaction.edit_original_message(content=ctx.bot.translations[lang]['msg']['no_regular_reg'], view=None)
                    await data_cursor.close()
                    return
            else:
                if list(set(regular_types).intersection(args)):
                    correct_ch = True
        await ctx.bot.force_update(args, get=get, channels=channels, forceget=get)
        await ctx.interaction.edit_original_message(content=ctx.bot.translations[lang]['msg']['command_is_done'], view=None)
        await data_cursor.close()
        return

    # @commands.slash_command(
    #     description='Register the channel as a place for LFG posts',
    #     default_permission=False
    # )
    # @commands.guild_only()
    # async def reglfg(self, ctx):
    #     pass
    #
    # @commands.slash_command(
    #     description="View and change settings for the server",
    #     default_permission=False
    # )
    # @commands.guild_only()
    # async def settings(self, ctx):
    #     pass


def setup(bot):
    bot.add_cog(ServerAdmin(bot))
