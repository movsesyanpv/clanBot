from discord.ext import commands
import discord
from datetime import datetime, timedelta, timezone
from hashids import Hashids
import dateparser


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

        translations = ctx.bot.translations[lang]['lfg']
        status = await ctx.bot.raid.dm_lfgs(ctx.author, translations)
        return status

    async def guild_lfg(self, ctx, lang, lfg_str=None):
        message = ctx.message
        ctx.bot.raid.add(message, lfg_str)
        role = ctx.bot.raid.get_cell('group_id', message.id, 'the_role')
        name = ctx.bot.raid.get_cell('group_id', message.id, 'name')
        time = datetime.fromtimestamp(ctx.bot.raid.get_cell('group_id', message.id, 'time'))
        is_embed = ctx.bot.raid.get_cell('group_id', message.id, 'is_embed')
        description = ctx.bot.raid.get_cell('group_id', message.id, 'description')
        msg = "{}, {} {}\n{} {}\n{}".format(role, ctx.bot.translations[lang]['lfg']['go'], name,
                                            ctx.bot.translations[lang]['lfg']['at'], time, description)
        if len(msg) > 2000:
            msg = "{}, {} {}".format(role, ctx.bot.translations[lang]['lfg']['go'], name)
            if len(msg) > 2000:
                msg = role
                if len(msg) > 2000:
                    parts = msg.split(', ')
                    msg = ''
                    while len(msg) < 1900:
                        msg = '{} {},'.format(msg, parts[0])
                        parts.pop(0)
        if is_embed and ctx.channel.permissions_for(ctx.guild.me).embed_links:
            embed = ctx.bot.raid.make_embed(message, ctx.bot.translations[lang], lang)
            out = await message.channel.send(content=msg)
            await out.edit(content=None, embed=embed)
        else:
            out = await message.channel.send(msg)
        ctx.bot.raid.set_id(out.id, message.id)
        await ctx.bot.raid.update_group_msg(out, ctx.bot.translations[lang], lang)
        if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            try:
                await message.delete()
            except discord.NotFound:
                pass
        return out.id

    async def dm_lfg(self, ctx, lang):
        def check(ms):
            return ms.channel == ctx.author.dm_channel and ms.author == ctx.message.author

        async def get_proper_length_arg(arg_name, max_len):
            await dm.send(content=translations[arg_name])
            q_msg = await self.bot.wait_for('message', check=check)
            arg = q_msg.content
            while len(arg) > max_len:
                await dm.send(content=translations['too_long'].format(len(arg), max_len, translations[arg_name]))
                q_msg = await self.bot.wait_for('message', check=check)
                arg = q_msg.content
            return arg

        if ctx.author.dm_channel is None:
            await ctx.author.create_dm()
        dm = ctx.author.dm_channel

        translations = ctx.bot.translations[lang]['lfg']

        response = await ctx.message.channel.send(translations['dm_start'].format(ctx.author.mention))

        name = await get_proper_length_arg('name', 256)

        await response.delete()

        description = await get_proper_length_arg('description', 2048)

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

        view = ActivityType()
        await dm.send(content=translations['type'], view=view)
        await view.wait()
        if view.value is None:
            await dm.send('Timed out')
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass
                return False
        a_type = view.value

        view = ModeLFG()
        await dm.send(content=translations['mode'], view=view)
        await view.wait()
        if view.value is None:
            await dm.send('Timed out')
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass
                return False
        mode = view.value

        role_list = []
        for role in ctx.guild.roles:
            if role.mentionable and not role.managed:
                role_list.append(discord.SelectOption(label=role.name, value=role.id))
        view = RoleLFG(len(role_list), role_list)
        await dm.send(content=translations['role'], view=view)
        await view.wait()
        if view.value is None:
            await dm.send('Timed out')
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass
                return False
        elif view.value in ['-', 'custom']:
            if view.value == 'custom':
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

        if len(role) > 0:
            role = role[:-1]

        at = ['default', 'default', 'vanguard', 'raid', 'crucible', 'gambit']
        args = ctx.bot.raid.parse_args('lfg\n-n:{}\n-d:{}\n-t:{}\n-s:{}\n-l:{}\n-at:{}\n-m:{}\n-r:{}'.
                                       format(name, description, time, size, length, a_type, mode, role).splitlines(),
                                       ctx.message, True)
        ts = datetime.fromtimestamp(args['time']).astimezone(tz=ts.tzinfo)
        check_msg = translations['check'].format(args['name'], args['description'], ts, args['size'],
                                                 args['length']/3600, at[args['is_embed']], args['group_mode'], role)
        view = ConfirmLFG(translations['again'].format(translations['creation'], translations['creation'].lower()), "Да", "Нет")
        view.add_item(view.confirm_button)
        view.add_item(view.cancel_button)
        if len(check_msg) <= 2000:
            await dm.send(check_msg, view=view)
        else:
            check_lines = check_msg.splitlines()
            for line in check_lines:
                last_view = None
                if line == check_lines[-1]:
                    last_view = None
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
            return False
        elif not view.value:
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                    try:
                        await ctx.message.delete()
                    except discord.NotFound:
                        pass
            return False

        group_id = await self.guild_lfg(ctx, lang, 'lfg\n-n:{}\n-d:{}\n-t:{}\n-s:{}\n-l:{}\n-at:{}\n-m:{}\n-r:{}'.
                                        format(name, description, time, size, length, at[args['is_embed']], mode,
                                               role_raw))
        ctx.bot.raid.set_owner(ctx.author.id, group_id)

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
        name = ctx.bot.raid.get_cell('group_id', group_id, 'name')
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
            ctx.bot.raid.set_group_space(group_id, group_role.id, group_ch_id)
        out = await ctx.channel.fetch_message(group_id)
        await out.add_reaction('👌')
        await out.add_reaction('❓')
        await out.add_reaction('❌')

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

    async def dm_edit_lfg(self, ctx, lang, hashids):

        def check(ms):
            return ms.channel == ctx.author.dm_channel and ms.author == ctx.message.author

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

        if ctx.author.dm_channel is None:
            await ctx.author.create_dm()
        dm = ctx.author.dm_channel

        translations = ctx.bot.translations[lang]['lfg']

        response = await ctx.message.channel.send(translations['dm_start'].format(ctx.author.mention))

        lfg_list = await self.lfglist(ctx, lang)
        if not lfg_list:
            return
        number = await get_numerical_answer('lfg_choice', len(lfg_list)+1)

        await response.delete()

        check_msg = translations['lfglist_choice_check']
        lfg = lfg_list[number]
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
        view = ActivityType()
        no_change_button = MyButton(type='nochange', label='no change', style=discord.ButtonStyle.red)
        view.add_item(no_change_button)
        await dm.send(content=q_line, view=view)
        await view.wait()
        await dm.send('Timed out')
        if view.value is None:
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass
                return False

        #msg = await self.bot.wait_for('message', check=check)
        a_type = view.value
        if a_type != '--':
            text = '{}-at:{}\n'.format(text, a_type)

        q_line = '{}\n{}'.format(translations['mode'], translations['dm_noedit'])
        await dm.send(content=q_line)
        msg = await self.bot.wait_for('message', check=check)
        mode = msg.content
        if mode != '--':
            text = '{}-m:{}\n'.format(text, mode)

        q_line = '{}\n{}'.format(translations['role'], translations['dm_noedit'])
        await dm.send(content=q_line)
        msg = await self.bot.wait_for('message', check=check)
        role = msg.content
        role_raw = msg.content
        if role != '--':
            role_str = ctx.bot.raid.find_roles(True, ctx.guild, [r.strip() for r in role.split(';')])
            role = ''
            for role_mention in role_str.split(', '):
                try:
                    role_obj = ctx.guild.get_role(int(role_mention.replace('<@', '').replace('!', '').replace('>', '').replace('&', '')))
                    role = '{} {};'.format(role, role_obj.name)
                except ValueError:
                    pass
            if len(role) > 0:
                role = role[:-1]
            text = '{}-r:{}\n'.format(text, role)

        at = ['default', 'default', 'vanguard', 'raid', 'crucible', 'gambit']
        args = ctx.bot.raid.parse_args(text.splitlines(), ctx.message, False)
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
            view = ConfirmLFG(translations['again'].format(translations['edit'], translations['edit'].lower()), "Да", "Нет")
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
            elif not view.value:
                if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                    try:
                        await ctx.message.delete()
                    except discord.NotFound:
                        pass
                return False

        return text

    @commands.command(aliases=['editlfg', 'editLfg', 'editLFG'])
    @commands.guild_only()
    async def edit_lfg(self, ctx, arg_id=None, *args):
        if ctx.message.guild is not None:
            lang = ctx.bot.guild_lang(ctx.message.guild.id)
        else:
            lang = 'en'
        hashids = Hashids()
        message = ctx.message
        if arg_id is None:
            text = await self.dm_edit_lfg(ctx, lang, hashids)
            if not text:
                return
            group_id = [int(text.splitlines()[0])]
            #TODO: notify participants about edits.
        else:
            text = message.content
            group_id = hashids.decode(arg_id)
        if len(group_id) > 0:
            old_lfg = ctx.bot.raid.get_cell('group_id', group_id[0], 'lfg_channel')
            old_lfg = ctx.bot.get_channel(old_lfg)
            owner = ctx.bot.raid.get_cell('group_id', group_id[0], 'owner')
            if old_lfg is not None and owner is not None:
                old_lfg = await old_lfg.fetch_message(group_id[0])
                if owner == message.author.id:
                    await ctx.bot.raid.edit(message, old_lfg, ctx.bot.translations[lang], lang, text)
                else:
                    await ctx.bot.check_ownership(message)
                    if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                        await ctx.message.delete()
            else:
                if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                    await ctx.message.delete()
        return


