import discord
from cogs.utils.converters import locale_2_lang, CtxLocale
from datetime import datetime, timedelta, timezone
from babel.dates import format_datetime
from babel import Locale


class MyButton(discord.ui.Button):
    def __init__(self, type, label, style, row=1, response_line=''):
        super().__init__(style=style, label=label, row=row)
        self.button_type = type
        self.response_line = response_line

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.view.owner:
            return
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
        if interaction.user != self.view.owner:
            return
        self.view.value = []
        for selected in self.values:
            self.view.value.append(selected)
            self.view.stop()


class ConfirmLFG(discord.ui.View):
    def __init__(self, cancel_line, owner, confirm='Confirm', cancel='Cancel'):
        super().__init__()
        self.owner = owner
        self.cancel_line = cancel_line
        self.confirm_button = MyButton(type='confirm', label=confirm, style=discord.ButtonStyle.green)
        self.cancel_button = MyButton(type='cancel', label=cancel, style=discord.ButtonStyle.red)
        self.confirm = confirm
        self.cancel = cancel
        self.value = None


class ActivityType(discord.ui.View):
    def __init__(self, owner, is_edit=False, raid='Raid', pve='pve', gambit='gambit', pvp='pvp', default='other', no_change='nochange'):
        super().__init__()
        self.owner = owner
        self.raid_button = MyButton(type='raid', label=raid, style=discord.ButtonStyle.gray)
        self.pve_button = MyButton(type='pve', label=pve, style=discord.ButtonStyle.gray)
        self.gambit_button = MyButton(type='gambit', label=gambit, style=discord.ButtonStyle.gray)
        self.pvp_button = MyButton(type='pvp', label=pvp, style=discord.ButtonStyle.gray)
        self.other_button = MyButton(type='default', label=default, style=discord.ButtonStyle.gray)
        self.add_item(self.raid_button)
        self.add_item(self.pve_button)
        self.add_item(self.pvp_button)
        self.add_item(self.gambit_button)
        self.add_item(self.other_button)
        if is_edit:
            self.no_change = MyButton(type='nochange', label=no_change, style=discord.ButtonStyle.red, row=2)
            self.add_item(self.no_change)
        self.value = None


class ModeLFG(discord.ui.View):
    def __init__(self, owner, is_edit=False, basic='Basic', manual='Manual', no_change='nochange'):
        super().__init__()
        self.owner = owner
        self.basic_button = MyButton(type='basic', label=basic, style=discord.ButtonStyle.green)
        self.manual_button = MyButton(type='manual', label=manual, style=discord.ButtonStyle.red)
        self.add_item(self.basic_button)
        self.add_item(self.manual_button)
        if is_edit:
            self.no_change = MyButton(type='nochange', label=no_change, style=discord.ButtonStyle.red, row=2)
            self.add_item(self.no_change)
        self.value = None


class RoleLFG(discord.ui.View):
    def __init__(self, max_val, options, owner, is_edit=False, manual='Enter manually', auto='Automatic',
                 no_change='nochange', response_line='Enter names of the roles', has_custom=True):
        super().__init__()
        self.owner = owner
        self.select = MySelect(min_values=0, max_values=max_val, options=options, row=1)
        if has_custom:
            self.custom_button = MyButton(type='custom', label=manual, style=discord.ButtonStyle.gray, row=2,
                                          response_line=response_line)
            self.add_item(self.custom_button)
        self.default_button = MyButton(type='default', label=auto, style=discord.ButtonStyle.gray, row=2)
        self.add_item(self.select)
        self.add_item(self.default_button)
        if is_edit:
            self.no_change = MyButton(type='nochange', label=no_change, style=discord.ButtonStyle.red, row=2)
            self.add_item(self.no_change)
        self.value = None


