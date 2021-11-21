import discord


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
    def __init__(self, owner, raid='Raid', pve='pve', gambit='gambit', pvp='pvp', default='other'):
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
        self.value = None


class ModeLFG(discord.ui.View):
    def __init__(self, owner, basic='Basic', manual='Manual'):
        super().__init__()
        self.owner = owner
        self.basic_button = MyButton(type='basic', label=basic, style=discord.ButtonStyle.green)
        self.manual_button = MyButton(type='manual', label=manual, style=discord.ButtonStyle.red)
        self.add_item(self.basic_button)
        self.add_item(self.manual_button)
        self.value = None


class RoleLFG(discord.ui.View):
    def __init__(self, max_val, options, owner, manual='Enter manually', auto='Automatic', response_line='Enter names of the roles'):
        super().__init__()
        self.owner = owner
        self.select = MySelect(min_values=0, max_values=max_val, options=options, row=1)
        self.custom_button = MyButton(type='custom', label=manual, style=discord.ButtonStyle.gray, row=2, response_line=response_line)
        self.default_button = MyButton(type='default', label=auto, style=discord.ButtonStyle.gray, row=2)
        self.add_item(self.select)
        self.add_item(self.custom_button)
        self.add_item(self.default_button)
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
            await interaction.response.send_message(content=self.view.bot.translations[lang]['lfg']['gotcha'].format(nick), ephemeral=True)
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
        emoji = ''
        if was_goer:
            emoji = '👌'
        elif is_mb_goer:
            emoji = '❓'
        self.view.bot.raid.rm_people(interaction.message.id, interaction.user, emoji)
        lang = self.view.bot.guild_lang(interaction.message.guild.id)
        await self.view.bot.raid.update_group_msg(interaction.message, self.view.bot.translations[lang], lang)
        if not was_goer and not is_mb_goer:
            await interaction.response.send_message(content=self.view.bot.translations[lang]['lfg']['was_not_going'], ephemeral=True)


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
            lang = self.view.bot.guild_lang(interaction.message.guild.id)
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
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.value = None

    @discord.ui.select(placeholder='Update type', max_values=8, options=[
        discord.SelectOption(label='Strikes', value='strikes', description='Daily vanguard strike playlist modifiers'),
        discord.SelectOption(label='Spider', value='spider', description='Spider\'s material exchange'),
        discord.SelectOption(label='Nightmare hunts', value='nightmares', description='Currently available nightmare hunts'),
        discord.SelectOption(label='Crucible rotators', value='crucible', description='Currently available crucible rotators'),
        discord.SelectOption(label='Raid challenges', value='raids', description='Current week\'s raid challenges'),
        discord.SelectOption(label='Nightfall: The Ordeal', value='ordeal', description='Current nightfall'),
        discord.SelectOption(label='Empire hunt', value='empire', description='Current empire hunt'),
        discord.SelectOption(label='Xur', value='xur', description='Xur\'s location and exotics'),
        discord.SelectOption(label='Trials of osiris', value='osiris', description="Current ToO info")
    ])
    async def updates(self, select: discord.ui.Select, interaction: discord.Interaction):
        self.value = []
        if self.owner != interaction.user:
            return
        for selected in select.values:
            self.value.append(selected)
            self.stop()


class BotLangs(discord.ui.View):
    def __init__(self, owner, bot):
        super().__init__()
        self.owner = owner
        self.value = None
        options = [discord.SelectOption(label=option, value=option) for option in bot.langs]
        self.select = MySelect(min_values=0, max_values=1, options=options, row=1)
        self.add_item(self.select)
