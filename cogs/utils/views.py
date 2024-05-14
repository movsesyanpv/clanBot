import discord
from cogs.utils.converters import locale_2_lang, CtxLocale
from datetime import datetime, timedelta, timezone
from babel.dates import format_datetime
from babel import Locale
import traceback
from tabulate import tabulate


class MyButton(discord.ui.Button):
    def __init__(self, type, label, style, row=1, response_line=''):
        super().__init__(style=style, label=label, row=row)
        self.button_type = type
        self.response_line = response_line

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        # if interaction.user != self.view.owner:
        #     return
        if self.button_type == 'confirm':
            await interaction.edit_original_message(content='OK', embed=None, view=None)
            self.view.value = True
            self.view.stop()
        elif self.button_type == 'cancel':
            await interaction.edit_original_message(content=self.view.cancel_line, embed=None, view=None)
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
            await interaction.edit_original_message(content=self.response_line)
            self.view.stop()
        elif self.button_type == 'all_upd_types':
            self.view.value = 'all'
            self.view.stop()
        elif self.button_type == 'cancel':
            self.view.value = 'cancel'
            self.view.stop()


class MySelect(discord.ui.Select):
    def __init__(self, min_values, max_values, options, row=1):
        super().__init__(min_values=min_values, max_values=max_values, options=options, row=row)

    async def callback(self, interaction: discord.Interaction):
        # try:
        #     if interaction.user != self.view.owner:
        #         return
        # except AttributeError:
        #     pass
        await interaction.response.defer()
        self.view.value = []
        for selected in self.values:
            self.view.value.append(selected)
        self.view.stop()


class ConfirmView(discord.ui.View):
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


class EOLButtons(discord.ui.View):
    def __init__(self, bot_id, support_label='Support', invite_label='Invite me'):
        super().__init__()
        self.add_item(discord.ui.Button(label=support_label, url='https://discord.gg/JEbzECp'))
        self.add_item(discord.ui.Button(label=invite_label, url='https://discord.com/oauth2/authorize?client_id={}&permissions=395204623424&scope=bot%20applications.commands'.format(bot_id)))


