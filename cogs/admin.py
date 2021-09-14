from discord.ext import commands
import importlib
import discord
import json
from tabulate import tabulate
from datetime import datetime, timedelta, timezone
import updater
import os
import sqlite3
import pydest
import mariadb
import asyncio

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

    @commands.command(aliases=['planMaintenance', 'planmaintenance'])
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
        description='Get Bungie JSON for the API path'
    )
    @commands.is_owner()
    async def bungierequest(self, ctx, path):
        resp = await ctx.bot.data.get_bungie_json(path, 'https://www.bungie.net/Platform/{}'.format(path), change_msg=False)
        resp_json = resp
        msg = '```{}```'.format(json.dumps(resp_json, indent=4, ensure_ascii=False))
        if len(msg) <= 2000:
            await ctx.channel.send(msg)
        else:
            msg_lines = json.dumps(resp_json, indent=4, ensure_ascii=False).splitlines()
            msg = '```'
            for line in msg_lines:
                if len(msg) + len(line) <= 1990:
                    msg = '{}{}\n'.format(msg, line)
                else:
                    msg = '{}```'.format(msg)
                    await ctx.channel.send(msg)
                    msg = '```{}\n'.format(line)
            if len(msg) > 0:
                msg = '{}```'.format(msg)
                await ctx.channel.send(msg)

    @commands.command(
        description='Drop cache database'
    )
    @commands.is_owner()
    async def dropcache(self, ctx):
        while True:
            try:
                cache_db = self.bot.data.cache_pool.get_connection()
                break
            except mariadb.PoolError:
                await asyncio.sleep(0.125)
        cursor = cache_db.cursor()
        cursor.execute('''DROP TABLE cache''')
        cache_db.commit()
        cache_db.close()
        await ctx.channel.send('Done, {}'.format(ctx.author.mention))

    @commands.is_owner()
    @commands.command(
        description='Force update playermetrics'
    )
    async def forcemetrics(self, ctx):
        await ctx.bot.update_metrics()
        await ctx.message.reply('Done')

    @commands.is_owner()
    @commands.command(
        description='Set Trials of Osiris info'
    )
    async def osiris(self, ctx, curr_map, flawless):
        url = 'https://bungie.net/Platform/Destiny2/Armory/Search/{}/{}'
        map_resp = await self.bot.data.get_bungie_json('too map', url.format('DestinyActivityDefinition', curr_map),
                                                       change_msg=False)
        if len(map_resp['Response']['results']['results']) > 0:
            curr_map = map_resp['Response']['results']['results'][0]['hash']
        if flawless not in self.bot.translations['en']['osiris'].keys():
            flawless_resp = await self.bot.data.get_bungie_json('flawless', url.format('DestinyCollectibleDefinition', flawless),
                                                            change_msg=False)
            if len(flawless_resp['Response']['results']['results']) > 0:
                if len(flawless_resp['Response']['results']['results']) > 1 and '(' in flawless_resp['Response']['results']['results'][0]['displayProperties']['name']:
                    flawless = flawless_resp['Response']['results']['results'][1]['hash']
                else:
                    flawless = flawless_resp['Response']['results']['results'][0]['hash']
        await self.bot.data.get_osiris_predictions(self.bot.langs, force_info=[curr_map, flawless])
        await ctx.bot.force_update('osiris', get=False, channels=None, forceget=False)
        await ctx.channel.send('done')

    @commands.is_owner()
    @commands.command(
        description='Check connection stats'
    )
    async def connstats(self, ctx):
        await ctx.channel.send(f'Ping is {ctx.bot.latency*1000} ms')

    @commands.is_owner()
    @commands.command()
    async def fetchclans(self, ctx, max_id=1):
        reason = await ctx.bot.data.iterate_clans_new(max_id)
        await ctx.channel.send('Exited ({})'.format(reason))

    @commands.is_owner()
    @commands.command()
    async def fetchplayers(self, ctx):
        reason = await ctx.bot.data.fetch_players()
        await ctx.channel.send('Exited ({})'.format(reason))

    @commands.is_owner()
    @commands.command(
        description='Switch update status posting',
        aliases=['poststatus']
    )
    async def switchupdstatus(self, ctx):
        ctx.bot.update_status = not ctx.bot.update_status
        await ctx.message.reply('Done, switched to {}'.format(ctx.bot.update_status))

    @commands.command(
        name='help',
        description='The help command!',
        usage='cog',
        aliases=['man', 'hlep', 'чотут', 'ман', 'инструкция', 'ruhelp', 'helpru']
    )
    async def help_command(self, ctx, command_name='all', lang=None, additional_arg=None):
        channel = ctx.message.channel
        if lang is not None and lang not in ctx.bot.langs:
            additional_arg = lang
            lang = None
        if ctx.message.guild is not None and lang is None:
            lang = ctx.bot.guild_lang(ctx.message.guild.id)
        if lang not in ctx.bot.langs:
            lang = 'en'
        if ctx.invoked_with in ['чотут', 'ман', 'инструкция', 'ruhelp', 'helpru']:
            lang = 'ru'
        if ctx.message.guild is not None:
            name = ctx.message.guild.me.display_name
        else:
            name = ctx.bot.user.name
        help_translations = ctx.bot.translations[lang]['help']
        command_name = command_name.lower()
        metric_tables = ['seasonsmetrics', 'accountmetrics', 'cruciblemetrics', 'destinationmetrics',
                         'gambitmetrics', 'raidsmetrics', 'strikesmetrics', 'trialsofosirismetrics']
        command_list = []
        help_msg = '`{} v{}`'.format(name, ctx.bot.version)
        await channel.send(help_msg)
        aliases = ''
        if str(ctx.bot.user.id) in ctx.prefix:
            prefix = '@{} '.format(name)
        else:
            prefix = ctx.prefix
        if command_name != 'all':
            try:
                command = ctx.bot.all_commands[command_name]
            except KeyError:
                if command_name in metric_tables:
                    command = ctx.bot.all_commands['top']
                    additional_arg = command_name
                else:
                    await ctx.channel.send(help_translations['no_command'].format(command_name))
                    return
            aliases = command.name
            for alias in command.aliases:
                aliases = '{}, {}'.format(aliases, alias)
            if len(command.aliases) > 0:
                await channel.send(help_translations['aliases'].format(aliases))
            command_string = command.name
            for arg in command.clean_params:
                if command.name == 'setclan' and arg == 'args':
                    continue
                if 'empty' not in str(command.clean_params[arg].default):
                    command_string = '{} {}'.format(command_string, arg)
                else:
                    command_string = '{} {}'.format(command_string, arg)
            await channel.send(help_translations['parameters'].format(command_string))
        if command_name == 'all' or 'help' in aliases:
            help_msg = '{}\n'.format(help_translations['list'])
            for command in ctx.bot.commands:
                if command.name in help_translations.keys():
                    command_desc = help_translations[command.name]
                else:
                    command_desc = command.description
                if (not (command.cog_name == 'Admin' and command.name != 'help') or await ctx.bot.is_owner(
                        ctx.author)) and (not (
                        command.cog_name == 'ServerAdmin' and command.name != 'help') or await ctx.bot.check_ownership(
                        ctx.message, is_silent=True, admin_check=True)):
                    command_list.append([command.name, command_desc])

            help_msg = '{}```\t{}```'.format(help_msg,
                                             tabulate(command_list, tablefmt='plain', colalign=('left', 'left'))
                                             .replace('\n', '\n\t'))
            lang_list = ''
            for lang in self.bot.langs:
                lang_list = '{}`, `{}'.format(lang_list, lang)
            help_msg = '{}{}'.format(help_msg, help_translations['additional_info'].format(prefix, lang_list[4:], prefix))
            await ctx.message.channel.send(help_msg)
            pass
        elif command.name == 'top':
            translations = help_translations['commands'][command.name]
            help_msg = '{}'.format(translations['info'])
            await channel.send(help_msg)

            try:
                if additional_arg in metric_tables and additional_arg is not None:
                    metric_tables = [additional_arg]
                internal_db = mariadb.connect(host=ctx.bot.api_data['db_host'], user=ctx.bot.api_data['cache_login'],
                                              password=ctx.bot.api_data['pass'], port=ctx.bot.api_data['db_port'],
                                              database='metrics')
                internal_cursor = internal_db.cursor()
                help_msg = ''
                if len(metric_tables) == 1:
                    for table in metric_tables:
                        metric_list = []
                        internal_cursor.execute('''SELECT name, hash, is_working FROM {}'''.format(table))
                        metrics = internal_cursor.fetchall()
                        if len(metrics) > 0:
                            for metric in metrics:
                                if str(metric[0]) != 'None':
                                    try:
                                        top_name = await ctx.bot.data.destiny.decode_hash(metric[1],
                                                                                          'DestinyMetricDefinition',
                                                                                          language=lang)
                                        if 'weekly' in metric[0] or 'season' in metric[0]:
                                            if 2230116619 in top_name['traitHashes']:
                                                trait = await ctx.bot.data.destiny.decode_hash(2230116619,
                                                                                               'DestinyTraitDefinition',
                                                                                               language=lang)
                                            elif 2356777566 in top_name['traitHashes']:
                                                trait = await ctx.bot.data.destiny.decode_hash(2356777566,
                                                                                               'DestinyTraitDefinition',
                                                                                               language=lang)
                                            modifier = ' ({})'.format(trait['displayProperties']['name'])
                                        else:
                                            modifier = ''
                                    except pydest.PydestException:
                                        top_name = translations['unavailable']
                                        modifier = ''
                                    if metric[2]:
                                        if metric[0] == '':
                                            name = str(metric[1])
                                        else:
                                            name = metric[0]
                                        metric_list.append(['`{}'.format(name), '{}{}`'.format(top_name['displayProperties']['name'], modifier)])
                            if len(metric_list) > 0:
                                help_msg = '{}**{}**'.format(help_msg, translations[table])
                                help_msg = '{}\n{}\n'.format(help_msg, tabulate(metric_list, tablefmt='plain',
                                                                                colalign=('left', 'left')))
                else:
                    cat_list = []
                    for table in metric_tables:
                        cat_list.append([table, translations[table]])
                    help_msg = '{}\n```{}``` '.format(translations['cat_list'].format(prefix), tabulate(cat_list, tablefmt='plain',
                                                                                           colalign=('left', 'left')))
                if len(help_msg) > 1:
                    help_msg = help_msg[:-1]
                internal_db.close()
            except mariadb.Error:
                pass
            if len(help_msg) > 2000:
                help_lines = help_msg.splitlines()
                help_msg = help_lines[0]
                while len(help_lines) > 1:
                    if len(help_msg) + 1 + len(help_lines[1]) <= 2000:
                        help_msg = '{}\n{}'.format(help_msg, help_lines[1])
                        if len(help_lines) > 1 and help_lines[1] in help_msg:
                            help_lines.pop(1)
                    else:
                        await channel.send(help_msg)
                        help_msg = ''
                    if len(help_lines) == 0:
                        break
            await channel.send(help_msg)
            pass
        elif command.name in ['lfg', 'edit_lfg']:
            help_translations = help_translations['commands']['lfg']
            help_msg = '{}\n{}\n'.format(help_translations['info'], help_translations['creation'])
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
            help_msg = '{}```@{} {}```'.format(help_msg, name, help_translations['example_lfg'])
            await channel.send(help_msg)

            help_msg = '{}\n'.format(help_translations['edit_title'])
            help_msg = '{}{}\n'.format(help_msg, help_translations['manual'])
            await channel.send(help_msg)

            help_msg = '{}\n'.format(help_translations['use_lfg'])
            await channel.send(help_msg)
            pass
        elif command.name in ['setlang']:
            if command.name in help_translations['commands'].keys():
                translations = help_translations['commands'][command.name]
                command_desc = translations['info']
            else:
                command_desc = command.description
            lang_list = ''
            for lang in self.bot.langs:
                lang_list = '{}`, `{}'.format(lang_list, lang)
            help_msg = '{}'.format(command_desc).format(lang_list[3:]+'`')
            await channel.send(help_msg)
            pass
        else:
            if command.name in help_translations['commands'].keys():
                translations = help_translations['commands'][command.name]
                command_desc = translations['info']
            else:
                command_desc = command.description
            help_msg = '{}'.format(command_desc)
            await channel.send(help_msg)
            pass


def setup(bot):
    bot.add_cog(Admin(bot))
