import json
import discord
import argparse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta, timezone
import asyncio

from discord.ext.commands.bot import Bot
from hashids import Hashids
import sqlite3
import logging
import traceback
from github import Github
from tabulate import tabulate

from discord.ext import commands

import raid as lfg
import destiny2data as d2
import unauthorized


class ClanBot(commands.Bot):
    version = '2.6'

    sched = AsyncIOScheduler(timezone='UTC')
    hist_db = ''
    hist_cursor = ''

    api_data_file = open('api.json', 'r')
    api_data = json.loads(api_data_file.read())

    lfgs = []

    notifiers = []
    seasonal_ch = []
    channel_db = ''
    channel_cursor = ''

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
        self.data = d2.D2data(self.translations, self.args.lang, self.args.oauth, self.args.production, (self.args.cert, self.args.key))
        self.raid = lfg.LFG()
        self.hist_db = sqlite3.connect('history.db')
        self.hist_cursor = self.hist_db.cursor()
        self.channel_db = sqlite3.connect('channels.db')
        self.channel_cursor = self.channel_db.cursor()

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
        parser.add_argument('-l', '--lang', type=str, help='Language of data', default='en')
        parser.add_argument('-t', '--type', type=str, help='Type of message. Use with -f')
        parser.add_argument('-tp', '--testprod', help='Use to launch in test production mode', action='store_true')
        parser.add_argument('-f', '--forceupdate', help='Force update right now', action='store_true')
        parser.add_argument('--oauth', help='Get Bungie access token', action='store_true')
        parser.add_argument('-k', '--key', help='SSL key', type=str, default='')
        parser.add_argument('-c', '--cert', help='SSL certificate', type=str, default='')
        self.args = parser.parse_args()

    async def force_update(self, upd_type):
        if 'daily' in upd_type:
            await self.universal_update(self.data.get_heroic_story, 'heroicstory', 86400)
            await self.universal_update(self.data.get_forge, 'forge', 86400)
            await self.universal_update(self.data.get_strike_modifiers, 'vanguardstrikes', 86400)
            await self.universal_update(self.data.get_reckoning_modifiers, 'reckoning', 86400)
        if 'weekly' in upd_type:
            await self.universal_update(self.data.get_nightfall820, 'nightfalls820', 604800)
            await self.universal_update(self.data.get_ordeal, 'ordeal', 604800)
            await self.universal_update(self.data.get_nightmares, 'nightmares', 604800)
            await self.universal_update(self.data.get_crucible_rotators, 'cruciblerotators', 604800)
            await self.universal_update(self.data.get_raids, 'raids', 604800)
            await self.universal_update(self.data.get_featured_bd, 'featured_bd', 604800)
            await self.universal_update(self.data.get_bd, 'bd', 604800)
        if 'spider' in upd_type:
            await self.universal_update(self.data.get_spider, 'spider', 86400)
        if 'xur' in upd_type:
            await self.universal_update(self.data.get_xur, 'xur', 345600)
        if 'tess' in upd_type:
            await self.universal_update(self.data.get_featured_silver, 'silver', 604800)
            await self.universal_update(self.data.get_featured_bd, 'featured_bd', 604800)
            await self.universal_update(self.data.get_bd, 'bd', 604800)
        if 'seasonal' in upd_type:
            await self.universal_update(self.data.get_seasonal_eververse, 'seasonal_eververse', channels=self.seasonal_ch)
        if self.args.forceupdate:
            await self.logout()
            await self.close()

    async def on_ready(self):
        await self.data.token_update()
        await self.update_history()
        self.get_channels()
        self.data.get_chars()
        if self.args.forceupdate:
            await self.force_update(self.args.type)
        if not self.sched.running:
            self.sched.start()
        self.add_command(self.lfg)
        self.add_command(self.lfglist)
        self.add_command(self.stop)
        self.add_command(self.help_lfg)

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
            await self.raid.update_group_msg(message, self.translations[self.args.lang])
            if self.raid.get_cell('group_id', message.id, 'group_mode') == 'manual':
                await user.dm_channel.send(self.translations[self.args.lang]['lfg']['gotcha'])
                owner = self.raid.get_cell('group_id', message.id, 'owner')
                owner = self.get_user(owner)
                await self.raid.upd_dm(owner, message.id, self.translations[self.args.lang])

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
                if user.dm_channel is None:
                    await user.create_dm()
                if mode == 'manual':
                    await user.dm_channel.send(self.translations[self.args.lang]['lfg']['gotcha'], delete_after=30)
                    await self.raid.upd_dm(owner, message.id, self.translations[self.args.lang])
                if mode == 'basic':
                    await self.raid.update_group_msg(message, self.translations[self.args.lang])
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
                    await self.raid.update_group_msg(message, self.translations[self.args.lang])
                    owner = self.raid.get_cell('group_id', message.id, 'owner')
                    owner = self.get_user(owner)
                    await self.raid.upd_dm(owner, lfg_message, self.translations[self.args.lang])
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

    @discord.ext.commands.command()
    @discord.ext.commands.dm_only()
    @discord.ext.commands.is_owner()
    async def stop(ctx):
        msg = 'Ok, {}'.format(ctx.author.mention)
        for i in ctx.bot.emojis:
            msg = '{} {}'.format(msg, i)
        await ctx.message.channel.send(msg)
        ctx.bot.sched.shutdown(wait=True)
        await ctx.bot.logout()
        await ctx.bot.close()
        return

    @discord.ext.commands.command()
    @discord.ext.commands.dm_only()
    async def lfglist(ctx):
        await ctx.bot.raid.dm_lfgs(ctx.author)
        return

    @discord.ext.commands.command()
    @discord.ext.commands.guild_only()
    async def lfg(ctx):
        message = ctx.message
        if '-man' in message.content.lower():
            if message.author.dm_channel is None:
                await message.author.create_dm
            await ctx.bot.help_lfg(message.author.dm_channel)
            await message.delete()
            return
        ctx.bot.raid.add(message)
        role = ctx.bot.raid.get_cell('group_id', message.id, 'the_role')
        name = ctx.bot.raid.get_cell('group_id', message.id, 'name')
        time = datetime.fromtimestamp(ctx.bot.raid.get_cell('group_id', message.id, 'time'))
        is_embed = ctx.bot.raid.get_cell('group_id', message.id, 'is_embed')
        description = ctx.bot.raid.get_cell('group_id', message.id, 'description')
        msg = "{}, {} {}\n{} {}\n{}".format(role, ctx.bot.translations[ctx.bot.args.lang]['lfg']['go'], name,
                                            ctx.bot.translations[ctx.bot.args.lang]['lfg']['at'], time, description)
        if is_embed:
            embed = ctx.bot.raid.make_embed(message, ctx.bot.translations[ctx.bot.args.lang])
            out = await message.channel.send(content=msg)
            await out.edit(content=None, embed=embed)
        else:
            out = await message.channel.send(msg)
        end_time = time + timedelta(seconds=ctx.bot.raid.get_cell('group_id', message.id, 'length'))
        await out.add_reaction('👌')
        await out.add_reaction('❌')
        ctx.bot.raid.set_id(out.id, message.id)
        await ctx.bot.raid.update_group_msg(out, ctx.bot.translations[ctx.bot.args.lang])
        # self.sched.add_job(out.delete, 'date', run_date=end_time, id='{}_del'.format(out.id))
        await message.delete()
        return

    async def on_command_error(self, ctx, exception):
        if isinstance(exception, commands.NoPrivateMessage):
            await ctx.send("\N{WARNING SIGN} Sorry, you can't use this command in a private message!")

        elif isinstance(exception, commands.PrivateMessageOnly):
            await ctx.send("\N{WARNING SIGN} Sorry, you can't use this command in a guild channel!")

        elif isinstance(exception, commands.CommandNotFound):
            await ctx.send("\N{WARNING SIGN} That command doesn't exist!")

        elif isinstance(exception, commands.DisabledCommand):
            await ctx.send("\N{WARNING SIGN} Sorry, this command is disabled!")

        elif isinstance(exception, commands.MissingPermissions):
            await ctx.send(f"\N{WARNING SIGN} You do not have permissions to use this command.")

        elif isinstance(exception, commands.CommandOnCooldown):
            await ctx.send(f"{ctx.author.mention} slow down! Try that again in {exception.retry_after:.1f} seconds")

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

    async def on_message(self, message):
        if message.author == self.user:
            return

        try:
            if 'help lfg' in message.content.lower() and (self.user in message.mentions or str(message.channel.type) == 'private'):
                await self.help_lfg(message.channel)
                if str(message.channel.type) != 'private':
                    await message.delete()
                return

            if 'man' in message.content.lower() and str(message.channel.type) == 'private':
                await self.help(message.author)
                return

            if 'lfglist' in message.content.lower() and str(message.channel.type) == 'private':
                await self.raid.dm_lfgs(message.author)
                return

            if 'stop' in message.content.lower() and str(message.channel.type) == 'private':
                if await self.check_ownership(message):
                    msg = 'Ok, {}'.format(message.author.mention)
                    for i in self.emojis:
                        msg = '{} {}'.format(msg, i)
                    await message.channel.send(msg)
                    self.sched.shutdown(wait=True)
                    await self.logout()
                    await self.close()
                    return
                return

            if 'plan maintenance' in message.content.lower() and str(message.channel.type) == 'private':
                if await self.check_ownership(message):
                    try:
                        content = message.content.splitlines()
                        start = datetime.strptime(content[1], "%d-%m-%Y %H:%M %z")
                        finish = datetime.strptime(content[2], "%d-%m-%Y %H:%M %z")
                        delta = finish-start
                        self.sched.add_job(self.pause_for, 'date', run_date=start, args=[message, delta], misfire_grace_time=600)
                    except Exception as e:
                        await message.channel.send('exception `{}`\nUse following format:```plan maintenance\n'
                                                   '<start time formatted %d-%m-%Y %H:%M %z>\n'
                                                   '<finish time formatted %d-%m-%Y %H:%M %z>```'.format(str(e)))
                    return
                return

            # if str(message.channel.type) == 'private':
            #     msg = 'Can\'t do this a private chat, {}'.format(message.author.mention)
            #     await message.channel.send(msg)
            #     return

            if 'edit lfg' in message.content.lower() and self.user in message.mentions:
                text = message.content.split()
                hashids = Hashids()
                for word in text:
                    group_id = hashids.decode(word)
                    if len(group_id) > 0:
                        old_lfg = self.raid.get_cell('group_id', group_id[0], 'lfg_channel')
                        old_lfg = self.get_channel(old_lfg)
                        if old_lfg is not None:
                            old_lfg = await old_lfg.fetch_message(group_id[0])
                            if old_lfg.author == message.author:
                                await self.raid.edit(message, old_lfg, self.translations[self.args.lang])
                            else:
                                await self.check_ownership(message)
                                await message.delete()
                        else:
                            await message.delete()
                return

            if 'regnotifier' in message.content.lower() and self.user in message.mentions:
                content = message.content.lower().split()
                notifier_type = 'notifiers'
                if len(content) >= 3 and 'seasonal' in message.content.lower():
                    notifier_type = content[2]
                if await self.check_ownership(message, is_silent=True, admin_check=True):
                    self.channel_cursor.execute('''INSERT or IGNORE into {} values (?)'''.format(notifier_type), (message.channel.id,))
                    self.channel_db.commit()
                    self.get_channels()
                    msg = 'Got it, {}'.format(message.author.mention)
                    await message.channel.send(msg, delete_after=10)
                await message.delete()
                return

            if 'rmnotifier' in message.content.lower() and self.user in message.mentions:
                content = message.content.lower().split()
                notifier_type = 'notifiers'
                if len(content) >= 3 and 'seasonal' in message.content.lower():
                    notifier_type = content[2]
                if await self.check_ownership(message, is_silent=True, admin_check=True):
                    self.channel_cursor.execute('''DELETE FROM {} WHERE channel_id=?'''.format(notifier_type),
                                                (message.channel.id,))
                    self.channel_db.commit()
                    self.get_channels()
                    msg = 'Got it, {}'.format(message.author.mention)
                    await message.channel.send(msg, delete_after=10)
                await message.delete()
                return

            if 'update' in message.content.lower() and self.user in message.mentions:
                content = message.content.lower().split()
                await message.delete()
                for upd_type in content[2:]:
                    await self.force_update(upd_type)
                return
            await self.process_commands(message)
        except discord.errors.Forbidden:
            pass
        except discord.ext.commands.errors.NoPrivateMessage:
            msg = 'Can\'t do this a private chat, {}'.format(message.author.mention)
            await message.channel.send(msg)
            return
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
                    await message.author.dm_channel.send(self.translations[self.args.lang]['error'])
                else:
                    self.git.create_issue(title='Exception on message',
                                          body='# Message\n\n{}\n\n# Traceback\n\n```{}```'.
                                          format(message.content, traceback.format_exc()))

    def get_channels(self):
        self.notifiers.clear()
        self.seasonal_ch.clear()
        try:
            self.channel_cursor.execute('''CREATE TABLE notifiers (channel_id integer)''')
            self.channel_cursor.execute('''CREATE UNIQUE INDEX notifiers_id ON notifiers(channel_id)''')
            self.channel_db.commit()
        except sqlite3.OperationalError:
            try:
                channels = self.channel_cursor.execute('''SELECT channel_id FROM notifiers''')
                channels = channels.fetchall()
                for entry in channels:
                    self.notifiers.append(entry[0])
            except sqlite3.OperationalError:
                pass
        try:
            self.channel_cursor.execute('''CREATE TABLE seasonal (channel_id integer)''')
            self.channel_cursor.execute('''CREATE UNIQUE INDEX seasonal_id ON seasonal(channel_id)''')
            self.channel_db.commit()
        except sqlite3.OperationalError:
            try:
                channels = self.channel_cursor.execute('''SELECT channel_id FROM seasonal''')
                channels = channels.fetchall()
                for entry in channels:
                    self.seasonal_ch.append(entry[0])
            except sqlite3.OperationalError:
                pass

    async def update_history(self):
        game = discord.Game('updating history')
        await self.change_presence(activity=game)
        for server in self.guilds:
            try:
                self.hist_cursor.execute('''CREATE TABLE \'{}\' ( server_name text, spider integer, xur integer, 
                                nightfalls820 integer, ordeal integer, nightmares integer, raids integer, 
                                cruciblerotators integer, heroicstory integer, forge integer, vanguardstrikes integer, 
                                reckoning integer )'''.format(server.id))
                init_values = [server.name, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
                self.hist_cursor.execute("INSERT INTO \'{}\' VALUES (?,?,?,?,?,?,?,?,?,?,?,?)".format(server.id), init_values)
                self.hist_db.commit()
            except sqlite3.OperationalError:
                try:
                    self.hist_cursor.execute('''UPDATE \'{}\' SET server_name=?'''.format(server.id), (server.name, ))
                except sqlite3.OperationalError:
                    pass
        game = discord.Game('v{}'.format(self.version))
        await self.change_presence(activity=game)

    async def universal_update(self, getter, name, time_to_delete=None, channels=None):
        await self.wait_until_ready()
        game = discord.Game('updating {}'.format(name))
        await self.change_presence(activity=game)

        lang = self.args.lang

        if channels is None:
            channels = self.notifiers

        if len(channels) == 0:
            game = discord.Game('v{}'.format(self.version))
            await self.change_presence(activity=game)
            return

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

        if self.data.data[name]:
            await self.post_embed(name, self.data.data[name], time_to_delete, channels)

        game = discord.Game('v{}'.format(self.version))
        await self.change_presence(activity=game)

    async def post_embed(self, upd_type, src_dict, time_to_delete, channels):
        if not self.args.nomessage:
            if type(src_dict) == list:
                embed = []
                for field in src_dict:
                    embed.append(discord.Embed.from_dict(field))
            else:
                embed = discord.Embed.from_dict(src_dict)

            for server in self.guilds:
                hist = 0
                try:
                    last = self.hist_cursor.execute('''SELECT {} FROM \'{}\''''.format(upd_type, server.id))
                    last = last.fetchone()
                    if last is not None:
                        if type(src_dict) == list:
                            hist = eval(last[0])
                        else:
                            if len(last) > 0:
                                hist = last[0]
                except sqlite3.OperationalError:
                    try:
                        if type(src_dict) == list:
                            self.hist_cursor.execute(
                                '''ALTER TABLE \'{}\' ADD COLUMN {} text'''.format(server.id, upd_type))
                        else:
                            self.hist_cursor.execute('''ALTER TABLE \'{}\' ADD COLUMN {} INTEGER'''.format(server.id, upd_type))
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
                self.hist_cursor.execute('''UPDATE \'{}\' SET {}=?'''.format(server.id, upd_type), (hist, ))
                self.hist_db.commit()

    def start_up(self):
        self.get_args()
        token = self.api_data['token']
        print('hmm')
        self.run(token)

    async def help(self, author):
        help_translations = self.translations[self.args.lang]['help']
        help_msg = '`{} v{}`\n{}\n'.format(self.user.name, self.version, help_translations['list'])
        commands = [
            ['help', help_translations['help']],
            ['lfglist', help_translations['lfglist']],
            ['stop', help_translations['stop']],
            ['plan maintenance', help_translations['maintenance']],
            ['@{} lfg ARGS'.format(self.user.name), help_translations['lfg']],
            ['@{} edit lfg ID ARGS'.format(self.user.name), help_translations['edit_lfg']],
            ['@{} regnotifier TYPE'.format(self.user.name), help_translations['regnotifier']],
            ['@{} rmnotifier TYPE'.format(self.user.name), help_translations['rmnotifier']],
            ['@{} update TYPE'.format(self.user.name), help_translations['update']]
        ]

        help_msg = '{}```\t{}```'.format(help_msg, tabulate(commands, tablefmt='plain', colalign=('left', 'left')).replace('\n', '\n\t'))
        if author.dm_channel is None:
            await author.create_dm()
        await author.dm_channel.send(help_msg)

    @discord.ext.commands.command()
    async def help_lfg(ctx):
        channel = ctx.message.channel
        help_translations = ctx.bot.translations[ctx.bot.args.lang]['help_lfg']
        help_msg = '`{} v{}`\n{}\n'.format(ctx.bot.user.name, ctx.bot.version, help_translations['creation'])
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
        help_msg = '{}```\t{}```'.format(help_msg, tabulate(args, tablefmt='plain', colalign=('left', 'left')).replace('\n', '\n\t'))
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


def get_prefix(client, message):
    prefixes = ['?']
    if message.guild:
        prefixes = []

    return commands.when_mentioned_or(*prefixes)(client, message)


if __name__ == '__main__':
    b = ClanBot(command_prefix=get_prefix)
    b.start_up()