class RoleLFG(discord.ui.View):
    def __init__(self, max_val, options, owner, is_edit=False, manual='Enter manually', auto='Automatic',
                 no_change='nochange', response_line='Enter names of the roles', has_custom=True):
        super().__init__()
        self.owner = owner
        self.select = MySelect(min_values=1, max_values=max_val, options=options, row=1)
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
        await interaction.response.defer()
        await self.view.bot.raid.add_people(interaction.message.id, interaction.user)
        lang = self.view.bot.guild_lang(interaction.message.guild.id)
        mode = await self.view.bot.raid.get_cell('group_id', interaction.message.id, 'group_mode')
        owner = self.view.bot.get_user(await self.view.bot.raid.get_cell('group_id', interaction.message.id, 'owner'))
        locale = await locale_2_lang(CtxLocale(self.view.bot, interaction.locale))
        overlap = await self.view.bot.raid.check_overlaps(interaction.message.id, interaction.user.id)
        if len(overlap) == 0:
            embed = None
        else:
            embed = await make_overlap_embed(self.view.bot, overlap, locale)
        if mode == 'manual' and owner.id != interaction.user.id:
            if interaction.user.nick is not None:
                nick = interaction.user.nick
            else:
                nick = interaction.user.name
            locale = await locale_2_lang(CtxLocale(self.view.bot, interaction.locale))
            await interaction.followup.send(content=self.view.bot.translations[locale]['lfg']['gotcha'].format(nick), embed=embed, ephemeral=True)
            await self.view.bot.raid.upd_dm(owner, interaction.message.id, self.view.bot.translations[lang])
        else:
            if embed is not None:
                await interaction.followup.send(content=None, embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(content=self.view.bot.translations[locale]['lfg']['will_not_go'],
                                                ephemeral=True)
        await self.view.bot.raid.update_group_msg(interaction.message, self.view.bot.translations[lang], lang)


async def make_overlap_embed(bot, overlap, locale) -> discord.Embed:
    translations = bot.translations[locale]['lfg']
    table_list = []
    for group in overlap:
        o_type = translations['overlap_actual']
        if group[1]:
            o_type = translations['overlap_potential']
        tz = group[0][2]
        if tz is None:
            tz = 'UTC+03:00'
        if tz == 'UTC':
            tz_elements = [0, 0]
        else:
            tz_elements = tz.strip('UTC+').split(':')
        ts = timezone(timedelta(hours=int(tz_elements[0]), minutes=int(tz_elements[1])))
        time = '{} {}'.format(format_datetime(group[0][0], 'short', tzinfo=ts, locale=Locale.parse(locale, sep='-')), tz)
        table_list.append([translations['overlap_group'].format(group_name=group[0][3], server_name=group[0][4], time=time), o_type])
    table = tabulate(tabular_data=table_list, headers=[translations['overlap_table_group'], translations['overlap_table_type']])
    if len(table) > 4090:
        table = ''
        table_tmp = tabulate(tabular_data=table_list, headers=['Group', 'Overlap type']).splitlines()
        for line in table_tmp:
            if len(table) + len(line) + 1 <= 4090:
                table = '{}{}\n'.format(table, line)

    return discord.Embed(title=translations['overlap_title'], description='```{}```'.format(table))


class MaybeButton(discord.ui.Button):
    def __init__(self, label, style, custom_id, row=1):
        super().__init__(style=style, label=label, row=row, custom_id=custom_id)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.view.bot.raid.add_mb_goers(interaction.message.id, interaction.user)
        lang = self.view.bot.guild_lang(interaction.message.guild.id)
        locale = await locale_2_lang(CtxLocale(self.view.bot, interaction.locale))
        overlap = await self.view.bot.raid.check_overlaps(interaction.message.id, interaction.user.id)
        if len(overlap) == 0:
            await interaction.followup.send(content=self.view.bot.translations[locale]['lfg']['will_not_go'], ephemeral=True)
        else:
            embed = await make_overlap_embed(self.view.bot, overlap, locale)
            await interaction.followup.send(content=None, embed=embed, ephemeral=True)
        await self.view.bot.raid.update_group_msg(interaction.message, self.view.bot.translations[lang], lang)


class AlertButton(discord.ui.Button):
    def __init__(self, label, style, custom_id, row=1):
        super().__init__(style=style, label=label, row=row, custom_id=custom_id)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        locale = await locale_2_lang(CtxLocale(self.view.bot, interaction.locale))

        was_goer = await self.view.bot.raid.is_goer(interaction.message, interaction.user)
        is_mb_goer = await self.view.bot.raid.is_mb_goer(interaction.message, interaction.user)
        was_wanter = await self.view.bot.raid.is_wanter(interaction.message, interaction.user)

        if was_wanter or was_goer or is_mb_goer:
            delta = await self.view.bot.get_lfg_alert(interaction.guild.id)
            await self.view.bot.raid.add_alert(interaction)

            await interaction.followup.send(content=self.view.bot.translations[locale]['lfg']['reminder_set'].format(delta),
                                            ephemeral=True)
        else:
            await interaction.followup.send(
                content=self.view.bot.translations[locale]['lfg']['reminder_not_set'], ephemeral=True)


class NoGoButton(discord.ui.Button):
    def __init__(self, label, style, custom_id, row=1):
        super().__init__(style=style, label=label, row=row, custom_id=custom_id)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        was_goer = await self.view.bot.raid.is_goer(interaction.message, interaction.user)
        is_mb_goer = await self.view.bot.raid.is_mb_goer(interaction.message, interaction.user)
        was_wanter = await self.view.bot.raid.is_wanter(interaction.message, interaction.user)
        emoji = ''
        if was_goer or was_wanter:
            emoji = '👌'
        elif is_mb_goer:
            emoji = '❓'
        await self.view.bot.raid.rm_people(interaction.message.id, interaction.user, emoji)
        lang = self.view.bot.guild_lang(interaction.message.guild.id)
        await self.view.bot.raid.update_group_msg(interaction.message, self.view.bot.translations[lang], lang)
        if not was_goer and not is_mb_goer:
            locale = await locale_2_lang(CtxLocale(self.view.bot, interaction.locale))
            if was_wanter:
                await interaction.followup.send(content=self.view.bot.translations[locale]['lfg']['will_not_go'], ephemeral=True)
                owner = self.view.bot.get_user(await self.view.bot.raid.get_cell('group_id', interaction.message.id, 'owner'))
                await self.view.bot.raid.upd_dm(owner, interaction.message.id, self.view.bot.translations[locale])
            else:
                await interaction.followup.send(content=self.view.bot.translations[locale]['lfg']['was_not_going'], ephemeral=True)


class DeleteButton(discord.ui.Button):
    def __init__(self, label, style, custom_id, row=1):
        super().__init__(style=style, label=label, row=row, custom_id=custom_id)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        owner = await self.view.bot.fetch_user(await self.view.bot.raid.get_cell('group_id', interaction.message.id, 'owner'))
        message = interaction.message
        if owner.id == interaction.user.id:
            mode = await self.view.bot.raid.get_cell('group_id', message.id, 'group_mode')
            if mode == 'manual':
                dm_id = await self.view.bot.raid.get_cell('group_id', message.id, 'dm_message')
                if owner.dm_channel is None:
                    await owner.create_dm()
                if dm_id != 0:
                    dm_message = await owner.dm_channel.fetch_message(dm_id)
                    await dm_message.delete()
            if message.guild.me.guild_permissions.manage_roles:
                role = message.guild.get_role(await self.view.bot.raid.get_cell('group_id', message.id, 'group_role'))
                if role is not None:
                    await role.delete(reason='LFG deletion')
            if message.guild.me.guild_permissions.manage_channels:
                group_ch = message.guild.get_channel(await self.view.bot.raid.get_cell('group_id', message.id, 'group_channel'))
                if group_ch is not None:
                    if group_ch.permissions_for(message.guild.me).manage_channels:
                        await group_ch.delete(reason='LFG deletion')
            await self.view.bot.raid.del_entry(message.id)
            await message.delete()
        else:
            lang = await locale_2_lang(CtxLocale(self.view.bot, interaction.locale))
            await interaction.followup.send(content=self.view.bot.translations[lang]['lfg']['will_not_delete'], ephemeral=True)


class GroupButtons(discord.ui.View):

    def __init__(self, group_id, bot, label_go='👌', label_help='❓', label_no_go='-', label_delete='❌',
                 label_alert='🔔', support_alerts=False):
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

        if support_alerts:
            self.alert_button = AlertButton(label_alert, discord.ButtonStyle.gray, '{}_alert'.format(group_id))
            self.add_item(self.alert_button)


class UpdateTypes(discord.ui.View):
    translations = {}
    owner = None
    value = None

    def __init__(self, ctx, lang):
        super().__init__()
        self.owner = ctx.author
        self.translations = ctx.bot.translations[lang]
        variants = set(self.translations['update_types']).intersection(set(ctx.bot.all_types))
        types = self.translations['update_types']
        options = [discord.SelectOption(label=types[option]['label'], value=option,
                                        description=types[option]['description']) for option in variants]
        self.select = MySelect(min_values=0, max_values=len(options), options=options, row=1)
        self.add_item(self.select)


class AutopostSettings(UpdateTypes):
    def __init__(self, ctx, lang, registration):
        super().__init__(ctx, lang)
        self.add_item(MyButton('all_upd_types', self.translations['msg']['all_upd_types'], discord.ButtonStyle.gray, row=2))
        if not registration:
            self.add_item(MyButton('cancel', self.translations['msg']['cancel'], discord.ButtonStyle.red, row=2))


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
        # if interaction.user != self.view.owner:
        #     return
        group = self.view.groups[int(self.values[0])]
        old_channel = await self.bot.fetch_channel(group[6])
        message = await old_channel.fetch_message(group[0])
        await self.bot.raid.make_edits(self.bot, interaction, message, self.translations)


class DMSelect(discord.ui.Select):
    def __init__(self, max_values, options, custom_id, bot):
        super().__init__(min_values=1, max_values=max_values, options=options, custom_id='{}_select'.format(custom_id))
        self.bot = bot
        self.custom_id = custom_id

    async def callback(self, interaction: discord.Interaction):
        want2goer = [int(number) for number in self.values]
        await self.bot.raid.add_going(self.custom_id, want2goer)
        lang = self.bot.guild_lang(await self.bot.raid.get_cell('group_id', self.custom_id, 'server_id'))
        channel = await self.bot.raid.get_cell('group_id', self.custom_id, 'lfg_channel')
        message = await self.bot.fetch_channel(channel)
        message = await message.fetch_message(self.custom_id)
        await self.bot.raid.update_group_msg(message, self.bot.translations[lang], lang)
        await self.bot.raid.upd_dm(interaction.user, self.custom_id, self.bot.translations[lang])


class DMSelectLFG(discord.ui.View):
    def __init__(self, options, custom_id, bot):
        super().__init__(timeout=None)

        self.select = DMSelect(max_values=len(options), options=options, custom_id=custom_id, bot=bot)
        self.add_item(self.select)


class ViewLFG(discord.ui.View):
    def __init__(self, options, owner, lfg_list, ctx, translations):
        super().__init__()
        self.owner = owner
        self.select = SelectLFG(min_values=1, max_values=1, options=options, row=1, ctx=ctx, translations=translations)
        self.add_item(self.select)
        self.groups = lfg_list


class PrioritySelection(discord.ui.View):
    def __init__(self, options, translations, cancel_line):
        super().__init__()
        self.add_item(MySelect(min_values=1, max_values=len(options), options=options))
        self.add_item(MyButton('cancel', translations['msg']['cancel'], discord.ButtonStyle.red, row=2))
        self.cancel_line = cancel_line


class LFGModal(discord.ui.Modal):
    a_type = None
    mode = None
    roles = None

    def __init__(self, bot, locale, translations, is_edit=False, data=None, message=None) -> None:
        if is_edit:
            title = translations['edit_modal_title']
        else:
            title = translations['modal_title']
        super().__init__(title=title)
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
                required=False
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

    async def on_error(self, error: Exception, interaction: discord.Interaction) -> None:
        bot_info = await self.bot_loc.bot.application_info()
        locale = await locale_2_lang(self.bot_loc)
        if isinstance(error, OverflowError):
            await interaction.edit_original_message(content=self.bot_loc.bot.translations[locale]['overflow_error'], view=None)
            return
        owner = bot_info.owner
        if owner.dm_channel is None:
            await owner.create_dm()
        traceback_str = ''
        for line in traceback.format_exception(type(error), error, error.__traceback__):
            traceback_str = '{}{}'.format(traceback_str, line)
        if len(traceback_str) < 1998:
            await owner.dm_channel.send('`{}`'.format(traceback_str))
        else:
            self.bot_loc.bot.logger.exception(traceback_str)
        command_line = '/lfg is_edit:{}'.format(self.is_edit)
        await owner.dm_channel.send('{}:\n{}'.format(interaction.user, command_line))
        await interaction.edit_original_message(content=self.bot_loc.bot.translations[locale]['error'], view=None)
        values = self.children
        self.bot_loc.bot.logger.info('Role LFG: \nname={}\ndescription={}\ntime={}\nsize={}\nlength={}\na_type={}\n'
                                     'mode={}\nroles={}'.
                                     format(values[0].value, values[1].value, values[2].value, values[3].value,
                                            values[4].value, self.a_type, self.mode,
                                            self.roles))

    async def send_initial_lfg(self, lang, args, channel) -> discord.Message:
        role = args['the_role']
        name = args['name']
        if args['timezone'] == 'UTC':
            tz_elements = [0, 0]
        else:
            tz_elements = args['timezone'].strip('UTC').split(':')
        tz_obj = timezone(timedelta(hours=int(tz_elements[0]), minutes=int(tz_elements[1])))
        time = datetime.fromtimestamp(args['time']).astimezone(tz_obj)
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

    async def validate_edits(self, a_type, mode, roles, role_str):
        cursor = await self.bot_loc.bot.raid.conn.cursor()
        group_data = await cursor.execute('''SELECT is_embed, group_mode, the_role FROM raid WHERE group_id=?''', (self.old_group.id,))
        group_data = await group_data.fetchone()
        edits = [a_type, mode, roles, role_str]
        if a_type == '--':
            edits[0] = self.at[group_data[0]]
        if a_type == '-':
            edits[0] = 'default'
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
        await cursor.close()
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
        self.a_type = view.value

        view = ModeLFG(interaction.user, self.is_edit, basic=translations['basic_mode'],
                       manual=translations['manual_mode'], no_change=translations['button_no_change'])
        await interaction.edit_original_message(
            content=translations['mode'].format(translations['manual_mode'], translations['basic_mode']),
            view=view)
        await view.wait()
        if view.value is None:
            await interaction.edit_original_message(content='Timed out')
            return
        self.mode = view.value

        role_list = []
        for role in interaction.guild.roles:
            if role.mentionable and not role.managed:
                role_list.append(discord.SelectOption(label=role.name, value=str(role.id)))
        if len(role_list) > 25:
            role_list = role_list[:25]
        if len(role_list) == 0:
            view.value = '-'
        else:
            view = RoleLFG(len(role_list), role_list, interaction.user, self.is_edit,
                           manual=translations['manual_roles'],
                           auto=translations['auto_roles'], has_custom=False,
                           no_change=translations['button_no_change'])
            await interaction.edit_original_message(content=translations['role'], view=view)
            await view.wait()
        if view.value is None:
            await interaction.edit_original_message(content='Timed out')
            return False
        elif view.value in ['-', '--']:
            role = view.value
            role_raw = view.value

            role_str = await self.bot_loc.bot.raid.find_roles(not self.is_edit, interaction.guild, [r.strip() for r in role.split(';')], self.old_group)
            role = ''
            self.roles = []
            for role_mention in role_str.split(', '):
                try:
                    if role_mention != '@everyone':
                        role_obj = interaction.guild.get_role(int(role_mention.replace('<@', '').replace('!', '').replace('>', '').replace('&', '')))
                        self.roles.append(role_obj)
                        role = '{} {};'.format(role, role_obj.name)
                    else:
                        role_obj = interaction.guild.default_role
                        self.roles.append(role_obj)
                        role = '{} {};'.format(role, 'everyone')
                except ValueError:
                    pass
        else:
            role = ''
            self.roles = []
            print(view.value)
            for role_id in view.value:
                try:
                    role_obj = interaction.guild.get_role(int(role_id))
                    self.roles.append(role_obj)
                    role = '{} {};'.format(role, role_obj.name)
                except ValueError:
                    pass
            role_raw = role[:-1]

        if len(role) > 0:
            role = role[:-1]

        values = self.children
        await interaction.edit_original_message(content=translations['processing'], view=None)
        if self.is_edit:
            button_inputs = await self.validate_edits(self.a_type, self.mode, self.roles, role)
        else:
            if self.a_type == '-':
                self.a_type = 'default'
            button_inputs = [self.a_type, self.mode, self.roles, role]
        args = await self.bot_loc.bot.raid.parse_args_sl(values[0].value, values[1].value, values[2].value, values[3].value, values[4].value, button_inputs[0], button_inputs[1], button_inputs[2], interaction.guild_id)
        ts = datetime.now(timezone(timedelta(0))).astimezone()
        if args['timezone'] == 'UTC':
            tz_elements = [0, 0]
        else:
            tz_elements = args['timezone'].strip('UTC').split(':')
        tz_obj = timezone(timedelta(hours=int(tz_elements[0]), minutes=int(tz_elements[1])))
        ts = datetime.fromtimestamp(args['time']).astimezone(tz=tz_obj)
        check_msg = translations['check'].format(translations['check_embed'], translations['check_embed'],
                                                 translations['check_embed'], args['size'], args['length'] / 3600,
                                                 self.at[args['is_embed']], args['group_mode'], button_inputs[3])
        view = ConfirmView(translations['again'].format(translations['creation'], translations['creation'].lower()),
                           interaction.user, translations['confirm_yes'], translations['confirm_no'])
        view.add_item(view.confirm_button)
        view.add_item(view.cancel_button)
        check_embed = discord.Embed()
        check_embed.description = args['description']
        check_embed.title = args['name']
        if 'zh' in lang:
            loc = 'zh'
        else:
            loc = lang
        if await self.bot_loc.bot.guild_timezone_is_set(interaction.guild_id):
            time_str = discord.utils.format_dt(ts)
        else:
            time_str = '{} {}'.format(
                format_datetime(ts, 'medium', tzinfo=ts.tzinfo, locale=Locale.parse(loc, sep='-')), args['timezone'])
        check_embed.add_field(
            name=self.bot_loc.bot.translations[lang]['lfge']['date'],
            value=time_str
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
            await self.bot_loc.bot.raid.add(group, args=args)
            await self.bot_loc.bot.raid.set_owner(interaction.user, group.id)
        else:
            old_channel = await self.bot_loc.bot.raid.get_cell('group_id', self.old_group.id, 'lfg_channel')
            old_channel = await self.bot_loc.bot.fetch_channel(old_channel)
            old_roles = await self.bot_loc.bot.raid.get_cell('group_id', self.old_group.id, 'the_role')
            if channel.id == old_channel.id and old_roles == args['the_role']:
                await self.bot_loc.bot.raid.edit_info(self.old_group, args)
                group = self.old_group
            else:
                group = await self.send_initial_lfg(lang, args, channel)
                await self.bot_loc.bot.raid.edit_info(self.old_group, args, group)
                await self.old_group.delete()
        if channel.permissions_for(interaction.guild.me).embed_links:
            embed = await self.bot_loc.bot.raid.make_embed(group, self.bot_loc.bot.translations[lang], lang)
            buttons = GroupButtons(group.id, self.bot_loc.bot,
                                   label_go=self.bot_loc.bot.translations[lang]['lfg']['button_want'],
                                   label_help=self.bot_loc.bot.translations[lang]['lfg']['button_help'],
                                   label_no_go=self.bot_loc.bot.translations[lang]['lfg']['button_no_go'],
                                   label_delete=self.bot_loc.bot.translations[lang]['lfg']['button_delete'],
                                   label_alert=self.bot_loc.bot.translations[lang]['lfg']['button_alert'],
                                   support_alerts=await self.bot_loc.bot.lfg_alerts_enabled(interaction.guild_id))
            await group.edit(content=None, embed=embed, view=buttons)
        else:
            buttons = GroupButtons(group.id, self.bot_loc.bot,
                                   label_go=self.bot_loc.bot.translations[lang]['lfg']['button_want'],
                                   label_help=self.bot_loc.bot.translations[lang]['lfg']['button_help'],
                                   label_no_go=self.bot_loc.bot.translations[lang]['lfg']['button_no_go'],
                                   label_delete=self.bot_loc.bot.translations[lang]['lfg']['button_delete'],
                                   label_alert=self.bot_loc.bot.translations[lang]['lfg']['button_alert'],
                                   support_alerts=await self.bot_loc.bot.lfg_alerts_enabled(interaction.guild_id))
            await group.edit(content=group.content, view=buttons)
        return
