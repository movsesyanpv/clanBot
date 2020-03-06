from discord.ext import commands
import importlib
import discord
from tabulate import tabulate
from datetime import datetime
import updater
import os
import main


class Admin(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.dm_only()
    @commands.is_owner()
    async def stop(self, ctx):
        msg = 'Ok, {}'.format(ctx.author.mention)
        await ctx.message.channel.send(msg)
        ctx.bot.sched.shutdown(wait=True)
        await ctx.bot.data.destiny.close()
        await ctx.bot.logout()
        await ctx.bot.close()
        return

    @commands.command(aliases=['planMaintenance'])
    @commands.dm_only()
    @commands.is_owner()
    async def plan_maintenance(self, ctx):
        try:
            content = ctx.message.content.splitlines()
            start = datetime.strptime(content[1], "%d-%m-%Y %H:%M %z")
            finish = datetime.strptime(content[2], "%d-%m-%Y %H:%M %z")
            delta = finish - start
            ctx.bot.sched.add_job(ctx.bot.pause_for, 'date', run_date=start, args=[ctx.message, delta],
                                  misfire_grace_time=600)
        except Exception as e:
            await ctx.message.channel.send('exception `{}`\nUse following format:```plan maintenance\n<start time '
                                           'formatted %d-%m-%Y %H:%M %z>\n<finish time formatted %d-%m-%Y %H:%M '
                                           '%z>```'.format(str(e)))
        return

    @commands.command(
        description='Pull the latest version from git and restart'
    )
    @commands.dm_only()
    @commands.is_owner()
    async def upgrade(self, ctx, lang='en'):
        os.system('git pull')
        importlib.reload(main)
        b = main.ClanBot(command_prefix='>')
        strings = ctx.message.content.splitlines()
        if len(strings) > 1:
            content = strings[1]
            if len(strings) > 2:
                for string in ctx.message.content.splitlines()[2:]:
                    content = '{}\n{}'.format(content, string)
            await ctx.bot.post_updates(b.version, content, lang)
        importlib.reload(updater)
        updater.go()
        await self.stop(ctx)

    @commands.command(
        name='help',
        description='The help command!',
        usage='cog',
        aliases=['man', 'hlep', 'чотут', 'ман', 'инструкция', 'ruhelp', 'helpru']
    )
    async def help_command(self, ctx, cog='all', lang=None):
        channel = ctx.message.channel
        if ctx.message.guild is not None and lang is None:
            lang = ctx.bot.guild_lang(ctx.message.guild.id)
        if lang not in ctx.bot.langs:
            lang = 'en'
        if ctx.invoked_with in ['чотут', 'ман', 'инструкция', 'ruhelp', 'helpru']:
            lang = 'ru'
        help_translations = ctx.bot.translations[lang]['help']
        cog = cog.lower()
        command_list = []
        if cog in ['all', 'help']:
            help_msg = '`{} v{}`\n{}\n'.format(ctx.bot.user.name, ctx.bot.version, help_translations['list'])
            for command in ctx.bot.commands:
                if command.name in help_translations.keys():
                    command_desc = help_translations[command.name]
                else:
                    command_desc = command.description
                if not (command.cog_name == 'Admin' and command.name != 'help') or await ctx.bot.is_owner(ctx.author):
                    command_list.append([command.name, command_desc])

            help_msg = '{}```\t{}```'.format(help_msg,
                                             tabulate(command_list, tablefmt='plain', colalign=('left', 'left'))
                                             .replace('\n', '\n\t'))
            if str(ctx.bot.user.id) in ctx.prefix:
                prefix = '@{} '.format(ctx.bot.user.name)
            else:
                prefix = ctx.prefix
            help_msg = '{}{}'.format(help_msg, help_translations['additional_info'].format(prefix, prefix))
            await ctx.message.channel.send(help_msg)
            pass
        elif cog == 'update':
            translations = help_translations['commands']['update']
            help_msg = '`{} v{}`\n{}'.format(ctx.bot.user.name, ctx.bot.version, translations['info'])
            await channel.send(help_msg)
            pass
        elif cog == 'rmnotifier':
            translations = help_translations['commands']['rmnotifier']
            help_msg = '`{} v{}`\n{}'.format(ctx.bot.user.name, ctx.bot.version, translations['info'])
            await channel.send(help_msg)
            pass
        elif cog == 'regnotifier':
            translations = help_translations['commands']['regnotifier']
            help_msg = '`{} v{}`\n{}'.format(ctx.bot.user.name, ctx.bot.version, translations['info'])
            await channel.send(help_msg)
            pass
        elif cog == 'planmaintenance':
            translations = help_translations['commands']['planmaintenance']
            help_msg = '`{} v{}`\n{}'.format(ctx.bot.user.name, ctx.bot.version, translations['info'])
            await channel.send(help_msg)
            pass
        elif cog == 'stop':
            translations = help_translations['commands']['stop']
            help_msg = '`{} v{}`\n{}'.format(ctx.bot.user.name, ctx.bot.version, translations['info'])
            await channel.send(help_msg)
            pass
        elif cog == 'lfglist':
            translations = help_translations['commands']['lfglist']
            help_msg = '`{} v{}`\n{}'.format(ctx.bot.user.name, ctx.bot.version, translations['info'])
            await channel.send(help_msg)
            pass
        elif cog in ['lfg', 'editlfg']:
            help_translations = help_translations['commands']['lfg']
            help_msg = '`{} v{}`\n{}\n{}\n'.format(ctx.bot.user.name, ctx.bot.version, help_translations['info'], help_translations['creation'])
            args = [
                ['[-n:][name:]', help_translations['name']],
                ['[-t:][time:]', help_translations['time']],
                ['[-d:][description:]', help_translations['description']],
                ['[-s:][size:]', help_translations['size']],
                ['[-m:][mode:]', help_translations['mode']],
                ['[-r:][role:]', help_translations['role']],
                ['[-l:][length:]', help_translations['length']],
                ['[-at:][type:]', help_translations['type']]
            ]
            help_msg = '{}```\t{}```'.format(help_msg,
                                             tabulate(args, tablefmt='plain', colalign=('left', 'left')).
                                             replace('\n', '\n\t'))
            await channel.send(help_msg)

            help_msg = '{}\n'.format(help_translations['creation_note'])
            await channel.send(help_msg)

            help_msg = '{}\n'.format(help_translations['example_title'])
            help_msg = '{}```@{} {}```'.format(help_msg, ctx.bot.user.name, help_translations['example_lfg'])
            await channel.send(help_msg)

            help_msg = '{}\n'.format(help_translations['edit_title'])
            help_msg = '{}{}\n'.format(help_msg, help_translations['manual'])
            await channel.send(help_msg)

            help_msg = '{}\n'.format(help_translations['use_lfg'])
            await channel.send(help_msg)
            pass


def setup(bot):
    bot.add_cog(Admin(bot))
