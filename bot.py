import io
import json
import discord
import argparse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta, timezone, time
import asyncio
import pydest
import mariadb
import gc
import random

from discord.ext.commands.bot import Bot
import discord.ext.tasks as tasks
from discord import ApplicationContext, DiscordException
import aiosqlite
import sqlite3
import logging
from logging.handlers import RotatingFileHandler
import traceback
from inspect import currentframe, getframeinfo
from tabulate import tabulate
from collections import Counter

from discord.ext import commands

import raid as lfg
import destiny2data as d2
import unauthorized
from cogs.utils.views import GroupButtons, DMSelectLFG
from cogs.utils.converters import locale_2_lang
from internationalization import I18n

from typing import List, Union, Callable


class ClanBot(commands.Bot):
    version = ''
    cog_list = ['cogs.admin', 'cogs.public', 'cogs.group', 'cogs.serveradmin']
    langs = ['en', 'de', 'es', 'es-mx', 'fr', 'it', 'ja', 'ko', 'pl', 'pt-br', 'ru', 'zh-cht', 'zh-chs']
    all_types = ['weekly', 'nightmares', 'crucible', 'raids', 'ordeal', 'evweekly', 'empire', 'daily', 'strikes', 'spider', 'banshee', 'ada', 'mods', 'lostsector', 'xur', 'osiris', 'alerts', 'events', 'gambit']
    daily_rotations = ('strikes', 'spider', 'banshee', 'ada', 'mods', 'lostsector')
    weekly_rotations = ('nightmares', 'crucible', 'raids', 'ordeal', 'evweekly', 'empire')
    embeds_with_img = ['events']

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

    raid: lfg.LFG

    args = ''

    translations = {}

    i18n: I18n

    def __init__(self, upgrade=False, **options):
        super().__init__(**options)
        self.get_args()
        self.load_translations()
        self.langs = list(set(self.langs).intersection(set(self.args.lang)))
        try:
            self.data = d2.D2data(self.translations, self.langs, self.args.oauth, self.args.production,
                                  (self.args.cert, self.args.key), self.loop)
        except RuntimeError:
            return
        self.raid = lfg.LFG(self)
        asyncio.run(self.set_up_guild_db())

        self.i18n = I18n(self)

        self.guild_db_sync = sqlite3.connect('guild.db')
        self.guild_cursor = self.guild_db_sync.cursor()
        self.persistent_views_added = False

        version_file = open('version.dat', 'r')
        self.version = version_file.read()

        self.sched.add_job(self.data.get_banshee, 'cron', hour='17', minute='1', second='35', misfire_grace_time=86300, args=[self.langs])
        self.sched.add_job(self.data.get_ada, 'cron', hour='17', minute='1', second='35', misfire_grace_time=86300, args=[self.langs])

        self.sched.add_job(self.data.drop_weekend_info, 'cron', day_of_week='tue', hour='17', minute='0', second='0', misfire_grace_time=86300, args=[self.langs])
        self.sched.add_job(self.data.get_weekly_eververse, 'cron', day_of_week='tue', hour='17', minute='1', second='40', misfire_grace_time=86300, args=[self.langs])

        # self.sched.add_job(self.universal_update, 'cron', day_of_week='fri', hour='17', minute='5', second='0', misfire_grace_time=86300, args=[self.data.get_xur, 'xur', 345600])
        # self.sched.add_job(self.universal_update, 'cron', day_of_week='fri', hour='17', minute='1', second='40', misfire_grace_time=86300, args=[self.data.get_osiris_predictions, 'osiris', 345600])

        self.sched.add_job(self.data.token_update, 'interval', hours=1)
        self.sched.add_job(self.lfg_cleanup, 'interval', weeks=1, args=[7])
        self.sched.add_job(self.update_metrics, 'cron', hour='10', minute='0', second='0', misfire_grace_time=86300)

        self.log_handler = RotatingFileHandler('bot.log', maxBytes=5*1024*1024, backupCount=20)
        logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s:%(message)s', handlers=[self.log_handler])
        self.ap_logger = logging.getLogger('apscheduler')

    @tasks.loop(time=time(hour=17, minute=0, second=35), reconnect=True)
    async def update_strikes(self):
        await self.wait_for('manifest ready')
        self.logger.info('Updating strike modifiers')
        await self.universal_update(self.data.get_strike_modifiers, 'vanguardstrikes', 86400)
        self.logger.info('Finished updating strike modifiers')

    @tasks.loop(time=time(hour=17, minute=0, second=35), reconnect=True)
    async def update_materials(self):
        await self.wait_for('manifest ready')
        self.logger.info('Updating material exchange')
        await self.universal_update(self.data.get_spider, 'spider', 86400)
        self.logger.info('Finished updating material exchange')

    @tasks.loop(time=time(hour=17, minute=0, second=35), reconnect=True)
    async def update_daily_mods(self):
        await self.wait_for('manifest ready')
        self.logger.info('Updating daily mods')
        await self.universal_update(self.data.get_daily_mods, 'daily_mods', 86400)
        self.logger.info('Finished updating daily mods')

    @tasks.loop(time=time(hour=17, minute=0, second=35), reconnect=True)
    async def update_lost_sector(self):
        await self.wait_for('manifest ready')
        self.logger.info('Updating lost sector')
        await self.universal_update(self.data.get_lost_sector, 'lostsector', 86400)
        self.logger.info('Finished updating lost sector')

    @tasks.loop(time=time(hour=17, minute=0, second=40), reconnect=True)
    async def update_nightmares(self):
        if datetime.today().weekday() == 1:
            await self.wait_for('manifest ready')
            self.logger.info('Updating nightmares')
            await self.universal_update(self.data.get_nightmares, 'nightmares', 604800)
            self.logger.info('Finished updating nightmares')

    @tasks.loop(time=time(hour=17, minute=0, second=40), reconnect=True)
    async def update_nightfall(self):
        if datetime.today().weekday() == 1:
            await self.wait_for('manifest ready')
            self.logger.info('Updating nightfall')
            await self.universal_update(self.data.get_ordeal, 'ordeal', 604800)
            self.logger.info('Finished updating nightfall')

    @tasks.loop(time=time(hour=17, minute=0, second=40), reconnect=True)
    async def update_empire_hunt(self):
        if datetime.today().weekday() == 1:
            await self.wait_for('manifest ready')
            self.logger.info('Updating empire hunt')
            await self.universal_update(self.data.get_empire_hunt, 'empire_hunts', 604800)
            self.logger.info('Finished updating empire hunt')

    @tasks.loop(time=time(hour=17, minute=0, second=40), reconnect=True)
    async def update_crucible(self):
        if datetime.today().weekday() == 1:
            await self.wait_for('manifest ready')
            self.logger.info('Updating crucible rotators')
            await self.universal_update(self.data.get_crucible_rotators, 'cruciblerotators', 604800)
            self.logger.info('Finished updating crucible rotators')

    @tasks.loop(time=time(hour=17, minute=0, second=40), reconnect=True)
    async def update_raids(self):
        if datetime.today().weekday() == 1:
            await self.wait_for('manifest ready')
            self.logger.info('Updating raid challenges')
            await self.universal_update(self.data.get_raids, 'raids', 604800)
            self.logger.info('Finished updating raid challenges')

    @tasks.loop(time=time(hour=17, minute=0, second=40), reconnect=True)
    async def update_xur(self):
        if datetime.today().weekday() == 4:
            await self.wait_for('manifest ready')
            self.logger.info('Updating xur')
            await self.universal_update(self.data.get_xur, 'xur', 345600)
            self.logger.info('Finished updating xur')

    @tasks.loop(time=time(hour=17, minute=0, second=40))
    async def update_trials(self):
        if datetime.today().weekday() == 4:
            await self.wait_for('manifest ready')
            self.logger.info('Updating trials')
            await self.universal_update(self.data.get_osiris_predictions, 'osiris', 345600)
            self.logger.info('Finished updating trials')

    @tasks.loop(time=[time(hour=t, minute=0, second=0) for t in range(24)])
    async def update_alerts(self):
        self.logger.info('Updating alerts')
        await self.universal_update(self.data.get_global_alerts, 'alerts', 86400)
        self.logger.info('Finished updating alerts')

    @tasks.loop(time=[time(hour=t, minute=0, second=0) for t in range(24)])
    async def update_event(self):
        self.logger.info('Updating event')
        await self.universal_update(self.data.get_event_progress, 'events', 86400)
        self.logger.info('Finished updating event')

    @tasks.loop(time=time(hour=17, minute=1, second=35), reconnect=True)
    async def update_manifest(self):
        self.logger.info('Updating manifest')
        for lang in self.langs:
            await self.data.destiny.update_manifest(lang)
        self.logger.info('Finished updating manifest')
        self.dispatch('manifest ready')

    def start_tasks(self):
        self.logger.info('Adding autopost tasks')

        self.update_manifest.start()
        self.update_strikes.start()
        self.update_materials.start()
        self.update_daily_mods.start()
        self.update_lost_sector.start()

        self.update_nightmares.start()
        self.update_nightfall.start()
        self.update_empire_hunt.start()
        self.update_crucible.start()
        self.update_raids.start()

        self.update_xur.start()
        self.update_trials.start()

        self.update_alerts.start()
        self.update_event.start()

    async def set_up_guild_db(self):
        self.guild_db = await aiosqlite.connect('guild.db')
        # cache_cursor = await self.cache_db.cursor()
        # try:
        #     await cache_cursor.execute(
        #         '''CREATE TABLE cache (id text, expires integer, json text, timestamp text);''')
        #     await cache_cursor.execute('''CREATE UNIQUE INDEX cache_id ON cache(id)''')
        #     await self.cache_db.commit()
        #     await cache_cursor.close()
        # except aiosqlite.OperationalError:
        #     pass

    def load_translations(self) -> None:
        self.translations = {}
        for lang in self.langs:
            translations_file = open('locales/{}.json'.format(lang), 'r', encoding='utf-8')
            self.translations[lang] = json.loads(translations_file.read())
            translations_file.close()

    def get_args(self) -> None:
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

    async def force_update(self, upd_type: List[str], post: bool = True, get: bool = True, channels: List[int] = None,
                           forceget: bool = False) -> None:
        if 'daily' in upd_type and post:
            upd_type = (tuple(upd_type) + self.daily_rotations)
        if 'weekly' in upd_type and post:
            upd_type = (tuple(upd_type) + self.weekly_rotations)
        if get and post:
            self.logger.info('upd_types: {}'.format(str(upd_type)))
        if 'strikes' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_strike_modifiers, 'vanguardstrikes', 86400, post=post, get=get, channels=channels, forceget=forceget)
        if 'banshee' in upd_type and get:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.data.get_banshee(self.langs, forceget=forceget)
        if 'ada' in upd_type and get:
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
        if 'evweekly' in upd_type and get:
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
        if 'mods' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_daily_mods, 'daily_mods', 345600, post=post, get=get, channels=channels, forceget=forceget)
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
                await self.universal_update(self.data.get_event_progress, 'events', 3600, channels=channels, post=post, get=get, forceget=forceget)
                pass
        # if 'gambit' in upd_type:
        #     if channels is None:
        #         channels = self.notifiers
        #     if (post and list(set(channels).intersection(self.notifiers))) or get:
        #         await self.universal_update(self.data.get_gambit_modifiers, 'gambit', 604800, post=post, get=get, channels=channels, forceget=forceget)
        if 'lostsector' in upd_type:
            if channels is None:
                channels = self.notifiers
            if (post and list(set(channels).intersection(self.notifiers))) or get:
                await self.universal_update(self.data.get_lost_sector, 'lostsector', 86400, post=post, get=get, channels=channels, forceget=forceget)
        if self.args.forceupdate:
            await self.data.destiny.close()
            await self.logout()
            await self.close()

    async def on_ready(self) -> None:
        await self.dm_owner('on_ready fired')
        game = discord.Game('v{}'.format(self.version))
        await self.change_presence(status=discord.Status.dnd, activity=game)
        # self.all_commands['update'].enabled = False
        # self.all_commands['top'].enabled = False
        # self.all_commands['online'].enabled = False
        await self.data.token_update()
        await self.update_langs()
        await self.update_prefixes()
        # if not self.args.production:
        await self.update_metric_list()
        self.get_channels()
        await self.update_history()
        await self.update_alert_preferences()
        await self.update_guild_timezones()
        await self.data.get_chars()
        # await self.update_metrics()
        if self.args.forceupdate:
            await self.force_update(self.args.type)
        if not self.sched.running:
            types = self.all_types.copy()
            # types.pop(types.index('osiris'))
            if not self.data.data_ready:
                await self.force_update(types, post=False)
            # for lang in self.langs:
            #     self.sched.add_job(self.data.destiny.update_manifest, 'cron', day_of_week='tue', hour='17', minute='0',
            #                        second='10', misfire_grace_time=86300, args=[lang])
            self.sched.start()
            self.start_tasks()
            if self.args.production:
                self.load_extension('cogs.dbl')
        game = discord.Game('v{}'.format(self.version))
        if not self.persistent_views_added:
            await self.raid.add_alert_jobs()
            lfg_list = await self.raid.get_all()
            for lfg in lfg_list:
                try:
                    lang = self.guild_lang(lfg[3])
                    group_msg = await self.fetch_channel(lfg[1])
                    try:
                        group_msg = await group_msg.fetch_message(lfg[0])
                    except discord.Forbidden:
                        continue
                    buttons = GroupButtons(lfg[0], self,
                                           label_go=self.translations[lang]['lfg']['button_want'],
                                           label_help=self.translations[lang]['lfg']['button_help'],
                                           label_no_go=self.translations[lang]['lfg']['button_no_go'],
                                           label_delete=self.translations[lang]['lfg']['button_delete'],
                                           label_alert=self.translations[lang]['lfg']['button_alert'],
                                           support_alerts=await self.lfg_alerts_enabled(lfg[3]))
                    await group_msg.edit(view=buttons)
                    self.persistent_views.pop(self.persistent_views.index(buttons))  # This bs is a workaround for a pycord broken persistent view processing
                    self.add_view(buttons)
                except discord.NotFound:
                    self.add_view(GroupButtons(lfg[0], self))
                if lfg[5] != 0:
                    owner = await self.fetch_user(lfg[6])
                    if owner.dm_channel is None:
                        await owner.create_dm()
                    dm_msg = await owner.dm_channel.fetch_message(lfg[5])
                    if len(dm_msg.components) == 0:
                        await self.raid.upd_dm(owner, lfg[0], self.translations[self.guild_lang(lfg[3])])
                    else:
                        self.add_view(DMSelectLFG(dm_msg.components[0].children[0].options, custom_id=dm_msg.components[0].children[0].custom_id, bot=self))
            self.persistent_views_added = True
        await self.change_presence(status=discord.Status.online, activity=game)
        # self.all_commands['update'].enabled = True
        # self.all_commands['top'].enabled = True
        # self.all_commands['online'].enabled = True
        await self.dm_owner('on_ready tasks finished')
        return

    async def on_guild_join(self, guild: discord.Guild) -> None:
        self.logger.info('added to {}'.format(guild.name))
        user = guild.owner
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add):
                if entry.target.id == guild.me.id:
                    user = entry.user
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass
        try:
            if user.dm_channel is None:
                await user.create_dm()
            start = await user.dm_channel.send('Thank you for inviting me to your guild!\n')
            prefixes = get_prefix(self, start)
            prefix = '?'
            for i in prefixes:
                if '@' not in i:
                    prefix = i
            await user.dm_channel.send('The `/help` command will get you the command list.\n'
                                              'To set up automatic Destiny 2 information updates use `/regnotifier` or `/autopost start` command in the channel you want me to post to.\n'
                                              'Please set my language for the guild with `/setlang`, sent in one of the guild\'s chats. Right now it\'s `en`. Available languages are `{}`.\n'
                                              'To use `/top` command you\'ll have to set up a D2 clan with the `/setclan` command.\n'
                                              'Feel free to ask for help at my Discord Server: https://discord.gg/JEbzECp'.
                                              format(str(self.langs).replace('[', '').replace(']', '').replace('\'', ''), self.user.name))
        except AttributeError:
            pass
        await self.update_history()
        await self.update_clans()
        await self.update_prefixes()
        await self.update_langs()
        await self.update_alert_preferences()
        await self.update_guild_timezones()

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        cursor = await self.guild_db.cursor()
        await cursor.execute('''DELETE FROM clans WHERE server_id=?''', (guild.id,))
        await cursor.execute('''DELETE FROM history WHERE server_id=?''', (guild.id,))
        await cursor.execute('''DELETE FROM post_settings WHERE server_id=?''', (guild.id,))
        await cursor.execute('''DELETE FROM language WHERE server_id=?''', (guild.id,))
        await cursor.execute('''DELETE FROM seasonal WHERE server_id=?''', (guild.id,))
        await cursor.execute('''DELETE FROM notifiers WHERE server_id=?''', (guild.id,))
        await cursor.execute('''DELETE FROM prefixes WHERE server_id=?''', (guild.id,))
        await cursor.execute('''DELETE FROM lfg_alerts WHERE server_id=?''', (guild.id,))
        await cursor.execute('''DELETE FROM timezones WHERE server_id=?''', (guild.id,))
        await self.guild_db.commit()
        await self.raid.purge_guild(guild.id)
        await cursor.close()

    async def dm_owner(self, text: str) -> None:
        bot_info = await self.application_info()
        if bot_info.owner.dm_channel is None:
            await bot_info.owner.create_dm()
        await bot_info.owner.dm_channel.send(text)

    async def check_ownership(self, message: discord.Message, is_silent: bool = False,
                              admin_check: bool = False) -> bool:
        bot_info = await self.application_info()
        is_owner = bot_info.owner == message.author
        if not is_owner and not is_silent:
            msg = '{}!'.format(message.author.mention)
            e = unauthorized.get_unauth_response()
            if message.author.dm_channel is None:
                await message.author.create_dm()
            await message.author.dm_channel.send(msg, embed=e)
        if message.guild is None:
            return is_owner
        else:
            return is_owner or (message.channel.permissions_for(message.author).administrator and admin_check)

    async def lfg_cleanup(self, days: Union[int, float], guild: discord.Guild = None) -> int:
        lfg_list = await self.raid.get_all()
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
                    await self.raid.del_entry(lfg[0])
                    i = i + 1
            except discord.NotFound:
                await self.raid.del_entry(lfg[0])
                i = i + 1
            except discord.Forbidden:
                await self.raid.del_entry(lfg[0])
                i = i + 1
        return i

    async def pause_for(self, message: discord.Message, delta: timedelta) -> None:
        self.sched.pause()
        await asyncio.sleep(delta.total_seconds())
        self.sched.resume()
        await message.channel.send('should be after delay finish {}'.format(str(datetime.now())))
        return

    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if await self.raid.is_raid(payload.message_id):
            owner = await self.raid.get_cell('group_id', payload.message_id, 'owner')
            owner = self.get_user(owner)
            if owner is not None:
                dm_id = await self.raid.get_cell('group_id', payload.message_id, 'dm_message')
                if owner.dm_channel is None:
                    await owner.create_dm()
                if dm_id != 0:
                    dm_message = await owner.dm_channel.fetch_message(dm_id)
                    await dm_message.delete()
                await self.raid.del_entry(payload.message_id)

    async def on_command_error(self, ctx: discord.ext.commands.Context, exception):
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

            elif isinstance(exception, commands.CommandNotFound):
                if message.guild is None:
                    await ctx.send("\N{WARNING SIGN} That command doesn't exist!", delete_after=60)

            elif isinstance(exception, commands.DisabledCommand):
                await ctx.send("\N{WARNING SIGN} Sorry, this command is temporarily disabled! Please, try again later.",
                               delete_after=60)

            elif isinstance(exception, commands.MissingPermissions):
                await ctx.send(f"\N{WARNING SIGN} You do not have permissions to use this command.", delete_after=60)

            elif isinstance(exception, commands.CommandOnCooldown):
                await ctx.send(f"{ctx.author.mention} slow down! Try that again in {exception.retry_after:.1f} seconds",
                               delete_after=60)

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
            elif isinstance(exception.original, discord.Forbidden):
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
                    if len(traceback_str) < 1998:
                        await owner.dm_channel.send('`{}`'.format(traceback_str))
                    else:
                        self.logger.exception(traceback_str)
                    await owner.dm_channel.send('{}:\n{}'.format(message.author, message.content))
                    if message.author.dm_channel is None:
                        await message.author.create_dm()
                    if message.author != owner:
                        await message.author.dm_channel.send(self.translations['en']['error'])
        except discord.Forbidden:
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

    async def on_application_command_error(
        self, context: ApplicationContext, exception: DiscordException
    ) -> None:
        locale = await locale_2_lang(context)
        if isinstance(exception, commands.NoPrivateMessage):
            await context.respond(self.translations[locale]['msg']['no_dm'], ephemeral=True)
        else:
            bot_info = await self.application_info()
            owner = bot_info.owner
            if owner.dm_channel is None:
                await owner.create_dm()
            traceback_str = ''
            for line in traceback.format_exception(type(exception), exception, exception.__traceback__):
                traceback_str = '{}{}'.format(traceback_str, line)
            if len(traceback_str) < 1998:
                await owner.dm_channel.send('`{}`'.format(traceback_str))
            else:
                self.logger.exception(traceback_str)
            command_line = '/{}'.format(context.interaction.data['name'])
            if 'options' in context.interaction.data.keys():
                for option in context.interaction.data['options']:
                    command_line = '{} {}:{}'.format(command_line, option['name'], option['value'])
            await owner.dm_channel.send('{}:\n{}'.format(context.author, command_line))
            if context.author.dm_channel is None:
                await context.author.create_dm()
            if context.author != owner:
                await context.author.dm_channel.send(self.translations[locale]['error'])

    async def on_interaction(self, interaction: discord.Interaction):
        await self.process_application_commands(interaction)
        if interaction.type == discord.InteractionType.application_command:
            command_line = '/{}'.format(interaction.data['name'])
            if 'options' in interaction.data.keys():
                for option in interaction.data['options']:
                    command_line = '{} {}:{}'.format(command_line, option['name'], option['value'])
            self.logger.info(command_line)

    async def on_command_completion(self, ctx: discord.ext.commands.Context) -> None:
        gc.collect()
        self.logger.info(ctx.message.content)

    def get_channel_type(self, ch_type: str):
        channel_list = []
        cursor = self.guild_cursor
        try:
            cursor.execute('''CREATE TABLE {} (channel_id integer, server_id integer)'''.format(ch_type))
            cursor.execute('''CREATE UNIQUE INDEX {}_id ON {}(channel_id)'''.format(ch_type, ch_type))
            self.guild_db_sync.commit()
        except aiosqlite.OperationalError:
            try:
                channels = cursor.execute('''SELECT channel_id FROM {}'''.format(ch_type))
                channels = channels.fetchall()
                for entry in channels:
                    channel_list.append(entry[0])
            except aiosqlite.OperationalError:
                pass
        return channel_list

    def get_channels(self) -> None:
        self.notifiers.clear()
        self.seasonal_ch.clear()
        self.update_ch.clear()

        self.notifiers = self.get_channel_type('notifiers')
        self.seasonal_ch = self.get_channel_type('seasonal')
        self.update_ch = self.get_channel_type('updates')

    async def register_channel(self, ctx, channel_type: str) -> None:
        cursor = await self.guild_db.cursor()

        await cursor.execute('''INSERT or IGNORE into {} values (?,?)'''.format(channel_type),
                             (ctx.channel.id, ctx.guild.id))
        if channel_type == 'notifiers':
            await cursor.execute('''INSERT or IGNORE into post_settings (channel_id, server_id, server_name) values (?,?,?)''',
                                 (ctx.channel.id, ctx.guild.id, ctx.guild.name))
        await self.guild_db.commit()
        await cursor.close()

        self.get_channels()

    async def remove_channel(self, channel_id: int) -> None:
        cursor = await self.guild_db.cursor()

        await cursor.execute('''DELETE FROM updates WHERE channel_id=?''', (channel_id,))
        await cursor.execute('''DELETE FROM notifiers WHERE channel_id=?''', (channel_id,))
        await cursor.execute('''DELETE FROM post_settings WHERE channel_id=?''', (channel_id,))
        await self.guild_db.commit()
        await cursor.close()

        self.get_channels()

    def guild_lang(self, guild_id: int) -> str:
        cursor = self.guild_cursor
        try:
            cursor.execute('''SELECT lang FROM language WHERE server_id=?''', (guild_id, ))
            lang = cursor.fetchone()
            if len(lang) > 0:
                if lang[0] in self.langs:
                    return lang[0]
                else:
                    return 'en'
            else:
                return 'en'
        except:
            return 'en'

    def guild_prefix(self, guild_id: int) -> list:
        cursor = self.guild_cursor
        try:
            cursor.execute('''SELECT prefix FROM prefixes WHERE server_id=?''', (guild_id, ))
            prefix = cursor.fetchone()
            if len(prefix) > 0:
                return eval(prefix[0])
            else:
                return []
        except:
            return []

    async def update_clans(self) -> None:
        cursor = await self.guild_db.cursor()
        data_cursor = await self.data.bot_data_db.cursor()
        try:
            await data_cursor.execute('''CREATE TABLE clans (clan_name text, clan_id integer)''')
            await data_cursor.execute('''CREATE UNIQUE INDEX clan ON clans(clan_id)''')
            await self.data.bot_data_db.commit()
        except aiosqlite.OperationalError:
            pass
        for server in self.guilds:
            try:
                await cursor.execute('''CREATE TABLE clans (server_name text, server_id integer, clan_name text, clan_id integer)''')
                await cursor.execute('''CREATE UNIQUE INDEX clan ON clans(server_id)''')
                await cursor.execute('''INSERT or IGNORE INTO clans VALUES (?,?,?,?)''', [server.name, server.id, '', 0])
            except aiosqlite.OperationalError:
                try:
                    await cursor.execute('''INSERT or IGNORE INTO clans VALUES (?,?,?,?)''', [server.name, server.id, '', 0])
                except:
                    pass

        await self.guild_db.commit()
        await cursor.close()
        await data_cursor.close()

    async def update_alert_preferences(self) -> None:
        cursor = await self.guild_db.cursor()
        for server in self.guilds:
            try:
                await cursor.execute('''CREATE TABLE lfg_alerts (server_name text, server_id integer, time integer)''')
                await cursor.execute('''CREATE UNIQUE INDEX alert ON lfg_alerts(server_id)''')
                await cursor.execute('''INSERT or IGNORE INTO lfg_alerts VALUES (?,?,?)''', [server.name, server.id, 0])
            except aiosqlite.OperationalError:
                try:
                    await cursor.execute('''INSERT or IGNORE INTO lfg_alerts VALUES (?,?,?)''', [server.name, server.id, 0])
                except:
                    pass

        await self.guild_db.commit()
        await cursor.close()

    async def update_langs(self) -> None:
        cursor = await self.guild_db.cursor()
        for server in self.guilds:
            try:
                await cursor.execute('''CREATE TABLE language (server_id integer, lang text, server_name text)''')
                await cursor.execute('''CREATE UNIQUE INDEX lang ON language(server_id)''')
                await cursor.execute('''INSERT or IGNORE INTO language VALUES (?,?,?)''', [server.id, 'en', server.name])
            except aiosqlite.OperationalError:
                try:
                    await cursor.execute('''ALTER TABLE language ADD COLUMN server_name text''')
                except aiosqlite.OperationalError:
                    try:
                        await cursor.execute('''INSERT or IGNORE INTO language VALUES (?,?,?)''',
                                                  [server.id, 'en', server.name])
                    except:
                        pass
            try:
                await cursor.execute('''UPDATE language SET server_name=? WHERE server_id=?''',
                                          (server.name, server.id))
            except:
                pass

        await self.guild_db.commit()
        await cursor.close()

        await self.update_clans()

    async def update_prefixes(self) -> None:
        cursor = await self.guild_db.cursor()
        for server in self.guilds:
            try:
                await cursor.execute('''CREATE TABLE prefixes (server_id integer, prefix text, server_name text)''')
                await cursor.execute('''CREATE UNIQUE INDEX prefix ON prefixes(server_id)''')
                await cursor.execute('''INSERT or IGNORE INTO prefixes VALUES (?,?,?)''', [server.id, '[\'?\']', server.name])
            except aiosqlite.OperationalError:
                try:
                    await cursor.execute('''INSERT or IGNORE INTO prefixes VALUES (?,?,?)''',
                                              [server.id, '[]', server.name])
                except:
                    pass
            try:
                await cursor.execute('''UPDATE prefixes SET server_name=? WHERE server_id=?''',
                                          (server.name, server.id))
            except:
                pass

        await self.guild_db.commit()
        await cursor.close()

        await self.update_clans()

    async def update_history(self) -> None:
        cursor = await self.guild_db.cursor()
        try:
            await cursor.execute('''CREATE TABLE history ( server_name text, server_id integer, channel_id integer)''')
            await cursor.execute('''CREATE UNIQUE INDEX hist ON history(channel_id)''')
        except aiosqlite.OperationalError:
            pass

        try:
            await cursor.execute('''CREATE TABLE post_settings ( server_name text, server_id integer, channel_id integer)''')
            await cursor.execute('''CREATE UNIQUE INDEX post_prefs ON post_settings(channel_id)''')
        except aiosqlite.OperationalError:
            pass

        for channel_id in self.notifiers:
            try:
                channel = self.get_channel(channel_id)
                if channel is not None:
                    init_values = [channel.guild.name, channel.guild.id, channel_id]
                    await cursor.execute("INSERT or IGNORE INTO history (server_name, server_id, channel_id) VALUES (?,?,?)", init_values)
                    await cursor.execute("INSERT or IGNORE INTO post_settings (server_name, server_id, channel_id) VALUES (?,?,?)", init_values)
                    await self.guild_db.commit()
            except aiosqlite.OperationalError:
                pass
        await cursor.close()

    async def update_guild_timezones(self) -> None:
        cursor = await self.guild_db.cursor()
        for server in self.guilds:
            try:
                await cursor.execute('''CREATE TABLE timezones (server_id integer, server_name text, timezone text)''')
                await cursor.execute('''CREATE UNIQUE INDEX timezone ON timezones(server_id)''')
                await cursor.execute('''INSERT or IGNORE INTO timezones (server_id, server_name) VALUES (?,?)''', [server.id, server.name])
            except aiosqlite.OperationalError:
                pass
            try:
                await cursor.execute('''INSERT or IGNORE INTO timezones (server_id, server_name) VALUES (?,?)''',
                                     [server.id, server.name])
            except aiosqlite.OperationalError:
                pass

        await self.guild_db.commit()
        await cursor.close()

    async def get_guild_timezone(self, guild_id: int) -> str:
        if guild_id is None:
            return 'UTC+03:00'

        cursor = await self.guild_db.cursor()

        data = await cursor.execute('''SELECT timezone FROM timezones WHERE server_id=?''', (guild_id,))
        data = await data.fetchone()

        await cursor.close()
        if data[0] is None:
            return 'UTC+03:00'
        else:
            return data[0]

    async def guild_timezone_is_set(self, guild_id: int) -> bool:
        if guild_id is None:
            return False

        cursor = await self.guild_db.cursor()

        data = await cursor.execute('''SELECT timezone FROM timezones WHERE server_id=?''', (guild_id,))
        data = await data.fetchone()

        await cursor.close()
        if data[0] is None:
            return False
        else:
            return True

    async def universal_update(self, getter: Callable, name: str, time_to_delete: float = None,
                               channels: List[int] = None, post: bool = True, get: bool = True,
                               forceget: bool = False) -> None:
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

    async def post_embed_to_channel(self, upd_type: str, src_dict: dict, time_to_delete: float,
                                    channel_id: int) -> list:
        # delay = random.uniform(0, 180)
        delay = 0
        # await asyncio.sleep(delay)
        # self.logger.info('ws limit status for {} in {}: {}'.format(upd_type, channel_id, self.is_ws_ratelimited()))
        cursor = await self.guild_db.cursor()
        if channel_id == 647890554943963136:
            self.logger.info('{} has got the db cursor'.format(upd_type))
        channel = self.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(channel_id)
            except discord.Forbidden:
                frameinfo = getframeinfo(currentframe())
                return [channel_id, 'unable to fetch the channel ({})'.format(frameinfo.lineno + 1)]
            except discord.NotFound:
                frameinfo = getframeinfo(currentframe())
                return [channel_id, 'NotFound while fetching the channel ({})'.format(frameinfo.lineno + 1)]
            except discord.HTTPException:
                frameinfo = getframeinfo(currentframe())
                return [channel_id, 'HTTPexception while fetching the channel ({})'.format(frameinfo.lineno + 1)]
            except discord.InvalidData:
                frameinfo = getframeinfo(currentframe())
                return [channel_id, 'InvalidData while fetching the channel ({})'.format(frameinfo.lineno + 1)]
            # frameinfo = getframeinfo(currentframe())
            # return [channel_id, 'channel id None ({})'.format(frameinfo.lineno + 1)]
        server = channel.guild
        if not channel.permissions_for(server.me).send_messages:
            frameinfo = getframeinfo(currentframe())
            return [channel_id, 'no permission to send messages ({})'.format(frameinfo.lineno + 1)]
        lang = self.guild_lang(channel.guild.id)
        # print('delay is {}'.format(delay))
        if channel_id == 647890554943963136:
            self.logger.info('{} has got the channel'.format(upd_type))

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
        if channel_id == 647890554943963136:
            self.logger.info('{} has created the embed'.format(upd_type))

        hist = 0
        try:
            last = await cursor.execute('''SELECT {} FROM history WHERE channel_id=?'''.format(upd_type),
                                        (channel_id,))
            last = await last.fetchone()
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
                    await cursor.execute(
                        "INSERT or IGNORE INTO history (server_name, server_id, channel_id) VALUES (?,?,?)", init_values)
                    # self.guild_db.commit()
                except aiosqlite.OperationalError:
                    pass

        except aiosqlite.OperationalError:
            try:
                if type(src_dict[lang][upd_type]) == list:
                    await cursor.execute(
                        '''ALTER TABLE history ADD COLUMN {} text'''.format(upd_type))
                else:
                    await cursor.execute('''ALTER TABLE history ADD COLUMN {} INTEGER'''.format(upd_type))
                # self.guild_db.commit()
            except aiosqlite.OperationalError:
                await self.update_history()
        if channel_id == 647890554943963136:
            self.logger.info('{} has got the history'.format(upd_type))

        try:
            last = await cursor.execute('''SELECT {} FROM post_settings WHERE channel_id=?'''.format(upd_type),
                                        (channel_id,))
            last = await last.fetchone()
        except aiosqlite.OperationalError:
            await cursor.execute('''ALTER TABLE post_settings ADD COLUMN {} INTEGER'''.format(upd_type))
            await self.guild_db.commit()
            last = None

        if last is not None:
            if len(last) > 0:
                if last[0] is not None:
                    last = last[0]
            if last == 0:
                frameinfo = getframeinfo(currentframe())
                return [channel_id, 'Aborted due to post preferences ({})'.format(frameinfo.lineno + 1)]

        if channel_id == 647890554943963136:
            self.logger.info('{} fetching history'.format(upd_type))
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
                        except discord.HTTPException as e:
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
                except discord.Forbidden:
                    pass
                except discord.NotFound:
                    pass
                except discord.HTTPException as e:
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
        if channel_id == 647890554943963136:
            self.logger.info('{} deletion is complete'.format(upd_type))
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
                    except discord.Forbidden:
                        pass
                    except discord.HTTPException:
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
            if channel_id == 647890554943963136:
                self.logger.info('{} has sent the message {}'.format(upd_type, message.id))
            hist = message.id
            if channel.type == discord.ChannelType.news:
                try:
                    # await asyncio.sleep(delay)
                    await message.publish()
                except discord.Forbidden:
                    pass
                except discord.HTTPException:
                    pass

        await cursor.execute('''UPDATE history SET {}=? WHERE channel_id=?'''.format(upd_type),
                                  (str(hist), channel_id))
        await self.guild_db.commit()

        await cursor.close()

        frameinfo = getframeinfo(currentframe())
        return [channel_id, 'posted ({})'.format(frameinfo.lineno + 1)]

    async def post_embed(self, upd_type: str, src_dict: dict, time_to_delete: float, channels: List[int]) -> None:
        responses = []
        for channel_id in channels:
            try:
                resp = await self.post_embed_to_channel(upd_type, src_dict, time_to_delete, channel_id)
                # if channel_id == 1028023408044281876:
                #     await self.dm_owner('{}: {}'.format(upd_type, resp[1]))
                responses.append(resp[1])
            except discord.Forbidden:
                responses.append("discord.Forbidden")
            except discord.HTTPException as e:
                # responses.append([channel_id, "discord.HTTPException"])
                responses.append("discord.HTTPException")
                # if channel_id == 1028023408044281876:
                #     await self.dm_owner('{}: {}'.format(upd_type, "discord.HTTPException"))
                bot_info = await self.application_info()
                owner = bot_info.owner
                if owner.dm_channel is None:
                    await owner.create_dm()
                traceback_str = ''
                for line in traceback.format_exception(type(e), e, e.__traceback__):
                    traceback_str = '{}{}'.format(traceback_str, line)
                if len(traceback_str) < 1998:
                    await owner.dm_channel.send('`{}`'.format(traceback_str))
                else:
                    self.logger.exception(traceback_str)
                channel = self.get_channel(channel_id)
                lang = self.guild_lang(channel.guild.id)
                self.logger.exception('Embed info {}\n{}'.format(lang, src_dict[lang][upd_type]))
            except Exception as e:
                # responses.append([channel_id, "Exception"])
                responses.append("Exception")
                # if channel_id == 1028023408044281876:
                #     await self.dm_owner('{}: {}'.format(upd_type, "Exception"))
                traceback_str = ''
                for line in traceback.format_exception(type(e), e, e.__traceback__):
                    traceback_str = '{}{}'.format(traceback_str, line)
                bot_info = await self.application_info()
                owner = bot_info.owner
                if owner.dm_channel is None:
                    await owner.create_dm()
                await owner.dm_channel.send('`{}`'.format(traceback_str))
            # self.sched.add_job(self.post_embed_to_channel, misfire_grace_time=86400, args=[upd_type, src_dict, time_to_delete, channel_id])
            # task = asyncio.ensure_future(self.post_embed_to_channel(upd_type, src_dict, time_to_delete, channel_id))
            # tasks.append(task)

        # responses = await asyncio.gather(*tasks)

        elements = Counter(responses)
        statuses = []
        response = []
        for key, value in elements.items():
            statuses.append([key, "{:.2f} %".format(value / len(responses) * 100)])
            response.append({
                'name': key,
                'description': statuses[-1][1]
            })
        if len(channels) > 1 and self.args.production:
            await self.data.write_to_db('status', upd_type, response, name=upd_type, template='table_items.html', annotations=[datetime.utcnow().isoformat(timespec='seconds')])
        if self.update_status:
            msg = '{} is posted'.format(upd_type)
            statuses = tabulate(statuses, tablefmt='simple', colalign=('left', 'left'), headers=['status', 'percentage'])
            # statuses = tabulate(responses, tablefmt='simple', colalign=('left', 'left'), headers=['channel', 'status'])
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

    async def post_updates(self, version: str, content: str, lang: str, attachments: List[discord.Attachment] = []) -> None:
        msg = '`{} v{}`\n{}'.format(self.user.name, version, content)
        files = []
        for attachment in attachments:
            fp = io.BytesIO()
            await attachment.save(fp)
            files.append(discord.File(fp, filename=attachment.filename))
        for server in self.guilds:
            if (lang == self.guild_lang(server.id) and lang == 'ru') or (lang != 'ru' and self.guild_lang(server.id) != 'ru'):
                for channel in server.channels:
                    if channel.id in self.update_ch:
                        try:
                            if channel.permissions_for(server.me).attach_files:
                                message = await channel.send(msg, files=files)
                            else:
                                message = await channel.send(msg)
                            if channel.type == discord.ChannelType.news:
                                try:
                                    await message.publish()
                                except discord.Forbidden:
                                    pass
                        except discord.Forbidden:
                            pass

    async def update_metrics(self) -> None:
        cursor = await self.data.bot_data_db.cursor()
        clan_ids_c = await cursor.execute('''SELECT clan_id FROM clans''')
        clan_ids_c = await clan_ids_c.fetchall()
        clan_ids = []
        for clan_id in clan_ids_c:
            clan_ids.append(clan_id[0])
        clan_ids = list(set(clan_ids))
        await self.data.update_clan_metrics(clan_ids)
        # await self.data.get_clan_leaderboard(clan_ids, 1572939289, 10)
        await cursor.close()

    async def update_metric_list(self) -> None:
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

    async def lfg_alerts_enabled(self, guild_id: int) -> bool:
        cursor = await self.guild_db.cursor()

        try:
            await cursor.execute('''SELECT time FROM lfg_alerts WHERE server_id=?''', (guild_id,))
            time = await cursor.fetchone()

            if len(time) > 0:
                return bool(time[0])
            else:
                return False
        except aiosqlite.OperationalError:
            await cursor.close()
            return False

    async def get_lfg_alert(self, guild_id: int) -> int:
        cursor = await self.guild_db.cursor()

        try:
            await cursor.execute('''SELECT time FROM lfg_alerts WHERE server_id=?''', (guild_id,))
            time = await cursor.fetchone()

            if len(time) > 0:
                return time[0]
            else:
                return 0
        except aiosqlite.OperationalError:
            await cursor.close()
            return 0

    def start_up(self) -> None:
        self.get_args()
        token = self.api_data['token']
        self.remove_command('help')
        for cog in self.cog_list:
            self.load_extension(cog)
        self.i18n.localize_commands()
        print('Ready to run')
        self.run(token)


def get_prefix(client, message):
    prefixes = ['?']
    if message.guild:
        prefixes = client.guild_prefix(message.guild.id)

    return commands.when_mentioned_or(*prefixes)(client, message)