class WantButton(discord.ui.Button):
    def __init__(self, label, style, custom_id, row=1):
        super().__init__(style=style, label=label, row=row, custom_id=custom_id)

    async def callback(self, interaction: discord.Interaction):
        self.view.bot.raid.add_people(interaction.message.id, interaction.user)
        lang = self.view.bot.guild_lang(interaction.message.guild.id)
        await self.view.bot.raid.update_group_msg(interaction.message, self.view.bot.translations[lang], lang)
        mode = self.view.bot.raid.get_cell('group_id', interaction.message.id, 'group_mode')
        owner = self.view.bot.get_user(self.view.bot.raid.get_cell('group_id', interaction.message.id, 'owner'))
        if mode == 'manual' and owner.id != interaction.user.id:
            if interaction.user.nick is not None:
                nick = interaction.user.nick
            else:
                nick = interaction.user.name
            locale = await locale_2_lang(CtxLocale(self.view.bot, interaction.locale))
            await interaction.response.send_message(content=self.view.bot.translations[locale]['lfg']['gotcha'].format(nick), ephemeral=True)
            await self.view.bot.raid.upd_dm(owner, interaction.message.id, self.view.bot.translations[lang])


class MaybeButton(discord.ui.Button):
    def __init__(self, label, style, custom_id, row=1):
        super().__init__(style=style, label=label, row=row, custom_id=custom_id)

    async def callback(self, interaction: discord.Interaction):
        self.view.bot.raid.add_mb_goers(interaction.message.id, interaction.user)
        lang = self.view.bot.guild_lang(interaction.message.guild.id)
        await self.view.bot.raid.update_group_msg(interaction.message, self.view.bot.translations[lang], lang)


class NoGoButton(discord.ui.Button):
    def __init__(self, label, style, custom_id, row=1):
        super().__init__(style=style, label=label, row=row, custom_id=custom_id)

    async def callback(self, interaction: discord.Interaction):
        was_goer = self.view.bot.raid.is_goer(interaction.message, interaction.user)
        is_mb_goer = self.view.bot.raid.is_mb_goer(interaction.message, interaction.user)
        was_wanter = self.view.bot.raid.is_wanter(interaction.message, interaction.user)
        emoji = ''
        if was_goer or was_wanter:
            emoji = '👌'
        elif is_mb_goer:
            emoji = '❓'
        self.view.bot.raid.rm_people(interaction.message.id, interaction.user, emoji)
        lang = self.view.bot.guild_lang(interaction.message.guild.id)
        await self.view.bot.raid.update_group_msg(interaction.message, self.view.bot.translations[lang], lang)
        if not was_goer and not is_mb_goer:
            locale = await locale_2_lang(CtxLocale(self.view.bot, interaction.locale))
            if was_wanter:
                await interaction.response.send_message(content=self.view.bot.translations[locale]['lfg']['will_not_go'], ephemeral=True)
                owner = self.view.bot.get_user(self.view.bot.raid.get_cell('group_id', interaction.message.id, 'owner'))
                await self.view.bot.raid.upd_dm(owner, interaction.message.id, self.view.bot.translations[locale])
            else:
                await interaction.response.send_message(content=self.view.bot.translations[locale]['lfg']['was_not_going'], ephemeral=True)


class DeleteButton(discord.ui.Button):
    def __init__(self, label, style, custom_id, row=1):
        super().__init__(style=style, label=label, row=row, custom_id=custom_id)

    async def callback(self, interaction: discord.Interaction):
        owner = self.view.bot.get_user(self.view.bot.raid.get_cell('group_id', interaction.message.id, 'owner'))
        message = interaction.message
        if owner.id == interaction.user.id:
            mode = self.view.bot.raid.get_cell('group_id', message.id, 'group_mode')
            if mode == 'manual':
                dm_id = self.view.bot.raid.get_cell('group_id', message.id, 'dm_message')
                if owner.dm_channel is None:
                    await owner.create_dm()
                if dm_id != 0:
                    dm_message = await owner.dm_channel.fetch_message(dm_id)
                    await dm_message.delete()
            if message.guild.me.guild_permissions.manage_roles:
                role = message.guild.get_role(self.view.bot.raid.get_cell('group_id', message.id, 'group_role'))
                if role is not None:
                    await role.delete(reason='LFG deletion')
            if message.guild.me.guild_permissions.manage_channels:
                group_ch = message.guild.get_channel(self.view.bot.raid.get_cell('group_id', message.id, 'group_channel'))
                if group_ch is not None:
                    if group_ch.permissions_for(message.guild.me).manage_channels:
                        await group_ch.delete(reason='LFG deletion')
            self.view.bot.raid.del_entry(message.id)
            await message.delete()
        else:
            lang = await locale_2_lang(CtxLocale(self.view.bot, interaction.locale))
            await interaction.response.send_message(content=self.view.bot.translations[lang]['lfg']['will_not_delete'], ephemeral=True)


