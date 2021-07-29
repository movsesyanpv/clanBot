import json
import discord
import argparse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta, timezone
import asyncio
import pydest
import mariadb
import gc
import random

from discord.ext.commands.bot import Bot
import sqlite3
import logging
import traceback
from inspect import currentframe, getframeinfo
from tabulate import tabulate

from discord.ext import commands

import raid as lfg
import destiny2data as d2
import unauthorized


class ClanBot(commands.Bot):
    version = '3.0a2'
    cog_list = ['cogs.admin', 'cogs.public', 'cogs.group', 'cogs.serveradmin']
    langs = ['de', 'en', 'es', 'es-mx', 'fr', 'it', 'ja', 'ko', 'pl', 'pt-br', 'ru', 'zh-cht']
    all_types = ['weekly', 'nightmares', 'crucible', 'raids', 'ordeal', 'evweekly', 'empire', 'daily', 'strikes', 'spider', 'banshee', 'ada', 'xur', 'osiris', 'alerts', 'events']
    daily_rotations = ('strikes', 'spider', 'banshee', 'ada')
    weekly_rotations = ('nightmares', 'crucible', 'raids', 'ordeal', 'evweekly', 'empire')
    embeds_with_img = ['thelie']

    sched = AsyncIOScheduler(timezone='UTC')
    guild_db = ''
    guild_cursor = ''

    api_data_file = open('api.json', 'r')
    api_data = json.loads(api_data_file.read())
    logger = logging.getLogger('ClanBot')

    update_status = False

    lfgs = []

    notifiers = []
    seasonal_ch = []
    update_ch = []

    raid = ''

    args = ''

    translations = {}

    def __init__(self, **options):
        super().__init__(**options)
        self.get_args()
        self.load_translations()
        self.langs = list(set(self.langs).intersection(set(self.args.lang)))
        self.data = d2.D2data(self.translations, self.langs, self.args.oauth, self.args.production,
                              (self.args.cert, self.args.key))
        self.raid = lfg.LFG()
        self.guild_db = sqlite3.connect('guild.db')
        self.guild_cursor = self.guild_db.cursor()


        # self.sched.add_job(self.universal_update, 'cron', hour='17', minute='0', second='35', misfire_grace_time=86300, args=[self.data.get_heroic_story, 'heroicstory', 86400])
        # self.sched.add_job(self.universal_update, 'cron', hour='17', minute='1', second='30', misfire_grace_time=86300, args=[self.data.get_forge, 'forge', 86400])
        self.sched.add_job(self.universal_update, 'cron', hour='17', minute='1', second='35', misfire_grace_time=86300, args=[self.data.get_strike_modifiers, 'vanguardstrikes', 86400])
        # self.sched.add_job(self.universal_update, 'cron', hour='17', minute='0', second='50', misfire_grace_time=86300, args=[self.data.get_reckoning_modifiers, 'reckoning', 86400])
        self.sched.add_job(self.universal_update, 'cron', hour='17', minute='1', second='35', misfire_grace_time=86300, args=[self.data.get_spider, 'spider', 86400])
        self.sched.add_job(self.data.get_banshee, 'cron', hour='17', minute='1', second='35', misfire_grace_time=86300, args=[self.langs])
        self.sched.add_job(self.data.get_ada, 'cron', hour='17', minute='1', second='35', misfire_grace_time=86300, args=[self.langs])

        self.sched.add_job(self.data.drop_weekend_info, 'cron', day_of_week='tue', hour='17', minute='0', second='0', misfire_grace_time=86300, args=[self.langs])
        # self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='0', second='40', misfire_grace_time=86300, args=[self.data.get_nightfall820, 'nightfalls820', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='1', second='40', misfire_grace_time=86300, args=[self.data.get_ordeal, 'ordeal', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='1', second='40', misfire_grace_time=86300, args=[self.data.get_nightmares, 'nightmares', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='1', second='40', misfire_grace_time=86300, args=[self.data.get_empire_hunt, 'empire_hunts', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='1', second='40', misfire_grace_time=86300, args=[self.data.get_crucible_rotators, 'cruciblerotators', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='1', second='40', misfire_grace_time=86300, args=[self.data.get_raids, 'raids', 604800])
        # self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='1', second='40', misfire_grace_time=86300, args=[self.data.get_featured_bd, 'featured_bd', 604800])
        # self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='1', second='40', misfire_grace_time=86300, args=[self.data.get_bd, 'bd', 604800])
        self.sched.add_job(self.data.get_weekly_eververse, 'cron', day_of_week='tue', hour='17', minute='1', second='40', misfire_grace_time=86300, args=[self.langs])

        self.sched.add_job(self.universal_update, 'cron', day_of_week='fri', hour='17', minute='5', second='0', misfire_grace_time=86300, args=[self.data.get_xur, 'xur', 345600])
        # self.sched.add_job(self.universal_update, 'cron', day_of_week='fri', hour='17', minute='0', second='0', misfire_grace_time=86300, args=[self.data.get_osiris_predictions, 'osiris', 345600])

        self.sched.add_job(self.data.token_update, 'interval', hours=1)
        self.sched.add_job(self.universal_update, 'cron', minute='0', second='0', misfire_grace_time=3500, args=[self.data.get_global_alerts, 'alerts', 86400])
        # self.sched.add_job(self.universal_update, 'cron', minute='0', second='0', misfire_grace_time=3500, args=[self.data.get_the_lie_progress, 'thelie', 3600])
        self.sched.add_job(self.lfg_cleanup, 'interval', weeks=1, args=[7])
        self.sched.add_job(self.update_metrics, 'cron', hour='10', minute='0', second='0', misfire_grace_time=86300)

        logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s:%(message)s')
        logging.getLogger('apscheduler')

        if self.args.production:
            self.load_extension('cogs.dbl')

    def load_translations(self):
        self.translations = {}
        for lang in self.langs:
            translations_file = open('locales/{}.json'.format(lang), 'r', encoding='utf-8')
            self.translations[lang] = json.loads(translations_file.read())
            translations_file.close()

    def get_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-nc', '--noclear', help='Don\'t clear last message of the type', action='store_true')
        parser.add_argument('-p', '--production', help='Use to launch in production mode', action='store_true')
        parser.add_argument('-nm', '--nomessage', help='Don\'t post any messages', action='store_true')
        parser.add_argument('-l', '--lang', nargs='+', help='Language of data', default=self.langs)
        parser.add_argument('-t', '--type', nargs='+', help='Type of message. Use with -f')
        parser.add_argument('-tp', '--testprod', help='Use to launch in test production mode', action='store_true')
        parser.add_argument('-f', '--forceupdate', help='Force update right now', action='store_true')
        parser.add_argument('--oauth', help='Get Bungie access token', action='store_true')
        parser.add_argument('-k', '--key', help='SSL key', type=str, default='')
        parser.add_argument('-c', '--cert', help='SSL certificate', type=str, default='')
        self.args = parser.parse_args()

    async def force_update(self, upd_type, post=True, get=True, channels=None, forceget=False):
        if 'daily' in upd_type and post:
            upd_type = (tuple(upd_type) + self.daily_rotations)
        if 'weekly' in upd_type and post:
            upd_type = (tuple(upd_type) + self.weekly_rotations)
        if 'strikes' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_strike_modifiers, 'vanguardstrikes', 86400, post=post, get=get, channels=channels, forceget=forceget)
        if 'banshee' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.data.get_banshee(self.langs, forceget=forceget)
        if 'ada' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.data.get_ada(self.langs, forceget=forceget)
        if 'spider' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_spider, 'spider', 86400, post=post, get=get, channels=channels, forceget=forceget)
        if 'ordeal' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_ordeal, 'ordeal', 604800, post=post, get=get, channels=channels, forceget=forceget)
        if 'nightmares' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_nightmares, 'nightmares', 604800, post=post, get=get, channels=channels, forceget=forceget)
        if 'empire' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_empire_hunt, 'empire_hunts', 604800, post=post, get=get, channels=channels, forceget=forceget)
        if 'crucible' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_crucible_rotators, 'cruciblerotators', 604800, post=post, get=get, channels=channels, forceget=forceget)
        if 'raids' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_raids, 'raids', 604800, post=post, get=get, channels=channels, forceget=forceget)
        if 'evweekly' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.data.get_weekly_eververse(self.langs)
        if 'xur' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_xur, 'xur', 345600, post=post, get=get, channels=channels, forceget=forceget)
        if 'osiris' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_osiris_predictions, 'osiris', 345600, post=post, get=get, channels=channels, forceget=forceget)
        if 'tess' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_featured_silver, 'silver', 604800, post=post, get=False, channels=channels, forceget=forceget)
                await self.universal_update(self.data.get_featured_bd, 'featured_bd', 604800, post=post, get=False, channels=channels, forceget=forceget)
                await self.universal_update(self.data.get_bd, 'bd', 604800, post=post, get=False, channels=channels, forceget=forceget)
        if 'alerts' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_global_alerts, 'alerts', 604800, channels=channels, post=post, get=get, forceget=forceget)
        if 'events' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                # await self.universal_update(self.data.get_the_lie_progress, 'thelie', 3600, channels=channels, post=post, get=get, forceget=forceget)
                pass
        if self.args.forceupdate:
            await self.data.destiny.close()
            await self.logout()
            await self.close()

    async def on_ready(self):
        await self.dm_owner('on_ready fired')
        game = discord.Game('v{}'.format(self.version))
        await self.change_presence(status=discord.Status.dnd, activity=game)
        self.all_commands['update'].enabled = False
        self.all_commands['top'].enabled = False
        self.all_commands['online'].enabled = False
        await self.data.token_update()
        await self.update_langs()
        await self.update_prefixes()
        # if not self.args.production:
        await self.update_metric_list()
        self.get_channels()
        await self.update_history()
        await self.data.get_chars()
        if self.args.forceupdate:
            await self.force_update(self.args.type)
        if not self.sched.running:
            types = self.all_types.copy()
            types.pop(types.index('osiris'))
            await self.force_update(types, post=False)
            for lang in self.langs:
                self.sched.add_job(self.data.destiny.update_manifest, 'cron', day_of_week='tue', hour='17', minute='0',
                                   second='10', misfire_grace_time=86300, args=[lang])
            self.sched.start()
        game = discord.Game('v{}'.format(self.version))
        await self.change_presence(status=discord.Status.online, activity=game)
        self.all_commands['update'].enabled = True
        self.all_commands['top'].enabled = True
        self.all_commands['online'].enabled = True
        await self.dm_owner('on_ready tasks finished')
        char_file = open('data.json', 'w')
        char_file.write(json.dumps(self.data.data))
        char_file.close()
        return

    async def on_guild_join(self, guild):
        self.logger.info('added to {}'.format(guild.name))
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
                                          'Please set my language for the guild with `@{} setlang LANG`, sent in one of the guild\'s chats. Right now it\'s `en`. Available languages are `{}`.\n'
                                          'To set up automatic updates for Destiny 2, use `regnotifier` command in the channel you want me to post to.\n'
                                          'To use `top` command you\'ll have to set up a D2 clan with the `setclan` command.\n'
                                          'Feel free to ask for help at my Discord Server: https://discord.gg/JEbzECp'.
                                          format(prefix, self.user.name, str(self.langs).replace('[', '').replace(']', '').replace('\'', '')))
        await self.update_history()
        self.update_clans()
        await self.update_prefixes()
        await self.update_langs()

    async def on_guild_remove(self, guild):
        self.guild_cursor.execute('''DELETE FROM clans WHERE server_id=?''', (guild.id,))
        self.guild_cursor.execute('''DELETE FROM history WHERE server_id=?''', (guild.id,))
        self.guild_cursor.execute('''DELETE FROM language WHERE server_id=?''', (guild.id,))
        self.guild_cursor.execute('''DELETE FROM seasonal WHERE server_id=?''', (guild.id,))
        self.guild_cursor.execute('''DELETE FROM notifiers WHERE server_id=?''', (guild.id,))
        self.guild_cursor.execute('''DELETE FROM prefixes WHERE server_id=?''', (guild.id,))
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

        try:
            message = await self.fetch_channel(payload.channel_id)
            message = await message.fetch_message(payload.message_id)
        except discord.NotFound:
            return
        for guild in self.guilds:
            if guild.id == payload.guild_id:
                user = guild.get_member(payload.user_id)

        if self.raid.is_raid(message.id):
            if str(payload.emoji) not in ['👌', '❓']:
                return
            was_goer = self.raid.is_goer(message, user)
            is_mb_goer = self.raid.is_mb_goer(message, user)
            self.raid.rm_people(message.id, user, str(payload.emoji))
            if message.guild.me.guild_permissions.manage_roles:
                role = message.guild.get_role(self.raid.get_cell('group_id', message.id, 'group_role'))
                if role is not None and was_goer:
                    await user.remove_roles(role, reason='User removed 👌')
                    goers = self.raid.get_cell_array('group_id', message.id, 'going')
                    for goer in goers:
                        user_goer = await message.guild.fetch_member(int(goer.replace('<@', '').replace('!', '').replace('>', '')))
                        if role not in user_goer.roles and user_goer is not None:
                            await user_goer.add_roles(role, reason='Previous participant opted out')
            if user.dm_channel is None:
                await user.create_dm()
            lang = self.guild_lang(payload.guild_id)
            await self.raid.update_group_msg(message, self.translations[lang], lang)
            if self.raid.get_cell('group_id', message.id, 'group_mode') == 'manual' and str(payload.emoji) == '👌':
                await user.dm_channel.send(self.translations[lang]['lfg']['gotcha'].format(user.mention))
                owner = self.raid.get_cell('group_id', message.id, 'owner')
                owner = self.get_user(owner)
                await self.raid.upd_dm(owner, message.id, self.translations[lang])

    async def on_raw_reaction_add(self, payload):
        user = payload.member
        if payload.user_id == self.user.id:
            return

        try:
            try:
                message = await self.fetch_channel(payload.channel_id)
                message = await message.fetch_message(payload.message_id)
            except discord.errors.NotFound:
                if self.raid.is_raid(payload.message_id):
                    self.raid.del_entry(payload.message_id)
                return
            except discord.errors.Forbidden:
                return

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
                    if message.guild.me.guild_permissions.manage_roles:
                        role = message.guild.get_role(self.raid.get_cell('group_id', message.id, 'group_role'))
                        if role is not None:
                            await role.delete(reason='LFG deletion')
                    if message.guild.me.guild_permissions.manage_channels:
                        group_ch = message.guild.get_channel(self.raid.get_cell('group_id', message.id, 'group_channel'))
                        if group_ch is not None:
                            if group_ch.permissions_for(message.guild.me).manage_channels:
                                await group_ch.delete(reason='LFG deletion')
                    self.raid.del_entry(message.id)
                    await message.delete()
                    return
                if str(payload.emoji) not in ['👌', '❓']:
                    for reaction in message.reactions:
                        if str(reaction.emoji) == str(payload.emoji):
                            try:
                                await reaction.remove(user)
                            except discord.errors.Forbidden:
                                pass
                            return
                if str(payload.emoji) == '👌':
                    for reaction in message.reactions:
                        if str(reaction.emoji) == '❓':
                            try:
                                await reaction.remove(user)
                            except discord.errors.Forbidden:
                                pass
                if str(payload.emoji) == '❓':
                    for reaction in message.reactions:
                        if str(reaction.emoji) == '👌':
                            try:
                                await reaction.remove(user)
                            except discord.errors.Forbidden:
                                pass
                owner = self.raid.get_cell('group_id', message.id, 'owner')
                owner = self.get_user(owner)
                if str(payload.emoji) == '👌':
                    self.raid.add_people(message.id, user)
                elif str(payload.emoji) == '❓':
                    self.raid.add_mb_goers(message.id, user)
                if message.guild.me.guild_permissions.manage_roles:
                    role = message.guild.get_role(self.raid.get_cell('group_id', message.id, 'group_role'))
                    if role is not None and self.raid.is_goer(message, user):
                        await user.add_roles(role, reason='User pressed 👌')
                lang = self.guild_lang(payload.guild_id)
                if user.dm_channel is None:
                    await user.create_dm()
                if mode == 'manual':
                    if str(payload.emoji) == '👌':
                        await user.dm_channel.send(self.translations[lang]['lfg']['gotcha'].format(user.mention), delete_after=30)
                    await self.raid.upd_dm(owner, message.id, self.translations[lang])
                if mode == 'basic' or str(payload.emoji) == '❓' or user == owner:
                    await self.raid.update_group_msg(message, self.translations[lang], lang)
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
                    lang = self.guild_lang(message.guild.id)
                    await self.raid.update_group_msg(message, self.translations[lang], lang)
                    owner = self.raid.get_cell('group_id', message.id, 'owner')
                    owner = self.get_user(owner)
                    await self.raid.upd_dm(owner, lfg_message, self.translations[lang])
        except Exception as e:
            bot_info = await self.application_info()
            owner = bot_info.owner
            if owner.dm_channel is None:
                await owner.create_dm()
            await owner.dm_channel.send('`{}`'.format(traceback.format_exc()))

    async def lfg_cleanup(self, days, guild=None):
        lfg_list = self.raid.get_all()
        if guild is None:
            guild_id = 0
        else:
            guild_id = guild.id

        i = 0
        for lfg in lfg_list:
            try:
                channel = await self.fetch_channel(lfg[1])
                lfg_msg = await channel.fetch_message(lfg[0])
                start = datetime.fromtimestamp(lfg[2])
                length = lfg[4] if lfg[4] > 0 else 0
                if (datetime.now() - start - timedelta(seconds=length)) > timedelta(days=days) and (guild_id == 0 or guild_id == lfg[3]):
                    await lfg_msg.delete()
                    self.raid.del_entry(lfg[0])
                    i = i + 1
            except discord.errors.NotFound:
                self.raid.del_entry(lfg[0])
                i = i + 1
        return i

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
        if message.guild is None:
            lang = 'en'
        else:
            lang = self.guild_lang(message.guild.id)
        try:
            if isinstance(exception, commands.NoPrivateMessage):
                await ctx.send("\N{WARNING SIGN} Sorry, you can't use this command in a private message!")

            elif isinstance(exception, commands.PrivateMessageOnly):
                await ctx.send("\N{WARNING SIGN} Sorry, you can't use this command in a guild channel!",
                               delete_after=60)
                await ctx.message.delete()

            elif isinstance(exception, commands.CommandNotFound):
                await ctx.send("\N{WARNING SIGN} That command doesn't exist!", delete_after=60)
                await ctx.message.delete()

            elif isinstance(exception, commands.DisabledCommand):
                await ctx.send("\N{WARNING SIGN} Sorry, this command is temporarily disabled! Please, try again later.",
                               delete_after=60)
                await ctx.message.delete()

            elif isinstance(exception, commands.MissingPermissions):
                await ctx.send(f"\N{WARNING SIGN} You do not have permissions to use this command.", delete_after=60)
                await ctx.message.delete()

            elif isinstance(exception, commands.CommandOnCooldown):
                await ctx.send(f"{ctx.author.mention} slow down! Try that again in {exception.retry_after:.1f} seconds",
                               delete_after=60)
                await ctx.message.delete()

            elif isinstance(exception, commands.MissingRequiredArgument) or isinstance(exception, commands.BadArgument):
                await ctx.send(f"\N{WARNING SIGN} {exception}")

            elif isinstance(exception, commands.NotOwner):
                msg = '{}!'.format(ctx.author.mention)
                e = unauthorized.get_unauth_response()
                if ctx.author.dm_channel is None:
                    await ctx.author.create_dm()
                await ctx.author.dm_channel.send(msg, embed=e)

            # elif isinstance(exception, commands.CommandInvokeError):
            #     if isinstance(exception.original, discord.errors.Forbidden):
            #         bot_info = await self.application_info()
            #         owner = bot_info.owner
            #         if owner.dm_channel is None:
            #             await owner.create_dm()
            #         await owner.dm_channel.send('`{}`'.format(traceback.format_exc()))
            #         await owner.dm_channel.send('{}:\n{}'.format(message.author, message.content))
            #         #await message.author.dm_channel.send(self.translations[lang]['msg']['no_send_messages'].format(message.author.mention))
            #         return
            #     raise exception
            elif isinstance(exception.original, discord.errors.Forbidden):
                pass
            else:
                if 'stop' not in message.content.lower() or (
                        self.user not in message.mentions and str(message.channel.type) != 'private'):
                    bot_info = await self.application_info()
                    owner = bot_info.owner
                    if owner.dm_channel is None:
                        await owner.create_dm()
                    traceback_str = ''
                    for line in traceback.format_exception(type(exception), exception, exception.__traceback__):
                        traceback_str = '{}{}'.format(traceback_str, line)
                    await owner.dm_channel.send('`{}`'.format(traceback_str))
                    await owner.dm_channel.send('{}:\n{}'.format(message.author, message.content))
                    if message.author.dm_channel is None:
                        await message.author.create_dm()
                    if message.author != owner:
                        await message.author.dm_channel.send(self.translations['en']['error'])
        except discord.errors.Forbidden:
            pass
        except Exception as e:
            if 'stop' not in message.content.lower() or (self.user not in message.mentions and str(message.channel.type) != 'private'):
                bot_info = await self.application_info()
                owner = bot_info.owner
                if owner.dm_channel is None:
                    await owner.create_dm()
                await owner.dm_channel.send('`{}`'.format(traceback.format_exc()))
                await owner.dm_channel.send('{}:\n{}'.format(message.author, message.content))
                if message.author.dm_channel is None:
                    await message.author.create_dm()
                if message.author != owner:
                    await message.author.dm_channel.send(self.translations['en']['error'])

    async def on_command_completion(self, ctx):
        gc.collect()
        self.logger.info(ctx.message.content)

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
                if lang[0] in self.langs:
                    return lang[0]
                else:
                    return 'en'
            else:
                return 'en'
        except:
            return 'en'

    def guild_prefix(self, guild_id):
        try:
            self.guild_cursor.execute('''SELECT prefix FROM prefixes WHERE server_id=?''', (guild_id, ))
            prefix = self.guild_cursor.fetchone()
            if len(prefix) > 0:
                return eval(prefix[0])
            else:
                return []
        except:
            return []

    def update_clans(self):
        for server in self.guilds:
            try:
                self.guild_cursor.execute('''CREATE TABLE clans (server_name text, server_id integer, clan_name text, clan_id integer)''')
                self.guild_cursor.execute('''CREATE UNIQUE INDEX clan ON clans(server_id)''')
                self.guild_cursor.execute('''INSERT or IGNORE INTO clans VALUES (?,?,?,?)''', [server.name, server.id, '', 0])
            except sqlite3.OperationalError:
                try:
                    self.guild_cursor.execute('''INSERT or IGNORE INTO clans VALUES (?,?,?,?)''', [server.name, server.id, '', 0])
                except:
                    pass

        self.guild_db.commit()

    async def update_langs(self):
        for server in self.guilds:
            try:
                self.guild_cursor.execute('''CREATE TABLE language (server_id integer, lang text, server_name text)''')
                self.guild_cursor.execute('''CREATE UNIQUE INDEX lang ON language(server_id)''')
                self.guild_cursor.execute('''INSERT or IGNORE INTO language VALUES (?,?,?)''', [server.id, 'en', server.name])
            except sqlite3.OperationalError:
                try:
                    self.guild_cursor.execute('''ALTER TABLE language ADD COLUMN server_name text''')
                except sqlite3.OperationalError:
                    try:
                        self.guild_cursor.execute('''INSERT or IGNORE INTO language VALUES (?,?,?)''',
                                                  [server.id, 'en', server.name])
                    except:
                        pass
            try:
                self.guild_cursor.execute('''UPDATE language SET server_name=? WHERE server_id=?''',
                                          (server.name, server.id))
            except:
                pass

        self.guild_db.commit()

        self.update_clans()

    async def update_prefixes(self):
        for server in self.guilds:
            try:
                self.guild_cursor.execute('''CREATE TABLE prefixes (server_id integer, prefix text, server_name text)''')
                self.guild_cursor.execute('''CREATE UNIQUE INDEX prefix ON prefixes(server_id)''')
                self.guild_cursor.execute('''INSERT or IGNORE INTO prefixes VALUES (?,?,?)''', [server.id, '[\'?\']', server.name])
            except sqlite3.OperationalError:
                try:
                    self.guild_cursor.execute('''INSERT or IGNORE INTO prefixes VALUES (?,?,?)''',
                                              [server.id, '[\'?\']', server.name])
                except:
                    pass
            try:
                self.guild_cursor.execute('''UPDATE prefixes SET server_name=? WHERE server_id=?''',
                                          (server.name, server.id))
            except:
                pass

        self.guild_db.commit()

        self.update_clans()

    async def update_history(self):
        try:
            self.guild_cursor.execute('''CREATE TABLE history ( server_name text, server_id integer, channel_id integer)''')
            self.guild_cursor.execute('''CREATE UNIQUE INDEX hist ON history(channel_id)''')
        except sqlite3.OperationalError:
            pass
        for channel_id in self.notifiers:
            try:
                channel = self.get_channel(channel_id)
                if channel is not None:
                    init_values = [channel.guild.name, channel.guild.id, channel_id]
                    self.guild_cursor.execute("INSERT or IGNORE INTO history (server_name, server_id, channel_id) VALUES (?,?,?)", init_values)
                    self.guild_db.commit()
            except sqlite3.OperationalError:
                pass

    async def universal_update(self, getter, name, time_to_delete=None, channels=None, post=True, get=True, forceget=False):
        await self.wait_until_ready()

        lang = self.langs

        if channels is None:
            channels = self.notifiers

        if len(channels) == 0 and not get:
            return

        status = True

        if get:
            try:
                status = await getter(lang, forceget)
            except Exception as e:
                bot_info = await self.application_info()
                owner = bot_info.owner
                if owner.dm_channel is None:
                    await owner.create_dm()
                await owner.dm_channel.send('`{}`'.format(traceback.format_exc()))
                return

            for locale in self.args.lang:
                if not self.data.data[locale][name] and type(self.data.data[locale][name]) == bool:
                    return

        if not status and status is not None:
            self.sched.add_job(self.universal_update, 'date', run_date=(datetime.utcnow() + timedelta(minutes=30)),
                               args=[getter, name, time_to_delete, channels, post, get, forceget])

        if post:
            await self.post_embed(name, self.data.data, time_to_delete, channels)

    async def post_embed_to_channel(self, upd_type, src_dict, time_to_delete, channel_id):
        await asyncio.sleep(random.randint(0, 60))
        try:
            channel = self.get_channel(channel_id)
        except discord.Forbidden:
            frameinfo = getframeinfo(currentframe())
            return [channel_id, 'unable to fetch the channel ({})'.format(frameinfo.lineno + 1)]
        if channel is None:
            frameinfo = getframeinfo(currentframe())
            return [channel_id, 'channel id None ({})'.format(frameinfo.lineno + 1)]
        server = channel.guild
        if not channel.permissions_for(server.me).send_messages:
            frameinfo = getframeinfo(currentframe())
            return [channel_id, 'no permission to send messages ({})'.format(frameinfo.lineno + 1)]
        lang = self.guild_lang(channel.guild.id)
        delay = 0#random.uniform(0, 0.2)
        # print('delay is {}'.format(delay))

        if not self.args.nomessage:
            if type(src_dict[lang][upd_type]) == list:
                embed = []
                for field in src_dict[lang][upd_type]:
                    embed.append(discord.Embed.from_dict(field))
            else:
                if upd_type in self.embeds_with_img:
                    image = discord.File("{}-{}.png".format(upd_type, lang),
                                         filename='{}-{}.png'.format(upd_type, lang))
                if len(src_dict[lang][upd_type]['fields']) == 0:
                    frameinfo = getframeinfo(currentframe())
                    return [channel_id, 'no need to post ({})'.format(frameinfo.lineno + 1)]
                embed = discord.Embed.from_dict(src_dict[lang][upd_type])

        hist = 0
        try:
            last = self.guild_cursor.execute('''SELECT {} FROM history WHERE channel_id=?'''.format(upd_type),
                                             (channel_id,))
            last = last.fetchone()
            if last is not None:
                if type(src_dict[lang][upd_type]) == list:
                    hist = [0]
                    if len(last) > 0:
                        if last[0] is not None:
                            hist = eval(last[0])
                        else:
                            hist = [0]
                else:
                    if len(last) > 0:
                        if last[0] is not None:
                            hist = last[0]
            else:
                try:
                    init_values = [channel.guild.name, channel.guild.id, channel_id]
                    self.guild_cursor.execute(
                        "INSERT or IGNORE INTO history (server_name, server_id, channel_id) VALUES (?,?,?)", init_values)
                    # self.guild_db.commit()
                except sqlite3.OperationalError:
                    pass

        except sqlite3.OperationalError:
            try:
                if type(src_dict[lang][upd_type]) == list:
                    self.guild_cursor.execute(
                        '''ALTER TABLE history ADD COLUMN {} text'''.format(upd_type))
                else:
                    self.guild_cursor.execute('''ALTER TABLE history ADD COLUMN {} INTEGER'''.format(upd_type))
                # self.guild_db.commit()
            except sqlite3.OperationalError:
                await self.update_history()

        if hist and not self.args.noclear:
            try:
                if type(hist) == list:
                    last = []
                    dict_embeds = []
                    for embed_p in embed:
                        dict_embeds.append(embed_p.to_dict())
                    for msg in hist:
                        # await asyncio.sleep(delay)
                        message = await channel.fetch_message(msg)
                        if len(message.embeds) > 0:
                            tmp_embed = message.embeds[0].to_dict()
                            tmp_embed['author'].pop('proxy_icon_url', None)
                            if tmp_embed not in dict_embeds:
                                last.append(message)
                    if len(last) == 0:
                        frameinfo = getframeinfo(currentframe())
                        return [channel_id, 'no need to post ({})'.format(frameinfo.lineno + 1)]
                else:
                    if hist != "[]":
                        try:
                            # await asyncio.sleep(delay)
                            last = await channel.fetch_message(hist)
                        except discord.errors.HTTPException:
                            # await asyncio.sleep(delay)
                            last = await channel.fetch_message(0)
                        if len(last.embeds) > 0:
                            if last.embeds[0].to_dict()['fields'] == embed.to_dict()['fields']:
                                frameinfo = getframeinfo(currentframe())
                                return [channel_id, 'no need to post ({})'.format(frameinfo.lineno + 1)]
                try:
                    if type(hist) == list and channel.type != discord.ChannelType.news:
                        if len(hist) < 100:
                            for msg in last:
                                # await asyncio.sleep(delay)
                                await msg.delete()
                    else:
                        if type(last) != tuple and channel.type != discord.ChannelType.news:
                            # await asyncio.sleep(delay)
                            await last.delete()
                except discord.errors.Forbidden:
                    pass
                except discord.NotFound:
                    pass
                except discord.errors.HTTPException as e:
                    bot_info = await self.application_info()
                    await bot_info.owner.dm_channel.send('`{}`'.format(traceback.format_exc()))
                    pass
            except discord.NotFound:
                pass
                # bot_info = await self.application_info()
                # await bot_info.owner.send('Not found at ```{}```. Channel ```{}``` of ```{}```'.
                #                           format(upd_type, channel.name, server.name))
            except discord.Forbidden:
                pass
        if type(embed) == list:
            hist = []
            for e in embed:
                if channel.permissions_for(server.me).embed_links:
                    if channel.type != discord.ChannelType.news:
                        # await asyncio.sleep(delay)
                        message = await channel.send(embed=e, delete_after=time_to_delete)
                    else:
                        # await asyncio.sleep(delay)
                        message = await channel.send(embed=e)
                else:
                    # await asyncio.sleep(delay)
                    message = await channel.send(self.translations[lang]['msg']['no_embed_links'])
                hist.append(message.id)
                if channel.type == discord.ChannelType.news:
                    try:
                        # await asyncio.sleep(delay)
                        await message.publish()
                    except discord.errors.Forbidden:
                        pass
            hist = str(hist)
        else:
            if channel.permissions_for(server.me).embed_links:
                if upd_type in self.embeds_with_img:
                    if channel.type != discord.ChannelType.news:
                        # await asyncio.sleep(delay)
                        message = await channel.send(file=image, embed=embed, delete_after=time_to_delete)
                    else:
                        # await asyncio.sleep(delay)
                        message = await channel.send(file=image, embed=embed)
                else:
                    if channel.type != discord.ChannelType.news:
                        # await asyncio.sleep(delay)
                        message = await channel.send(embed=embed, delete_after=time_to_delete)
                    else:
                        # await asyncio.sleep(delay)
                        message = await channel.send(embed=embed)
            else:
                # await asyncio.sleep(delay)
                message = await channel.send(self.translations[lang]['msg']['no_embed_links'])
            hist = message.id
            if channel.type == discord.ChannelType.news:
                try:
                    # await asyncio.sleep(delay)
                    await message.publish()
                except discord.errors.Forbidden:
                    pass

        self.guild_cursor.execute('''UPDATE history SET {}=? WHERE channel_id=?'''.format(upd_type),
                                  (str(hist), channel_id))
        self.guild_db.commit()

        frameinfo = getframeinfo(currentframe())
        return [channel_id, 'posted ({})'.format(frameinfo.lineno + 1)]

    async def post_embed(self, upd_type, src_dict, time_to_delete, channels):
        tasks = []
        for channel_id in channels:
            task = asyncio.ensure_future(self.post_embed_to_channel(upd_type, src_dict, time_to_delete, channel_id))
            tasks.append(task)

        responses = await asyncio.gather(*tasks)

        if self.update_status:
            msg = '{} is posted'.format(upd_type)
            statuses = tabulate(responses, tablefmt='simple', colalign=('left', 'left'), headers=['channel', 'status'])
            msg = '{}\n```{}```'.format(msg, statuses)
            if len(msg) > 2000:
                msg_strs = msg.splitlines()
                msg = ''
                for line in msg_strs:
                    if len(msg) + len(line) <= 1990:
                        msg = '{}{}\n'.format(msg, line)
                    else:
                        msg = '{}```'.format(msg)
                        await self.dm_owner(msg)
                        msg = '```{}\n'.format(line)
                if len(msg) > 0:
                    msg = '{}'.format(msg)
                    await self.dm_owner(msg)
            else:
                await self.dm_owner(msg)

    async def post_updates(self, version, content, lang):
        msg = '`{} v{}`\n{}'.format(self.user.name, version, content)
        for server in self.guilds:
            if lang == self.guild_lang(server.id):
                for channel in server.channels:
                    if channel.id in self.update_ch:
                        message = await channel.send(msg)
                        if channel.type == discord.ChannelType.news:
                            try:
                                await message.publish()
                            except discord.errors.Forbidden:
                                pass

    async def update_metrics(self):
        clan_ids_c = self.guild_cursor.execute('''SELECT clan_id FROM clans''')
        clan_ids_c = clan_ids_c.fetchall()
        clan_ids = []
        for clan_id in clan_ids_c:
            clan_ids.append(clan_id[0])
        await self.data.get_clan_leaderboard(clan_ids, 1572939289, 10)

    async def update_metric_list(self):
        internal_db = mariadb.connect(host=self.api_data['db_host'], user=self.api_data['cache_login'],
                                      password=self.api_data['pass'], port=self.api_data['db_port'],
                                      database='metrics')
        internal_cursor = internal_db.cursor()

        metrics_manifest = await self.data.destiny.decode_hash(1074663644, 'DestinyPresentationNodeDefinition')

        for node in metrics_manifest['children']['presentationNodes']:
            internal_cursor.execute('''SELECT name FROM metrictables WHERE id=?''', (node['presentationNodeHash'],))
            metric_node = internal_cursor.fetchone()
            node_manifest = await self.data.destiny.decode_hash(node['presentationNodeHash'], 'DestinyPresentationNodeDefinition')
            if metric_node is not None:
                internal_cursor.execute('''SELECT hash, name, is_working FROM {}'''.format(metric_node[0]))
                metrics = internal_cursor.fetchall()
                for metric in metrics:
                    tmp = list(metrics[metrics.index(metric)])
                    tmp.append(metric[0])
                    try:
                        await self.data.destiny.decode_hash(metric[0], 'DestinyMetricDefinition')
                        tmp[2] = 1
                    except pydest.PydestException:
                        tmp[2] = 0
                    metrics[metrics.index(metric)] = tuple(tmp)
                internal_cursor.executemany('''UPDATE {} SET hash=?, name=?, is_working=? WHERE hash=?'''.format(metric_node[0]), metrics)
                metrics = []
                for metric in node_manifest['children']['metrics']:
                    metrics.append(tuple(['', metric['metricHash'], 1]))
                internal_cursor.executemany('''INSERT IGNORE INTO {} VALUES (?,?,?)'''.format(metric_node[0]), metrics)
                pass

        internal_db.commit()
        internal_db.close()

    def start_up(self):
        self.get_args()
        token = self.api_data['token']
        print('hmm')
        self.remove_command('help')
        for cog in self.cog_list:
            self.load_extension(cog)
        self.run(token)


def get_prefix(client, message):
    prefixes = ['?']
    if message.guild:
        prefixes = client.guild_prefix(message.guild.id)

    return commands.when_mentioned_or(*prefixes)(client, message)


if __name__ == '__main__':
    intents = discord.Intents.default()
    intents.members = True
    b = ClanBot(command_prefix=get_prefix, intents=intents)
    b.start_up()