class MyButton(discord.ui.Button):
    def __init__(self, type, label, style, row=1, response_line=''):
        super().__init__(style=style, label=label, row=row)
        self.button_type = type
        self.response_line = response_line

    async def callback(self, interaction: discord.Interaction):
        if self.button_type == 'confirm':
            await interaction.response.send_message('OK', ephemeral=True)
            self.view.value = True
            self.view.stop()
        elif self.button_type == 'cancel':
            await interaction.response.send_message(self.view.cancel_line, ephemeral=True)
            self.view.value = False
            self.view.stop()
        elif self.button_type == 'raid':
            self.view.value = 'raid'
            self.view.stop()
        elif self.button_type == 'pve':
            self.view.value = 'pve'
            self.view.stop()
        elif self.button_type == 'gambit':
            self.view.value = 'gambit'
            self.view.stop()
        elif self.button_type == 'pvp':
            self.view.value = 'pvp'
            self.view.stop()
        elif self.button_type == 'nochange':
            self.view.value = '--'
            self.view.stop()
        elif self.button_type == 'basic':
            self.view.value = 'basic'
            self.view.stop()
        elif self.button_type == 'manual':
            self.view.value = 'manual'
            self.view.stop()
        elif self.button_type == 'default':
            self.view.value = '-'
            self.view.stop()
        elif self.button_type == 'custom':
            self.view.value = 'custom'
            await interaction.response.send_message(self.response_line)
            self.view.stop()