class GroupButtons(discord.ui.View):

    def __init__(self, group_id, bot, label_go='👌', label_help='❓', label_no_go='-', label_delete='❌'):
        super().__init__(timeout=None)
        self.bot = bot

        self.want_button = WantButton(label_go, discord.ButtonStyle.green, '{}_go'.format(group_id))
        self.maybe_button = MaybeButton(label_help, discord.ButtonStyle.gray, '{}_maybe'.format(group_id))
        self.no_go_button = NoGoButton(label_no_go, discord.ButtonStyle.gray, '{}_no_go'.format(group_id))
        self.delete_button = DeleteButton(label_delete, discord.ButtonStyle.red, '{}_delete'.format(group_id))
        self.add_item(self.want_button)
        self.add_item(self.maybe_button)
        self.add_item(self.no_go_button)
        self.add_item(self.delete_button)


class UpdateTypes(discord.ui.View):
    def __init__(self, ctx, lang):
        super().__init__()
        self.owner = ctx.author
        self.value = None
        translations = ctx.bot.translations[lang]
        variants = set(translations['update_types']).intersection(set(ctx.bot.all_types))
        types = translations['update_types']
        options = [discord.SelectOption(label=types[option]['label'], value=option,
                                        description=types[option]['description']) for option in variants]
        self.select = MySelect(min_values=0, max_values=1, options=options, row=1)
        self.add_item(self.select)


class BotLangs(discord.ui.View):
    def __init__(self, owner, bot):
        super().__init__()
        self.owner = owner
        self.value = None
        options = [discord.SelectOption(label=option, value=option) for option in bot.langs]
        self.select = MySelect(min_values=0, max_values=1, options=options, row=1)
        self.add_item(self.select)


class SelectLFG(discord.ui.Select):
    def __init__(self, min_values, max_values, options, ctx, translations, row=1):
        super().__init__(min_values=min_values, max_values=max_values, options=options, row=row)
        self.bot = ctx.bot
        self.ctx = ctx
        self.translations = translations

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.view.owner:
            return
        group = self.view.groups[int(self.values[0])]
        old_channel = await self.bot.fetch_channel(group[6])
        message = await old_channel.fetch_message(group[0])
        await self.bot.raid.make_edits(self.bot, interaction, message, self.translations)


class ViewLFG(discord.ui.View):
    def __init__(self, options, owner, lfg_list, ctx, translations):
        super().__init__()
        self.owner = owner
        self.select = SelectLFG(min_values=1, max_values=1, options=options, row=1, ctx=ctx, translations=translations)
        self.add_item(self.select)
        self.groups = lfg_list


