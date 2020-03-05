import json
import discord
import argparse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta, timezone
import asyncio

from discord.ext.commands.bot import Bot
import sqlite3
import logging
import traceback
from github import Github

from discord.ext import commands

import raid as lfg
import destiny2data as d2
import unauthorized


class ClanBot(commands.Bot):
    version = '2.8.6'
    cogs = ['cogs.admin', 'cogs.updates', 'cogs.group']
    langs = ['en', 'ru']
    all_types = ['weekly', 'daily', 'spider', 'xur', 'tess', 'seasonal']

    sched = AsyncIOScheduler(timezone='UTC')
    guild_db = ''
    guild_cursor = ''

    api_data_file = open('api.json', 'r')
    api_data = json.loads(api_data_file.read())

    lfgs = []

    notifiers = []
    seasonal_ch = []
    update_ch = []

    raid = ''

    args = ''

    translations = {}

    git = ''

    def __init__(self, **options):
        super().__init__(**options)
        self.get_args()
        translations_file = open('translations.json', 'r', encoding='utf-8')
        self.translations = json.loads(translations_file.read())
        translations_file.close()
        self.data = d2.D2data(self.translations, self.langs, self.args.oauth, self.args.production, (self.args.cert, self.args.key))
        self.raid = lfg.LFG()
        self.guild_db = sqlite3.connect('guild.db')
        self.guild_cursor = self.guild_db.cursor()

        self.sched.add_job(self.universal_update, 'cron', hour='17', minute='0', second='30', misfire_grace_time=86300, args=[self.data.get_heroic_story, 'heroicstory', 86400])
        self.sched.add_job(self.universal_update, 'cron', hour='17', minute='1', second='30', misfire_grace_time=86300, args=[self.data.get_forge, 'forge', 86400])
        self.sched.add_job(self.universal_update, 'cron', hour='17', minute='0', second='30', misfire_grace_time=86300, args=[self.data.get_strike_modifiers, 'vanguardstrikes', 86400])
        self.sched.add_job(self.universal_update, 'cron', hour='17', minute='0', second='50', misfire_grace_time=86300, args=[self.data.get_reckoning_modifiers, 'reckoning', 86400])
        self.sched.add_job(self.universal_update, 'cron', hour='17', minute='0', second='30', misfire_grace_time=86300, args=[self.data.get_spider, 'spider', 86400])

        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='0', second='40', misfire_grace_time=86300, args=[self.data.get_nightfall820, 'nightfalls820', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='0', second='40', misfire_grace_time=86300, args=[self.data.get_ordeal, 'ordeal', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='0', second='40', misfire_grace_time=86300, args=[self.data.get_nightmares, 'nightmares', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='0', second='40', misfire_grace_time=86300, args=[self.data.get_crucible_rotators, 'cruciblerotators', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='0', second='40', misfire_grace_time=86300, args=[self.data.get_raids, 'raids', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='1', second='40', misfire_grace_time=86300, args=[self.data.get_featured_bd, 'featured_bd', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='1', second='40', misfire_grace_time=86300, args=[self.data.get_bd, 'bd', 604800])

        self.sched.add_job(self.universal_update, 'cron', day_of_week='fri', hour='17', minute='5', second='0', misfire_grace_time=86300, args=[self.data.get_xur, 'xur', 345600])

        self.sched.add_job(self.data.token_update, 'interval', hours=1)

        logging.basicConfig(filename='scheduler.log')
        logging.getLogger('apscheduler').setLevel(logging.DEBUG)

        if self.args.production:
            git_file = open('git.dat', 'r')
            git_token = git_file.read()
            self.git = Github(git_token)
            self.git = self.git.get_repo('movsesyanpv/clanBot')

    def get_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-nc', '--noclear', help='Don\'t clear last message of the type', action='store_true')
        parser.add_argument('-p', '--production', help='Use to launch in production mode', action='store_true')
        parser.add_argument('-nm', '--nomessage', help='Don\'t post any messages', action='store_true')
        parser.add_argument('-l', '--lang', nargs='+', help='Language of data', default=['en'])
        parser.add_argument('-t', '--type', nargs='+', help='Type of message. Use with -f')
        parser.add_argument('-tp', '--testprod', help='Use to launch in test production mode', action='store_true')
        parser.add_argument('-f', '--forceupdate', help='Force update right now', action='store_true')
        parser.add_argument('--oauth', help='Get Bungie access token', action='store_true')
        parser.add_argument('-k', '--key', help='SSL key', type=str, default='')
        parser.add_argument('-c', '--cert', help='SSL certificate', type=str, default='')
        self.args = parser.parse_args()

    async def force_update(self, upd_type, post=True, get=True, channels=None):
        if 'daily' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_heroic_story, 'heroicstory', 86400, post=post, get=get, channels=channels)
                await self.universal_update(self.data.get_forge, 'forge', 86400, post=post, get=get, channels=channels)
                await self.universal_update(self.data.get_strike_modifiers, 'vanguardstrikes', 86400, post=post, get=get, channels=channels)
                await self.universal_update(self.data.get_reckoning_modifiers, 'reckoning', 86400, post=post, get=get, channels=channels)
        if 'weekly' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_nightfall820, 'nightfalls820', 604800, post=post, get=get, channels=channels)
                await self.universal_update(self.data.get_ordeal, 'ordeal', 604800, post=post, get=get, channels=channels)
                await self.universal_update(self.data.get_nightmares, 'nightmares', 604800, post=post, get=get, channels=channels)
                await self.universal_update(self.data.get_crucible_rotators, 'cruciblerotators', 604800, post=post, get=get, channels=channels)
                await self.universal_update(self.data.get_raids, 'raids', 604800, post=post, get=get, channels=channels)
                await self.universal_update(self.data.get_featured_bd, 'featured_bd', 604800, post=post, get=get, channels=channels)
                await self.universal_update(self.data.get_bd, 'bd', 604800, post=post, get=get, channels=channels)
        if 'spider' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_spider, 'spider', 86400, post=post, get=get, channels=channels)
        if 'xur' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_xur, 'xur', 345600, post=post, get=get, channels=channels)
        if 'tess' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_featured_silver, 'silver', 604800, post=post, get=get, channels=channels)
                await self.universal_update(self.data.get_featured_bd, 'featured_bd', 604800, post=post, get=get, channels=channels)
                await self.universal_update(self.data.get_bd, 'bd', 604800, post=post, get=get, channels=channels)
        if 'seasonal' in upd_type:
            if channels is None:
                channels = self.seasonal_ch
            if (post and list(set(channels).intersection(self.seasonal_ch))) or get:
                await self.universal_update(self.data.get_seasonal_eververse, 'seasonal_eververse', channels=channels, post=post, get=get)
        if self.args.forceupdate:
            await self.data.destiny.close()
            await self.logout()
            await self.close()

    async def on_ready(self):
        await self.data.token_update()
        await self.update_history()
        await self.update_langs()
        self.get_channels()
        self.data.get_chars()
        if self.args.forceupdate:
            await self.force_update(self.args.type)
        await self.force_update(self.all_types, post=False)
        if not self.sched.running:
            for lang in self.langs:
                self.sched.add_job(self.data.destiny.update_manifest, 'cron', day_of_week='tue', hour='17', minute='0',
                                   second='10', misfire_grace_time=86300, args=[lang])
            self.sched.start()
        self.remove_command('help')
        for cog in self.cogs:
            self.load_extension(cog)
        await self.dm_owner('Ready for action')
        return

    async def on_guild_join(self, guild):
        await self.update_history()
        if guild.owner.dm_channel is None:
            await guild.owner.create_dm()
        start = await guild.owner.dm_channel.send('Thank you for inviting me to your guild!\n')
        prefixes = get_prefix(self, start)
        prefix = '?'
        for i in prefixes:
            if '@' not in i:
                prefix = i
        await guild.owner.dm_channel.send('The `{}help` command will get you the command list.\n'
                                          'To set up automatic Destiny 2 information updates use `regnotifier` command.\n'
                                          'Please set my language for the guild with `@{} setlang LANG`, sent in one of the guild\'s chats. Right now it\'s `en`. Available languages are `{}`.'.format(prefix, self.user.name, str(self.langs).replace('[', '').replace(']', '').replace('\'', '')))

    async def on_guild_remove(self, guild):
        self.guild_cursor.execute('''DELETE FROM history WHERE server_id=?''', (guild.id,))
        self.guild_cursor.execute('''DELETE FROM language WHERE server_id=?''', (guild.id,))
        self.guild_cursor.execute('''DELETE FROM seasonal WHERE server_id=?''', (guild.id,))
        self.guild_cursor.execute('''DELETE FROM notifiers WHERE server_id=?''', (guild.id,))
        self.guild_db.commit()
        self.raid.purge_guild(guild.id)

    async def dm_owner(self, text):
        bot_info = await self.application_info()
        if bot_info.owner.dm_channel is None:
            await bot_info.owner.create_dm()
        await bot_info.owner.dm_channel.send(text)

    async def check_ownership(self, message, is_silent=False, admin_check=False):
        bot_info = await self.application_info()
        is_owner = bot_info.owner == message.author
        if not is_owner and not is_silent:
            msg = '{}!'.format(message.author.mention)
            e = unauthorized.get_unauth_response()
            if message.author.dm_channel is None:
                await message.author.create_dm()
            await message.author.dm_channel.send(msg, embed=e)
        return is_owner or (message.channel.permissions_for(message.author).administrator and admin_check)

    async def on_raw_reaction_remove(self, payload):
        user = self.get_user(payload.user_id)
        if user == self.user:
            return

        message = await self.fetch_channel(payload.channel_id)
        message = await message.fetch_message(payload.message_id)
        for guild in self.guilds:
            if guild.id == payload.guild_id:
                user = guild.get_member(payload.user_id)

        if self.raid.is_raid(message.id):
            if str(payload.emoji) != '👌':
                return
            self.raid.rm_people(message.id, user)
            if user.dm_channel is None:
                await user.create_dm()
            lang = self.guild_lang(payload.guild_id)
            await self.raid.update_group_msg(message, self.translations[lang])
            if self.raid.get_cell('group_id', message.id, 'group_mode') == 'manual':
                await user.dm_channel.send(self.translations[lang]['lfg']['gotcha'])
                owner = self.raid.get_cell('group_id', message.id, 'owner')
                owner = self.get_user(owner)
                await self.raid.upd_dm(owner, message.id, self.translations[lang])

    async def on_raw_reaction_add(self, payload):
        user = payload.member
        if payload.member == self.user:
            return

        try:
            message = await self.fetch_channel(payload.channel_id)
            message = await message.fetch_message(payload.message_id)

            if self.raid.is_raid(message.id):
                mode = self.raid.get_cell('group_id', message.id, 'group_mode')
                owner = self.get_user(self.raid.get_cell('group_id', message.id, 'owner'))
                if str(payload.emoji) == '❌' and payload.user_id == owner.id:
                    if mode == 'manual':
                        dm_id = self.raid.get_cell('group_id', message.id, 'dm_message')
                        if owner.dm_channel is None:
                            await owner.create_dm()
                        if dm_id != 0:
                            dm_message = await owner.dm_channel.fetch_message(dm_id)
                            await dm_message.delete()
                    self.raid.del_entry(message.id)
                    await message.delete()
                    return
                if str(payload.emoji) != '👌':
                    for reaction in message.reactions:
                        if str(reaction.emoji) == str(payload.emoji):
                            try:
                                await reaction.remove(user)
                            except discord.errors.Forbidden:
                                pass
                            return
                owner = self.raid.get_cell('group_id', message.id, 'owner')
                owner = self.get_user(owner)
                self.raid.add_people(message.id, user)
                lang = self.guild_lang(payload.guild_id)
                if user.dm_channel is None:
                    await user.create_dm()
                if mode == 'manual':
                    await user.dm_channel.send(self.translations[lang]['lfg']['gotcha'], delete_after=30)
                    await self.raid.upd_dm(owner, message.id, self.translations[lang])
                if mode == 'basic':
                    await self.raid.update_group_msg(message, self.translations[lang])
                return

            raid_dm = self.raid.get_cell('dm_message', message.id, 'dm_message')

            if raid_dm == message.id:
                emojis = ["{}\N{COMBINING ENCLOSING KEYCAP}".format(num) for num in range(1, 7)]
                if str(payload.emoji) in emojis:
                    number = emojis.index(str(payload.emoji))
                    lfg_message = self.raid.get_cell('dm_message', raid_dm, 'group_id')
                    channel = self.raid.get_cell('group_id', lfg_message, 'lfg_channel')
                    message = await self.fetch_channel(channel)
                    message = await message.fetch_message(lfg_message)
                    await self.raid.add_going(lfg_message, number)
                    lang = self.guild_lang(payload.guild_id)
                    await self.raid.update_group_msg(message, self.translations[lang])
                    owner = self.raid.get_cell('group_id', message.id, 'owner')
                    owner = self.get_user(owner)
                    await self.raid.upd_dm(owner, lfg_message, self.translations[lang])
        except Exception as e:
            if not self.args.production:
                bot_info = await self.application_info()
                owner = bot_info.owner
                if owner.dm_channel is None:
                    await owner.create_dm()
                await owner.dm_channel.send('`{}`'.format(traceback.format_exc()))
            else:
                self.git.create_issue(title='Exception on reaction add',
                                      body='# Traceback\n\n```{}```'.
                                      format(traceback.format_exc()))

    async def pause_for(self, message, delta):
        self.sched.pause()
        await asyncio.sleep(delta.total_seconds())
        self.sched.resume()
        await message.channel.send('should be after delay finish {}'.format(str(datetime.now())))
        return

    async def on_raw_message_delete(self, payload):
        if self.raid.is_raid(payload.message_id):
            owner = self.raid.get_cell('group_id', payload.message_id, 'owner')
            owner = self.get_user(owner)
            dm_id = self.raid.get_cell('group_id', payload.message_id, 'dm_message')
            if owner.dm_channel is None:
                await owner.create_dm()
            if dm_id != 0:
                dm_message = await owner.dm_channel.fetch_message(dm_id)
                await dm_message.delete()
            self.raid.del_entry(payload.message_id)

    async def on_command_error(self, ctx, exception):
        message = ctx.message
        try:
            if isinstance(exception, commands.NoPrivateMessage):
                await ctx.send("\N{WARNING SIGN} Sorry, you can't use this command in a private message!")

            elif isinstance(exception, commands.PrivateMessageOnly):
                await ctx.send("\N{WARNING SIGN} Sorry, you can't use this command in a guild channel!", delete_after=60)
                await ctx.message.delete()

            elif isinstance(exception, commands.CommandNotFound):
                await ctx.send("\N{WARNING SIGN} That command doesn't exist!", delete_after=60)
                await ctx.message.delete()

            elif isinstance(exception, commands.DisabledCommand):
                await ctx.send("\N{WARNING SIGN} Sorry, this command is disabled!", delete_after=60)
                await ctx.message.delete()

            elif isinstance(exception, commands.MissingPermissions):
                await ctx.send(f"\N{WARNING SIGN} You do not have permissions to use this command.", delete_after=60)
                await ctx.message.delete()

            elif isinstance(exception, commands.CommandOnCooldown):
                await ctx.send(f"{ctx.author.mention} slow down! Try that again in {exception.retry_after:.1f} seconds", delete_after=60)
                await ctx.message.delete()

            elif isinstance(exception, commands.MissingRequiredArgument) or isinstance(exception, commands.BadArgument):
                await ctx.send(f"\N{WARNING SIGN} {exception}")

            elif isinstance(exception, commands.NotOwner):
                msg = '{}!'.format(ctx.author.mention)
                e = unauthorized.get_unauth_response()
                if ctx.author.dm_channel is None:
                    await ctx.author.create_dm()
                await ctx.author.dm_channel.send(msg, embed=e)

            elif isinstance(exception, commands.CommandInvokeError):
                raise exception
        except discord.errors.Forbidden:
            pass
        except Exception as e:
            if 'stop' not in message.content.lower() or (self.user not in message.mentions and str(message.channel.type) != 'private'):
                if not self.args.production:
                    bot_info = await self.application_info()
                    owner = bot_info.owner
                    if owner.dm_channel is None:
                        await owner.create_dm()
                    await owner.dm_channel.send('`{}`'.format(traceback.format_exc()))
                    await owner.dm_channel.send('{}:\n{}'.format(message.author, message.content))
                    if message.author.dm_channel is None:
                        await message.author.create_dm()
                    await message.author.dm_channel.send(self.translations['en']['error'])
                else:
                    self.git.create_issue(title='Exception on message',
                                          body='# Message\n\n{}\n\n# Traceback\n\n```{}```'.
                                          format(message.content, traceback.format_exc()))

    def get_channel_type(self, ch_type):
        channel_list = []
        try:
            self.guild_cursor.execute('''CREATE TABLE {} (channel_id integer, server_id integer)'''.format(ch_type))
            self.guild_cursor.execute('''CREATE UNIQUE INDEX {}_id ON {}(channel_id)'''.format(ch_type, ch_type))
            self.guild_db.commit()
        except sqlite3.OperationalError:
            try:
                channels = self.guild_cursor.execute('''SELECT channel_id FROM {}'''.format(ch_type))
                channels = channels.fetchall()
                for entry in channels:
                    channel_list.append(entry[0])
            except sqlite3.OperationalError:
                pass
        return channel_list

    def get_channels(self):
        self.notifiers.clear()
        self.seasonal_ch.clear()
        self.update_ch.clear()

        self.notifiers = self.get_channel_type('notifiers')
        self.seasonal_ch = self.get_channel_type('seasonal')
        self.update_ch = self.get_channel_type('updates')

    def guild_lang(self, guild_id):
        try:
            self.guild_cursor.execute('''SELECT lang FROM language WHERE server_id=?''', (guild_id, ))
            lang = self.guild_cursor.fetchone()
            if len(lang) > 0:
                return lang[0]
            else:
                return 'en'
        except:
            return 'en'

    async def update_langs(self):
        game = discord.Game('updating langs')
        await self.change_presence(activity=game)

        for server in self.guilds:
            try:
                self.guild_cursor.execute('''CREATE TABLE language (server_id integer, lang text)''')
                self.guild_cursor.execute('''CREATE UNIQUE INDEX lang ON language(server_id)''')
                self.guild_cursor.execute('''INSERT or IGNORE INTO language VALUES (?,?)''', [server.id, 'en'])
            except sqlite3.OperationalError:
                try:
                    self.guild_cursor.execute('''INSERT or IGNORE INTO language VALUES (?,?)''', [server.id, 'en'])
                except sqlite3.OperationalError:
                    pass
        self.guild_db.commit()

        game = discord.Game('v{}'.format(self.version))
        await self.change_presence(activity=game)

    async def update_history(self):
        game = discord.Game('updating history')
        await self.change_presence(activity=game)
        for server in self.guilds:
            try:
                self.guild_cursor.execute('''CREATE TABLE history ( server_name text, server_id integer)''')
                self.guild_cursor.execute('''CREATE UNIQUE INDEX hist ON history(server_id)''')
                init_values = [server.name, server.id]
                self.guild_cursor.execute("INSERT or IGNORE INTO history VALUES (?,?)", init_values)
                self.guild_db.commit()
            except sqlite3.OperationalError:
                try:
                    init_values = [server.name, server.id]
                    self.guild_cursor.execute("INSERT or IGNORE INTO history VALUES (?,?)", init_values)
                except sqlite3.OperationalError:
                    pass
        game = discord.Game('v{}'.format(self.version))
        await self.change_presence(activity=game)

    async def universal_update(self, getter, name, time_to_delete=None, channels=None, post=True, get=True):
        await self.wait_until_ready()
        game = discord.Game('updating {}'.format(name))
        await self.change_presence(activity=game)

        lang = self.langs

        if channels is None:
            channels = self.notifiers

        if len(channels) == 0 and not get:
            game = discord.Game('v{}'.format(self.version))
            await self.change_presence(activity=game)
            return

        if get:
            try:
                await getter(lang)
            except Exception as e:
                bot_info = await self.application_info()
                owner = bot_info.owner
                if owner.dm_channel is None:
                    await owner.create_dm()
                await owner.dm_channel.send('`{}`'.format(traceback.format_exc()))
                game = discord.Game('v{}'.format(self.version))
                await self.change_presence(activity=game)
                return

            for locale in self.args.lang:
                if not self.data.data[locale][name]:
                    game = discord.Game('v{}'.format(self.version))
                    await self.change_presence(activity=game)
                    return
        if post:
            await self.post_embed(name, self.data.data, time_to_delete, channels)

        game = discord.Game('v{}'.format(self.version))
        await self.change_presence(activity=game)

    async def post_embed(self, upd_type, src_dict, time_to_delete, channels):
        for server in self.guilds:
            lang = self.guild_lang(server.id)
            if not self.args.nomessage:
                if type(src_dict[lang][upd_type]) == list:
                    embed = []
                    for field in src_dict[lang][upd_type]:
                        embed.append(discord.Embed.from_dict(field))
                else:
                    embed = discord.Embed.from_dict(src_dict[lang][upd_type])

            hist = 0
            try:
                last = self.guild_cursor.execute('''SELECT {} FROM history WHERE server_id=?'''.format(upd_type), (server.id,))
                last = last.fetchone()
                if last is not None:
                    if type(src_dict[lang][upd_type]) == list:
                        if last[0] is not None:
                            hist = eval(last[0])
                        else:
                            hist = [0]
                    else:
                        if len(last) > 0:
                            if last[0] is not None:
                                hist = last[0]

            except sqlite3.OperationalError:
                try:
                    if type(src_dict[lang][upd_type]) == list:
                        self.guild_cursor.execute(
                            '''ALTER TABLE history ADD COLUMN {} text'''.format(upd_type))
                    else:
                        self.guild_cursor.execute('''ALTER TABLE history ADD COLUMN {} INTEGER'''.format(upd_type))
                    self.guild_db.commit()
                except sqlite3.OperationalError:
                    await self.update_history()

            for channel in server.channels:
                if channel.id in channels:
                    if hist and not self.args.noclear:
                        try:
                            if type(hist) == list:
                                last = []
                                for msg in hist:
                                    last.append(await channel.fetch_message(msg))
                            else:
                                last = await channel.fetch_message(hist)
                            try:
                                if type(hist) == list:
                                    if len(hist) < 100:
                                        await channel.delete_messages(last)
                                    else:
                                        for week in [last[i:i + 4] for i in range(0, len(last), 4)]:
                                            await channel.delete_messages(week)
                                else:
                                    await last.delete()
                            except discord.errors.Forbidden:
                                pass
                            except discord.errors.HTTPException:
                                bot_info = await self.application_info()
                                await bot_info.owner.dm_channel.send('`{}`'.format(traceback.format_exc()))
                        except discord.NotFound:
                            bot_info = await self.application_info()
                            await bot_info.owner.send('Not found at ```{}```. Channel ```{}``` of ```{}```'.
                                                      format(upd_type, channel.name, server.name))
                    if type(embed) == list:
                        hist = []
                        for e in embed:
                            message = await channel.send(embed=e, delete_after=time_to_delete)
                            hist.append(message.id)
                        hist = str(hist)
                    else:
                        message = await channel.send(embed=embed, delete_after=time_to_delete)
                        hist = message.id
            self.guild_cursor.execute('''UPDATE history SET {}=? WHERE server_id=?'''.format(upd_type), (str(hist), server.id))
            self.guild_db.commit()

    async def post_updates(self, version, content, lang):
        msg = '`{} v{}`\n{}'.format(self.user.name, version, content)
        for server in self.guilds:
            if lang == self.guild_lang(server.id):
                for channel in server.channels:
                    if channel.id in self.update_ch:
                        await channel.send(msg)

    def start_up(self):
        self.get_args()
        token = self.api_data['token']
        print('hmm')
        self.run(token)


def get_prefix(client, message):
    prefixes = ['?']
    if message.guild:
        prefixes = []

    return commands.when_mentioned_or(*prefixes)(client, message)


if __name__ == '__main__':
    b = ClanBot(command_prefix=get_prefix)
    b.start_up()
