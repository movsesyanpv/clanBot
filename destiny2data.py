import json
import time
from urllib.parse import quote
import pydest
from bs4 import BeautifulSoup
from bungied2auth import BungieOAuth
from datetime import datetime, timezone, timedelta
from dateutil.parser import *
import aiohttp
import aiosqlite
import matplotlib.pyplot as plt
import csv
import codecs
import aiomysql
import mariadb
import asyncio
import tracemalloc
import warnings

from typing import Optional, Union, List

from lstorations import lost_sector_order, loot_order


class D2data:
    api_data_file = open('api.json', 'r')
    api_data = json.loads(api_data_file.read())
    destiny = ''

    cache_db = ''

    data_db = ''

    bot_data_db = ''

    icon_prefix = "https://www.bungie.net"

    token = {}

    headers = {}

    data = {}

    data_ready = False

    wait_codes = [1672]
    max_retries = 10

    vendor_params = {
        'components': '400,401,402,302,304,306,310,305'
    }

    activities_params = {
        'components': '204'
    }

    record_params = {
        "components": "900,700"
    }

    metric_params = {
        "components": "1100"
    }

    is_oauth = False

    char_info = {}

    oauth = ''

    data_pool: aiomysql.Pool

    def __init__(self, translations, lang, is_oauth, prod, context, loop=None, **options):
        super().__init__(**options)
        self.translations = translations
        self.is_oauth = is_oauth
        for locale in lang:
            self.data[locale] = json.loads(open('d2data.json', 'r').read())
            self.data[locale]['api_is_down'] = {
                'fields': [{
                    'inline': True,
                    'name': translations[locale]['msg']['noapi'],
                    'value': translations[locale]['msg']['later']
                }],
                'color': 0xff0000,
                'type': "rich",
                'title': translations[locale]['msg']['error'],
            }
            self.data[locale]['api_maintenance'] = {
                'fields': [{
                    'inline': True,
                    'name': translations[locale]['msg']['maintenance'],
                    'value': translations[locale]['msg']['later']
                }],
                'color': 0xff0000,
                'type': "rich",
                'title': translations[locale]['msg']['error'],
            }
        if prod:
            self.oauth = BungieOAuth(self.api_data['id'], self.api_data['secret'], context=context, host='0.0.0.0',
                                     port='4200')
        else:
            self.oauth = BungieOAuth(self.api_data['id'], self.api_data['secret'], host='localhost', port='4200')
        self.session = aiohttp.ClientSession()
        asyncio.run(self.set_up_cache(lang))
        asyncio.run(self.load_data(lang))
        try:
            self.cache_pool = mariadb.ConnectionPool(pool_name='cache', pool_size=10, pool_reset_connection=False,
                                                     host=self.api_data['db_host'], user=self.api_data['cache_login'],
                                                     password=self.api_data['pass'], port=self.api_data['db_port'],
                                                     database=self.api_data['cache_name'])
            # self.cache_pool.pool_reset_connection = True
        except mariadb.ProgrammingError:
            pass
        # self.cache_db.auto_reconnect = True
        warnings.filterwarnings('ignore', module=r"aiomysql")
        self.ev_loop = loop
        asyncio.run(self.set_up_data(loop))
        # self.data_db.auto_reconnect = True

    async def set_up_cache(self, lang: List[str]) -> None:
        self.cache_db = await aiosqlite.connect('cache.db')
        cache_cursor = await self.cache_db.cursor()
        try:
            await cache_cursor.execute(
                '''CREATE TABLE cache (id text, expires integer, json text, timestamp text);''')
            await cache_cursor.execute('''CREATE UNIQUE INDEX cache_id ON cache(id)''')
            await self.cache_db.commit()
            await cache_cursor.close()
        except aiosqlite.OperationalError:
            pass
        await cache_cursor.close()

        self.bot_data_db = await aiosqlite.connect('data.db')
        data_cursor = await self.bot_data_db.cursor()
        for locale in lang:
            try:
                await data_cursor.execute('''CREATE TABLE `{}` (id text, json text, timestamp text)'''.format(locale))
                await data_cursor.execute('''CREATE UNIQUE INDEX data_id_{} on `{}`(id)'''.format(locale.replace('-', '_'), locale))
                await self.bot_data_db.commit()
            except aiosqlite.OperationalError:
                pass
        try:
            await data_cursor.execute('''CREATE TABLE playermetrics (membershipId text, name text, timestamp text)''')
            await data_cursor.execute('''CREATE UNIQUE INDEX player_id on playermetrics(membershipId)''')
            await self.bot_data_db.commit()
        except aiosqlite.OperationalError:
            pass
        await data_cursor.close()

    async def set_up_data(self, loop) -> None:
        try:
            self.data_pool = await aiomysql.create_pool(minsize=0, maxsize=0, host=self.api_data['db_host'],
                                                        user=self.api_data['cache_login'],
                                                        password=self.api_data['pass'], port=self.api_data['db_port'],
                                                        db=self.api_data['data_db'], pool_recycle=60, loop=loop)
            # self.data_pool.pool_reset_connection = True
        except aiomysql.ProgrammingError:
            pass

    async def get_chars(self) -> None:
        platform = 0
        membership_id = ''
        try:
            char_file = open('char.json', 'r')
            self.char_info = json.loads(char_file.read())
        except FileNotFoundError:
            membership_url = 'https://www.bungie.net/platform/User/GetMembershipsForCurrentUser/'
            search_resp = await self.session.get(url=membership_url, headers=self.headers)
            search_json = await search_resp.json()
            self.char_info['membershipid'] = search_json['Response']['primaryMembershipId']
            membership_id = search_json['Response']['primaryMembershipId']
            for membership in search_json['Response']['destinyMemberships']:
                if membership['membershipId'] == self.char_info['membershipid']:
                    platform = membership['membershipType']
            self.char_info['platform'] = platform

            char_search_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/'.format(platform, membership_id)
            char_search_params = {
                'components': '200'
            }
            char_search_resp = await self.session.get(char_search_url, params=char_search_params, headers=self.headers)
            char_search_json = await char_search_resp.json()
            chars = char_search_json['Response']['characters']['data']
            char_ids = []
            for key in sorted(chars.keys()):
                char_ids.append(chars[key]['characterId'])
            self.char_info['charid'] = char_ids

            char_file = open('char.json', 'w')
            char_file.write(json.dumps(self.char_info))

    async def load_data(self, lang):
        cursor = await self.bot_data_db.cursor()

        try:
            for locale in lang:
                data = await cursor.execute('''SELECT * from `{}`'''.format(locale))
                data = await data.fetchall()
                for entry in data:
                    self.data[locale][entry[0]] = json.loads(entry[1])
            self.data_ready = True
        except:
            pass

        await cursor.close()

    async def refresh_token(self, re_token: str) -> None:
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        params = {
            'grant_type': 'refresh_token',
            'refresh_token': re_token,
            'client_id': self.api_data['id'],
            'client_secret': self.api_data['secret']
        }
        r = await self.session.post('https://www.bungie.net/platform/app/oauth/token/', data=params, headers=headers)
        while not r:
            print("re_token get error", json.dumps(r.json(), indent=4, sort_keys=True) + "\n")
            r = await self.session.post('https://www.bungie.net/platform/app/oauth/token/', data=params,
                                        headers=headers)
            if not r:
                r_json = await r.json()
                if not r_json['error_description'] == 'DestinyThrottledByGameServer':
                    break
            await asyncio.sleep(5)
        if not r:
            r_json = await r.json()
            print("re_token get error", json.dumps(r_json, indent=4, sort_keys=True) + "\n")
            return
        resp = await r.json()

        try:
            token = {
                'refresh': resp['refresh_token'],
                'expires': time.time() + resp['refresh_expires_in']
            }
            token_file = open('token.json', 'w')
            token_file.write(json.dumps(token))

            self.headers = {
                'X-API-Key': self.api_data['key'],
                'Authorization': 'Bearer ' + resp['access_token']
            }
        except KeyError:
            pass
        self.destiny = pydest.Pydest(self.api_data['key'])

    async def get_bungie_json(self, name: str, url: str, params: Optional[dict] = None, lang: Optional[str] = None,
                              string: Optional[str] = None, change_msg: bool = True, is_get: bool = True,
                              body: Optional[dict] = None) -> Union[dict, None]:

        async def request(url, params, headers, is_get, json=None):
            if is_get:
                resp = await self.session.get(url, params=params, headers=headers)
            else:
                resp = await self.session.post(url, params=params, headers=headers, json=json)
            return resp

        if lang is None:
            lang = list(self.data.keys())
            lang_str = ''
        else:
            lang_str = lang
        if string is None:
            string = str(name)
        try:
            resp = await request(url, params, self.headers, is_get, body)
        except:
            if change_msg:
                for locale in lang:
                    self.data[locale][name] = self.data[locale]['api_is_down']
            return False
        try:
            resp_code = await resp.json()
            resp_code = resp_code['ErrorCode']
        except KeyError:
            resp_code = 1
        except json.decoder.JSONDecodeError:
            if change_msg:
                for locale in lang:
                    self.data[locale][name] = self.data[locale]['api_is_down']
            resp.close()
            return False
        except aiohttp.ContentTypeError:
            if change_msg:
                for locale in lang:
                    self.data[locale][name] = self.data[locale]['api_is_down']
            resp.close()
            return False
        print('getting {} {}'.format(string, lang_str))
        curr_try = 2
        while resp_code in self.wait_codes and curr_try <= self.max_retries:
            print('{}, attempt {}'.format(resp_code, curr_try))
            resp = await request(url, params, self.headers, is_get, body)
            try:
                resp_code = await resp.json()
                resp_code = resp_code['ErrorCode']
            except aiohttp.ContentTypeError:
                resp_code = 1672
            if resp_code == 5:
                if change_msg:
                    for locale in lang:
                        self.data[locale][name] = self.data[locale]['api_maintenance']
                curr_try -= 1
            curr_try += 1
            await asyncio.sleep(5)
        if not resp:
            try:
                resp_code = await resp.json()
            except aiohttp.ContentTypeError:
                if change_msg:
                    for locale in lang:
                        self.data[locale][name] = self.data[locale]['api_is_down']
                resp.close()
                return False
            resp_code = resp_code['ErrorCode']
            if resp_code in [5, 1618]:
                if change_msg:
                    for locale in lang:
                        self.data[locale][name] = self.data[locale]['api_maintenance']
                resp.close()
                return False
            print("{} get error".format(name), json.dumps(resp.json(), indent=4, sort_keys=True) + "\n")
            if change_msg:
                for locale in lang:
                    self.data[locale][name] = self.data[locale]['api_is_down']
            resp.close()
            return False
        else:
            try:
                resp_code = await resp.json()
            except aiohttp.ContentTypeError:
                if change_msg:
                    for locale in lang:
                        self.data[locale][name] = self.data[locale]['api_is_down']
                resp.close()
                return False
            if 'ErrorCode' in resp_code.keys():
                resp_code = resp_code['ErrorCode']
                if resp_code == 5:
                    if change_msg:
                        for locale in lang:
                            self.data[locale][name] = self.data[locale]['api_maintenance']
                    resp.close()
                    return False
            else:
                for suspected_season in resp_code:
                    if 'seasonNumber' in resp_code[suspected_season].keys():
                        resp.close()
                        return resp_code
            resp_code = await resp.json()
            if 'Response' not in resp_code.keys():
                if change_msg:
                    for locale in lang:
                        self.data[locale][name] = self.data[locale]['api_is_down']
                resp.close()
                return False
        resp_json = await resp.json()
        resp.close()
        return resp_json

    async def get_vendor_sales(self, lang: str, vendor_resp: dict, cats: List[int], exceptions: list = []) -> list:
        embed_sales = []
        data_sales = []

        vendor_json = vendor_resp
        tess_sales = vendor_json['Response']['sales']['data']
        n_order = 0
        for key in cats:
            item = tess_sales[str(key)]
            item_hash = item['itemHash']
            if item_hash not in exceptions:
                definition = 'DestinyInventoryItemDefinition'
                item_resp = await self.destiny.decode_hash(item_hash, definition, language=lang)
                item_name_list = item_resp['displayProperties']['name'].split()
                item_name = ' '.join(item_name_list)
                costs = []
                if len(item['costs']) > 0:
                    cost_line = '{}: '.format(self.translations[lang]['msg']['cost'])
                    for cost in item['costs']:
                        currency = cost
                        currency_resp = await self.destiny.decode_hash(currency['itemHash'], definition, language=lang)

                        currency_cost = str(currency['quantity'])
                        currency_item = currency_resp['displayProperties']['name']
                        currency_icon = currency_resp['displayProperties']['icon']
                        cost_line = '{}{} {}\n'.format(cost_line, currency_cost, currency_item.capitalize())
                        costs.append({
                            'currency_name': currency_item,
                            'currency_icon': currency_icon,
                            'cost': currency_cost
                        })
                else:
                    currency_cost = 'N/A\n'
                    currency_item = ''
                    currency_icon = ''
                    cost_line = currency_cost
                    costs.append({
                        'currency_name': currency_item,
                        'currency_icon': currency_icon,
                        'cost': currency_cost
                    })
                if 'screenshot' in item_resp.keys():
                    screenshot = '<img alt="Screenshot" class="screenshot_hover" src="https://bungie.net{}" ' \
                                 'loading="lazy">'.format(item_resp['screenshot'])
                else:
                    screenshot = ''

                stats = []
                perks = []
                if 'itemComponents' in vendor_json['Response']:
                    if str(item['vendorItemIndex']) in vendor_json['Response']['itemComponents']['stats']['data'].keys():
                        stats_json = \
                        vendor_json['Response']['itemComponents']['stats']['data'][str(item['vendorItemIndex'])]['stats']
                        for stat in stats_json:
                            value = stats_json[stat]['value']
                            if value == 0:
                                continue
                            stat_def = await self.destiny.decode_hash(stats_json[stat]['statHash'], 'DestinyStatDefinition',
                                                                      language=lang)
                            stats.append({
                                'name': stat_def['displayProperties']['name'],
                                'value': stats_json[stat]['value']
                            })

                    if str(item['vendorItemIndex']) in vendor_json['Response']['itemComponents']['perks']['data'].keys():
                        try:
                            plugs_json = vendor_json['Response']['itemComponents']['reusablePlugs']['data'][
                                str(item['vendorItemIndex'])]['plugs']
                            plug_str = 'plugItemHash'
                        except KeyError:
                            plugs_json = \
                            vendor_json['Response']['itemComponents']['sockets']['data'][str(item['vendorItemIndex'])][
                                'sockets']
                            plug_str = 'plugHash'
                        for perk in plugs_json:
                            plug = []
                            if type(perk) == str:
                                perk_list = plugs_json[perk]
                            elif type(perk) == dict:
                                perk_list = [perk]
                            else:
                                raise TypeError
                            for perk_dict in perk_list:
                                if plug_str in perk_dict.keys():
                                    perk_def = await self.destiny.decode_hash(perk_dict[plug_str],
                                                                              'DestinyInventoryItemDefinition',
                                                                              language=lang)
                                    if 'name' in perk_def['displayProperties'].keys() and 'icon' in perk_def[
                                        'displayProperties'].keys():
                                        plug.append({
                                            'name': perk_def['displayProperties']['name'],
                                            'icon': 'https://bungie.net{}'.format(perk_def['displayProperties']['icon'])
                                        })
                            perks.append(plug)

                cost_line = cost_line[:-1]
                item_data = {
                    'inline': True,
                    'name': item_name.capitalize(),
                    'value': cost_line
                }
                data_sales.append({
                    'id': '{}_{}_{}'.format(item['itemHash'], key, n_order),
                    'icon': item_resp['displayProperties']['icon'],
                    'name': item_name.capitalize(),
                    'description': "{}: {} {}".format('Цена', currency_cost,
                                                currency_item.capitalize()),
                    'tooltip_id': '{}_{}_{}_tooltip'.format(item['itemHash'], key, n_order),
                    'hash': item['itemHash'],
                    'screenshot': screenshot,
                    'costs': costs,
                    'stats': stats,
                    'perks': perks
                })
                embed_sales.append(item_data)
                n_order += 1
        return [embed_sales, data_sales]

    async def get_featured_bd(self, langs: List[str], forceget: bool = False) -> None:
        tess_resp = []
        for char in self.char_info['charid']:
            tess_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/3361454721/'. \
                format(self.char_info['platform'], self.char_info['membershipid'], char)
            resp = await self.get_cached_json('eververse_{}'.format(char), 'featured_bd', tess_url, self.vendor_params,
                                              string='featured bright dust for {}'.format(char), force=forceget)
            if not resp:
                return
            tess_resp.append(resp)
            resp_time = resp['timestamp']

        for lang in langs:
            tess_def = await self.destiny.decode_hash(3361454721, 'DestinyVendorDefinition', language=lang)
            self.data[lang]['featured_bd'] = {
                'thumbnail': {
                    'url': self.icon_prefix + '/common/destiny2_content/icons/30c6cc828d7753bcca72748ba2aa83d6.png'
                },
                'fields': [],
                'color': 0x38479F,
                'type': "rich",
                'title': self.translations[lang]['msg']['featured_bd'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']}
            }

            tmp_fields = []
            for resp in tess_resp:
                resp_json = resp
                tess_cats = resp_json['Response']['categories']['data']['categories']
                items_to_get = tess_cats[3]['itemIndexes']
                sales = await self.get_vendor_sales(lang, resp, items_to_get,
                                                    [353932628, 3260482534, 3536420626, 3187955025,
                                                    2638689062])
                tmp_fields = tmp_fields + sales[0]
                await self.write_to_db(lang, 'featured_bright_dust_items', sales[1])

            for i in range(0, len(tmp_fields)):
                if tmp_fields[i] not in tmp_fields[i + 1:]:
                    self.data[lang]['featured_bd']['fields'].append(tmp_fields[i])
            self.data[lang]['featured_bd']['timestamp'] = resp_time

    async def get_bd(self, langs: List[str], forceget: bool = False) -> None:
        tess_resp = []
        for char in self.char_info['charid']:
            tess_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/3361454721/'. \
                format(self.char_info['platform'], self.char_info['membershipid'], char)
            resp = await self.get_cached_json('eververse_{}'.format(char), 'bd', tess_url, self.vendor_params,
                                              string='bright dust for {}'.format(char), force=forceget)
            if not resp:
                return
            tess_resp.append(resp)
            resp_time = resp['timestamp']

        for lang in langs:
            tess_def = await self.destiny.decode_hash(3361454721, 'DestinyVendorDefinition', language=lang)
            self.data[lang]['bd'] = {
                'thumbnail': {
                    'url': self.icon_prefix + '/common/destiny2_content/icons/30c6cc828d7753bcca72748ba2aa83d6.png'
                },
                'fields': [],
                'color': 0x38479F,
                'type': "rich",
                'title': self.translations[lang]['msg']['bd'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']}
            }

            tmp_fields = []
            for resp in tess_resp:
                resp_json = resp
                tess_cats = resp_json['Response']['categories']['data']['categories']
                items_to_get = tess_cats[8]['itemIndexes'] + tess_cats[10]['itemIndexes']
                sales = await self.get_vendor_sales(lang, resp, items_to_get,
                                                    [353932628, 3260482534, 3536420626, 3187955025,
                                                    2638689062])
                tmp_fields = tmp_fields + sales[0]
                await self.write_to_db(lang, 'bright_dust_items', sales[1])

            for i in range(0, len(tmp_fields)):
                if tmp_fields[i] not in tmp_fields[i + 1:]:
                    self.data[lang]['bd']['fields'].append(tmp_fields[i])
            self.data[lang]['bd']['timestamp'] = resp_time

    async def get_featured_silver(self, langs: List[str], forceget: bool = False) -> None:
        tess_resp = []
        for char in self.char_info['charid']:
            tess_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/3361454721/'. \
                format(self.char_info['platform'], self.char_info['membershipid'], char)
            resp = await self.get_cached_json('eververse_{}'.format(char), 'silver', tess_url, self.vendor_params,
                                              string='silver for {}'.format(char), force=forceget)
            if not resp:
                return
            tess_resp.append(resp)
            resp_time = resp['timestamp']

        for lang in langs:
            tess_def = await self.destiny.decode_hash(3361454721, 'DestinyVendorDefinition', language=lang)
            self.data[lang]['silver'] = {
                'thumbnail': {
                    'url': self.icon_prefix + '/common/destiny2_content/icons/30c6cc828d7753bcca72748ba2aa83d6.png'
                },
                'fields': [],
                'color': 0x38479F,
                'type': "rich",
                'title': self.translations[lang]['msg']['silver'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']}
            }

            tmp_fields = []
            for resp in tess_resp:
                resp_json = resp
                tess_cats = resp_json['Response']['categories']['data']['categories']
                items_to_get = tess_cats[2]['itemIndexes']
                sales = await self.get_vendor_sales(lang, resp, items_to_get, [827183327])
                tmp_fields = tmp_fields + sales[0]
                await self.write_to_db(lang, 'featured_silver', sales[1])

            for i in range(0, len(tmp_fields)):
                if tmp_fields[i] not in tmp_fields[i + 1:]:
                    self.data[lang]['silver']['fields'].append(tmp_fields[i])
            self.data[lang]['silver']['timestamp'] = resp_time

    async def get_global_alerts(self, langs: List[str], forceget: bool = False) -> None:
        alert_url = 'https://www.bungie.net/Platform/GlobalAlerts/'
        alert_json = await self.get_bungie_json('alerts', alert_url, {}, '')
        if not alert_json:
            return

        for lang in langs:
            self.data[lang]['alerts'].clear()
            for alert in alert_json['Response']:
                alert_embed = {
                    'color': 0xff0000,
                    'type': "rich",
                    'description': alert['AlertHtml'],
                    'timestamp': '{}+00:00'.format(alert['AlertTimestamp'][:-1]),
                    'author': {
                        'name': 'Bungie Help',
                        'url': alert['AlertLink'],
                        'icon_url': 'https://pbs.twimg.com/profile_images/887332604143312896/ydVDSfjE_400x400.jpg'
                    }
                }
                self.data[lang]['alerts'].append(alert_embed)

    async def get_season_start(self) -> datetime:
        manifest_url = 'https://www.bungie.net/Platform/Destiny2/Manifest/'
        manifest_json = await self.get_bungie_json('default', manifest_url, {}, '')
        season_url = 'https://www.bungie.net{}'.format(
            manifest_json['Response']['jsonWorldComponentContentPaths']['en']['DestinySeasonDefinition'])
        season_json = await self.get_bungie_json('default', season_url, {}, '')

        for season in season_json:
            try:
                start = isoparse(season_json[season]['startDate'])
                end = isoparse(season_json[season]['endDate'])
                if start <= datetime.now(tz=timezone.utc) <= end:
                    current_season = season
                    return start
            except KeyError:
                if 'startDate' in season_json[season].keys() and 'endDate' not in season_json[season].keys():
                    return isoparse(season_json[season]['startDate'])
                pass

    async def get_season_number(self) -> int:
        manifest_url = 'https://www.bungie.net/Platform/Destiny2/Manifest/'
        manifest_json = await self.get_bungie_json('default', manifest_url, {}, '')
        season_url = 'https://www.bungie.net{}'.format(
            manifest_json['Response']['jsonWorldComponentContentPaths']['en']['DestinySeasonDefinition'])
        season_json = await self.get_bungie_json('default', season_url, {}, '')

        for season in season_json:
            try:
                start = isoparse(season_json[season]['startDate'])
                end = isoparse(season_json[season]['endDate'])
                if start <= datetime.now(tz=timezone.utc) <= end:
                    return season_json[season]['seasonNumber']
            except KeyError:
                if 'startDate' in season_json[season].keys() and 'endDate' not in season_json[season].keys():
                    return 0
                pass

    async def get_seasonal_featured_bd(self, langs: List[str], start: datetime) -> list:
        tess_def = await self.destiny.decode_hash(3361454721, 'DestinyVendorDefinition')

        bd = []

        for lang in langs:
            classnames = self.translations[lang]['classnames']
            n_items = 0
            curr_week = []
            i_week = 1
            class_items = 0
            n_order = 0
            for i, item in enumerate(tess_def['itemList']):
                if n_items >= 4 and n_items - class_items / 3 * 2 >= 4:
                    i_week = i_week + 1
                    bd.append(list.copy(curr_week))
                    n_items = 0
                    curr_week = []
                    class_items = 0
                if item['displayCategoryIndex'] == 2 and item['itemHash'] not in [353932628, 3260482534, 3536420626,
                                                                                  3187955025, 2638689062]:
                    definition = 'DestinyInventoryItemDefinition'
                    item_def = await self.destiny.decode_hash(item['itemHash'], definition, language=lang)
                    if len(item['currencies']) > 0:
                        currency_resp = await self.destiny.decode_hash(item['currencies'][0]['itemHash'], definition,
                                                                       language=lang)
                    else:
                        currency_resp = {'displayProperties': {'icon': '', 'name': ''}}
                        item['currencies'] = [{'quantity': ''}]
                    cat_number = 2
                    if 'screenshot' in item_def.keys():
                        screenshot = '<img alt="Screenshot" class="screenshot_hover" src="https://bungie.net{}"' \
                                     'loading="lazy">'.format(item_def['screenshot'])
                    else:
                        screenshot = ''
                    curr_week.append({
                        'id': '{}_{}_{}'.format(item['itemHash'], cat_number, n_order),
                        'icon': item_def['displayProperties']['icon'],
                        'tooltip_id': '{}_{}_{}_tooltip'.format(item['itemHash'], cat_number, n_order),
                        'hash': item['itemHash'],
                        'name': item_def['displayProperties']['name'],
                        'screenshot': screenshot,
                        'costs': [
                            {
                                'currency_icon': currency_resp['displayProperties']['icon'],
                                'cost': item['currencies'][0]['quantity'],
                                'currency_name': currency_resp['displayProperties']['name']
                            }]
                    })
                    n_order += 1
                    n_items = n_items + 1
                    if item_def['classType'] < 3 or any(
                            class_name in item_def['itemTypeDisplayName'].lower() for class_name in classnames):
                        class_items = class_items + 1
        return bd

    async def get_seasonal_bd(self, langs: List[str], start: datetime) -> list:
        tess_def = await self.destiny.decode_hash(3361454721, 'DestinyVendorDefinition')

        bd = []

        for lang in langs:
            classnames = self.translations[lang]['classnames']

            n_items = 0
            curr_week = []
            i_week = 1
            class_items = 0
            n_order = 0
            for i, item in enumerate(tess_def['itemList']):
                if n_items >= 7 and n_items - class_items / 3 * 2 >= 7:
                    i_week = i_week + 1
                    bd.append(list.copy(curr_week))
                    n_items = 0
                    curr_week = []
                    class_items = 0
                if item['displayCategoryIndex'] == 8 and item['itemHash'] not in [353932628, 3260482534, 3536420626,
                                                                                  3187955025, 2638689062]:
                    definition = 'DestinyInventoryItemDefinition'
                    item_def = await self.destiny.decode_hash(item['itemHash'], definition, language=lang)
                    if len(item['currencies']) > 0:
                        currency_resp = await self.destiny.decode_hash(item['currencies'][0]['itemHash'], definition,
                                                                       language=lang)
                    else:
                        currency_resp = {'displayProperties': {'icon': '', 'name': ''}}
                        item['currencies'] = [{'quantity': ''}]
                    cat_number = 8
                    if 'screenshot' in item_def.keys():
                        screenshot = '<img alt="Screenshot" class="screenshot_hover" src="https://bungie.net{}" ' \
                                     'loading="lazy">'.format(item_def['screenshot'])
                    else:
                        screenshot = ''
                    curr_week.append({
                        'id': '{}_{}_{}'.format(item['itemHash'], cat_number, n_order),
                        'icon': item_def['displayProperties']['icon'],
                        'tooltip_id': '{}_{}_{}_tooltip'.format(item['itemHash'], cat_number, n_order),
                        'hash': item['itemHash'],
                        'name': item_def['displayProperties']['name'],
                        'screenshot': screenshot,
                        'costs': [
                            {
                                'currency_icon': currency_resp['displayProperties']['icon'],
                                'cost': item['currencies'][0]['quantity'],
                                'currency_name': currency_resp['displayProperties']['name']
                            }]
                    })
                    n_order += 1
                    n_items = n_items + 1
                    if item_def['classType'] < 3 or any(
                            class_name in item_def['itemTypeDisplayName'].lower() for class_name in classnames):
                        class_items = class_items + 1
        return bd

    async def get_seasonal_featured_silver(self, langs: List[str], start: datetime) -> list:
        tess_def = await self.destiny.decode_hash(3361454721, 'DestinyVendorDefinition')

        bd = []

        for lang in langs:
            classnames = self.translations[lang]['classnames']
            n_items = 0
            curr_week = []
            i_week = 1
            class_items = 0
            n_order = 0
            for i, item in enumerate(tess_def['itemList']):
                if n_items >= 5 and n_items - class_items / 3 * 2 >= 5:
                    i_week = i_week + 1
                    bd.append(list.copy(curr_week))
                    n_items = 0
                    curr_week = []
                    class_items = 0
                if item['displayCategoryIndex'] == 1 and item['categoryIndex'] != 37:
                    definition = 'DestinyInventoryItemDefinition'
                    item_def = await self.destiny.decode_hash(item['itemHash'], definition, language=lang)
                    if len(item['currencies']) > 0:
                        currency_resp = await self.destiny.decode_hash(item['currencies'][0]['itemHash'], definition,
                                                                       language=lang)
                    else:
                        currency_resp = {'displayProperties': {'icon': '', 'name': ''}}
                        item['currencies'] = [{'quantity': ''}]
                    cat_number = 2
                    if 'screenshot' in item_def.keys():
                        screenshot = '<img alt="Screenshot" class="screenshot_hover" src="https://bungie.net{}"' \
                                     'loading="lazy">'.format(item_def['screenshot'])
                    else:
                        screenshot = ''
                    curr_week.append({
                        'id': '{}_{}_{}'.format(item['itemHash'], cat_number, n_order),
                        'icon': item_def['displayProperties']['icon'],
                        'tooltip_id': '{}_{}_{}_tooltip'.format(item['itemHash'], cat_number, n_order),
                        'hash': item['itemHash'],
                        'name': item_def['displayProperties']['name'],
                        'screenshot': screenshot,
                        'costs': [
                            {
                                'currency_icon': currency_resp['displayProperties']['icon'],
                                'cost': item['currencies'][0]['quantity'],
                                'currency_name': currency_resp['displayProperties']['name']
                            }]
                    })
                    n_order += 1
                    n_items = n_items + 1
                    if item_def['classType'] < 3 or any(
                            class_name in item_def['itemTypeDisplayName'].lower() for class_name in classnames):
                        class_items = class_items + 1
        return bd

    async def get_weekly_eververse(self, langs: List[str]) -> None:
        data = []
        start = await self.get_season_start()
        week_n = datetime.now(tz=timezone.utc) - await self.get_season_start()
        week_n = int(week_n.days / 7)
        for lang in langs:
            data.clear()
            bd = await self.get_seasonal_bd([lang], start)
            featured_bd = await self.get_seasonal_featured_bd([lang], start)
            # await self.get_seasonal_consumables(langs, start)
            silver = await self.get_seasonal_featured_silver([lang], start)
            for i in range(0, len(bd)):
                data.append({
                    'items': [*bd[i]]
                })
            if len(bd) == len(featured_bd):
                for i in range(0, len(bd)):
                    data[i]['items'] = [*data[i]['items'], *featured_bd[i]]
            if len(bd) == len(silver):
                for i in range(0, len(bd)):
                    data[i]['items'] = [*data[i]['items'], *silver[i]]

            await self.write_to_db(lang, 'weekly_eververse', data[week_n]['items'],
                                   name=self.translations[lang]['site']['bd'],
                                   template='hover_items.html', order=0, type='weekly', size='tall')

    async def write_to_db(self, lang: str, id: str, response: list, size: str = '', name: str = '',
                            template: str = 'table_items.html', order: int = 0, type: str = 'daily',
                            annotations: list = []) -> None:

        no_connection = True
        while no_connection:
            try:
                conn = await self.data_pool.acquire()
                no_connection = False
            except aiomysql.OperationalError:
                await asyncio.sleep(1)
            except RuntimeError:
                await asyncio.sleep(10)
                conn = await self.data_pool.acquire()
                no_connection = False

        cur = await conn.cursor()
        try:
            await cur.execute(
                '''CREATE TABLE IF NOT EXISTS `{}` (id text, timestamp_int integer, json json, timestamp text, size text, name text, template text, place integer, type text, annotations text)'''.format(
                    lang))
            await cur.execute('''CREATE UNIQUE INDEX IF NOT EXISTS `data_id_{}` ON `{}`(id(256))'''.format(lang, lang))
        except aiomysql.Error:
            pass

        try:
            await cur.execute('''INSERT IGNORE INTO `{}` VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)'''.format(lang),
                                (id, datetime.utcnow().timestamp(), json.dumps({'data': response}),
                                 datetime.utcnow().isoformat(), size, name, template, order, type,
                                 str(annotations)))
            await conn.commit()
        except aiomysql.Error:
            pass

        try:
            await cur.execute(
                '''UPDATE `{}` SET timestamp_int=%s, json=%s, timestamp=%s, name=%s, size=%s, template=%s, place=%s, type=%s, annotations=%s WHERE id=%s'''.format(
                    lang),
                (datetime.utcnow().timestamp(), json.dumps({'data': response}),
                 datetime.utcnow().isoformat(), name, size, template, order, type, str(annotations), id))
            await conn.commit()
        except aiomysql.Error:
            pass
        await conn.commit()
        await cur.close()
        self.data_pool.release(conn)

    async def write_bot_data(self, id: str, langs: List[str]) -> None:
        cursor = await self.bot_data_db.cursor()
        timestamp = datetime.utcnow().isoformat()
        for lang in langs:
            try:
                await cursor.execute('''INSERT INTO `{}` VALUES(?,?,?)'''.format(lang),
                                     (id, json.dumps(self.data[lang][id]), timestamp))
            except aiosqlite.IntegrityError:
                await cursor.execute('''UPDATE `{}` SET json=?, timestamp=? WHERE id=?'''.format(lang),
                                     (json.dumps(self.data[lang][id]), timestamp, id))
        await self.bot_data_db.commit()
        await cursor.close()

    async def get_spider(self, lang: List[str], forceget: bool = False) -> Union[bool, None]:
        char_info = self.char_info

        spider_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/2255782930/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'][0])
        spider_resp = await self.get_cached_json('spider', 'spider', spider_url, self.vendor_params, force=forceget)
        if not spider_resp:
            for locale in lang:
                db_data = {
                    'name': self.translations[locale]['msg']['spider'],
                    'description': self.data[locale]['spider']['fields'][0]['value']
                }
                await self.write_to_db(locale, 'spider_mats', [db_data],
                                       name=self.translations[locale]['site']['spider'])
            await self.write_bot_data('spider', lang)
            return False
        spider_json = spider_resp
        spider_cats = spider_json['Response']['categories']['data']['categories']
        resp_time = spider_json['timestamp']
        for locale in lang:
            spider_def = await self.destiny.decode_hash(2255782930, 'DestinyVendorDefinition', language=locale)

            self.data[locale]['spider'] = {
                'thumbnail': {
                    'url': self.icon_prefix + spider_def['displayProperties']['smallTransparentIcon']
                },
                'fields': [],
                'color': 7102001,
                'type': "rich",
                'title': self.translations[locale]['msg']['spider'],
                'footer': {'text': self.translations[locale]['msg']['resp_time']},
                'timestamp': resp_time
            }

            items_to_get = spider_cats[0]['itemIndexes']

            spider_sales = await self.get_vendor_sales(locale, spider_resp, items_to_get, [1812969468, 2979281381])
            self.data[locale]['spider']['fields'] = self.data[locale]['spider']['fields'] + spider_sales[0]
            data = spider_sales[1]

            items_to_get = spider_cats[1]['itemIndexes']
            spider_sales = await self.get_vendor_sales(locale, spider_resp, items_to_get, [1812969468, 2979281381])
            self.data[locale]['spider']['fields'] = self.data[locale]['spider']['fields'] + spider_sales[0]
            #data = spider_sales[1]
            await self.write_to_db(locale, 'spider_mats', data, name=self.translations[locale]['site']['spider'],
                                   order=0, size='tall')
        await self.write_bot_data('spider', lang)

    async def get_banshee(self, lang: List[str], forceget: bool = False) -> Union[bool, None]:
        char_info = self.char_info
        cat_templates = {
            '6': 'contract_item.html',
            '0': 'weapon_item.html',
            '4': 'armor_item.html'
        }

        banshee_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/672118013/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'][0])
        banshee_resp = await self.get_cached_json('banshee', 'banshee', banshee_url, self.vendor_params, force=forceget)
        if not banshee_resp:
            for locale in lang:
                banshee_def = await self.destiny.decode_hash(672118013, 'DestinyVendorDefinition', language=locale)
                db_data = {
                    'name': self.translations[locale]['msg']['error'],
                    'description': self.translations[locale]['msg']['noapi']
                }
                await self.write_to_db(locale, 'spider_mats', [db_data], name=banshee_def['displayProperties']['name'])
            return False
        banshee_json = banshee_resp
        banshee_cats = banshee_json['Response']['categories']['data']['categories']
        resp_time = banshee_json['timestamp']
        for locale in lang:
            banshee_def = await self.destiny.decode_hash(672118013, 'DestinyVendorDefinition', language=locale)

            items_to_get = banshee_cats[2]['itemIndexes']

            sales = []
            banshee_sales = await self.get_vendor_sales(locale, banshee_resp, items_to_get, [1812969468, 2979281381])
            # self.data[locale]['spider']['fields'] = self.data[locale]['spider']['fields'] + banshee_sales[0]
            sales.append({'name': "", "items": banshee_sales[1], "template": cat_templates['6']})
            items_to_get = banshee_cats[3]['itemIndexes']
            banshee_sales = await self.get_vendor_sales(locale, banshee_resp, items_to_get, [1812969468])
            sales.append({'name': "", "items": banshee_sales[1], "template": cat_templates['0']})
            await self.write_to_db(locale, 'banshee_mods', sales, name=banshee_def['displayProperties']['name'], order=5,
                                   template='vendor_items.html', annotations=[])
                             # size='tall')

    async def get_ada(self, lang: List[str], forceget: bool = False) -> Union[bool, None]:
        char_info = self.char_info
        cat_templates = {
            '6': 'contract_item.html',
            '0': 'weapon_item.html',
            '4': 'armor_item.html'
        }

        ada_resps = []
        for char in char_info['charid']:
            ada_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/350061650/'. \
                format(char_info['platform'], char_info['membershipid'], char)
            ada_resps.append(await self.get_cached_json('ada_{}'.format(char), 'ada', ada_url, self.vendor_params, force=forceget))
        for ada_resp in ada_resps:
            if not ada_resp:
                for locale in lang:
                    ada_def = await self.destiny.decode_hash(350061650, 'DestinyVendorDefinition', language=locale)
                    db_data = {
                        'name': self.translations[locale]['msg']['error'],
                        'description': self.translations[locale]['msg']['noapi']
                    }
                    await self.write_to_db(locale, 'spider_mats', [db_data], name=ada_def['displayProperties']['name'])
                return False
        ada_json = ada_resps[0]
        ada_cats = ada_json['Response']['categories']['data']['categories']
        resp_time = ada_json['timestamp']
        for locale in lang:
            ada_def = await self.destiny.decode_hash(350061650, 'DestinyVendorDefinition', language=locale)

            items_to_get = ada_cats[1]['itemIndexes']

            sales = []
            ada_sales = await self.get_vendor_sales(locale, ada_resps[0], items_to_get, [1812969468, 2979281381])
            # self.data[locale]['spider']['fields'] = self.data[locale]['spider']['fields'] + banshee_sales[0]
            sales.append({'name': "", "items": ada_sales[1], "template": cat_templates['6']})
            items_to_get = ada_cats[2]['itemIndexes']
            for ada_resp in ada_resps:
                items_to_get = ada_resp['Response']['categories']['data']['categories'][2]['itemIndexes']
                ada_sales = await self.get_vendor_sales(locale, ada_resp, items_to_get, [1812969468])
                sales.append({'name': "", "items": ada_sales[1], "template": cat_templates['4']})
            await self.write_to_db(locale, 'ada_mods', sales, name=ada_def['displayProperties']['name'], order=5,
                                   template='vendor_items.html', annotations=[], size='tall')

    async def get_daily_mods(self, langs: List[str], forceget: bool = False) -> Union[bool, None]:
        char_info = self.char_info

        ada_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/350061650/'.\
            format(char_info['platform'], char_info['membershipid'], char_info['charid'][0])
        banshee_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/672118013/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'][0])

        ada_resp = await self.get_cached_json('ada_{}'.format(char_info['charid'][0]), 'ada', ada_url, self.vendor_params, force=forceget)
        banshee_resp = await self.get_cached_json('banshee', 'banshee', banshee_url, self.vendor_params, force=forceget)

        if not(ada_resp and banshee_resp):
            return False

        ada_cats = ada_resp['Response']['categories']['data']['categories']
        banshee_cats = banshee_resp['Response']['categories']['data']['categories']
        resp_time = banshee_resp['timestamp']

        for lang in langs:
            self.data[lang]['daily_mods'] = {
                'fields': [],
                'color': 0x4c3461,
                'type': "rich",
                'title': self.translations[lang]['msg']['daily_mods'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']},
                'timestamp': resp_time
            }

            ada_def = await self.destiny.decode_hash(350061650, 'DestinyVendorDefinition', language=lang)
            banshee_def = await self.destiny.decode_hash(672118013, 'DestinyVendorDefinition', language=lang)

            mods = []
            items_to_get = ada_cats[1]['itemIndexes']
            ada_sales = await self.get_vendor_sales(lang, ada_resp, items_to_get, [1812969468])

            fields = [{'inline': True, 'name': self.translations[lang]['msg']['armor_mods'], 'value': ''}]
            for item in ada_sales[1]:
                item_def = await self.destiny.decode_hash(item['hash'], 'DestinyInventoryItemDefinition', language=lang)
                if item_def['itemType'] == 19:
                    mods.append({'inline': True, 'name': item_def['displayProperties']['name'], 'value': item_def['itemTypeDisplayName']})
                    fields[-1]['value'] = '{}{}\n'.format(fields[-1]['value'], item_def['displayProperties']['name'])

            items_to_get = banshee_cats[2]['itemIndexes']
            banshee_sales = await self.get_vendor_sales(lang, banshee_resp, items_to_get, [1812969468, 2731650749])
            fields.append({'inline': True, 'name': self.translations[lang]['msg']['weapon_mods'], 'value': ''})
            for item in banshee_sales[1]:
                item_def = await self.destiny.decode_hash(item['hash'], 'DestinyInventoryItemDefinition', language=lang)
                if item_def['itemType'] == 19:
                    mods.append({'inline': True, 'name': item_def['displayProperties']['name'], 'value': item_def['itemTypeDisplayName']})
                    fields[-1]['value'] = '{}{}\n'.format(fields[-1]['value'], item_def['displayProperties']['name'])
            for i in range(len(fields)):
                fields[i]['value'] = fields[i]['value'][:-1]
            self.data[lang]['daily_mods']['fields'] = fields
        await self.write_bot_data('daily_mods', langs)

    async def get_xur_loc(self) -> dict:
        url = 'https://paracausal.science/xur/current.json'
        r = await self.session.get(url)
        r_json = await r.json()

        return r_json

    async def get_xur(self, langs: List[str], forceget: bool = False) -> Union[bool, None]:
        char_info = self.char_info
        cat_templates = {
            '6': 'contract_item.html',
            '0': 'weapon_item.html',
            '4': 'armor_item.html'
        }

        place_hashes = {
            '1737926756': 3747705955,
            '3607432451': 3607432451,
            '697502628': 3747705955
        }

        xur_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/2190858386/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'][0])
        xur_resp = await self.get_cached_json('xur', 'xur', xur_url, self.vendor_params, force=forceget)
        if not xur_resp:
            for lang in langs:
                db_data = {
                    'name': self.translations[lang]['msg']['xur'],
                    'description': self.data[lang]['xur']['fields'][0]['value']
                }
                await self.write_to_db(lang, 'xur', [db_data],
                                       name=self.translations[lang]['msg']['xur'])
            await self.write_bot_data('xur', langs)
            return False
        resp_time = xur_resp['timestamp']
        xur_loc = await self.get_xur_loc()
        for lang in langs:

            xur_def = await self.destiny.decode_hash(2190858386, 'DestinyVendorDefinition', language=lang)
            self.data[lang]['xur'] = {
                'thumbnail': {
                    'url': self.icon_prefix + xur_def['displayProperties']['smallTransparentIcon']
                },
                'fields': [],
                'color': 0x3DD5D6,
                'type': "rich",
                'title': self.translations[lang]['msg']['xurtitle'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']},
                'timestamp': resp_time
            }

            xur_json = xur_resp
            if not xur_json['ErrorCode'] == 1627:
                loc_field = {
                    "inline": False,
                    "name": self.translations[lang]['msg']['xurloc'],
                    "value": self.translations[lang]['xur']['NULL']
                }
                weapon = {
                    'inline': False,
                    'name': self.translations[lang]['msg']['weapon'],
                    'value': ''
                }

                annotations = []

                if xur_loc:
                    self.data[lang]['xur']['footer']['text'] = self.translations[lang]['xur']['copyright']
                    annotations = [self.translations[lang]['xur']['copyright']]
                else:
                    xur_loc = {}

                if xur_def['locations'][xur_json['Response']['vendor']['data']['vendorLocationIndex']] != 2961497387:
                    xur_loc['destinationHash'] = xur_def['locations'][xur_json['Response']['vendor']['data']['vendorLocationIndex']]['destinationHash']
                    xur_loc['placeHash'] = place_hashes[str(xur_loc['destinationHash'])]
                    self.data[lang]['xur'].pop('footer')
                    annotations = []

                sales = []
                if xur_loc:
                    xur_place_name = await self.destiny.decode_hash(xur_loc['placeHash'], 'DestinyPlaceDefinition', language=lang)
                    xur_destination_name = await self.destiny.decode_hash(xur_loc['destinationHash'], 'DestinyDestinationDefinition', language=lang)
                    loc_field['value'] = '{}, {}'.format(xur_place_name['displayProperties']['name'], xur_destination_name['displayProperties']['name'])
                    self.data[lang]['xur']['fields'].append(loc_field)
                    sales = [{'name': '{}, {}'.format(xur_place_name['displayProperties']['name'],
                                                      xur_destination_name['displayProperties']['name']),
                              'items': [], 'template': cat_templates['6']},
                             {'name': 'Оружие', 'items': [], 'template': cat_templates['0']},
                             {'name': 'Броня', 'items': [], 'template': cat_templates['4']}]

                    xur_cats = xur_resp['Response']['categories']['data']['categories']
                    cat_sales = await self.get_vendor_sales(lang, xur_resp, xur_cats[0]['itemIndexes'], [3875551374])
                    xur_sales = xur_json['Response']['sales']['data']

                    weapons = await self.get_vendor_sales(lang, xur_resp, xur_cats[1]['itemIndexes'], [3875551374])
                    cat_sales[0] = [*cat_sales[0], *weapons[0]]
                    cat_sales[1] = [*cat_sales[1], *weapons[1]]
                    self.data[lang]['xur']['fields'].append(weapon)

                    for key in sorted(xur_sales.keys()):
                        item_hash = xur_sales[key]['itemHash']
                        if item_hash not in [4285666432, 2293314698, 2125848607, 3875551374]:
                            definition = 'DestinyInventoryItemDefinition'
                            item_resp = await self.destiny.decode_hash(item_hash, definition, language=lang)
                            item_name = item_resp['displayProperties']['name']
                            if item_resp['itemType'] == 2:
                                item_sockets = item_resp['sockets']['socketEntries']
                                plugs = []
                                for s in item_sockets:
                                    if len(s['reusablePlugItems']) > 0 and s['plugSources'] == 2:
                                        plugs.append(s['reusablePlugItems'][0]['plugItemHash'])

                                exotic = {
                                    'inline': True,
                                    'name': '',
                                    'value': item_name
                                }

                                if item_resp['summaryItemHash'] in [715326750, 2673424576]:
                                    if item_resp['classType'] == 0:
                                        exotic['name'] = self.translations[lang]['Titan']
                                    elif item_resp['classType'] == 1:
                                        exotic['name'] = self.translations[lang]['Hunter']
                                    elif item_resp['classType'] == 2:
                                        exotic['name'] = self.translations[lang]['Warlock']

                                    if item_hash not in [3654674561, 3856705927]:
                                        self.data[lang]['xur']['fields'].append(exotic)
                                    for item in cat_sales[1]:
                                        if item['hash'] == item_hash:
                                            sales[2]['items'].append(item)
                            else:
                                if item_resp['summaryItemHash'] in [715326750, 2673424576]:
                                    i = 0
                                    for item in self.data[lang]['xur']['fields']:
                                        if item['name'] == self.translations[lang]['msg']['weapon'] and item_hash not in [3654674561, 3856705927]:
                                            self.data[lang]['xur']['fields'][i]['value'] = item_name
                                        i += 1
                                    for item in cat_sales[1]:
                                        if item['hash'] == item_hash:
                                            sales[1]['items'].append(item)

                else:
                    loc_field = {
                        "inline": False,
                        "name": self.translations[lang]['msg']['xurloc'],
                        "value": self.translations[lang]['xur']['noxur']
                    }
                    self.data[lang]['xur']['fields'].append(loc_field)
                    sales = [{'name': self.translations[lang]['xur']['noxur'],
                              'items': [], 'template': cat_templates['6']}]
            else:
                loc_field = {
                    "inline": False,
                    "name": self.translations[lang]['msg']['xurloc'],
                    "value": self.translations[lang]['xur']['noxur']
                }
                self.data[lang]['xur']['fields'].append(loc_field)
                sales = [{'name': self.translations[lang]['xur']['noxur'],
                          'items': [], 'template': cat_templates['6']}]
            await self.write_to_db(lang, 'xur', sales, template='vendor_items.html', order=7,
                                   name=xur_def['displayProperties']['name'],
                                   annotations=annotations)
        await self.write_bot_data('xur', langs)

    async def get_heroic_story(self, langs: List[str], forceget: bool = False) -> Union[bool, None]:
        activities_resp = await self.get_activities_response('heroicstory', string='heroic story missions',
                                                             force=forceget)
        if not activities_resp:
            for lang in langs:
                db_data = {
                    'name': self.data[lang]['heroicstory']['fields'][0]['name'],
                    'description': self.data[lang]['heroicstory']['fields'][0]['value']
                }
                await self.write_to_db(lang, 'heroic_story_missions', [db_data],
                                       name=self.translations[lang]['site']['heroicstory'])
            return False
        resp_time = activities_resp['timestamp']
        for lang in langs:
            local_types = self.translations[lang]

            self.data[lang]['heroicstory'] = {
                'thumbnail': {
                    'url': "https://www.bungie.net/common/destiny2_content/icons/DestinyActivityModeDefinition_"
                           "5f8a923a0d0ac1e4289ae3be03f94aa2.png"
                },
                'fields': [],
                'color': 10070709,
                'type': 'rich',
                'title': self.translations[lang]['msg']['heroicstory'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']},
                'timestamp': resp_time
            }
            db_data = []
            activities_json = activities_resp
            for key in activities_json['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await self.destiny.decode_hash(item_hash, definition, language=lang)

                if local_types['heroicstory'] in r_json['displayProperties']['name']:
                    info = {
                        'inline': True,
                        "name": r_json['selectionScreenDisplayProperties']['name'],
                        "value": r_json['selectionScreenDisplayProperties']['description']
                    }
                    db_data.append({
                        "name": r_json['selectionScreenDisplayProperties']['name'],
                        "description": r_json['selectionScreenDisplayProperties']['description']
                    })
                    self.data[lang]['heroicstory']['fields'].append(info)
            await self.write_to_db(lang, 'heroic_story_missions', db_data, name=self.translations[lang]['site']['heroicstory'],
                                   size='tall', order=3)

    async def get_forge(self, langs: List[str], forceget: bool = False) -> Union[bool, None]:
        activities_resp = await self.get_activities_response('forge', force=forceget)
        if not activities_resp:
            for lang in langs:
                local_types = self.translations[lang]
                db_data = {
                    'name': self.data[lang]['forge']['fields'][0]['name'],
                    'description': self.data[lang]['forge']['fields'][0]['value']
                }
                await self.write_to_db(lang, 'forge', [db_data], name=self.translations[lang]['site']['forge'],
                                       template='table_items.html')
            return False
        resp_time = activities_resp['timestamp']
        for lang in langs:
            local_types = self.translations[lang]

            self.data[lang]['forge'] = {
                'thumbnail': {
                    'url': ''
                },
                'fields': [],
                'color': 3678761,
                'type': 'rich',
                'title': self.translations[lang]['msg']['forge'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']},
                'timestamp': resp_time
            }
            db_data = []
            activities_json = activities_resp
            for key in activities_json['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await self.destiny.decode_hash(item_hash, definition, language=lang)

                if local_types['forge'] in r_json['displayProperties']['name']:
                    forge_def = 'DestinyDestinationDefinition'
                    place = await self.destiny.decode_hash(r_json['destinationHash'], forge_def, language=lang)
                    self.data[lang]['forge']['thumbnail']['url'] = self.icon_prefix + r_json['displayProperties'][
                        'icon']
                    info = {
                        "inline": True,
                        "name": r_json['displayProperties']['name'],
                        "value": place['displayProperties']['name']
                    }
                    db_data.append({
                        "name": r_json['displayProperties']['name'],
                        "description": place['displayProperties']['name'],
                        "icon": r_json['displayProperties']['icon']
                    })
                    self.data[lang]['forge']['fields'].append(info)
            await self.write_to_db(lang, 'forge', db_data, name=self.translations[lang]['site']['forge'],
                                   template='table_items.html', order=4)

    async def get_strike_modifiers(self, langs: List[str], forceget: bool = False) -> Union[bool, None]:
        activities_resp = await self.get_activities_response('vanguardstrikes', string='strike modifiers',
                                                             force=forceget)
        if not activities_resp:
            for lang in langs:
                db_data = {
                    'name': self.data[lang]['vanguardstrikes']['fields'][0]['name'],
                    'description': self.data[lang]['vanguardstrikes']['fields'][0]['value']
                }
                await self.write_to_db(lang, 'strike_modifiers', [db_data],
                                       name=self.translations[lang]['msg']['strikesmods'])
            await self.write_bot_data('vanguardstrikes', langs)
            return False
        resp_time = activities_resp['timestamp']
        for lang in langs:
            local_types = self.translations[lang]

            self.data[lang]['vanguardstrikes'] = {
                'thumbnail': {
                    'url': ''
                },
                'fields': [],
                'color': 7506394,
                'type': 'rich',
                'title': self.translations[lang]['msg']['strikesmods'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']},
                'timestamp': resp_time
            }

            db_data = []
            activities_json = activities_resp
            strikes = await self.destiny.decode_hash(743628305, 'DestinyActivityDefinition', language=lang)
            for key in activities_json['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await self.destiny.decode_hash(item_hash, definition, language=lang)

                if item_hash == 743628305:
                    mods = await self.decode_modifiers(key, lang)
                    self.data[lang]['vanguardstrikes']['fields'] = mods[0]
                    db_data = mods[1]
                if self.translations[lang]['strikes'] in r_json['displayProperties']['name']:
                    self.data[lang]['vanguardstrikes']['thumbnail']['url'] = self.icon_prefix + \
                                                                             r_json['displayProperties']['icon']
            await self.write_to_db(lang, 'strike_modifiers', db_data, size='wide',
                                   name=self.translations[lang]['msg']['strikesmods'], order=1)
        await self.write_bot_data('vanguardstrikes', langs)

    async def get_reckoning_boss(self, lang: str) -> None:
        first_reset_time = 1539709200
        seconds_since_first = time.time() - first_reset_time
        weeks_since_first = seconds_since_first // 604800
        reckoning_bosses = ['swords', 'oryx']

        self.data[lang]['reckoningboss'] = {
            "thumbnail": {
                "url": "https://www.bungie.net/common/destiny2_content/icons/DestinyActivityModeDefinition_"
                       "e74b3385c5269da226372df8ae7f500d.png"
            },
            'fields': [
                {
                    'inline': True,
                    "name": self.translations[lang][reckoning_bosses[int(weeks_since_first % 2)]],
                    "value": self.translations[lang]['r_desc']
                }
            ],
            "color": 1332799,
            "type": "rich",
            "title": self.translations[lang]['msg']['reckoningboss'],
        }

    def add_reckoning_boss(self, lang: str) -> list:
        first_reset_time = 1539709200
        seconds_since_first = time.time() - first_reset_time
        weeks_since_first = seconds_since_first // 604800
        reckoning_bosses = ['swords', 'oryx']

        data = [{
            'inline': False,
            'name': self.translations[lang]['msg']['reckoningboss'],
            'value': self.translations[lang][reckoning_bosses[int(weeks_since_first % 2)]],
        }]
        db_data = [{
            'name': self.translations[lang]['site']['reckoningboss'],
            'description': self.translations[lang][reckoning_bosses[int(weeks_since_first % 2)]],
            'icon': "/common/destiny2_content/icons/DestinyActivityModeDefinition_e74b3385c5269da226372df8ae7f500d.png"
        }]

        return [data, db_data]

    async def get_reckoning_modifiers(self, langs: List[str], forceget: bool = False) -> Union[bool, None]:
        activities_resp = await self.get_activities_response('reckoning', string='reckoning modifiers', force=forceget)
        if not activities_resp:
            for lang in langs:
                db_data = {
                    'name': self.data[lang]['reckoning']['fields'][0]['name'],
                    'description': self.data[lang]['reckoning']['fields'][0]['value']
                }
                await self.write_to_db(lang, 'reckoning', [db_data],
                                       name=self.translations[lang]['msg']['reckoningmods'])
            return False
        resp_time = activities_resp['timestamp']
        for lang in langs:
            local_types = self.translations[lang]

            self.data[lang]['reckoning'] = {
                'thumbnail': {
                    'url': "https://www.bungie.net/common/destiny2_content/icons/DestinyActivityModeDefinition_"
                           "e74b3385c5269da226372df8ae7f500d.png"
                },
                'fields': [],
                'color': 1332799,
                'type': 'rich',
                'title': self.translations[lang]['msg']['reckoningmods'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']},
                'timestamp': resp_time
            }

            self.data[lang]['reckoning']['fields'] = self.add_reckoning_boss(lang)[0]

            db_data = self.add_reckoning_boss(lang)[1]
            activities_json = activities_resp
            for key in activities_json['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await self.destiny.decode_hash(item_hash, definition, language=lang)

                if self.translations[lang]['reckoning'] in r_json['displayProperties']['name']:
                    mods = await self.decode_modifiers(key, lang)
                    db_data = [*db_data, *mods[1]]
                    self.data[lang]['reckoning']['fields'] = [*self.data[lang]['reckoning']['fields'], *mods[0]]
            await self.write_to_db(lang, 'reckoning', db_data, 'wide', self.translations[lang]['msg']['reckoningmods'],
                                   order=2)

    async def get_nightfall820(self, langs: List[str], forceget: bool = False) -> Union[bool, None]:
        activities_resp = await self.get_activities_response('nightfalls820', string='820 nightfalls', force=forceget)
        if not activities_resp:
            for lang in langs:
                db_data = {
                    'name': self.data[lang]['nightfalls820']['fields'][0]['name'],
                    'description': self.data[lang]['nightfalls820']['fields'][0]['value']
                }
                await self.write_to_db(lang, '820_nightfalls', [db_data],
                                       name=self.translations[lang]['site']['nightfalls820'], type='weekly')
            return False
        resp_time = activities_resp['timestamp']
        for lang in langs:
            local_types = self.translations[lang]

            self.data[lang]['nightfalls820'] = {
                'thumbnail': {
                    'url': ''
                },
                'fields': [],
                'color': 7506394,
                'type': 'rich',
                'title': self.translations[lang]['msg']['nightfalls820'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']},
                'timestamp': resp_time
            }

            db_data = []
            activities_json = activities_resp
            for key in activities_json['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await self.destiny.decode_hash(item_hash, definition, language=lang)
                try:
                    recommended_light = key['recommendedLight']
                    if recommended_light == 820:
                        self.data[lang]['nightfalls820']['thumbnail']['url'] = self.icon_prefix + \
                                                                               r_json['displayProperties']['icon']
                        if r_json['matchmaking']['requiresGuardianOath']:
                            info = {
                                'inline': True,
                                'name': self.translations[lang]['msg']['guidedgamenightfall'],
                                'value': r_json['selectionScreenDisplayProperties']['name']
                            }
                            db_data.append({
                                'name': self.translations[lang]['msg']['guidedgamenightfall'],
                                'description': r_json['selectionScreenDisplayProperties']['name']
                            })
                        else:
                            info = {
                                'inline': True,
                                'name': r_json['selectionScreenDisplayProperties']['name'],
                                'value': r_json['selectionScreenDisplayProperties']['description']
                            }
                            db_data.append({
                                'name': r_json['selectionScreenDisplayProperties']['name'],
                                'description': r_json['selectionScreenDisplayProperties']['description']
                            })
                        self.data[lang]['nightfalls820']['fields'].append(info)
                except KeyError:
                    pass
            await self.write_to_db(lang, '820_nightfalls', db_data,
                                   name=self.translations[lang]['site']['nightfalls820'], order=0, type='weekly')

    async def get_modifiers(self, lang: str, act_hash: int, mods_to_seek=None) -> Union[bool, list]:
        url = 'https://www.bungie.net/{}/Explore/Detail/DestinyActivityDefinition/{}'.format(lang, act_hash)
        r = await self.session.get(url)
        r = await r.text()
        soup = BeautifulSoup(r, features="html.parser")
        modifier_list = soup.find_all('div', {'data-identifier': 'modifier-information'})
        modifiers = []
        for item in modifier_list:
            modifier = item.find('div', {'class': 'text-content'})
            modifier_title = modifier.find('div', {'class': 'title'})
            modifier_subtitle = modifier.find('div', {'class': 'subtitle'})
            mod = {
                "name": modifier_title.text,
                "description": modifier_subtitle.text
            }
            modifiers.append(mod)
        if r:
            return modifiers
        else:
            return False

    async def get_raids(self, langs: List[str], forceget: bool = False) -> Union[bool, None]:
        activities_resp = await self.get_activities_response('raids', force=forceget)
        if not activities_resp:
            for lang in langs:
                db_data = {
                    'name': self.data[lang]['raids']['fields'][0]['name'],
                    'description': self.data[lang]['raids']['fields'][0]['value']
                }
                await self.write_to_db(lang, 'raid_challenges', [db_data], self.translations[lang]['msg']['raids'],
                                       type='weekly')
            await self.write_bot_data('raids', langs)
            return False
        resp_time = activities_resp['timestamp']

        # hawthorne_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/3347378076/'. \
        #     format(self.char_info['platform'], self.char_info['membershipid'], self.char_info['charid'][0])
        # hawthorne_resp = await self.get_cached_json('hawthorne', 'hawthorne', hawthorne_url, self.vendor_params,
        #                                             force=forceget)
        for lang in langs:
            local_types = self.translations[lang]

            self.data[lang]['raids'] = {
                'thumbnail': {
                    'url': 'https://www.bungie.net/common/destiny2_content/icons/8b1bfd1c1ce1cab51d23c78235a6e067.png'
                },
                'fields': [],
                'color': 0xF1C40F,
                'type': 'rich',
                'title': self.translations[lang]['msg']['raids'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']},
                'timestamp': resp_time
            }

            first_reset_time = 1580230800
            seconds_since_first = time.time() - first_reset_time
            weeks_since_first = seconds_since_first // 604800
            eow_loadout = int(weeks_since_first % 6)
            last_wish_challenges = [1250327262, 3871581136, 1568895666, 4007940282, 2836954349]
            sotp_challenges = [1348944144, 3415614992, 1381881897]
            cos_challenges = [2459033425, 2459033426, 2459033427]
            lw_ch = 0
            sotp_ch = 0
            cos_ch = 0

            # hawthorne_json = hawthorne_resp
            # if hawthorne_resp:
            #     resp_time = hawthorne_json['timestamp']
            #     for cat in hawthorne_json['Response']['sales']['data']:
            #         if hawthorne_json['Response']['sales']['data'][cat]['itemHash'] in last_wish_challenges:
            #             lw_ch = hawthorne_json['Response']['sales']['data'][cat]['itemHash']
            #         elif hawthorne_json['Response']['sales']['data'][cat]['itemHash'] in sotp_challenges:
            #             sotp_ch = hawthorne_json['Response']['sales']['data'][cat]['itemHash']
            #         elif hawthorne_json['Response']['sales']['data'][cat]['itemHash'] in cos_challenges:
            #             cos_ch = hawthorne_json['Response']['sales']['data'][cat]['itemHash']

            db_data = []
            activities_json = activities_resp
            for key in activities_json['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await self.destiny.decode_hash(item_hash, definition, language=lang)
                i = 1
                # if str(r_json['hash']) in self.translations[lang]['levi_order'] and \
                #         not r_json['matchmaking']['requiresGuardianOath']:
                #     challenges = await self.get_modifiers(lang, item_hash)
                #     if challenges:
                #         challenge = set(challenges[0]['name'].lower().replace('"', '').split(' '))
                #         challenge.discard('the')
                #         order_strings = self.translations[lang]['levi_order'][str(r_json['hash'])].splitlines()
                #         levi_str = ''
                #         for string in order_strings:
                #             intersection = challenge.intersection(set(string.lower().split(' ')))
                #             if intersection:
                #                 levi_str = '{}<b>{}</b>\n'.format(levi_str, string)
                #             else:
                #                 levi_str = '{}{}\n'.format(levi_str, string)
                #         levi_str = levi_str[:-1]
                #     else:
                #         levi_str = self.translations[lang]['levi_order'][str(r_json['hash'])]
                #     info = {
                #         'inline': True,
                #         'name': r_json['originalDisplayProperties']['name'],
                #         'value': levi_str.replace('<b>', '**').replace('</b>', '**')
                #     }
                #     db_data.append({
                #         'name': info['name'],
                #         'description': levi_str.replace('\n', '<br>')
                #     })
                #     self.data[lang]['raids']['fields'].append(info)
                # if self.translations[lang]["EoW"] in r_json['displayProperties']['name'] and \
                #         not r_json['matchmaking']['requiresGuardianOath']:
                #     info = {
                #         'inline': False,
                #         'name': self.translations[lang]['lairs'],
                #         'value': u"\u2063"
                #     }
                #     mods = await self.get_modifiers(lang, r_json['hash'])
                #     resp_time = datetime.utcnow().isoformat()
                #     if mods:
                #         loadout = '{}\n{}\n{}'.format(self.translations[lang]['armsmaster'][eow_loadout*3],
                #                                       self.translations[lang]['armsmaster'][eow_loadout*3+1],
                #                                       self.translations[lang]['armsmaster'][eow_loadout*3+2])
                #         info['value'] = '{}: {}\n\n{}:\n{}'.format(mods[0]['name'], mods[0]['description'],
                #                                                    mods[1]['name'], loadout)
                #     else:
                #         info['value'] = self.data[lang]['api_is_down']['fields'][0]['name']
                #     db_data.append({
                #         'name': info['name'],
                #         'description': info['value'].replace('\n\n', '<br>').replace('\n', '<br>')
                #     })
                #     self.data[lang]['raids']['fields'].append(info)
                # if self.translations[lang]['LW'] in r_json['displayProperties']['name'] and \
                #         not r_json['matchmaking']['requiresGuardianOath'] and lw_ch != 0 and hawthorne_resp:
                #     info = {
                #         'inline': True,
                #         'name': r_json['originalDisplayProperties']['name'],
                #         'value': u"\u2063"
                #     }
                #     curr_challenge = lw_ch
                #     curr_challenge = await self.destiny.decode_hash(curr_challenge, 'DestinyInventoryItemDefinition',
                #                                                     language=lang)
                #     info['value'] = curr_challenge['displayProperties']['name']
                #     db_data.append({
                #         'name': info['name'],
                #         'description': info['value'].replace('\n', '<br>')
                #     })
                #     self.data[lang]['raids']['fields'].append(info)
                # if self.translations[lang]['SotP'] in r_json['displayProperties']['name'] and \
                #         not r_json['matchmaking']['requiresGuardianOath'] and sotp_ch != 0 and hawthorne_resp:
                #     info = {
                #         'inline': True,
                #         'name': r_json['originalDisplayProperties']['name'],
                #         'value': u"\u2063"
                #     }
                #     curr_challenge = sotp_ch
                #     curr_challenge = await self.destiny.decode_hash(curr_challenge, 'DestinyInventoryItemDefinition',
                #                                                     language=lang)
                #     info['value'] = curr_challenge['displayProperties']['name']
                #     db_data.append({
                #         'name': info['name'],
                #         'description': info['value'].replace('\n', '<br>')
                #     })
                #     self.data[lang]['raids']['fields'].append(info)
                # if self.translations[lang]['CoS'] in r_json['displayProperties']['name'] and \
                #         not r_json['matchmaking']['requiresGuardianOath'] and cos_ch != 0 and hawthorne_resp:
                #     info = {
                #         'inline': True,
                #         'name': r_json['originalDisplayProperties']['name'],
                #         'value': u"\u2063"
                #     }
                #     curr_challenge = cos_ch
                #     curr_challenge = await self.destiny.decode_hash(curr_challenge, 'DestinyInventoryItemDefinition',
                #                                                     language=lang)
                #     info['value'] = curr_challenge['displayProperties']['name']
                #     db_data.append({
                #         'name': info['name'],
                #         'description': info['value'].replace('\n', '<br>')
                #     })
                #     self.data[lang]['raids']['fields'].append(info)
                # if self.translations[lang]['GoS'] in r_json['displayProperties']['name'] and \
                #         not r_json['matchmaking']['requiresGuardianOath'] and 'modifierHashes' in key.keys():
                #     info = {
                #         'inline': True,
                #         'name': r_json['originalDisplayProperties']['name'],
                #         'value': u"\u2063"
                #     }
                #     # mods = await self.get_modifiers(lang, r_json['hash'])
                #     mods = await self.destiny.decode_hash(key['modifierHashes'][0], 'DestinyActivityModifierDefinition', lang)
                #     resp_time = datetime.utcnow().isoformat()
                #     if mods:
                #         info['value'] = mods['displayProperties']['name']
                #     else:
                #         info['value'] = self.data[lang]['api_is_down']['fields'][0]['name']
                #     db_data.append({
                #         'name': info['name'],
                #         'description': info['value'].replace('\n', '<br>')
                #     })
                #     self.data[lang]['raids']['fields'].append(info)
                if r_json['hash'] in [910380154, 3881495763, 1441982566, 2122313384, 3458480158, 1374392663] and 'modifierHashes' in key.keys():
                    info = {
                        'inline': True,
                        'name': r_json['originalDisplayProperties']['name'],
                        'value': u"\u2063"
                    }
                    intersection = list(set(key['modifierHashes']).intersection(set([1783825372])))
                    valid_mods = []
                    for mod in key['modifierHashes']:
                        if mod not in intersection:
                            valid_mods.append(mod)
                    mods = await self.destiny.decode_hash(valid_mods[0], 'DestinyActivityModifierDefinition', lang)
                    resp_time = datetime.utcnow().isoformat()
                    if mods:
                        if len(valid_mods) > 2:
                            info['value'] = local_types['msg']['featured_raid']
                        else:
                            info['value'] = mods['displayProperties']['name']
                    else:
                        info['value'] = self.data[lang]['api_is_down']['fields'][0]['name']
                    if mods['displayProperties']['name']:
                        db_data.append({
                            'name': info['name'],
                            'description': info['value'].replace('\n', '<br>').replace('**', '')
                        })
                        self.data[lang]['raids']['fields'].append(info)
            self.data[lang]['raids']['timestamp'] = resp_time
            await self.write_to_db(lang, 'raid_challenges', db_data, '',
                                   self.translations[lang]['msg']['raids'], order=1, type='weekly')
        await self.write_bot_data('raids', langs)

    async def get_ordeal(self, langs: List[str], forceget: bool = False) -> Union[bool, None]:
        activities_resp = await self.get_activities_response('ordeal', force=forceget)
        if not activities_resp:
            for lang in langs:
                db_data = {
                    'name': self.data[lang]['ordeal']['fields'][0]['name'],
                    'description': self.data[lang]['ordeal']['fields'][0]['value']
                }
                await self.write_to_db(lang, 'ordeal', [db_data], name=self.translations[lang]['msg']['ordeal'],
                                       type='weekly')
            await self.write_bot_data('ordeal', langs)
            return False
        resp_time = activities_resp['timestamp']
        for lang in langs:
            local_types = self.translations[lang]

            self.data[lang]['ordeal'] = {
                'thumbnail': {
                    'url': 'https://www.bungie.net/common/destiny2_content/icons/DestinyMilestoneDefinition'
                           '_a72e5ce5c66e21f34a420271a30d7ec3.png'
                },
                'fields': [],
                'color': 5331575,
                'type': 'rich',
                'title': self.translations[lang]['ordeal'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']},
                'timestamp': resp_time
            }

            strikes = []

            db_data = []
            activities_json = activities_resp
            for key in activities_json['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await self.destiny.decode_hash(item_hash, definition, language=lang)
                if r_json['activityTypeHash'] == 4110605575:
                    strikes.append({"name": r_json['displayProperties']['name'],
                                    "description": r_json['displayProperties']['description']})
                if r_json['activityTypeHash'] == 575572995 and \
                        local_types['adept'] in r_json['displayProperties']['name']:
                    info = {
                        'inline': True,
                        'name': r_json['originalDisplayProperties']['description'],
                        'value': u"\u2063"
                    }
                    self.data[lang]['ordeal']['fields'].append(info)
                    db_data.append({
                        'name': info['name'],
                        'description': info['value']
                    })
                    if 1171597537 in key['modifierHashes']:  # Check for double rewards
                        mod_info = await self.destiny.decode_hash(1171597537, 'DestinyActivityModifierDefinition', language=lang)
                        self.data[lang]['ordeal']['fields'].append({
                            'inline': False,
                            'name': mod_info['displayProperties']['name'],
                            'value': mod_info['displayProperties']['description']
                        })
                        db_data.append({
                            'name': mod_info['displayProperties']['name'],
                            'description': mod_info['displayProperties']['description']
                        })

            if len(self.data[lang]['ordeal']['fields']) > 0:
                for strike in strikes:
                    if strike['name'] in self.data[lang]['ordeal']['fields'][0]['name']:
                        self.data[lang]['ordeal']['fields'][0]['value'] = strike['description']
                        db_data[0]['description'] = strike['description']
                        break
            await self.write_to_db(lang, 'ordeal', db_data, name=self.translations[lang]['msg']['ordeal'], order=3,
                                   type='weekly')
        await self.write_bot_data('ordeal', langs)

    async def get_nightmares(self, langs: List[str], forceget: bool = False) -> Union[bool, None]:
        activities_resp = await self.get_activities_response('nightmares', force=forceget)
        if not activities_resp:
            for lang in langs:
                db_data = {
                    'name': self.data[lang]['nightmares']['fields'][0]['name'],
                    'description': self.data[lang]['nightmares']['fields'][0]['value']
                }
                await self.write_to_db(lang, 'nightmare_hunts', [db_data],
                                       name=self.translations[lang]['site']['nightmares'], type='weekly')
            await self.write_bot_data('nightmares', langs)
            return False
        resp_time = activities_resp['timestamp']
        for lang in langs:
            local_types = self.translations[lang]

            self.data[lang]['nightmares'] = {
                'thumbnail': {
                    'url': 'https://www.bungie.net/common/destiny2_content/icons/DestinyActivityModeDefinition_'
                           '48ad57129cd0c46a355ef8bcaa1acd04.png'
                },
                'fields': [],
                'color': 6037023,
                'type': 'rich',
                'title': self.translations[lang]['msg']['nightmares'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']},
                'timestamp': resp_time
            }

            db_data = []
            activities_json = activities_resp
            for key in activities_json['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await self.destiny.decode_hash(item_hash, definition, language=lang)
                if local_types['nightmare'] in r_json['displayProperties']['name'] and \
                        local_types['adept'] in r_json['displayProperties']['name']:
                    info = {
                        'inline': True,
                        'name': r_json['displayProperties']['name'].replace(local_types['adept'], ""),
                        'value': r_json['displayProperties']['description']
                    }
                    db_data.append({
                        'name': info['name'].replace(local_types['nightmare'], '').replace('\"', ''),
                        'description': info['value']
                    })
                    self.data[lang]['nightmares']['fields'].append(info)
            await self.write_to_db(lang, 'nightmare_hunts', db_data, name=self.translations[lang]['site']['nightmares'],
                                   order=2, type='weekly')
        await self.write_bot_data('nightmares', langs)

    async def get_empire_hunt(self, langs: List[str], forceget: bool = False) -> Union[bool, None]:
        activities_resp = await self.get_activities_response('empire_hunts', force=forceget)
        if not activities_resp:
            for lang in langs:
                db_data = {
                    'name': self.data[lang]['empire_hunts']['fields'][0]['name'],
                    'description': self.data[lang]['empire_hunts']['fields'][0]['value']
                }
                await self.write_to_db(lang, 'empire_hunts', [db_data],
                                       name=self.translations[lang]['site']['empire_hunts'], type='weekly')
            await self.write_bot_data('empire_hunts', langs)
            return False
        resp_time = activities_resp['timestamp']

        for lang in langs:
            local_types = self.translations[lang]

            self.data[lang]['empire_hunts'] = {
                'thumbnail': {
                    'url': 'https://www.bungie.net/common/destiny2_content/icons/64ea61b26a2cba84954b4b73960bef7e.jpg'
                },
                'fields': [],
                'color': 0x0a2b4c,
                'type': 'rich',
                'title': self.translations[lang]['msg']['empire_hunts'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']},
                'timestamp': resp_time
            }

            db_data = []
            for key in activities_resp['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await self.destiny.decode_hash(item_hash, definition, language=lang)
                if r_json['activityTypeHash'] == 494260690 and \
                        local_types['adept'] in r_json['displayProperties']['name']:
                    info = {
                        'inline': True,
                        'name': r_json['displayProperties']['name'].replace(local_types['adept'], "").
                            replace(local_types['empire_hunt'], "").lstrip(),
                        'value': r_json['displayProperties']['description']
                    }
                    db_data.append({
                        'name': info['name'].replace(local_types['empire_hunt'], '').replace('\"', '').lstrip(),
                        'description': info['value']
                    })
                    self.data[lang]['empire_hunts']['fields'].append(info)
            await self.write_to_db(lang, 'empire_hunts', db_data, name=self.translations[lang]['site']['empire_hunts'],
                                   order=5, type='weekly')
        await self.write_bot_data('empire_hunts', langs)

    async def get_gambit_modifiers(self, langs: List[str], forceget: bool = False) -> Union[bool, None]:
        activities_resp = await self.get_activities_response('gambit_modifiers', force=forceget)
        if not activities_resp:
            return False
        resp_time = activities_resp['timestamp']

        for lang in langs:
            local_types = self.translations[lang]
            r_json = await self.destiny.decode_hash(135431604, 'DestinyActivityDefinition', language=lang)

            self.data[lang]['gambit'] = {
                'thumbnail': {
                    'url': 'https://www.bungie.net/common/destiny2_content/icons/DestinyActivityModeDefinition_'
                           '96f7e9009d4f26e30cfd60564021925e.png'
                },
                'fields': [],
                'color': 1332799,
                'type': 'rich',
                'title': r_json['displayProperties']['name'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']},
                'timestamp': resp_time
            }

            db_data = []
            for key in activities_resp['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                if item_hash in [135431604, 1479362175, 2051483412]:
                    try:
                        key['modifierHashes'].pop(key['modifierHashes'].index(2841995557))
                    except ValueError:
                        pass
                    try:
                        key['modifierHashes'].pop(key['modifierHashes'].index(1783825372))
                    except ValueError:
                        pass
                    try:
                        key['modifierHashes'].pop(key['modifierHashes'].index(1123720291))
                    except ValueError:
                        pass
                    mods = await self.decode_modifiers(key, lang)
                    self.data[lang]['gambit']['fields'] = mods[0]
                    db_data = mods[1]
            await self.write_to_db(lang, 'gambit', db_data, name=r_json['displayProperties']['name'],
                                   order=5, type='weekly')
        await self.write_bot_data('gambit', langs)

    async def get_crucible_rotators(self, langs: List[str], forceget: bool = False) -> Union[bool, None]:
        activities_resp = await self.get_activities_response('cruciblerotators', string='crucible rotators',
                                                             force=forceget)
        if not activities_resp:
            for lang in langs:
                local_types = self.translations[lang]
                db_data = {
                    'name': self.data[lang]['cruciblerotators']['fields'][0]['name'],
                    'description': self.data[lang]['cruciblerotators']['fields'][0]['value']
                }
                await self.write_to_db(lang, 'crucible_rotators', [db_data],
                                       name=self.translations[lang]['msg']['cruciblerotators'],
                                       template='table_items.html', type='weekly')
            await self.write_bot_data('cruciblerotators', langs)
            return False
        resp_time = activities_resp['timestamp']
        for lang in langs:
            local_types = self.translations[lang]

            self.data[lang]['cruciblerotators'] = {
                'thumbnail': {
                    'url': self.icon_prefix + '/common/destiny2_content/icons/cc8e6eea2300a1e27832d52e9453a227.png'
                },
                'fields': [],
                'color': 6629649,
                'type': 'rich',
                'title': self.translations[lang]['msg']['cruciblerotators'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']},
                'timestamp': resp_time
            }

            db_data = []
            activities_json = activities_resp
            for key in activities_json['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await self.destiny.decode_hash(item_hash, definition, language=lang)
                if r_json['destinationHash'] == 4088006058:
                    if item_hash in [540869524, 3847433434, 142028034, 1683791010, 3787302650, 935998519, 1683791010, 2393304349, 1689094744, 2056796644, 3254496172, 1214397515]:
                        if not self.data[lang]['cruciblerotators']['thumbnail']['url']:
                            if 'icon' in r_json['displayProperties']:
                                self.data[lang]['cruciblerotators']['thumbnail']['url'] = self.icon_prefix + \
                                                                                          r_json[
                                                                                              'displayProperties'][
                                                                                              'icon']
                            else:
                                self.data[lang]['cruciblerotators']['thumbnail']['url'] = self.icon_prefix + \
                                                                                          '/common/destiny2_content/icons/' \
                                                                                          'cc8e6eea2300a1e27832d52e9453a227.png'
                        if 'icon' in r_json['displayProperties']:
                            icon = r_json['displayProperties']['icon']
                        else:
                            icon = '/common/destiny2_content/icons/cc8e6eea2300a1e27832d52e9453a227.png'
                        info = {
                            'inline': True,
                            "name": r_json['displayProperties']['name'],
                            "value": r_json['displayProperties']['description']
                        }
                        db_data.append({
                            'name': info['name'],
                            'description': info['value'].replace('\n\n', '<br>'),
                            'icon': icon
                        })
                        self.data[lang]['cruciblerotators']['fields'].append(info)
            if len(db_data) >= 3:
                style = 'wide tall'
            else:
                style = 'wide'
            await self.write_to_db(lang, 'crucible_rotators', db_data,
                                   name=self.translations[lang]['msg']['cruciblerotators'], size=style, order=4,
                                   type='weekly')
        await self.write_bot_data('cruciblerotators', langs)

    async def get_event_progress(self, langs: List[str], forceget: bool = False) -> Union[bool, None]:
        url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/'.format(self.char_info['platform'],
                                                                                            self.char_info[
                                                                                                'membershipid'],
                                                                                            self.char_info['charid'][0])
        progression_json = await self.get_cached_json('objectives_{}'.format(self.char_info['charid'][0]),
                                                      'progressions', url, {'components': 301}, force=forceget)
        resp_time = progression_json['timestamp']
        progress = []

        steps = ['2314235473', '3765635756', '3782413343', '3832746200', '3849523787', '3866301502', '3883079057', '3899856644', '3916634359', '3950189533']

        step = list(set(steps).intersection(set(progression_json['Response']['uninstancedItemComponents']['objectives']['data'])))

        objectives = {'589977764': 400000000, '990898098': 260000000, '2697257462': 40000000, '2957300623': 80000000, '3453628075': 320000000, '3527414433': 200000000, '4221523416': 140000000}


        if len(step) > 0:
            step = step[0]
            for lang in langs:
                quest_def = await self.destiny.decode_hash(step, 'DestinyInventoryItemDefinition', language=lang)
                self.data[lang]['events'] = {
                    'thumbnail': {
                        'url': self.icon_prefix + quest_def['displayProperties']['icon']
                    },
                    'fields': [],
                    'color': 0x226197,
                    'type': 'rich',
                    'title': quest_def['displayProperties']['name'],
                    'footer': {'text': self.translations[lang]['msg']['resp_time']},
                    'timestamp': resp_time
                }
                newrow = [resp_time, 0, 0, 0]
                names = ['', '', '']
                progression_json['Response']['uninstancedItemComponents']['objectives']['data'][str(step)][
                    'objectives'] = [progression_json['Response']['uninstancedItemComponents']['objectives']['data'][str(step)][
                    'objectives'][0]]
                for place in \
                progression_json['Response']['uninstancedItemComponents']['objectives']['data'][str(step)][
                    'objectives']:
                    objective_def = await self.destiny.decode_hash(place['objectiveHash'], 'DestinyObjectiveDefinition',
                                                                   language=lang)
                    if place['progress'] >= place['completionValue']:
                        values = list(objectives.values())
                        values.sort()
                        objective = min([i for i in values if place['progress'] < i])
                    else:
                        objective = objectives[str(place['objectiveHash'])]

                    self.data[lang]['events']['fields'].append({
                        'inline': True,
                        'name': objective_def['progressDescription'],
                        'value': '{} ({:.2f}%)'.format(place['progress'],
                                                       place['progress'] / objective * 100)
                    })
                    if str(place['objectiveHash']) in objectives.keys():
                        newrow[1] = place['progress'] / objective * 100
                        names[0] = objective_def['progressDescription']
                date = []
                edz = []
                try:
                    with open('rising_tide.csv', 'r') as csvfile:
                        plots = csv.reader(csvfile, delimiter=',')
                        for row in plots:
                            if len(row) < 4:
                                continue
                            diff = datetime.fromisoformat(row[0]) - datetime.fromisoformat('2022-11-22T17:00:00')
                            date.append(diff.total_seconds() / 86400)
                            edz.append(float(row[1]))
                        csvfile.close()
                    diff = datetime.fromisoformat(newrow[0]) - datetime.fromisoformat('2022-11-22T17:00:00')
                    date.append(diff.total_seconds() / 86400)
                    edz.append(float(newrow[1]))
                except FileNotFoundError:
                    pass
                with open('rising_tide.csv', 'a') as csvfile:
                    writer = csv.writer(csvfile, delimiter=',')
                    writer.writerow(newrow)
                    csvfile.close()
                fig = plt.figure()
                ax = plt.axes()
                for spine in ax.spines.values():
                    spine.set_visible(False)
                plt.plot(date, edz, label=names[0])
                ax.set_xlabel(self.translations[lang]['graph']['datefromstart'], color='#226197')
                ax.set_ylabel(self.translations[lang]['graph']['percentage'], color='#226197')
                ax.tick_params(colors='#bdbdff', direction='out')
                for tick in ax.get_xticklabels():
                    tick.set_color('#226197')
                for tick in ax.get_yticklabels():
                    tick.set_color('#226197')
                plt.grid(color='#bdbdff', linestyle='solid', axis='y')
                plt.legend()
                plt.savefig('events-{}.png'.format(lang), format='png', transparent=True)
                plt.close(fig)
                self.data[lang]['events']['image'] = {
                    'url': 'attachment://events-{}.png'.format(lang)
                }
            await self.write_bot_data('events', langs)

    async def decode_modifiers(self, key: dict, lang: str) -> list:
        data = []
        db_data = []
        for mod_key in key['modifierHashes']:
            mod_def = 'DestinyActivityModifierDefinition'
            mod_json = await self.destiny.decode_hash(mod_key, mod_def, lang)
            mod = {
                'inline': True,
                "name": mod_json['displayProperties']['name'],
                "value": mod_json['displayProperties']['description']
            }
            data.append(mod)
            db_data.append({
                "name": mod_json['displayProperties']['name'],
                "description": mod_json['displayProperties']['description'],
                "icon": mod_json['displayProperties']['icon']
            })

        return [data, db_data]

    async def get_activities_response(self, name: str, lang: Optional[str] = None, string: Optional[str] = None,
                                      force: bool = False) -> Union[bool, dict]:
        char_info = self.char_info
        activities = []
        hashes = set()

        for char in char_info['charid']:
            activities_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/'. \
                format(char_info['platform'], char_info['membershipid'], char)
            activities_resp = await self.get_cached_json('activities_{}'.format(char), name, activities_url,
                                                         self.activities_params, lang, string, force=force)
            if activities_resp:
                activities.append(activities_resp)
        activities_json = await self.get_cached_json('activities_{}'.format(char_info['charid'][-1]), name,
                                                     activities_url, self.activities_params, lang, string, force=force)
        if activities_json:
            activities_json['Response']['activities']['data']['availableActivities'].clear()

        if len(activities) == 0:
            return False
        else:
            if len(activities) > 0:
                for char_activities in activities:
                    for activity in char_activities['Response']['activities']['data']['availableActivities']:
                        if activity['activityHash'] not in hashes and activities_json:
                            activities_json['Response']['activities']['data']['availableActivities'].append(activity)
                            hashes.add(activity['activityHash'])
            return activities_json

    async def get_player_metric(self, membership_type: int, membership_id: int, metric: int,
                                is_global: bool = False) -> Union[int, dict]:
        url = 'https://www.bungie.net/Platform/Destiny2/{}/Profile/{}/'.format(membership_type, membership_id)
        metric_resp = await self.get_cached_json('playermetrics_{}'.format(membership_id),
                                                 'metric {} for {}'.format(metric, membership_id), url,
                                                 params=self.metric_params, change_msg=False, cache_only=is_global)
        if metric_resp:
            metric_json = metric_resp
            try:
                return metric_json['Response']['metrics']['data']['metrics'][str(metric)]['objectiveProgress'][
                    'progress']
            except KeyError:
                return -1
        else:
            return -1

    async def get_member_metric_wrapper(self, member: dict, metric: int, is_global: bool = False, tag: str = '') -> list:
        member_id = member['destinyUserInfo']['membershipId']
        member_type = member['destinyUserInfo']['membershipType']
        if member['destinyUserInfo']['bungieGlobalDisplayName'] != '' and False:
            name = '{}#{}'.format(member['destinyUserInfo']['bungieGlobalDisplayName'], member['destinyUserInfo']['bungieGlobalDisplayNameCode'])
        else:
            name = member['destinyUserInfo']['LastSeenDisplayName']
        if is_global:
            player = '{} [{}]'.format(name, tag)
        else:
            player = name
        await self.update_player_metrics(member_type, member_id, '{} [{}]'.format(name, tag))
        return [player, await self.get_player_metric(member_type, member_id, metric, is_global)]

    async def update_clan_metrics(self, clan_ids: list) -> None:
        for clan_id in clan_ids:
            url = 'https://www.bungie.net/Platform/GroupV2/{}/Members/'.format(clan_id)

            clan_members_resp = await self.get_cached_json('clanmembers_{}'.format(clan_id), 'clan members', url, change_msg=False)

            url = 'https://www.bungie.net/Platform/GroupV2/{}/'.format(clan_id)
            clan_resp = await self.get_cached_json('clan_{}'.format(clan_id), 'clan info', url)
            clan_json = clan_resp
            try:
                code = clan_json['ErrorCode']
            except KeyError:
                code = 0
            except TypeError:
                code = 0
            if code == 1:
                tag = clan_json['Response']['detail']['clanInfo']['clanCallsign']
            else:
                tag = ''

            if clan_members_resp and type(clan_json) == dict:
                clan_json = clan_members_resp
                try:
                    tasks = []
                    # member = clan_json['Response']['results'][0]
                    # name = '{} [{}]'.format(member['destinyUserInfo']['bungieGlobalDisplayName'], tag)
                    # await self.update_player_metrics(member['destinyUserInfo']['membershipType'],
                    #                                  member['destinyUserInfo']['membershipId'], name)
                    for member in clan_json['Response']['results']:
                        name = '{} [{}]'.format(member['destinyUserInfo']['bungieGlobalDisplayName'], tag)
                        task = asyncio.ensure_future(self.update_player_metrics(
                            member['destinyUserInfo']['membershipType'], member['destinyUserInfo']['membershipId'],
                            name))
                        tasks.append(task)
                    results = await asyncio.gather(*tasks)
                except KeyError:
                    pass

    async def update_player_metrics(self, membership_type: str, membership_id: str, name: str) -> None:
        cursor = await self.bot_data_db.cursor()
        url = 'https://www.bungie.net/Platform/Destiny2/{}/Profile/{}/'.format(membership_type, membership_id)
        member = await self.get_cached_json('playermetrics_{}'.format(membership_id),
                                            'metrics for {}'.format(membership_id), url, params=self.metric_params,
                                            change_msg=False)
        metrics = []
        try:
            await cursor.execute('''INSERT OR IGNORE INTO playermetrics (membershipId, timestamp) VALUES (?,?)''',
                                 (membership_id, datetime.utcnow().isoformat()))
            # await self.bot_data_db.commit()
        except aiosqlite.OperationalError:
            pass
        try:
            await cursor.execute('''UPDATE playermetrics SET name=? WHERE membershipId=?''',
                                 (name, membership_id))
            await self.bot_data_db.commit()
        except aiosqlite.OperationalError:
            pass
        if member:
            if 'data' in member['Response']['metrics'].keys():
                for metric in member['Response']['metrics']['data']['metrics'].keys():
                    try:
                        await cursor.execute('''ALTER TABLE playermetrics ADD COLUMN '{}' INTEGER'''.format(metric))
                        # await self.bot_data_db.commit()
                    except aiosqlite.OperationalError:
                        pass
                    if 'objectiveProgress' in member['Response']['metrics']['data']['metrics'][metric].keys():
                        value = member['Response']['metrics']['data']['metrics'][metric]['objectiveProgress']['progress']
                        metrics.append({
                            'name': metric,
                            'value': value
                        })
                        try:
                            await cursor.execute('''UPDATE playermetrics SET '{}'=? WHERE membershipId=?'''.format(metric), (value, membership_id))
                            # await self.bot_data_db.commit()
                        except aiosqlite.OperationalError:
                            pass
                await self.bot_data_db.commit()
        await cursor.close()
        return

    async def get_osiris_predictions(self, langs: List[str], forceget: bool = False, force_info: Optional[list] = None):
        win3_rotation = ['?', '?', 'gloves', '?', '?', 'chest', '?', '?', 'boots', '?', '?', 'helmet', '?', '?', 'class']
        # win3_rotation = ['?', '?', '?']
        win5_rotation = ['?', 'gloves', '?', '?', 'chest', '?', '?', 'boots', '?', '?', 'helmet', '?', '?', 'class', '?']
        # win5_rotation = ['?', '?', '?']
        win7_rotation = ['gloves', '?', 'chest', '?', 'boots', '?', 'helmet', '?', 'class', '?']
        # win7_rotation = ['?', '?', '?']
        # flawless_rotation = ['gloves', 'chest', 'class', 'helmet', 'boots']
        flawless_rotation = ['?', '?', '?']
        mod_rotation = ['?', '?', '?']

        def find_adept(saint_resp):
            flawless = '?'
            for item in saint_resp['Response']['sales']['data']:
                for cost in saint_resp['Response']['sales']['data'][item]['costs']:
                    if cost['quantity'] == 50000:
                        flawless = saint_resp['Response']['sales']['data'][item]['itemHash']
            return flawless

        week_n = datetime.now(tz=timezone.utc) - await self.get_season_start()
        week_n = int(week_n.days / 7)

        saint_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/765357505/'.\
            format(self.char_info['platform'], self.char_info['membershipid'], self.char_info['charid'][0])
        saint_resp = await self.get_cached_json('saint', 'saint', saint_url, self.vendor_params, force=forceget)

        if force_info is not None:
            if force_info[1] != '?':
                flawless = force_info[1]
            else:
                flawless = find_adept(saint_resp)
        else:
            flawless = find_adept(saint_resp)

        modifiers = {}
        trials_are_active = True
        # activities = await self.get_activities_response('activities')
        # for activity in activities['Response']['activities']['data']['availableActivities']:
        #     if activity['activityHash'] in [588019350, 2431109627, 4150051058]:
        #         if 1361609633 in activity['modifierHashes']:
        #             modifiers = activity
        #             modifiers['modifierHashes'] = [1361609633]
        #         trials_are_active = True
        #         break

        for lang in langs:
            db_data = []
            self.data[lang]['osiris'] = {
                'thumbnail': {
                    'url': self.icon_prefix + '/common/destiny2_content/icons/DestinyActivityModeDefinition_'
                                              'e35792b49b249ca5dcdb1e7657ca42b6.png'
                },
                'fields': [],
                'color': 0xb69460,
                'type': "rich",
                'title': self.translations[lang]['msg']['osiris'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']},
                'timestamp': datetime.utcnow().isoformat()
            }
            if not trials_are_active:
                continue
            locale = self.translations[lang]['osiris']
            if flawless != '?':
                flawless_def = await self.destiny.decode_hash(flawless, 'DestinyInventoryItemDefinition', language=lang)
            else:
                flawless_def = {
                    'displayProperties': {'name': '?'},
                    'itemTypeDisplayName': '?'
                }
            if force_info is None:
                self.data[lang]['osiris']['fields'] = [
                    {
                        'name': locale['map'],
                        'value': locale['?']
                    },
                    {
                        'name': locale['flawless'],
                        'value': '{} ({})'.format(flawless_def['displayProperties']['name'], flawless_def['itemTypeDisplayName'])
                    }
                ]
            else:
                info = []
                for parameter in force_info:
                    if isinstance(parameter, int):
                        try:
                            definition = await self.destiny.decode_hash(parameter, 'DestinyActivityDefinition', lang)
                            info.append(definition['displayProperties']['name'])
                        except pydest.PydestException:
                            try:
                                definition = await self.destiny.decode_hash(parameter, 'DestinySandboxPerkDefinition',
                                                                            lang)
                                info.append(definition['displayProperties']['name'])
                            except pydest.PydestException:
                                definition = await self.destiny.decode_hash(parameter, 'DestinyInventoryItemDefinition',
                                                                            lang)
                                info.append('{} ({})'.format(definition['displayProperties']['name'],
                                                             definition['itemTypeDisplayName']))
                    elif parameter in locale.keys():
                        info.append(locale[parameter])
                    else:
                        info.append(parameter)
                self.data[lang]['osiris']['fields'] = [
                    {
                        'name': locale['map'],
                        'value': info[0]
                    },
                    {
                        'name': locale['flawless'],
                        'value': '{} ({})'.format(flawless_def['displayProperties']['name'], flawless_def['itemTypeDisplayName'])
                    }
                ]
            if modifiers:
                mods = await self.decode_modifiers(modifiers, lang)
                self.data[lang]['osiris']['fields'].append(*mods[0])
            for field in self.data[lang]['osiris']['fields']:
                db_data.append({
                    'name': field['name'],
                    'description': field['value']
                })
            await self.write_to_db(lang, 'trials_of_osiris', db_data, order=6,
                                   name=self.translations[lang]['site']['osiris'])
        await self.write_bot_data('osiris', langs)

    async def get_lost_sector(self, langs: List[str], forceget: bool = False, force_info: Optional[list] = None) -> None:
        season_start = await self.get_season_start()
        season_number = await self.get_season_number()
        day_n = datetime.now(tz=timezone.utc) - season_start
        if season_number in lost_sector_order.keys():
            ls_hash = lost_sector_order[season_number][int(day_n.days % len(lost_sector_order[season_number]))]
            ls_loot = loot_order[season_number][day_n.days % len(loot_order[season_number])]
        else:
            ls_hash = 0
            ls_loot = '?'

        for lang in langs:
            db_data = []
            self.data[lang]['lostsector'] = {
                'thumbnail': {
                    'url': self.icon_prefix + '/common/destiny2_content/icons/DestinyActivityModeDefinition_'
                                              '7d11acd7d5a3daebc0a0c906452932d6.png'
                },
                'fields': [],
                'color': 5331575,
                'type': "rich",
                'title': self.translations[lang]['msg']['lostsector'],
                'footer': {'text': self.translations[lang]['msg']['resp_time']},
                'timestamp': datetime.utcnow().isoformat()
            }
            if ls_hash != 0:
                ls_def = await self.destiny.decode_hash(ls_hash, 'DestinyActivityDefinition', lang)
                dest_def = await self.destiny.decode_hash(ls_def['destinationHash'], 'DestinyDestinationDefinition', lang)
                dest_str = dest_def['displayProperties']['name']
            else:
                ls_def = {'displayProperties': {'name': self.translations[lang]['osiris']['?']}}
                dest_str = '?'
            loot_str = self.translations[lang]['osiris'][ls_loot]

            self.data[lang]['lostsector']['fields'].append({'name': ls_def['displayProperties']['name'].split(':')[0], 'value': '{}\n{}'.format(loot_str, dest_str)})
            db_data.append({
                'name': ls_def['displayProperties']['name'].split(':')[0],
                'description': '{}<br>{}'.format(loot_str, dest_str)
            })
            await self.write_to_db(lang, 'lost_sector', db_data, order=6,
                                   name=self.translations[lang]['site']['lostsector'])
        await self.write_bot_data('lostsector', langs)

    async def drop_weekend_info(self, langs: List[str]) -> None:
        # while True:
        #     try:
        #         data_db = self.data_pool.get_connection()
        #         data_db.auto_reconnect = True
        #         break
        #     except mariadb.PoolError:
        #         try:
        #             self.data_pool.add_connection()
        #         except mariadb.PoolError:
        #             pass
        #         await asyncio.sleep(0.125)
        # data_cursor = data_db.cursor()
        #
        # for lang in langs:
        #     data_cursor.execute('''DELETE FROM `{}` WHERE id=?'''.format(lang), ('trials_of_osiris',))
        #     data_cursor.execute('''DELETE FROM `{}` WHERE id=?'''.format(lang), ('xur',))
        #     data_cursor.execute('''DELETE FROM `{}` WHERE id=?'''.format(lang), ('gambit',))
        # data_db.commit()
        # data_cursor.close()
        # data_db.close()

        conn = await aiomysql.connect(host=self.api_data['db_host'],
                                      user=self.api_data['cache_login'],
                                      password=self.api_data['pass'], port=self.api_data['db_port'],
                                      db=self.api_data['data_db'], loop=self.ev_loop)

        cur = await conn.cursor()
        for lang in langs:
            await cur.execute('''DELETE FROM `{}` WHERE id=?'''.format(lang), ('trials_of_osiris',))
            await cur.execute('''DELETE FROM `{}` WHERE id=?'''.format(lang), ('xur',))
            await cur.execute('''DELETE FROM `{}` WHERE id=?'''.format(lang), ('gambit',))
        await conn.commit()
        await cur.close()
        conn.close()

    async def get_cached_json(self, cache_id: str, name: str, url: str, params: Optional[dict] = None,
                              lang: Optional[str] = None, string: Optional[str] = None, change_msg: bool = True,
                              force: bool = False, cache_only: bool = False, expires_in: int = 1800) -> Union[bool, dict]:
        # while True:
        #     try:
        #         cache_connection = self.cache_pool.get_connection()
        #         cache_connection.auto_reconnect = True
        #         break
        #     except mariadb.PoolError:
        #         try:
        #             self.cache_pool.add_connection()
        #         except mariadb.PoolError:
        #             pass
        #         await asyncio.sleep(0.125)
        # cache_cursor = cache_connection.cursor()
        cache_connection = self.cache_db
        cache_cursor = await cache_connection.cursor()

        try:
            await cache_cursor.execute('''SELECT json, expires, timestamp from cache WHERE id=?''', (cache_id,))
            cached_entry = await cache_cursor.fetchone()
            if cached_entry is not None:
                expired = datetime.now().timestamp() > cached_entry[1]
            else:
                expired = True
        except aiosqlite.OperationalError:
        # except mariadb.Error:
            expired = True
            if cache_only:
                await cache_cursor.close()
                # await cache_connection.close()
                return False

        if (expired or force) and not cache_only:
            response = await self.get_bungie_json(name, url, params, lang, string, change_msg)
            timestamp = datetime.utcnow().isoformat()
            if response:
                response_json = response
                try:
                    await cache_cursor.execute(
                        '''CREATE TABLE cache (id text, expires integer, json text, timestamp text);''')
                    await cache_cursor.execute('''CREATE UNIQUE INDEX cache_id ON cache(id)''')
                    await cache_cursor.execute('''INSERT OR IGNORE INTO cache VALUES (?,?,?,?)''',
                                         (cache_id, int(datetime.now().timestamp() + expires_in), json.dumps(response_json),
                                          timestamp))
                except aiosqlite.OperationalError:
                # except mariadb.Error:
                    try:
                        await cache_cursor.execute('''ALTER TABLE cache ADD COLUMN timestamp text''')
                        await cache_cursor.execute('''INSERT OR IGNORE INTO cache VALUES (?,?,?,?)''',
                                             (cache_id, int(datetime.now().timestamp() + expires_in),
                                              json.dumps(response_json), timestamp))
                    # except mariadb.Error:
                    except aiosqlite.OperationalError:
                        pass
                # try:
                await cache_cursor.execute('''INSERT OR IGNORE INTO cache VALUES (?,?,?,?)''',
                                     (cache_id, int(datetime.now().timestamp() + expires_in), json.dumps(response_json),
                                      timestamp))
                # except mariadb.Error:
                #     pass
                # try:
                await cache_cursor.execute('''UPDATE cache SET expires=?, json=?, timestamp=? WHERE id=?''',
                                     (int(datetime.now().timestamp() + expires_in), json.dumps(response_json), timestamp,
                                      cache_id))
                # except mariadb.Error:
                #     pass
            else:
                await cache_cursor.close()
                # await cache_connection.close()
                return False
        else:
            if cached_entry is not None:
                timestamp = cached_entry[2]
                response_json = json.loads(cached_entry[0])
            else:
                await cache_cursor.close()
                # await cache_connection.close()
                return False
        await cache_cursor.close()
        await cache_connection.commit()
        # await cache_connection.close()
        response_json['timestamp'] = timestamp
        return response_json

    async def get_global_leaderboard(self, metric: int, number: int, is_time: bool = False,
                                     is_kda: bool = False, is_ranking: bool = False) -> list:
        cursor = await self.bot_data_db.cursor()

        leaderboard = []

        if is_time or is_ranking:
            raw_leaderboard = await cursor.execute('''SELECT name, `{}` FROM (SELECT RANK () OVER (ORDER BY `{}` ASC) place, name, `{}` FROM playermetrics WHERE `{}`>0 ORDER BY place ASC) WHERE place<=?'''.format(metric, metric, metric, metric), (number,))
            raw_leaderboard = await raw_leaderboard.fetchall()

            if is_time:
                for place in raw_leaderboard:
                    index = raw_leaderboard.index(place)
                    leaderboard.append([raw_leaderboard[index][0], str(timedelta(minutes=(int(raw_leaderboard[index][1]) / 60000))).split('.')[0]])
            if is_ranking:
                for place in raw_leaderboard:
                    index = raw_leaderboard.index(place)
                    leaderboard.append([raw_leaderboard[index][0], raw_leaderboard[index][1]])
        else:
            raw_leaderboard = await cursor.execute('''SELECT name, `{}` FROM (SELECT RANK () OVER (ORDER BY `{}` DESC) place, name, `{}` FROM playermetrics WHERE `{}`>0 ORDER BY place ASC) WHERE place<=?'''.format(metric, metric, metric, metric), (number,))
            raw_leaderboard = await raw_leaderboard.fetchall()

            if is_kda:
                for place in raw_leaderboard:
                    index = raw_leaderboard.index(place)
                    leaderboard.append([raw_leaderboard[index][0], raw_leaderboard[index][1] / 100])
            else:
                for place in raw_leaderboard:
                    index = raw_leaderboard.index(place)
                    leaderboard.append([raw_leaderboard[index][0], raw_leaderboard[index][1]])
        await cursor.close()

        if len(leaderboard) > 0:
            for place in leaderboard[1:]:
                delta = 0
                try:
                    index = leaderboard.index(place)
                except ValueError:
                    continue
                if leaderboard[index][1] == leaderboard[index - 1][1]:
                    leaderboard[index][0] = '{}\n{}'.format(leaderboard[index - 1][0], leaderboard[index][0])
                    leaderboard.pop(index - 1)
            indexed_list = leaderboard.copy()
            i = 1
            for place in indexed_list:
                old_i = i
                index = indexed_list.index(place)
                indexed_list[index] = [i, *indexed_list[index]]
                i = i + len(indexed_list[index][1].splitlines())
            while indexed_list[-1][0] > number:
                indexed_list.pop(-1)

            return indexed_list
        else:
            return leaderboard

    async def get_clan_leaderboard(self, clan_ids: list, metric: int, number: int, is_time: bool = False,
                                   is_kda: bool = False, is_ranking: bool = False, is_global: bool = False) -> list:
        metric_list = []
        for clan_id in clan_ids:
            url = 'https://www.bungie.net/Platform/GroupV2/{}/Members/'.format(clan_id)

            clan_members_resp = await self.get_cached_json('clanmembers_{}'.format(clan_id), 'clan members', url, change_msg=False,
                                                           cache_only=is_global)

            url = 'https://www.bungie.net/Platform/GroupV2/{}/'.format(clan_id)
            clan_resp = await self.get_cached_json('clan_{}'.format(clan_id), 'clan info', url)
            clan_json = clan_resp
            try:
                code = clan_json['ErrorCode']
            except KeyError:
                code = 0
            except TypeError:
                code = 0
            if code == 1:
                tag = clan_json['Response']['detail']['clanInfo']['clanCallsign']
            else:
                tag = ''

            if clan_members_resp and type(clan_json) == dict:
                clan_json = clan_members_resp
                if 'Response' in clan_json.keys():
                    if 'results' in clan_json['Response'].keys():
                        tasks = []
                        for member in clan_json['Response']['results']:
                            task = asyncio.ensure_future(self.get_member_metric_wrapper(member, metric, is_global, tag))
                            tasks.append(task)
                        results = await asyncio.gather(*tasks)
                        metric_list = [*metric_list, *results]

        if len(metric_list) > 0:
            try:
                if is_time or is_ranking:
                    metric_list.sort(reverse=False, key=lambda x: x[1])
                    while metric_list[0][1] <= 0:
                        metric_list.pop(0)
                else:
                    metric_list.sort(reverse=True, key=lambda x: x[1])
                    while metric_list[-1][1] <= 0:
                        metric_list.pop(-1)
            except IndexError:
                return []

            for place in metric_list[1:]:
                delta = 0
                try:
                    index = metric_list.index(place)
                except ValueError:
                    continue
                if metric_list[index][1] == metric_list[index - 1][1]:
                    metric_list[index][0] = '{}\n{}'.format(metric_list[index - 1][0], metric_list[index][0])
                    metric_list.pop(index - 1)

            indexed_list = metric_list.copy()
            i = 1
            for place in indexed_list:
                old_i = i
                index = indexed_list.index(place)
                indexed_list[index] = [i, *indexed_list[index]]
                i = i + len(indexed_list[index][1].splitlines())
            while indexed_list[-1][0] > number:
                indexed_list.pop(-1)
            if is_time:
                for place in indexed_list:
                    index = indexed_list.index(place)
                    indexed_list[index][2] = str(timedelta(minutes=(indexed_list[index][2] / 60000))).split('.')[0]
            if is_kda:
                for place in indexed_list:
                    index = indexed_list.index(place)
                    indexed_list[index][2] = indexed_list[index][2] / 100

            return indexed_list[:old_i]
        else:
            return metric_list

    async def get_last_activity(self, member: dict, lang: str):
        status_change = datetime.fromtimestamp(float(member['lastOnlineStatusChange']))
        now = datetime.utcnow()

        membership_id = member['destinyUserInfo']['membershipId']
        membership_type = member['destinyUserInfo']['membershipType']
        url = 'https://www.bungie.net/Platform/Destiny2/{}/Profile/{}/'.format(membership_type,
                                                                               membership_id)
        profile_resp = await self.get_bungie_json('playeractivity_{}'.format(membership_id),
                                                  url, params={'components': 204}, change_msg=False)
        activity_string = ''
        if profile_resp:
            try:
                test = profile_resp['Response']['characterActivities']['data']
            except KeyError:
                return [member['destinyUserInfo']['LastSeenDisplayName'], '-']
            for char in profile_resp['Response']['characterActivities']['data']:
                char_resp = profile_resp['Response']['characterActivities']['data'][char]
                try:
                    if char_resp['currentActivityHash'] != 0:
                        activity = await self.destiny.decode_hash(char_resp['currentActivityHash'],
                                                                  'DestinyActivityDefinition', language=lang)
                        try:
                            activity_mode = await self.destiny.decode_hash(char_resp['currentActivityModeHash'],
                                                                           'DestinyActivityModeDefinition', language=lang)
                        except pydest.PydestException:
                            activity_mode = {'displayProperties': {'name': ''}}
                        activity_type = await self.destiny.decode_hash(activity['activityTypeHash'],
                                                                       'DestinyActivityTypeDefinition', language=lang)
                        place = await self.destiny.decode_hash(activity['placeHash'], 'DestinyPlaceDefinition',
                                                               language=lang)
                        if activity['activityTypeHash'] in [332181804] and char_resp['currentActivityHash'] not in [
                            82913930]:
                            activity_string = activity['displayProperties']['name']
                        elif char_resp['currentActivityHash'] in [82913930]:
                            activity_string = place['displayProperties']['name']
                        elif activity['activityTypeHash'] in [4088006058, 2371050408]:
                            activity_string = '{}: {}: {}'.format(activity_type['displayProperties']['name'],
                                                                  activity_mode['displayProperties']['name'],
                                                                  activity['displayProperties']['name'])
                        elif activity['activityTypeHash'] in [4110605575, 1686739444, 248695599, 2043403989, 2112637710] \
                                and char_resp['currentActivityModeHash'] not in [2166136261]:
                            activity_string = '{}: {}'.format(activity_mode['displayProperties']['name'],
                                                              activity['displayProperties']['name'])
                        elif activity['activityTypeHash'] in [3497767639]:
                            activity_string = '{}: {}'.format(activity_mode['displayProperties']['name'],
                                                              place['displayProperties']['name'])
                        else:
                            activity_string = '{}'.format(activity['displayProperties']['name'])
                        break
                except pydest.PydestException:
                    activity_string = '???'
            length = now - datetime.fromisoformat(char_resp['dateActivityStarted'].replace('Z', ''))
            activity_string = '{} ({})'.format(activity_string, str(timedelta(seconds=length.seconds)))
        else:
            activity_string = '-'
        return [member['destinyUserInfo']['LastSeenDisplayName'], activity_string]

    async def get_online_clan_members(self, clan_id: Union[str, int], lang: str) -> list:
        url = 'https://www.bungie.net/Platform/GroupV2/{}/Members/'.format(clan_id)

        clan_members_resp = await self.get_cached_json('clanmembers_{}'.format(clan_id), 'clan members', url,
                                                       change_msg=False, force=True)

        header = [[self.translations[lang]['online']['nick'], self.translations[lang]['online']['since']]]
        if clan_members_resp:
            tasks = []
            for member in clan_members_resp['Response']['results']:
                if member['isOnline']:
                    task = asyncio.ensure_future(self.get_last_activity(member, lang))
                    tasks.append(task)
            online_members = await asyncio.gather(*tasks)
            online_members = [*header, *online_members]
        else:
            online_members = [[self.translations[lang]['online']['error'], self.translations[lang]['online']['error_t']]]
        return online_members

    async def iterate_clans(self, max_id: int) -> Union[int, str]:
        # while True:
        #     try:
        #         cache_connection = self.cache_pool.get_connection()
        #         cache_connection.auto_reconnect = True
        #         break
        #     except mariadb.PoolError:
        #         try:
        #             self.cache_pool.add_connection()
        #         except mariadb.PoolError:
        #             pass
        #         await asyncio.sleep(0.125)
        # clan_cursor = cache_connection.cursor()
        cache_connection = await aiomysql.connect(host=self.api_data['db_host'],
                                      user=self.api_data['cache_login'],
                                      password=self.api_data['pass'], port=self.api_data['db_port'],
                                      db=self.api_data['cache_name'], loop=self.ev_loop)
        clan_cursor = await cache_connection.cursor()

        min_id = 1
        try:
            await clan_cursor.execute('''CREATE TABLE clans (id INTEGER, json JSON)''')
            await cache_connection.commit()
        except aiomysql.OperationalError:
            # clan_cursor = clan_db.cursor()
            await clan_cursor.execute('''SELECT id FROM clans ORDER by id DESC''')
            min_id_tuple = await clan_cursor.fetchall()
            if len(min_id_tuple) > 0:
                min_id = min_id_tuple[0][0] + 1
        for clan_id in range(min_id, max_id+1):
            url = 'https://www.bungie.net/Platform/GroupV2/{}/'.format(clan_id)
            clan_resp = await self.get_cached_json('clan_{}'.format(clan_id), '{} clan info'.format(clan_id), url,
                                                   expires_in=86400)
            clan_json = clan_resp

            if not clan_json:
                continue
                # clan_cursor.close()
                # cache_connection.close()
                # return 'unable to fetch clan {}'.format(clan_id)
            try:
                code = clan_json['ErrorCode']
                # print('{} ec {}'.format(clan_id, clan_json['ErrorCode']))
            except KeyError:
                code = 0
                await clan_cursor.close()
                cache_connection.close()
                return '```{}```'.format(json.dumps(clan_json))
            if code in [621, 622, 686]:
                continue
            if code != 1:
                await clan_cursor.close()
                cache_connection.close()
                return code
            # print('{} {}'.format(clan_id, clan_json['Response']['detail']['features']['capabilities'] & 16))
            if clan_json['Response']['detail']['features']['capabilities'] & 16:
                await clan_cursor.execute('''INSERT INTO clans VALUES (%s,%s)''', (clan_id, json.dumps(clan_json)))
                await cache_connection.commit()
        await clan_cursor.close()
        cache_connection.close()
        return 'Finished'

    async def iterate_clans_new(self, max_id: int) -> Union[int, str]:
        # tracemalloc.start()
        # snapshot1 = tracemalloc.take_snapshot()
        # while True:
        #     try:
        #         cache_connection = self.cache_pool.get_connection()
        #         cache_connection.auto_reconnect = True
        #         break
        #     except mariadb.PoolError:
        #         try:
        #             self.cache_pool.add_connection()
        #         except mariadb.PoolError:
        #             pass
        #         await asyncio.sleep(0.125)
        # clan_cursor = cache_connection.cursor()
        # cache_connection = self.cache_db
        cache_connection = await aiomysql.connect(host=self.api_data['db_host'],
                                                  user=self.api_data['cache_login'],
                                                  password=self.api_data['pass'], port=self.api_data['db_port'],
                                                  db=self.api_data['cache_name'], loop=self.ev_loop)
        clan_cursor = await cache_connection.cursor()

        min_id = 1
        try:
            await clan_cursor.execute('''CREATE TABLE clans (id INTEGER, json JSON)''')
            # clan_db.commit()
        # except mariadb.Error:
        except aiomysql.OperationalError:
            # clan_cursor = clan_db.cursor()
            await clan_cursor.execute('''SELECT id FROM clans ORDER by id DESC''')
            min_id_tuple = await clan_cursor.fetchall()
            if min_id_tuple is not None:
                min_id = min_id_tuple[0][0] + 1

        ranges = list(range(min_id, max_id, 1000))
        if max(ranges) != max_id:
            ranges.append(max_id)
        for max_id_ranged in ranges[1:]:
            min_id = ranges[ranges.index(max_id_ranged) - 1]
            max_id = max_id_ranged
            tasks = []
            for clan_id in range(min_id, max_id+1):
                task = asyncio.ensure_future(self.get_cached_json('clan_{}'.format(clan_id), '{} clan info'.format(clan_id),
                                                                  'https://www.bungie.net/Platform/GroupV2/{}/'.
                                                                  format(clan_id), expires_in=86400))
                tasks.append(task)

            responses = await asyncio.gather(*tasks)

            a = ''
            for clan_json in responses:
                if not clan_json:
                    continue
                    # clan_cursor.close()
                    # cache_connection.close()
                    # return 'unable to fetch clan {}'.format(clan_id)
                try:
                    code = clan_json['ErrorCode']
                    # print('{} ec {}'.format(clan_id, clan_json['ErrorCode']))
                except KeyError:
                    code = 0
                    await clan_cursor.close()
                    # await cache_connection.close()
                    return '```{}```'.format(json.dumps(clan_json))
                if code in [621, 622, 686]:
                    continue
                if code != 1:
                    await clan_cursor.close()
                    # await cache_connection.close()
                    return code
                # print('{} {}'.format(clan_id, clan_json['Response']['detail']['features']['capabilities'] & 16))
                if clan_json['Response']['detail']['features']['capabilities'] & 16:
                    clan_id = clan_json['Response']['detail']['groupId']
                    await clan_cursor.execute('''INSERT INTO clans VALUES (%s,%s)''', (clan_id, json.dumps(clan_json)))
                    await cache_connection.commit()
                    # clan_db.commit()

        await clan_cursor.close()
        cache_connection.close()
        # await cache_connection.close()
        # snapshot2 = tracemalloc.take_snapshot()
        # top_stats = snapshot2.compare_to(snapshot1, 'lineno')
        # print(top_stats)
        return 'Finished'

    async def fetch_players(self) -> str:
        clan_db = mariadb.connect(host=self.api_data['db_host'], user=self.api_data['cache_login'],
                                  password=self.api_data['pass'], port=self.api_data['db_port'],
                                  database=self.api_data['cache_name'])
        clan_cursor = clan_db.cursor()

        try:
            clan_cursor.execute('''CREATE TABLE clans (id INTEGER, json JSON)''')
            # clan_db.commit()
        except mariadb.Error:
            clan_cursor.execute('''SELECT id FROM clans ORDER by id DESC''')
            min_id_tuple = clan_cursor.fetchall()
            if min_id_tuple is not None:
                min_id = min_id_tuple[0][0] + 1
            for clan_id_tuple in min_id_tuple:
                clan_id = clan_id_tuple[0]
                url = 'https://www.bungie.net/Platform/GroupV2/{}/'.format(clan_id)
                clan_resp = await self.get_cached_json('clan_{}'.format(clan_id), '{} clan check'.format(clan_id), url,
                                                       expires_in=86400)
                clan_json = clan_resp
                try:
                    code = clan_json['ErrorCode']
                except KeyError:
                    continue
                if code in [622, 621]:
                    try:
                        clan_cursor.execute('''DELETE FROM clans WHERE id=?''', (clan_id,))
                        # clan_db.commit()
                    except mariadb.Error:
                        pass
        clan_db.close()
        return 'Finished'

    async def token_update(self) -> Union[bool, None]:
        # check to see if token.json exists, if not we have to start with oauth
        try:
            f = open('token.json', 'r')
        except FileNotFoundError:
            if self.is_oauth:
                self.oauth.get_oauth()
            else:
                print('token file not found!  run the script with --oauth or add a valid token.js file!')
                return False

        try:
            f = open('token.json', 'r')
            self.token = json.loads(f.read())
        except json.decoder.JSONDecodeError:
            if self.is_oauth:
                self.oauth.get_oauth()
            else:
                print('token file invalid!  run the script with --oauth or add a valid token.js file!')
                return False

        # check if token has expired, if so we have to oauth, if not just refresh the token
        if self.token['expires'] < time.time():
            if self.is_oauth:
                self.oauth.get_oauth()
            else:
                print('refresh token expired!  run the script with --oauth or add a valid token.js file!')
                return False
        else:
            await self.refresh_token(self.token['refresh'])
