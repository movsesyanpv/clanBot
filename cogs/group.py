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

    @commands.slash_command(name='lfglist',
                            description_localizations={
                                'ru': 'Вывести список ваших сборов',
                                'de': 'Kopiere deine LFG liste',
                                'fr': 'Affichez votre liste LFG'
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

    @commands.slash_command(name='lfg',
                            description_localizations={
                                'ru': 'Создать сбор',
                                'de': 'Erstellen Sie eine LFG-Nachricht',
                                'fr': 'Creer un message LFG'
                            },
                            description='Create a group',
                            guild_only=True)
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
            'ru': 'Редактировать сбор',
            'fr': 'Editer le LFG'
        },
        description="Edit LFG post",
        guild_only=True
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
            'ru': 'Редактировать сбор',
            'de': 'Bearbeite eine LFG Nachricht',
            'fr': 'Édition du message LFG'
        },
        description='Edit LFG post',
        guild_only=True
    )
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
