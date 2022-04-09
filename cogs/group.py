from discord.ext import commands
import discord
from datetime import datetime, timedelta, timezone
from hashids import Hashids
import dateparser
import asyncio
import aiosqlite
from cogs.utils.views import GroupButtons, ActivityType, ModeLFG, RoleLFG, ConfirmLFG, MyButton, ViewLFG, LFGModal
from cogs.utils.converters import locale_2_lang, CtxLocale
from cogs.utils.checks import message_permissions
from babel.dates import format_datetime
from babel import Locale


class Group(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.dm_only()
    async def lfglist(self, ctx, lang=None):
        if ctx.message.guild is not None and lang is None:
            lang = ctx.bot.guild_lang(ctx.message.guild.id)
        if lang not in ctx.bot.langs:
            lang = 'en'

        await ctx.channel.send(ctx.bot.translations[lang]['msg']['deprecation_warning'])
        translations = ctx.bot.translations[lang]['lfg']
        status = await ctx.bot.raid.dm_lfgs(ctx.author, translations)
        return status

    @commands.slash_command(name='lfglist',
                            description_localizations={
                                'ru': 'Вывести список ваших сборов'
                            },
                            description='Print your LFG list')
    async def sl_lfglist(self, ctx):
        await ctx.defer(ephemeral=True)
        lang = await locale_2_lang(ctx)
        cursor = await ctx.bot.raid.conn.cursor()

        translations = ctx.bot.translations[lang]['lfg']

        lfg_list = await cursor.execute(
            'SELECT group_id, name, time, channel_name, server_name, timezone FROM raid WHERE owner=?',
            (ctx.author.id,))
        lfg_list = await lfg_list.fetchall()

        if len(lfg_list) == 0:
            await ctx.respond(translations['lfglist_empty'])
            await cursor.close()
            return

        msg = translations['lfglist_head']
        i = 1
        for lfg in lfg_list:
            msg = translations['lfglist'].format(msg, i, lfg[1], datetime.fromtimestamp(lfg[2]), lfg[5],
                                                 lfg[3], lfg[4], ctx.bot.raid.hashids.encode(lfg[0]))
            i = i + 1
        await cursor.close()
        await ctx.respond(embed=discord.Embed(description=msg))

    async def guild_lfg(self, ctx, lang, lfg_str=None):
        message = ctx.message
        await ctx.bot.raid.add(message, lfg_str)
        role = await ctx.bot.raid.get_cell('group_id', message.id, 'the_role')
        name = await ctx.bot.raid.get_cell('group_id', message.id, 'name')
        time = datetime.fromtimestamp(await ctx.bot.raid.get_cell('group_id', message.id, 'time'))
        is_embed = await ctx.bot.raid.get_cell('group_id', message.id, 'is_embed')
        description = await ctx.bot.raid.get_cell('group_id', message.id, 'description')
        lang_overrides = ['pt-br']
        if lang not in lang_overrides:
            msg = "{}, {} {}\n{} {}\n{}".format(role, ctx.bot.translations[lang]['lfg']['go'], name,
                                                ctx.bot.translations[lang]['lfg']['at'], time, description)
        else:
            msg = "{}, {} {}\n{} {}\n{}".format(role, name, ctx.bot.translations[lang]['lfg']['go'],
                                                ctx.bot.translations[lang]['lfg']['at'], time, description)
        if len(msg) > 2000:
            if lang not in lang_overrides:
                msg = "{}, {} {}".format(role, ctx.bot.translations[lang]['lfg']['go'], name)
            else:
                msg = "{} {} {}".format(role, name, ctx.bot.translations[lang]['lfg']['go'])
            if len(msg) > 2000:
                msg = role
                if len(msg) > 2000:
                    parts = msg.split(', ')
                    msg = ''
                    while len(msg) < 1900:
                        msg = '{} {},'.format(msg, parts[0])
                        parts.pop(0)
        if is_embed and ctx.channel.permissions_for(ctx.guild.me).embed_links:
            embed = await ctx.bot.raid.make_embed(message, ctx.bot.translations[lang], lang)
            out = await message.channel.send(content=msg)
            buttons = GroupButtons(out.id, ctx.bot, label_go=ctx.bot.translations[lang]['lfg']['button_want'],
                                   label_help=ctx.bot.translations[lang]['lfg']['button_help'],
                                   label_no_go=ctx.bot.translations[lang]['lfg']['button_no_go'],
                                   label_delete=ctx.bot.translations[lang]['lfg']['button_delete'])
            await out.edit(content=None, embed=embed, view=buttons)
        else:
            out = await message.channel.send(msg)
            buttons = GroupButtons(out.id, ctx.bot, label_go=ctx.bot.translations[lang]['lfg']['button_want'],
                                   label_help=ctx.bot.translations[lang]['lfg']['button_help'],
                                   label_no_go=ctx.bot.translations[lang]['lfg']['button_no_go'],
                                   label_delete=ctx.bot.translations[lang]['lfg']['button_delete'])
            await out.edit(content=msg, view=buttons)
        await ctx.bot.raid.set_id(out.id, message.id)
        await ctx.bot.raid.update_group_msg(out, ctx.bot.translations[lang], lang)
        if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            try:
                await message.delete()
            except discord.NotFound:
                pass
        return out.id

    async def dm_lfg(self, ctx, lang):
        def check(ms):
            return (ms.channel == dm) and ms.author == ctx.message.author

        async def get_proper_length_arg(arg_name, max_len):
            await dm.send(content=translations[arg_name])
            q_msg = await self.bot.wait_for('message', check=check)
            arg = q_msg.content
            while len(arg) > max_len:
                await dm.send(content=translations['too_long'].format(len(arg), max_len, translations[arg_name]))
                q_msg = await self.bot.wait_for('message', check=check)
                arg = q_msg.content
            return arg

        translations = ctx.bot.translations[lang]['lfg']

        if ctx.channel.permissions_for(ctx.guild.me).create_public_threads and ctx.channel.permissions_for(ctx.guild.me).manage_threads:
            dm = await ctx.message.create_thread(name='LFG', auto_archive_duration=60)
            await dm.add_user(ctx.message.author)

            name = await get_proper_length_arg('name', 256)
        else:
            if ctx.author.dm_channel is None:
                await ctx.author.create_dm()
            dm = ctx.author.dm_channel
            response = await ctx.message.channel.send(translations['dm_start'].format(ctx.author.mention))
            name = await get_proper_length_arg('name', 256)

            try:
                await response.delete()
            except discord.NotFound:
                pass

        description = await get_proper_length_arg('description', 4096)

        ts = datetime.now(timezone(timedelta(0))).astimezone()
        await dm.send(content=translations['time'].format(datetime.now().strftime('%d-%m-%Y %H:%M'), datetime.now().replace(tzinfo=ts.tzinfo).strftime('%d-%m-%Y %H:%M%z')))
        msg = await self.bot.wait_for('message', check=check)
        time = self.parse_date(msg.content)
        # ts = dateparser.parse(msg.content)
        # time = ts.strftime('%d-%m-%Y %H:%M%z')

        await dm.send(content=translations['size'])
        msg = await self.bot.wait_for('message', check=check)
        size = msg.content

        await dm.send(content=translations['length'])
        msg = await self.bot.wait_for('message', check=check)
        length = msg.content

        view = ActivityType(ctx.message.author, raid=translations['raid'], pve=translations['pve'],
                            gambit=translations['gambit'], pvp=translations['pvp'], default=translations['default'])
        await dm.send(content=translations['type'], view=view)
        await view.wait()
        if view.value is None:
            await dm.send('Timed out')
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass
                if type(dm) == discord.Thread:
                    await asyncio.sleep(10)
                    await dm.delete()
                return False
        a_type = view.value

        view = ModeLFG(ctx.message.author, basic=translations['basic_mode'], manual=translations['manual_mode'])
        await dm.send(content=translations['mode'].format(translations['manual_mode'], translations['basic_mode']),
                      view=view)
        await view.wait()
        if view.value is None:
            await dm.send('Timed out')
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass
                if type(dm) == discord.Thread:
                    await asyncio.sleep(10)
                    await dm.delete()
                return False
        mode = view.value

        role_list = []
        for role in ctx.guild.roles:
            if role.mentionable and not role.managed:
                role_list.append(discord.SelectOption(label=role.name, value=role.id))
        view = RoleLFG(len(role_list), role_list, ctx.message.author, manual=translations['manual_roles'],
                       auto=translations['auto_roles'])
        await dm.send(content=translations['role'], view=view)
        await view.wait()
        if view.value is None:
            await dm.send('Timed out')
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass
                if type(dm) == discord.Thread:
                    await asyncio.sleep(10)
                    await dm.delete()
                return False
        elif view.value in ['-', 'custom']:
            if view.value == 'custom':
                await dm.send(content=translations['role_manual'])
                msg = await self.bot.wait_for('message', check=check)
                role = msg.content
                role_raw = msg.content
            else:
                role = '-'
                role_raw = '-'

            role_str = ctx.bot.raid.find_roles(True, ctx.guild, [r.strip() for r in role.split(';')])
            role = ''
            for role_mention in role_str.split(', '):
                try:
                    role_obj = ctx.guild.get_role(int(role_mention.replace('<@', '').replace('!', '').replace('>', '').replace('&', '')))
                    role = '{} {};'.format(role, role_obj.name)
                except ValueError:
                    pass
        else:
            role = ''
            for role_id in view.value:
                try:
                    role_obj = ctx.guild.get_role(int(role_id))
                    role = '{} {};'.format(role, role_obj.name)
                except ValueError:
                    pass
            role_raw = role[:-1]

        if len(role) > 0:
            role = role[:-1]

        at = ['default', 'default', 'vanguard', 'raid', 'crucible', 'gambit']
        args = await ctx.bot.raid.parse_args('lfg\n-n:{}\n-d:{}\n-t:{}\n-s:{}\n-l:{}\n-at:{}\n-m:{}\n-r:{}'.
                                             format(name, description, time, size, length, a_type, mode, role)
                                             .splitlines(), ctx.message, True)
        ts = datetime.fromtimestamp(args['time']).astimezone(tz=ts.tzinfo)
        check_msg = translations['check'].format(args['name'], args['description'], ts, args['size'],
                                                 args['length']/3600, at[args['is_embed']], args['group_mode'], role)
        view = ConfirmLFG(translations['again'].format(translations['creation'], translations['creation'].lower()), ctx.message.author, translations['confirm_yes'], translations['confirm_no'])
        view.add_item(view.confirm_button)
        view.add_item(view.cancel_button)
        if len(check_msg) <= 2000:
            await dm.send(check_msg, view=view)
        else:
            check_lines = check_msg.splitlines()
            for line in check_lines:
                last_view = None
                if line == check_lines[-1]:
                    last_view = view
                if len(line) <= 2000:
                    await dm.send(line, view=last_view)
                else:
                    line_parts = line.split(':')
                    lines = ['{}:'.format(line_parts[0]), line_parts[1]]
                    if len(line_parts) > 2:
                        for arg_part in line_parts[2:]:
                            lines[1] = '{}: {}'.format(lines[1], arg_part)
                    await dm.send(lines[0])
                    await dm.send('{}...'.format(lines[1][:1997]), view=last_view)

        await view.wait()
        if view.value is None:
            await dm.send('Timed out')
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                    try:
                        await ctx.message.delete()
                    except discord.NotFound:
                        pass
            if type(dm) == discord.Thread:
                await asyncio.sleep(10)
                await dm.delete()
            return False
        elif not view.value:
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                    try:
                        await ctx.message.delete()
                    except discord.NotFound:
                        pass
            if type(dm) == discord.Thread:
                await asyncio.sleep(10)
                await dm.delete()
            return False

        group_id = await self.guild_lfg(ctx, lang, 'lfg\n-n:{}\n-d:{}\n-t:{}\n-s:{}\n-l:{}\n-at:{}\n-m:{}\n-r:{}'.
                                        format(name, description, time, size, length, at[args['is_embed']], mode,
                                               role_raw))
        await ctx.bot.raid.set_owner(ctx.author.id, group_id)

        if type(dm) == discord.Thread:
            await dm.delete()
        return group_id

    @commands.command(aliases=['сбор', 'лфг'])
    @commands.guild_only()
    async def lfg(self, ctx):
        lang = ctx.bot.guild_lang(ctx.message.guild.id)
        if len(ctx.message.content.splitlines()) > 1:
            group_id = await self.guild_lfg(ctx, lang)
        else:
            group_id = await self.dm_lfg(ctx, lang)
        if not group_id:
            return
        await ctx.channel.send(ctx.bot.translations[lang]['msg']['deprecation_warning'], delete_after=60)
        name = await ctx.bot.raid.get_cell('group_id', group_id, 'name')
        hashids = Hashids()
        group = hashids.encode(group_id)
        if ctx.guild.me.guild_permissions.manage_roles and False:  # Temporarily disabled
            group_role = await ctx.guild.create_role(name='{} | {}'.format(name, group), mentionable=True,
                                                     reason='LFG creation')
            group_ch_id = 0
            if ctx.guild.me.guild_permissions.manage_channels:
                overwrites = {
                    ctx.guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=False),
                    group_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                    ctx.guild.me: discord.PermissionOverwrite(connect=True, manage_channels=True, view_channel=True)
                }
                group_ch = await ctx.guild.create_voice_channel(name='{} | {}'.format(name, group),
                                                                reason='LFG creation', category=ctx.channel.category,
                                                                overwrites=overwrites)
                group_ch_id = group_ch.id
            await ctx.bot.raid.set_group_space(group_id, group_role.id, group_ch_id)
        out = await ctx.channel.fetch_message(group_id)
        # await out.add_reaction('👌')
        # await out.add_reaction('❓')
        # await out.add_reaction('❌')

    def parse_date(self, time):
        try:
            time_t = datetime.strptime(time, "%d-%m-%Y %H:%M%z")
        except ValueError:
            try:
                time_t = datetime.strptime(time, "%d-%m-%Y %H:%M")
            except ValueError:
                try:
                    ts = dateparser.parse(time)
                    time = ts.strftime('%d-%m-%Y %H:%M%z')
                except AttributeError:
                    time = datetime.now().strftime("%d-%m-%Y %H:%M")
        return time

    async def dm_edit_lfg(self, ctx, lang, hashids, number=None):

        def check(ms):
            return ms.channel == dm and ms.author == ctx.author

        async def get_proper_length_arg(arg_name, max_len):
            dm_content = '{}\n{}'.format(translations[arg_name], translations['dm_noedit'])
            await dm.send(content=dm_content)
            q_msg = await self.bot.wait_for('message', check=check)
            arg = q_msg.content
            while len(arg) > max_len:
                await dm.send(content=translations['too_long'].format(len(arg), max_len, dm_content))
                q_msg = await self.bot.wait_for('message', check=check)
                arg = q_msg.content
            return arg

        async def get_numerical_answer(arg_name, restraint):
            await dm.send(content=translations[arg_name])
            q_msg = await self.bot.wait_for('message', check=check)
            arg = q_msg.content
            is_number = False
            number = -1
            try:
                number = int(arg) - 1
                is_number = True
            except ValueError:
                pass
            while not is_number or (0 > number or number + 1 >= restraint):
                await dm.send(content=translations['lfg_choice_fail'].format(arg, restraint, translations[arg_name]))
                q_msg = await self.bot.wait_for('message', check=check)
                arg = q_msg.content
                try:
                    number = int(arg) - 1
                    is_number = True
                except ValueError:
                    pass
            return number

        cursor = await ctx.bot.raid.conn.cursor()

        translations = ctx.bot.translations[lang]['lfg']

        if number is None:
            is_msg = False
        else:
            is_msg = True

        if ctx.channel.permissions_for(ctx.guild.me).create_public_threads and ctx.channel.permissions_for(ctx.guild.me).manage_threads:
            lfg_list = await cursor.execute(
                'SELECT group_id, name, time, channel_name, server_name, timezone FROM raid WHERE owner=?',
                (ctx.author.id,))
            lfg_list = await lfg_list.fetchall()

            if number is None:
                dm = await ctx.message.create_thread(name='LFG', auto_archive_duration=60)
                await dm.add_user(ctx.author)

                msg = translations['lfglist_head']
                i = 1
                for lfg in lfg_list:
                    msg = translations['lfglist'].format(msg, i, lfg[1], datetime.fromtimestamp(lfg[2]), lfg[5],
                                                         lfg[3], lfg[4], ctx.bot.raid.hashids.encode(lfg[0]))
                    i = i + 1
                if len(lfg_list) > 0:
                    await dm.send(msg)
                else:
                    await dm.send(translations['lfglist_empty'])
                    if not lfg_list:
                        if type(dm) == discord.Thread:
                            await asyncio.sleep(10)
                            await dm.delete()
                            await cursor.close()
                        return
                number = await get_numerical_answer('lfg_choice', len(lfg_list) + 1)
            else:
                ctx.message = await ctx.channel.send(translations['thread_start'])
                try:
                    dm = await ctx.message.create_thread(name='LFG', auto_archive_duration=60)
                    await dm.add_user(ctx.author)
                except discord.HTTPException:
                    if ctx.author.dm_channel is None:
                        await ctx.author.create_dm()
                    dm = ctx.author.dm_channel
                    await ctx.respond(translations['dm_start'].format(ctx.author.mention))
        else:
            if ctx.author.dm_channel is None:
                await ctx.author.create_dm()
            dm = ctx.author.dm_channel
            response = await ctx.channel.send(translations['dm_start'].format(ctx.author.mention), delete_after=60)

            if number is None:
                lfg_list = await self.lfglist(ctx, lang)
                if not lfg_list:
                    if type(dm) == discord.Thread:
                        await asyncio.sleep(10)
                        await dm.delete()
                        await cursor.close()
                    return

                number = await get_numerical_answer('lfg_choice', len(lfg_list)+1)

                try:
                    await response.delete()
                except discord.NotFound:
                    pass
            else:
                lfg_list = await cursor.execute(
                    'SELECT group_id, name, time, channel_name, server_name, timezone FROM raid WHERE owner=?',
                    (ctx.author.id,))
                lfg_list = await lfg_list.fetchall()

        lfg = lfg_list[number]
        if not is_msg:
            check_msg = translations['lfglist_choice_check']
            check_msg = translations['lfglist'].format(check_msg, number+1, lfg[1], datetime.fromtimestamp(lfg[2]), lfg[5],
                                                       lfg[3], lfg[4], hashids.encode(lfg[0]))
            await dm.send(check_msg)
            msg = await self.bot.wait_for('message', check=check)
            if msg.content.lower() == translations['no']:
                await dm.send(translations['again'].format(translations['edit'], translations['edit'].lower()))
                if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                    try:
                        await ctx.message.delete()
                    except discord.NotFound:
                        pass
                    except AttributeError:
                        pass
                if type(dm) == discord.Thread:
                    await asyncio.sleep(10)
                    await dm.delete()
                    await cursor.close()
                return False
        text = '{}\n'.format(lfg[0])

        name = await get_proper_length_arg('name', 256)
        if name != '--':
            text = '{}-n:{}\n'.format(text, name)

        description = await get_proper_length_arg('description', 2048)
        if description != '--':
            text = '{}-d:{}\n'.format(text, description)

        ts = datetime.now(timezone(timedelta(0))).astimezone()
        q_line = '{}\n{}'.format(translations['time'].format(datetime.now().strftime('%d-%m-%Y %H:%M'),
                                                             datetime.now().replace(tzinfo=ts.tzinfo).
                                                             strftime('%d-%m-%Y %H:%M%z')),
                                 translations['dm_noedit'])
        await dm.send(content=q_line)
        msg = await self.bot.wait_for('message', check=check)
        time = msg.content
        if time != '--':
            ts = dateparser.parse(msg.content)
            if ts is None:
                ts = datetime.now(timezone(timedelta(0))).astimezone()
            time = self.parse_date(msg.content)
            text = '{}-t:{}\n'.format(text, time)

        q_line = '{}\n{}'.format(translations['size'], translations['dm_noedit'])
        await dm.send(content=q_line)
        msg = await self.bot.wait_for('message', check=check)
        size = msg.content
        if size != '--':
            text = '{}-s:{}\n'.format(text, size)

        q_line = '{}\n{}'.format(translations['length'], translations['dm_noedit'])
        await dm.send(content=q_line)
        msg = await self.bot.wait_for('message', check=check)
        length = msg.content
        if length != '--':
            text = '{}-l:{}\n'.format(text, length)

        q_line = '{}\n{}'.format(translations['type'], translations['dm_noedit'])
        view = ActivityType(ctx.author, raid=translations['raid'], pve=translations['pve'],
                            gambit=translations['gambit'], pvp=translations['pvp'], default=translations['default'])
        no_change_button = MyButton(type='nochange', label=translations['button_no_change'], style=discord.ButtonStyle.red, row=2)
        view.add_item(no_change_button)
        await dm.send(content=q_line, view=view)
        await view.wait()
        if view.value is None:
            await dm.send('Timed out')
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass
                except AttributeError:
                    pass
                if type(dm) == discord.Thread:
                    await asyncio.sleep(10)
                    await dm.delete()
                    await cursor.close()
                return False

        a_type = view.value
        if a_type != '--':
            text = '{}-at:{}\n'.format(text, a_type)

        q_line = '{}\n{}'.format(translations['mode'].format(translations['manual_mode'], translations['basic_mode']), translations['dm_noedit'])
        view = ModeLFG(ctx.author, basic=translations['basic_mode'], manual=translations['manual_mode'])
        view.add_item(no_change_button)
        await dm.send(content=q_line, view=view)
        await view.wait()
        if view.value is None:
            await dm.send('Timed out')
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass
                except AttributeError:
                    pass
                if type(dm) == discord.Thread:
                    await asyncio.sleep(10)
                    await dm.delete()
                    await cursor.close()
                return False
        mode = view.value
        if mode != '--':
            text = '{}-m:{}\n'.format(text, mode)

        q_line = '{}\n{}'.format(translations['role'], translations['dm_noedit'])
        role_list = []
        for role in ctx.guild.roles:
            if role.mentionable and not role.managed:
                role_list.append(discord.SelectOption(label=role.name, value=role.id))
        view = RoleLFG(len(role_list), role_list, ctx.author, manual=translations['manual_roles'],
                       auto=translations['auto_roles'])
        view.add_item(no_change_button)
        await dm.send(content=q_line, view=view)
        await view.wait()
        if view.value is None:
            await dm.send('Timed out')
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass
                except AttributeError:
                    pass
                if type(dm) == discord.Thread:
                    await asyncio.sleep(10)
                    await dm.delete()
                    await cursor.close()
                return False
        elif view.value in ['-', 'custom']:
            if view.value == 'custom':
                msg = await self.bot.wait_for('message', check=check)
                role = msg.content
                role_raw = msg.content
            else:
                role = '--'
                role_raw = '--'

            role_str = ctx.bot.raid.find_roles(True, ctx.guild, [r.strip() for r in role.split(';')])
            role = ''
            for role_mention in role_str.split(', '):
                try:
                    role_obj = ctx.guild.get_role(
                        int(role_mention.replace('<@', '').replace('!', '').replace('>', '').replace('&', '')))
                    role = '{} {};'.format(role, role_obj.name)
                except ValueError:
                    pass
            if len(role) > 0:
                role = role[:-1]
            text = '{}-r:{}\n'.format(text, role)
            pass
        elif view.value == '--':
            role = view.value
        else:
            role = ''
            for role_id in view.value:
                try:
                    role_obj = ctx.guild.get_role(int(role_id))
                    role = '{} {};'.format(role, role_obj.name)
                except ValueError:
                    pass

            if len(role) > 0:
                role = role[:-1]
            text = '{}-r:{}\n'.format(text, role)

        at = ['default', 'default', 'vanguard', 'raid', 'crucible', 'gambit']
        if is_msg:
            args = await ctx.bot.raid.parse_args(text.splitlines(), lfg[0], False, ctx.guild)
        else:
            args = await ctx.bot.raid.parse_args(text.splitlines(), ctx.message, False)
        if len(args) > 0:
            if 'length' in args.keys():
                args['length'] /= 3600
            if 'is_embed' in args.keys():
                args['is_embed'] = at[args['is_embed']]
            if 'name' not in args.keys():
                args['name'] = translations['no_change']
            if 'description' not in args.keys():
                args['description'] = translations['no_change']
            if 'description' not in args.keys():
                args['description'] = translations['no_change']
            if 'size' not in args.keys():
                args['size'] = translations['no_change']
            if 'length' not in args.keys():
                args['length'] = translations['no_change']
            if 'is_embed' not in args.keys():
                args['is_embed'] = translations['no_change']
            if 'group_mode' not in args.keys():
                args['group_mode'] = translations['no_change']
            if time != '--':
                ts = datetime.fromtimestamp(args['time']).astimezone(tz=ts.tzinfo)
                args['time'] = ts
            else:
                args['time'] = translations['no_change']
            if role == '--':
                role = translations['no_change']
            check_msg = translations['check'].format(args['name'], args['description'], args['time'], args['size'],
                                                     args['length'], args['is_embed'], args['group_mode'], role)
            view = ConfirmLFG(translations['again'].format(translations['creation'], translations['creation'].lower()),
                              ctx.author, translations['confirm_yes'], translations['confirm_no'])
            view.add_item(view.confirm_button)
            view.add_item(view.cancel_button)
            if len(check_msg) <= 2000:
                await dm.send(check_msg, view=view)
            else:
                check_lines = check_msg.splitlines()
                for line in check_lines:
                    last_view = None
                    if line == check_lines[-1]:
                        last_view = view
                    if len(line) <= 2000:
                        await dm.send(line, view=last_view)
                    else:
                        line_parts = line.split(':')
                        lines = ['{}:'.format(line_parts[0]), line_parts[1]]
                        if len(line_parts) > 2:
                            for arg_part in line_parts[2:]:
                                lines[1] = '{}: {}'.format(lines[1], arg_part)
                        await dm.send(lines[0])
                        await dm.send(lines[1], view=last_view)

            await view.wait()
            if view.value is None:
                await dm.send('Timed out')
                if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                    try:
                        await ctx.message.delete()
                    except discord.NotFound:
                        pass
                    except AttributeError:
                        pass
            elif not view.value:
                if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                    try:
                        await ctx.message.delete()
                    except discord.NotFound:
                        pass
                    except AttributeError:
                        pass
                if type(dm) == discord.Thread:
                    await asyncio.sleep(10)
                    await dm.delete()
                    await cursor.close()
                return False

        if type(dm) == discord.Thread:
            await dm.delete()
        if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            try:
                await ctx.message.delete()
            except discord.NotFound:
                pass
            except AttributeError:
                pass
        await cursor.close()
        return text

    @commands.command(aliases=['editlfg', 'editLfg', 'editLFG'])
    @commands.guild_only()
    async def edit_lfg(self, ctx, arg_id=None, *args):
        if arg_id is not None:
            if type(arg_id) == discord.Message:
                ctx.message = arg_id
        if ctx.message.guild is not None:
            lang = ctx.bot.guild_lang(ctx.message.guild.id)
        else:
            lang = 'en'
        await ctx.channel.send(ctx.bot.translations[lang]['msg']['deprecation_warning'], delete_after=60)
        message = ctx.message
        hashids = Hashids()
        dm = (arg_id is None)
        if not dm:
            dm = (type(arg_id) == discord.Message)
        if dm:
            text = await self.dm_edit_lfg(ctx, lang, hashids)
            if not text:
                return
            group_id = [int(text.splitlines()[0])]
            #TODO: notify participants about edits.
        else:
            text = message.content
            group_id = hashids.decode(arg_id)
        if len(group_id) > 0:
            old_lfg = await ctx.bot.raid.get_cell('group_id', group_id[0], 'lfg_channel')
            old_lfg = ctx.bot.get_channel(old_lfg)
            owner = await ctx.bot.raid.get_cell('group_id', group_id[0], 'owner')
            if old_lfg is not None and owner is not None:
                old_lfg = await old_lfg.fetch_message(group_id[0])
                if owner == message.author.id:
                    new_lfg = await ctx.bot.raid.edit(message, old_lfg, ctx.bot.translations[lang], lang, text)
                    buttons = GroupButtons(new_lfg.id, ctx.bot, label_go=ctx.bot.translations[lang]['lfg']['button_want'],
                                           label_help=ctx.bot.translations[lang]['lfg']['button_help'],
                                           label_no_go=ctx.bot.translations[lang]['lfg']['button_no_go'],
                                           label_delete=ctx.bot.translations[lang]['lfg']['button_delete'])
                    await new_lfg.edit(view=buttons)
                else:
                    await ctx.bot.check_ownership(message)
                    if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                        await ctx.message.delete()
            else:
                if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                    await ctx.message.delete()
        return

    @commands.slash_command(name='lfg',
                            description_localizations={
                                'ru': 'Создать сбор'
                            },
                            description='Create a group')
    @commands.guild_only()
    async def lfg_sl(self, ctx):
        lang = await locale_2_lang(ctx)
        translations = ctx.bot.translations[lang]['lfg']

        if not await message_permissions(ctx, lang):
            return

        modal = LFGModal(ctx.bot, ctx.interaction.locale, translations)
        await ctx.interaction.response.send_modal(modal)

    @commands.message_command(
        name="Edit LFG",
        name_localizations={
            'ru': 'Редактировать сбор'
        },
        description="Edit LFG post"
    )
    async def edit_lfg_msg(self, ctx, message: discord.Message):
        lang = await locale_2_lang(ctx)
        translations = ctx.bot.translations[lang]['lfg']

        if not await message_permissions(ctx, lang):
            return

        if await ctx.bot.raid.is_raid(message.id):
            owner = await ctx.bot.raid.get_cell('group_id', message.id, 'owner')
            if ctx.author.id == owner:
                await ctx.bot.raid.make_edits(ctx.bot, ctx.interaction, message, translations)
            else:
                await ctx.respond(ctx.bot.translations[lang]['lfg']['will_not_delete'], ephemeral=True)
        else:
            await ctx.respond(ctx.bot.translations[lang]['lfg']['not_a_post'], ephemeral=True)

    @commands.slash_command(
        name='editlfg',
        description_localizations={
            'ru': 'Редактировать сбор'
        },
        description='Edit LFG post'
    )
    @commands.guild_only()
    async def edit_lfg_sl(self, ctx):
        lang = await locale_2_lang(ctx)
        translations = ctx.bot.translations[lang]['lfg']

        if not await message_permissions(ctx, lang):
            return
        await ctx.defer(ephemeral=True)

        cursor = await ctx.bot.raid.conn.cursor()

        lfg_list = await cursor.execute(
            'SELECT group_id, name, time, channel_name, server_name, timezone, lfg_channel FROM raid WHERE owner=?',
            (ctx.author.id,))
        lfg_list = await lfg_list.fetchall()

        if len(lfg_list) == 0:
            await ctx.respond(translations['lfglist_empty'], ephemeral=True)
            await cursor.close()
            return
        lfg_options = []
        i = 0
        for lfg in lfg_list:
            label = ' ' if not lfg[1] else lfg[1]
            lfg_options.append(discord.SelectOption(label=label, value=str(i), description=translations['lfg_choice_select'].format(lfg[3], lfg[4], datetime.fromtimestamp(lfg[2]))))
            i += 1
        view = ViewLFG(lfg_options, ctx.author, lfg_list, ctx, translations)
        await cursor.close()
        await ctx.respond(content=translations['lfg_select'], view=view, ephemeral=True)


def setup(bot):
    bot.add_cog(Group(bot))