class LFGModal(discord.ui.Modal):

    def __init__(self, bot, locale, translations, is_edit=False, data=None, message=None) -> None:
        if is_edit:
            title = translations['edit_modal_title']
        else:
            title = translations['modal_title']
        super().__init__(title)
        self.bot_loc = CtxLocale(bot, locale)
        self.is_edit = is_edit
        self.old_group = message
        self.at = ['default', 'default', 'pve', 'raid', 'pvp', 'gambit']
        if data is None:
            data = {
                'name': '',
                'description': '',
                'time': '',
                'size': '',
                'length': ''
            }
        self.add_item(discord.ui.InputText(
            label=translations['name'],
            value=data['name'],
            max_length=256,
            required=True))
        self.add_item(
            discord.ui.InputText(
                label=translations['description'],
                value=data['description'],
                style=discord.InputTextStyle.long,
                required=True
            )
        )
        self.add_item(
            discord.ui.InputText(
                label=translations['time_modal'],
                value=data['time'],
                placeholder=translations['time_placeholder'],
                style=discord.InputTextStyle.short,
                required=True
            )
        )
        self.add_item(
            discord.ui.InputText(
                label=translations['size'],
                value=data['size'],
                style=discord.InputTextStyle.short,
                required=True
            )
        )
        self.add_item(
            discord.ui.InputText(
                label=translations['length_modal'],
                value=data['length'],
                placeholder=translations['length_placeholder'],
                style=discord.InputTextStyle.short,
                required=False
            )
        )

    async def send_initial_lfg(self, lang, args, channel) -> discord.Message:
        role = args['the_role']
        name = args['name']
        time = datetime.fromtimestamp(args['time'])
        description = args['description']

        lang_overrides = ['pt-br']
        if lang not in lang_overrides:
            msg = "{}, {} {}\n{} {}\n{}".format(role, self.bot_loc.bot.translations[lang]['lfg']['go'], name,
                                                self.bot_loc.bot.translations[lang]['lfg']['at'], time, description)
        else:
            msg = "{}, {} {}\n{} {}\n{}".format(role, name, self.bot_loc.bot.translations[lang]['lfg']['go'],
                                                self.bot_loc.bot.translations[lang]['lfg']['at'], time, description)
        if len(msg) > 2000:
            if lang not in lang_overrides:
                msg = "{}, {} {}".format(role, self.bot_loc.bot.translations[lang]['lfg']['go'], name)
            else:
                msg = "{} {} {}".format(role, name, self.bot_loc.bot.translations[lang]['lfg']['go'])
            if len(msg) > 2000:
                msg = role
                if len(msg) > 2000:
                    parts = msg.split(', ')
                    msg = ''
                    while len(msg) < 1900:
                        msg = '{} {},'.format(msg, parts[0])
                        parts.pop(0)
        return await channel.send(msg)

    def validate_edits(self, a_type, mode, roles, role_str):
        group_data = self.bot_loc.bot.raid.c.execute('''SELECT is_embed, group_mode, the_role FROM raid WHERE group_id=?''', (self.old_group.id,))
        group_data = group_data.fetchone()
        edits = [a_type, mode, roles, role_str]
        if a_type == '--':
            edits[0] = self.at[group_data[0]]
        if mode == '--':
            edits[1] = group_data[1]
        if not roles:
            edits[2] = []
            for role_mention in group_data[2].split(', '):
                try:
                    role_obj = self.old_group.guild.get_role(int(role_mention.replace('<@', '').replace('!', '').replace('>', '').replace('&', '')))
                    edits[2].append(role_obj)
                    edits[3] = '{} {};'.format(edits[3], role_obj.name)
                except ValueError:
                    pass
            if len(edits[3]) > 0:
                edits[3] = edits[3][:-1]
        return edits

    async def callback(self, interaction: discord.Interaction):
        lang = await locale_2_lang(self.bot_loc)
        translations = self.bot_loc.bot.translations[lang]['lfg']
        view = ActivityType(interaction.user, self.is_edit, raid=translations['raid'], pve=translations['pve'],
                            gambit=translations['gambit'], pvp=translations['pvp'], default=translations['default'],
                            no_change=translations['button_no_change'])
        await interaction.response.send_message(content=translations['type'], view=view, ephemeral=True)
        await view.wait()
        if view.value is None:
            await interaction.edit_original_message(content='Timed out')
            return
        a_type = view.value

        view = ModeLFG(interaction.user, self.is_edit, basic=translations['basic_mode'],
                       manual=translations['manual_mode'], no_change=translations['button_no_change'])
        await interaction.edit_original_message(
            content=translations['mode'].format(translations['manual_mode'], translations['basic_mode']),
            view=view)
        await view.wait()
        if view.value is None:
            await interaction.edit_original_message(content='Timed out')
            return
        mode = view.value

        role_list = []
        for role in interaction.guild.roles:
            if role.mentionable and not role.managed:
                role_list.append(discord.SelectOption(label=role.name, value=str(role.id)))
        view = RoleLFG(len(role_list), role_list, interaction.user, self.is_edit, manual=translations['manual_roles'],
                       auto=translations['auto_roles'], has_custom=False, no_change=translations['button_no_change'])
        await interaction.edit_original_message(content=translations['role'], view=view)
        await view.wait()
        if view.value is None:
            await interaction.edit_original_message(content='Timed out')
            return False
        elif view.value in ['-']:
            role = '-'
            role_raw = '-'

            role_str = self.bot_loc.bot.raid.find_roles(True, interaction.guild, [r.strip() for r in role.split(';')])
            role = ''
            roles = []
            for role_mention in role_str.split(', '):
                try:
                    role_obj = interaction.guild.get_role(int(role_mention.replace('<@', '').replace('!', '').replace('>', '').replace('&', '')))
                    roles.append(role_obj)
                    role = '{} {};'.format(role, role_obj.name)
                except ValueError:
                    pass
        else:
            role = ''
            roles = []
            for role_id in view.value:
                try:
                    role_obj = interaction.guild.get_role(int(role_id))
                    roles.append(role_obj)
                    role = '{} {};'.format(role, role_obj.name)
                except ValueError:
                    pass
            role_raw = role[:-1]

        if len(role) > 0:
            role = role[:-1]

        values = self.children
        await interaction.edit_original_message(content=translations['processing'], view=None)
        if self.is_edit:
            button_inputs = self.validate_edits(a_type, mode, roles, role)
        else:
            button_inputs = [a_type, mode, roles, role]
        args = self.bot_loc.bot.raid.parse_args_sl(values[0].value, values[1].value, values[2].value, values[3].value, values[4].value, button_inputs[0], button_inputs[1], button_inputs[2])
        ts = datetime.now(timezone(timedelta(0))).astimezone()
        ts = datetime.fromtimestamp(args['time']).astimezone(tz=ts.tzinfo)
        check_msg = translations['check'].format(translations['check_embed'], translations['check_embed'],
                                                 translations['check_embed'], args['size'], args['length'] / 3600,
                                                 self.at[args['is_embed']], args['group_mode'], button_inputs[3])
        view = ConfirmLFG(translations['again'].format(translations['creation'], translations['creation'].lower()),
                          interaction.user, translations['confirm_yes'], translations['confirm_no'])
        view.add_item(view.confirm_button)
        view.add_item(view.cancel_button)
        check_embed = discord.Embed()
        check_embed.description = args['description']
        check_embed.title = args['name']
        check_embed.add_field(
            name=self.bot_loc.bot.translations[lang]['lfge']['date'],
            value='{} {}'.format(format_datetime(ts, 'medium', tzinfo=ts.tzinfo, locale=Locale.parse(lang, sep='-')),
                                 args['timezone'])
        )

        await interaction.edit_original_message(content=check_msg, embed=check_embed, view=view)

        await view.wait()
        if view.value is None:
            await interaction.edit_original_message(content='Timed out')
            return
        elif not view.value:
            return

        channel = await self.bot_loc.bot.fetch_channel(interaction.channel.id)
        lang = self.bot_loc.bot.guild_lang(interaction.guild.id)
        if not self.is_edit:
            group = await self.send_initial_lfg(lang, args, channel)
            self.bot_loc.bot.raid.add(group, args=args)
            self.bot_loc.bot.raid.set_owner(interaction.user.id, group.id)
        else:
            old_channel = self.bot_loc.bot.raid.get_cell('group_id', self.old_group.id, 'lfg_channel')
            old_channel = await self.bot_loc.bot.fetch_channel(old_channel)
            old_roles = self.bot_loc.bot.raid.get_cell('group_id', self.old_group.id, 'the_role')
            if channel.id == old_channel.id and old_roles == args['the_role']:
                await self.bot_loc.bot.raid.edit_info(self.old_group, args)
                group = self.old_group
            else:
                group = await self.send_initial_lfg(lang, args, channel)
                await self.bot_loc.bot.raid.edit_info(self.old_group, args, group)
                await self.old_group.delete()
        if channel.permissions_for(interaction.guild.me).embed_links:
            embed = self.bot_loc.bot.raid.make_embed(group, self.bot_loc.bot.translations[lang], lang)
            buttons = GroupButtons(group.id, self.bot_loc.bot,
                                   label_go=self.bot_loc.bot.translations[lang]['lfg']['button_want'],
                                   label_help=self.bot_loc.bot.translations[lang]['lfg']['button_help'],
                                   label_no_go=self.bot_loc.bot.translations[lang]['lfg']['button_no_go'],
                                   label_delete=self.bot_loc.bot.translations[lang]['lfg']['button_delete'])
            await group.edit(content=None, embed=embed, view=buttons)
        else:
            buttons = GroupButtons(group.id, self.bot_loc.bot,
                                   label_go=self.bot_loc.bot.translations[lang]['lfg']['button_want'],
                                   label_help=self.bot_loc.bot.translations[lang]['lfg']['button_help'],
                                   label_no_go=self.bot_loc.bot.translations[lang]['lfg']['button_no_go'],
                                   label_delete=self.bot_loc.bot.translations[lang]['lfg']['button_delete'])
            await group.edit(content=group.content, view=buttons)
        return