class MySelect(discord.ui.Select):
    def __init__(self, min_values, max_values, options, row=1):
        super().__init__(min_values=min_values, max_values=max_values, options=options, row=row)

    async def callback(self, interaction: discord.Interaction):
        self.view.value = []
        for selected in self.values:
            self.view.value.append(selected)
            self.view.stop()


class ConfirmLFG(discord.ui.View):
    def __init__(self, cancel_line, confirm='Confirm', cancel='Cancel'):
        super().__init__()
        self.cancel_line = cancel_line
        self.confirm_button = MyButton(type='confirm', label=confirm, style=discord.ButtonStyle.green)
        self.cancel_button = MyButton(type='cancel', label=cancel, style=discord.ButtonStyle.red)
        self.confirm = confirm
        self.cancel = cancel
        self.value = None


class ActivityType(discord.ui.View):
    def __init__(self, raid='Raid', pve='pve', gambit='gambit', pvp='pvp'):
        super().__init__()
        self.raid_button = MyButton(type='raid', label='raid', style=discord.ButtonStyle.gray)
        self.pve_button = MyButton(type='pve', label='pve', style=discord.ButtonStyle.gray)
        self.gambit_button = MyButton(type='gambit', label='gambit', style=discord.ButtonStyle.gray)
        self.pvp_button = MyButton(type='pvp', label='pvp', style=discord.ButtonStyle.gray)
        self.other_button = MyButton(type='default', label='other', style=discord.ButtonStyle.gray)
        self.add_item(self.raid_button)
        self.add_item(self.pve_button)
        self.add_item(self.pvp_button)
        self.add_item(self.gambit_button)
        self.add_item(self.other_button)
        self.value = None


class ModeLFG(discord.ui.View):
    def __init__(self, basic='Basic', manual='Manual'):
        super().__init__()
        self.basic_button = MyButton(type='basic', label=basic, style=discord.ButtonStyle.green)
        self.manual_button = MyButton(type='manual', label=manual, style=discord.ButtonStyle.red)
        self.add_item(self.basic_button)
        self.add_item(self.manual_button)
        self.value = None


class RoleLFG(discord.ui.View):
    def __init__(self, max_val, options, manual='Enter manually', auto='Automatic', response_line='Enter names of the roles'):
        super().__init__()
        self.select = MySelect(min_values=0, max_values=max_val, options=options, row=1)
        self.custom_button = MyButton(type='custom', label=manual, style=discord.ButtonStyle.gray, row=2, response_line=response_line)
        self.default_button = MyButton(type='default', label=auto, style=discord.ButtonStyle.gray, row=2)
        self.add_item(self.select)
        self.add_item(self.custom_button)
        self.add_item(self.default_button)
        self.value = None


def setup(bot):
    bot.add_cog(Group(bot))
