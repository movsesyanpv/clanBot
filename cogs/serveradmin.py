from discord.ext import commands
from discord.commands import Option, option, SlashCommandGroup
import importlib
import discord
import json
from tabulate import tabulate
from datetime import datetime, timedelta, timezone
import updater
import os
import sqlite3
from cogs.utils.views import UpdateTypes, BotLangs
from cogs.utils.converters import locale_2_lang
from cogs.utils.checks import message_permissions
import dateparser


class ServerAdmin(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    autopost = SlashCommandGroup("autopost", "Autopost channel settings")

    register = autopost.create_subgroup(
        "start", "Register this channel for automatic posts"
    )

    @autopost.command(
        description_localizations={
            'ru': "Прекратить автоматические посты бота в этом канале",
            'fr': 'Forcer le Bot a ne plus poster de mise a jour dans ce canal'
        },
        description='Make the bot stop posting updates in this channel'
    )
    async def remove(self, ctx):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        if ctx.guild is None:
            await ctx.respond(ctx.bot.translations[lang]['msg']['no_dm'])
            return
        if not ctx.channel.permissions_for(ctx.author).administrator:
            await ctx.respond(ctx.bot.translations[lang]['msg']['no_admin'])
            return
        if await ctx.bot.check_ownership(ctx, is_silent=True, admin_check=True):
            ctx.bot.guild_cursor.execute('''DELETE FROM updates WHERE channel_id=?''', (ctx.channel.id,))
            ctx.bot.guild_cursor.execute('''DELETE FROM notifiers WHERE channel_id=?''', (ctx.channel.id,))
            ctx.bot.guild_db_sync.commit()
            ctx.bot.get_channels()
            msg = 'Got it, {}'.format(ctx.author.mention)
            await ctx.respond(msg)

    @register.command(
        description_localizations={
            'ru': "Начать автоматические посты об обновлениях игры в этом канале",
            'fr': 'Autorisez le bot à poster la mise a jour des rotations dans ce canal'
        },
        description='Make the bot start posting rotation updates in this channel'
    )
    async def rotations(self, ctx):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        if ctx.guild is None:
            await ctx.respond(ctx.bot.translations[lang]['msg']['no_dm'])
            return
        if not ctx.channel.permissions_for(ctx.author).administrator:
            await ctx.respond(ctx.bot.translations[lang]['msg']['no_admin'])
            return
        if not await message_permissions(ctx, lang):
            return
        if await ctx.bot.check_ownership(ctx, is_silent=True, admin_check=True):
            ctx.bot.guild_cursor.execute('''INSERT or IGNORE into notifiers values (?,?)''',
                                         (ctx.channel.id, ctx.guild.id))
            ctx.bot.guild_db_sync.commit()
            ctx.bot.get_channels()
            msg = 'Got it, {}'.format(ctx.author.mention)
            await ctx.respond(msg)
            await ctx.bot.force_update(['daily', 'weekly'], get=False, channels=[ctx.channel.id], forceget=False)
        return

    @register.command(
        description_localizations={
            'ru': "Начать автоматические посты об обновлениях бота в этом канале",
            'fr': 'Autorisez le bot à poster les changelogs dans ce canal'
        },
        description='Make the bot start posting changelogs in this channel'
    )
    async def changelogs(self, ctx):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        if ctx.guild is None:
            await ctx.respond(ctx.bot.translations[lang]['msg']['no_dm'])
            return
        if not ctx.channel.permissions_for(ctx.author).administrator:
            await ctx.respond(ctx.bot.translations[lang]['msg']['no_admin'])
            return
        if not await message_permissions(ctx, lang):
            return
        if await ctx.bot.check_ownership(ctx, is_silent=True, admin_check=True):
            ctx.bot.guild_cursor.execute('''INSERT or IGNORE into updates values (?,?)''',
                                         (ctx.channel.id, ctx.guild.id))
            ctx.bot.guild_db_sync.commit()
            ctx.bot.get_channels()
            msg = 'Got it, {}'.format(ctx.author.mention)
            await ctx.respond(msg)
        return

    @commands.command(description='Delete groups that are unavailable or inactive')
    async def lfgcleanup(self, ctx, days=0):
        lang = 'en'
        msg = 'Done, removed {} entries.'
        if ctx.guild is None:
            await ctx.channel.send(ctx.bot.translations[lang]['msg']['deprecation_warning'])
            if await ctx.bot.check_ownership(ctx.message, is_silent=False, admin_check=False):
                n = await ctx.bot.lfg_cleanup(days, ctx.guild)
                await ctx.message.channel.send(msg.format(n))
        else:
            lang = ctx.bot.guild_lang(ctx.guild.id)
            await ctx.channel.send(ctx.bot.translations[lang]['msg']['deprecation_warning'], delete_after=60)
            if await ctx.bot.check_ownership(ctx.message, is_silent=False, admin_check=True):
                n = await ctx.bot.lfg_cleanup(days, ctx.guild)
                await ctx.message.channel.send(msg.format(n), delete_after=30)
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass

    @commands.slash_command(name='lfgcleanup',
                            description_localizations={
                                'ru': "Удалить прошедшие сборы",
                                'fr': 'Supprimer les messages LFG expirés'
                            },
                            description='Delete groups that are unavailable or inactive')
    async def sl_lfgcleanup(self, ctx,
                            days: Option(int, "Days since the activity was finished", required=False, default=0,
                                         name_localizations={
                                             'ru': 'дни',
                                             'fr': 'jours'
                                         },
                                         description_localizations={
                                             'ru': 'Дней с окончания активности',
                                             'fr': 'jours depuis la fin de l\'activité'
                                         })
                            ):
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
            if await ctx.bot.check_ownership(ctx, is_silent=True, admin_check=True):
                n = await ctx.bot.lfg_cleanup(days, ctx.guild)
                await ctx.respond(msg.format(n))
            else:
                await ctx.respond(ctx.bot.translations[lang]['msg']['no_admin'])

    @commands.command()
    @commands.guild_only()
    async def regnotifier(self, ctx, upd_type='notifiers'):
        message = ctx.message
        lang = ctx.bot.guild_lang(ctx.guild.id)
        await ctx.channel.send(ctx.bot.translations[lang]['msg']['deprecation_warning'], delete_after=30)
        available_types = ['notifiers', 'seasonal', 'updates']
        notifier_type = 'notifiers'
        if upd_type in available_types:
            notifier_type = upd_type
        if await ctx.bot.check_ownership(message, is_silent=True, admin_check=True):
            ctx.bot.guild_cursor.execute('''INSERT or IGNORE into {} values (?,?)'''.format(notifier_type),
                                        (message.channel.id, message.guild.id))
            ctx.bot.guild_db_sync.commit()
            ctx.bot.get_channels()
            msg = 'Got it, {}'.format(message.author.mention)
            await message.channel.send(msg, delete_after=10)
        if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            await message.delete()
        return

    @commands.slash_command(name='regnotifier',
                            description_localizations={
                                'ru': "Зарегистрировать канал для автоматических постов",
                                'de': 'Meldekanal registrieren',
                                'fr': 'Enregistrer le canal de notification'
                            },
                            description='Register notifier channel')
    @commands.guild_only()
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
                                                                            })],
                                              name_localizations={
                                                  'ru': 'тип_постов',
                                                  'fr': 'upd_type'
                                              },
                                              description_localizations={
                                                  'ru': 'Тип постов на канале',
                                                  'fr': 'Le type du paramètre'
                                              })
                             ):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        if not ctx.channel.permissions_for(ctx.author).administrator:
            await ctx.respond(ctx.bot.translations[lang]['msg']['no_admin'])
            return
        if not await message_permissions(ctx, lang):
            return
        notifier_type = upd_type
        if await ctx.bot.check_ownership(ctx, is_silent=True, admin_check=True):
            ctx.bot.guild_cursor.execute('''INSERT or IGNORE into {} values (?,?)'''.format(notifier_type),
                                         (ctx.channel.id, ctx.guild.id))
            ctx.bot.guild_db_sync.commit()
            ctx.bot.get_channels()
            await ctx.respond(ctx.bot.translations[lang]['msg']['command_is_done'])
        return

    @commands.command()
    @commands.guild_only()
    async def rmnotifier(self, ctx, upd_type='notifiers'):
        message = ctx.message
        lang = ctx.bot.guild_lang(ctx.guild.id)
        await ctx.channel.send(ctx.bot.translations[lang]['msg']['deprecation_warning'], delete_after=30)
        available_types = ['notifiers', 'seasonal', 'updates']
        notifier_type = 'notifiers'
        if upd_type in available_types:
            notifier_type = upd_type
        if await ctx.bot.check_ownership(message, is_silent=True, admin_check=True):
            ctx.bot.guild_cursor.execute('''DELETE FROM {} WHERE channel_id=?'''.format(notifier_type),
                                         (message.channel.id,))
            ctx.bot.guild_db_sync.commit()
            ctx.bot.get_channels()
            msg = 'Got it, {}'.format(message.author.mention)
            await message.channel.send(msg, delete_after=10)
        if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            await message.delete()
        return

    @commands.slash_command(name='rmnotifier',
                            description_localizations={
                                'ru': "Удалить регистрацию канала для автоматических постов",
                                'de': 'Meldekanal abmelden',
                                'fr': 'Supprimer le canal de notification'
                            },
                            description='Deregister notifier channel')
    @commands.guild_only()
    async def sl_rmnotifier(self, ctx):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        if not ctx.channel.permissions_for(ctx.author).administrator:
            await ctx.respond(ctx.bot.translations[lang]['msg']['no_admin'])
            return
        if not await message_permissions(ctx, lang):
            return
        if await ctx.bot.check_ownership(ctx, is_silent=True, admin_check=True):
            ctx.bot.guild_cursor.execute('''DELETE FROM updates WHERE channel_id=?''', (ctx.channel.id,))
            ctx.bot.guild_cursor.execute('''DELETE FROM notifiers WHERE channel_id=?''', (ctx.channel.id,))
            ctx.bot.guild_db_sync.commit()
            ctx.bot.get_channels()
            await ctx.respond(ctx.bot.translations[lang]['msg']['command_is_done'])

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
            ctx.bot.guild_db_sync.commit()
        await ctx.channel.send(ctx.bot.translations[lang.lower()]['msg']['deprecation_warning'], delete_after=30)
        msg = 'Got it, {}'.format(message.author.mention)
        if ctx.guild.me.guild_permissions.change_nickname:
            await ctx.guild.me.edit(nick=ctx.bot.translations[lang.lower()]['nick'], reason='language change')
        await message.channel.send(msg, delete_after=10)
        if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            await message.delete()
        return

    @commands.slash_command(
        name='setlang',
        description_localizations={
            'ru': "Указать боту язык сервера",
            'de': 'Serversprache einstellen',
            'fr': 'Selectionner la langue du serveur'
        },
        description='Tell the bot the server\'s language'
    )
    @commands.guild_only()
    async def sl_setlang(self, ctx):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        if not ctx.channel.permissions_for(ctx.author).administrator:
            await ctx.respond(ctx.bot.translations[lang]['msg']['no_admin'])
            return
        view = BotLangs(ctx.author, self.bot)
        await ctx.respond(ctx.bot.translations[lang]['msg']['language_select'], view=view)
        await view.wait()
        args = view.value

        msg = ctx.bot.translations[lang]['msg']['command_is_done']
        if await ctx.bot.check_ownership(ctx, is_silent=True, admin_check=True):
            ctx.bot.guild_cursor.execute('''UPDATE language SET lang=? WHERE server_id=?''',
                                         (args[0].lower(), ctx.guild.id))
            ctx.bot.guild_db_sync.commit()
            if ctx.guild.me.guild_permissions.change_nickname:
                await ctx.guild.me.edit(nick=ctx.bot.translations[args[0].lower()]['nick'], reason='language change')
        await ctx.interaction.edit_original_message(content=msg, view=None)

    @commands.command()
    @commands.guild_only()
    async def setclan(self, ctx, clan_id, *args):
        lang = ctx.bot.guild_lang(ctx.message.guild.id)
        await ctx.channel.send(ctx.bot.translations[lang]['msg']['deprecation_warning'], delete_after=60)
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
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                await ctx.message.delete()
            return
        if code == 1:
            await ctx.channel.send('{}\nid: {}'.format(clan_json['Response']['detail']['name'],
                                                       clan_json['Response']['detail']['groupId']), delete_after=60)
            if await ctx.bot.check_ownership(ctx.message, is_silent=True, admin_check=True):
                ctx.bot.guild_cursor.execute('''UPDATE clans SET clan_name=?, clan_id=? WHERE server_id=?''',
                                             (clan_json['Response']['detail']['name'],
                                              clan_json['Response']['detail']['groupId'], ctx.guild.id))
                ctx.bot.guild_db_sync.commit()
                if ctx.guild.me.guild_permissions.change_nickname:
                    try:
                        await ctx.guild.me.edit(
                            nick='{}bot'.format(clan_json['Response']['detail']['clanInfo']['clanCallsign']),
                            reason='clan setup')
                    except KeyError:
                        pass
        else:
            await ctx.channel.send('{}: {}'.format(clan_id, clan_json['Message']), delete_after=60)
        if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            await ctx.message.delete()

    @commands.slash_command(name='setclan',
                            description_localizations={
                                'ru': "Задать клан Destiny 2 для сервера",
                                'de': 'Lege einen Destiny 2-Clan für den Server fest',
                                'fr': 'Définir le clan Destiny 2 sur le serveur'
                            },
                            description='Set a Destiny 2 clan for the server')
    @commands.guild_only()
    async def sl_setclan(self, ctx, clan_id: Option(str, "Name or id of a clan", required=True,
                                                    name_localizations={
                                                        'ru': 'клан'
                                                    },
                                                    description_localizations={
                                                        'ru': 'Имя или ID клана'
                                                    })
                         ):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        if not ctx.channel.permissions_for(ctx.author).administrator:
            await ctx.respond(ctx.bot.translations[lang]['msg']['no_admin'])
            return
        # lang = ctx.bot.guild_lang(ctx.guild.id)
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
            if await ctx.bot.check_ownership(ctx, is_silent=True, admin_check=True):
                ctx.bot.guild_cursor.execute('''UPDATE clans SET clan_name=?, clan_id=? WHERE server_id=?''',
                                             (clan_json['Response']['detail']['name'],
                                              clan_json['Response']['detail']['groupId'], ctx.guild.id))
                ctx.bot.guild_db_sync.commit()
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

    @commands.slash_command(
        name='update',
        description_localizations={
            'ru': "Получить обновления от Bungie",
            'de': 'Holen Sie sich Updates von Bungie',
            'fr': 'Recevoir les mises a jour de Bungie'
        },
        description='Get updates from Bungie'
    )
    @commands.guild_only()
    async def sl_update(self, ctx):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        if not ctx.channel.permissions_for(ctx.author).administrator:
            await ctx.respond(ctx.bot.translations[lang]['msg']['no_admin'])
            return
        if not await message_permissions(ctx, lang):
            return
        get = True
        channels = None

        get = False
        channels = [ctx.channel.id]
        reg_ch_c = ctx.bot.guild_cursor.execute('''SELECT channel_id FROM notifiers WHERE server_id=?
                                                    UNION ALL
                                                    SELECT channel_id FROM seasonal WHERE server_id=?''',
                                                (ctx.guild.id, ctx.guild.id))
        reg_ch_c = reg_ch_c.fetchall()
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
                    await ctx.interaction.edit_original_message(content=ctx.bot.translations[lang]['msg']['no_regular_reg'], view=None)
                    return
            else:
                if list(set(regular_types).intersection(args)):
                    correct_ch = True
        await ctx.bot.force_update(args, get=get, channels=channels, forceget=get)
        await ctx.interaction.edit_original_message(content=ctx.bot.translations[lang]['msg']['command_is_done'], view=None)
        return

    @commands.command()
    @commands.guild_only()
    async def setprefix(self, ctx, prefix, *prefixes):
        prefix = [prefix, *prefixes]
        if await ctx.bot.check_ownership(ctx.message, is_silent=True, admin_check=True):
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                await ctx.message.delete()
            if prefix[0].lower() == 'none':
                prefix = []
            ctx.bot.guild_cursor.execute('''UPDATE prefixes SET prefix=? WHERE server_id=?''',
                                         (str(list(prefix)), ctx.message.guild.id))
            ctx.bot.guild_db_sync.commit()
            msg = 'Got it, {}'.format(ctx.message.author.mention)
            await ctx.message.channel.send(msg, delete_after=10)

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
