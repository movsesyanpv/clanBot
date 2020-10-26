import json
import time
from urllib.parse import quote
import pydest
from bs4 import BeautifulSoup
from bungied2auth import BungieOAuth
from datetime import datetime, timezone, timedelta
from dateutil.parser import *
import aiohttp
import sqlite3
import matplotlib.pyplot as plt
import csv
import codecs
import mariadb
import asyncio


class D2data:
    api_data_file = open('api.json', 'r')
    api_data = json.loads(api_data_file.read())
    destiny = ''

    cache_db = ''

    data_db = ''

    icon_prefix = "https://www.bungie.net"

    token = {}

    headers = {}

    data = {}

    wait_codes = [1672]
    max_retries = 10

    vendor_params = {
        'components': '400,401,402'
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

    def __init__(self, translations, lang, is_oauth, prod, context, **options):
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
        try:
            self.cache_pool = mariadb.ConnectionPool(pool_name='cache', pool_size=10, pool_reset_connection=False,
                                                     host=self.api_data['db_host'], user=self.api_data['cache_login'],
                                                     password=self.api_data['pass'], port=self.api_data['db_port'],
                                                     database=self.api_data['cache_name'])
            # self.cache_pool.pool_reset_connection = True
        except mariadb.ProgrammingError:
            pass
        # self.cache_db.auto_reconnect = True
        try:
            self.data_pool = mariadb.ConnectionPool(pool_name='data', pool_size=10, pool_reset_connection=False,
                                                    host=self.api_data['db_host'], user=self.api_data['cache_login'],
                                                    password=self.api_data['pass'], port=self.api_data['db_port'],
                                                    database=self.api_data['data_db'])
            # self.data_pool.pool_reset_connection = True
        except mariadb.ProgrammingError:
            pass
        # self.data_db.auto_reconnect = True

    async def get_chars(self):
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

    async def refresh_token(self, re_token):
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

    async def get_bungie_json(self, name, url, params=None, lang=None, string=None, change_msg=True):
        if lang is None:
            lang = list(self.data.keys())
            lang_str = ''
        else:
            lang_str = lang
        if string is None:
            string = str(name)
        try:
            resp = await self.session.get(url, params=params, headers=self.headers)
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
            return False
        except aiohttp.ContentTypeError:
            if change_msg:
                for locale in lang:
                    self.data[locale][name] = self.data[locale]['api_is_down']
            return False
        print('getting {} {}'.format(string, lang_str))
        curr_try = 2
        while resp_code in self.wait_codes and curr_try <= self.max_retries:
            print('{}, attempt {}'.format(resp_code, curr_try))
            resp = await self.session.get(url, params=params, headers=self.headers)
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
                return False
            resp_code = resp_code['ErrorCode']
            if resp_code in [5, 1618]:
                if change_msg:
                    for locale in lang:
                        self.data[locale][name] = self.data[locale]['api_maintenance']
                return False
            print("{} get error".format(name), json.dumps(resp.json(), indent=4, sort_keys=True) + "\n")
            if change_msg:
                for locale in lang:
                    self.data[locale][name] = self.data[locale]['api_is_down']
            return False
        else:
            try:
                resp_code = await resp.json()
            except aiohttp.ContentTypeError:
                if change_msg:
                    for locale in lang:
                        self.data[locale][name] = self.data[locale]['api_is_down']
                return False
            if 'ErrorCode' in resp_code.keys():
                resp_code = resp_code['ErrorCode']
                if resp_code == 5:
                    if change_msg:
                        for locale in lang:
                            self.data[locale][name] = self.data[locale]['api_maintenance']
                    return False
            else:
                for suspected_season in resp_code:
                    if 'seasonNumber' in resp_code[suspected_season].keys():
                        return resp_code
            resp_code = await resp.json()
            if 'Response' not in resp_code.keys():
                if change_msg:
                    for locale in lang:
                        self.data[locale][name] = self.data[locale]['api_is_down']
                return False
        return await resp.json()

    async def get_vendor_sales(self, lang, vendor_resp, cats, exceptions=[]):
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
                cost_line = cost_line[:-1]
                item_data = {
                    'inline': True,
                    'name': item_name.capitalize(),
                    'value': cost_line
                }
                data_sales.append({
                    'id': '{}_{}_{}'.format(item['itemHash'], key, n_order),
                    'name': item_name.capitalize(),
                    'icon': item_resp['displayProperties']['icon'],
                    'description': cost_line.replace('\n', '<br>'),
                    'tooltip_id': '{}_{}_{}_tooltip'.format(item['itemHash'], key, n_order),
                    'costs': costs
                })
                embed_sales.append(item_data)
                n_order += 1
        return [embed_sales, data_sales]

    async def get_featured_bd(self, langs, forceget=False):
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

    async def get_bd(self, langs, forceget=False):
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

    async def get_featured_silver(self, langs, forceget=False):
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

    async def get_global_alerts(self, langs, forceget=False):
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

    async def get_season_start(self):
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
                pass

    async def get_seasonal_featured_bd(self, langs, start):
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
                if item['displayCategoryIndex'] == 4 and item['itemHash'] not in [353932628, 3260482534, 3536420626,
                                                                                  3187955025, 2638689062]:
                    definition = 'DestinyInventoryItemDefinition'
                    item_def = await self.destiny.decode_hash(item['itemHash'], definition, language=lang)
                    currency_resp = await self.destiny.decode_hash(item['currencies'][0]['itemHash'], definition,
                                                                   language=lang)
                    cat_number = 4
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

    async def get_seasonal_bd(self, langs, start):
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
                if n_items >= 7 and n_items - class_items/3*2 >= 7:
                    i_week = i_week + 1
                    bd.append(list.copy(curr_week))
                    n_items = 0
                    curr_week = []
                    class_items = 0
                if item['displayCategoryIndex'] == 9 and item['itemHash'] not in [353932628, 3260482534, 3536420626,
                                                                                  3187955025, 2638689062]:
                    definition = 'DestinyInventoryItemDefinition'
                    item_def = await self.destiny.decode_hash(item['itemHash'], definition, language=lang)
                    currency_resp = await self.destiny.decode_hash(item['currencies'][0]['itemHash'], definition,
                                                                   language=lang)
                    cat_number = 9
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

    async def get_weekly_eververse(self, langs):
        data = []
        start = await self.get_season_start()
        week_n = datetime.now(tz=timezone.utc) - await self.get_season_start()
        week_n = int(week_n.days / 7)
        for lang in langs:
            data.clear()
            bd = await self.get_seasonal_bd([lang], start)
            featured_bd = await self.get_seasonal_featured_bd([lang], start)
            # await self.get_seasonal_consumables(langs, start)
            # await self.get_seasonal_featured_silver(langs, start)
            if len(bd) == len(featured_bd):
                for i in range(0, len(bd)):
                    data.append({
                        'items': [*bd[i], *featured_bd[i]]
                    })

                await self.write_to_db(lang, 'weekly_eververse', data[week_n]['items'],
                                       name=self.translations[lang]['site']['bd'],
                                       template='hover_items.html', order=2, type='weekly')

    async def write_to_db(self, lang, id, response, size='', name='', template='table_items.html', order=0, type='daily'):
        while True:
            try:
                data_db = self.data_pool.get_connection()
                data_db.auto_reconnect = True
                break
            except mariadb.PoolError:
                try:
                    self.data_pool.add_connection()
                except mariadb.PoolError:
                    pass
                await asyncio.sleep(0.125)
        data_cursor = data_db.cursor()

        try:
            data_cursor.execute('''CREATE TABLE `{}` (id text, timestamp_int integer, json json, timestamp text, size text, name text, template text, place integer, type text)'''.format(lang))
            data_cursor.execute('''CREATE UNIQUE INDEX `data_id_{}` ON `{}`(id(256))'''.format(lang, lang))
        except mariadb.Error:
            pass

        try:
            data_cursor.execute('''INSERT IGNORE INTO `{}` VALUES (?,?,?,?,?,?,?,?,?)'''.format(lang),
                                (id, datetime.utcnow().timestamp(), json.dumps({'data': response}),
                                 datetime.utcnow().isoformat(), size, name, template, order, type))
            data_db.commit()
        except mariadb.Error:
            pass

        try:
            data_cursor.execute('''UPDATE `{}` SET timestamp_int=?, json=?, timestamp=?, name=?, size=?, template=?, place=?, type=? WHERE id=?'''.format(lang),
                                (datetime.utcnow().timestamp(), json.dumps({'data': response}),
                                 datetime.utcnow().isoformat(), name, size, template, order, type, id))
            data_db.commit()
        except mariadb.Error:
            pass
        data_cursor.close()
        data_db.close()

    async def get_spider(self, lang, forceget=False):
        char_info = self.char_info

        spider_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/863940356/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'][0])
        spider_resp = await self.get_cached_json('spider', 'spider', spider_url, self.vendor_params, force=forceget)
        if not spider_resp:
            for locale in lang:
                db_data = {
                    'name': self.data[locale]['spider']['fields'][0]['name'],
                    'description': self.data[locale]['spider']['fields'][0]['value']
                }
                await self.write_to_db(locale, 'spider_mats', [db_data],
                                       name=self.translations[locale]['site']['spider'])
            return False
        spider_json = spider_resp
        spider_cats = spider_json['Response']['categories']['data']['categories']
        resp_time = spider_json['timestamp']
        for locale in lang:
            spider_def = await self.destiny.decode_hash(863940356, 'DestinyVendorDefinition', language=locale)

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

            spider_sales = await self.get_vendor_sales(locale, spider_resp, items_to_get, [1812969468])
            self.data[locale]['spider']['fields'] = self.data[locale]['spider']['fields'] + spider_sales[0]
            data = spider_sales[1]
            await self.write_to_db(locale, 'spider_mats', data, name=self.translations[locale]['site']['spider'],
                                   order=0, size='tall')

    async def get_banshee(self, lang, forceget=False):
        char_info = self.char_info

        banshee_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/672118013/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'][0])
        banshee_resp = await self.get_cached_json('banshee', 'banshee', banshee_url, self.vendor_params, force=forceget)
        if not banshee_resp:
            for locale in lang:
                banshee_def = await self.destiny.decode_hash(672118013, 'DestinyVendorDefinition', language=locale)
                db_data = {
                    'name': self.data[locale]['spider']['fields'][0]['name'],
                    'description': self.data[locale]['spider']['fields'][0]['value']
                }
                await self.write_to_db(locale, 'spider_mats', [db_data], name=banshee_def['displayProperties']['name'])
            return False
        banshee_json = banshee_resp
        banshee_cats = banshee_json['Response']['categories']['data']['categories']
        resp_time = banshee_json['timestamp']
        for locale in lang:
            banshee_def = await self.destiny.decode_hash(672118013, 'DestinyVendorDefinition', language=locale)

            # self.data[locale]['spider'] = {
            #     'thumbnail': {
            #         'url': self.icon_prefix + banshee_def['displayProperties']['smallTransparentIcon']
            #     },
            #     'fields': [],
            #     'color': 7102001,
            #     'type': "rich",
            #     'title': self.translations[locale]['msg']['spider'],
            #     'footer': {'text': self.translations[locale]['msg']['resp_time']},
            #     'timestamp': resp_time
            # }

            items_to_get = banshee_cats[2]['itemIndexes']

            banshee_sales = await self.get_vendor_sales(locale, banshee_resp, items_to_get, [1812969468])
            # self.data[locale]['spider']['fields'] = self.data[locale]['spider']['fields'] + banshee_sales[0]
            data = banshee_sales[1]
            await self.write_to_db(locale, 'banshee_mods', data, name=banshee_def['displayProperties']['name'], order=5,
                                   template='hover_items.html')
                             # size='tall')

    async def get_xur_loc(self):
        url = 'https://wherethefuckisxur.com/'
        r = await self.session.get(url)
        r_text = await r.text()
        soup = BeautifulSoup(r_text, features="html.parser")
        modifier_list = soup.find('div', {'class': 'xur-location'})
        loc = modifier_list.find('h1', {'class': 'page-title'})
        location = loc.text.split(' >')
        return location[0]

    async def get_xur(self, langs, forceget=False):
        char_info = self.char_info

        xur_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/2190858386/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'][0])
        xur_resp = await self.get_cached_json('xur', 'xur', xur_url, self.vendor_params, force=forceget)
        if not xur_resp:
            return False
        resp_time = xur_resp['timestamp']
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
                try:
                    loc_field['value'] = self.translations[lang]['xur'][await self.get_xur_loc()]
                    self.data[lang]['xur']['fields'].append(loc_field)
                except:
                    pass
                xur_sales = xur_json['Response']['sales']['data']

                self.data[lang]['xur']['fields'].append(weapon)

                for key in sorted(xur_sales.keys()):
                    item_hash = xur_sales[key]['itemHash']
                    if item_hash not in [4285666432, 2293314698]:
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

                            if item_resp['classType'] == 0:
                                exotic['name'] = self.translations[lang]['Titan']
                            elif item_resp['classType'] == 1:
                                exotic['name'] = self.translations[lang]['Hunter']
                            elif item_resp['classType'] == 2:
                                exotic['name'] = self.translations[lang]['Warlock']

                            self.data[lang]['xur']['fields'].append(exotic)
                        else:
                            i = 0
                            for item in self.data[lang]['xur']['fields']:
                                if item['name'] == self.translations[lang]['msg']['weapon']:
                                    self.data[lang]['xur']['fields'][i]['value'] = item_name
                                i += 1
            else:
                loc_field = {
                    "inline": False,
                    "name": self.translations[lang]['msg']['xurloc'],
                    "value": self.translations[lang]['xur']['noxur']
                }
                self.data[lang]['xur']['fields'].append(loc_field)

    async def get_heroic_story(self, langs, forceget=False):
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

    async def get_forge(self, langs, forceget=False):
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

    async def get_strike_modifiers(self, langs, forceget=False):
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
            for key in activities_json['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await self.destiny.decode_hash(item_hash, definition, language=lang)

                if local_types['heroicstory'] in r_json['displayProperties']['name']:
                    mods = await self.decode_modifiers(key, lang)
                    self.data[lang]['vanguardstrikes']['fields'] = mods[0]
                    db_data = mods[1]
                if self.translations[lang]['strikes'] in r_json['displayProperties']['name']:
                    self.data[lang]['vanguardstrikes']['thumbnail']['url'] = self.icon_prefix + \
                                                                             r_json['displayProperties']['icon']
            await self.write_to_db(lang, 'strike_modifiers', db_data, size='wide',
                                   name=self.translations[lang]['msg']['strikesmods'], order=1)

    async def get_reckoning_boss(self, lang):
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

    def add_reckoning_boss(self, lang):
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

    async def get_reckoning_modifiers(self, langs, forceget=False):
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

    async def get_nightfall820(self, langs, forceget=False):
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

    async def get_modifiers(self, lang, act_hash):
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

    async def get_raids(self, langs, forceget=False):
        activities_resp = await self.get_activities_response('raids', force=forceget)
        if not activities_resp:
            for lang in langs:
                db_data = {
                    'name': self.data[lang]['raids']['fields'][0]['name'],
                    'description': self.data[lang]['raids']['fields'][0]['value']
                }
                await self.write_to_db(lang, 'raid_challenges', [db_data], self.translations[lang]['msg']['raids'],
                                       type='weekly')
            return False
        resp_time = activities_resp['timestamp']
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

            hawthorne_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/3347378076/'. \
                format(self.char_info['platform'], self.char_info['membershipid'], self.char_info['charid'][0])
            hawthorne_resp = await self.get_cached_json('hawthorne', 'hawthorne', hawthorne_url, self.vendor_params,
                                                        force=forceget)
            if not hawthorne_resp:
                return
            hawthorne_json = hawthorne_resp
            resp_time = hawthorne_json['timestamp']
            for cat in hawthorne_json['Response']['sales']['data']:
                if hawthorne_json['Response']['sales']['data'][cat]['itemHash'] in last_wish_challenges:
                    lw_ch = hawthorne_json['Response']['sales']['data'][cat]['itemHash']
                elif hawthorne_json['Response']['sales']['data'][cat]['itemHash'] in sotp_challenges:
                    sotp_ch = hawthorne_json['Response']['sales']['data'][cat]['itemHash']
                elif hawthorne_json['Response']['sales']['data'][cat]['itemHash'] in cos_challenges:
                    cos_ch = hawthorne_json['Response']['sales']['data'][cat]['itemHash']

            db_data = []
            activities_json = activities_resp
            for key in activities_json['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await self.destiny.decode_hash(item_hash, definition, language=lang)
                i = 1
                if str(r_json['hash']) in self.translations[lang]['levi_order'] and \
                        not r_json['matchmaking']['requiresGuardianOath']:
                    challenges = await self.get_modifiers(lang, item_hash)
                    if challenges:
                        challenge = set(challenges[0]['name'].lower().replace('"', '').split(' '))
                        challenge.discard('the')
                        order_strings = self.translations[lang]['levi_order'][str(r_json['hash'])].splitlines()
                        levi_str = ''
                        for string in order_strings:
                            intersection = challenge.intersection(set(string.lower().split(' ')))
                            if intersection:
                                levi_str = '{}<b>{}</b>\n'.format(levi_str, string)
                            else:
                                levi_str = '{}{}\n'.format(levi_str, string)
                        levi_str = levi_str[:-1]
                    else:
                        levi_str = self.translations[lang]['levi_order'][str(r_json['hash'])]
                    info = {
                        'inline': True,
                        'name': r_json['originalDisplayProperties']['name'],
                        'value': levi_str.replace('<b>', '**').replace('</b>', '**')
                    }
                    db_data.append({
                        'name': info['name'],
                        'description': levi_str.replace('\n', '<br>')
                    })
                    self.data[lang]['raids']['fields'].append(info)
                if self.translations[lang]["EoW"] in r_json['displayProperties']['name'] and \
                        not r_json['matchmaking']['requiresGuardianOath']:
                    info = {
                        'inline': False,
                        'name': self.translations[lang]['lairs'],
                        'value': u"\u2063"
                    }
                    mods = await self.get_modifiers(lang, r_json['hash'])
                    resp_time = datetime.utcnow().isoformat()
                    if mods:
                        loadout = '{}\n{}\n{}'.format(self.translations[lang]['armsmaster'][eow_loadout*3],
                                                      self.translations[lang]['armsmaster'][eow_loadout*3+1],
                                                      self.translations[lang]['armsmaster'][eow_loadout*3+2])
                        info['value'] = '{}: {}\n\n{}:\n{}'.format(mods[0]['name'], mods[0]['description'],
                                                                   mods[1]['name'], loadout)
                    else:
                        info['value'] = self.data[lang]['api_is_down']['fields'][0]['name']
                    db_data.append({
                        'name': info['name'],
                        'description': info['value'].replace('\n\n', '<br>').replace('\n', '<br>')
                    })
                    self.data[lang]['raids']['fields'].append(info)
                if self.translations[lang]['LW'] in r_json['displayProperties']['name'] and \
                        not r_json['matchmaking']['requiresGuardianOath'] and lw_ch != 0:
                    info = {
                        'inline': True,
                        'name': r_json['originalDisplayProperties']['name'],
                        'value': u"\u2063"
                    }
                    curr_challenge = lw_ch
                    curr_challenge = await self.destiny.decode_hash(curr_challenge, 'DestinyInventoryItemDefinition',
                                                                    language=lang)
                    info['value'] = curr_challenge['displayProperties']['name']
                    db_data.append({
                        'name': info['name'],
                        'description': info['value'].replace('\n', '<br>')
                    })
                    self.data[lang]['raids']['fields'].append(info)
                if self.translations[lang]['SotP'] in r_json['displayProperties']['name'] and \
                        not r_json['matchmaking']['requiresGuardianOath'] and sotp_ch != 0:
                    info = {
                        'inline': True,
                        'name': r_json['originalDisplayProperties']['name'],
                        'value': u"\u2063"
                    }
                    curr_challenge = sotp_ch
                    curr_challenge = await self.destiny.decode_hash(curr_challenge, 'DestinyInventoryItemDefinition',
                                                                    language=lang)
                    info['value'] = curr_challenge['displayProperties']['name']
                    db_data.append({
                        'name': info['name'],
                        'description': info['value'].replace('\n', '<br>')
                    })
                    self.data[lang]['raids']['fields'].append(info)
                if self.translations[lang]['CoS'] in r_json['displayProperties']['name'] and \
                        not r_json['matchmaking']['requiresGuardianOath'] and cos_ch != 0:
                    info = {
                        'inline': True,
                        'name': r_json['originalDisplayProperties']['name'],
                        'value': u"\u2063"
                    }
                    curr_challenge = cos_ch
                    curr_challenge = await self.destiny.decode_hash(curr_challenge, 'DestinyInventoryItemDefinition',
                                                                    language=lang)
                    info['value'] = curr_challenge['displayProperties']['name']
                    db_data.append({
                        'name': info['name'],
                        'description': info['value'].replace('\n', '<br>')
                    })
                    self.data[lang]['raids']['fields'].append(info)
                if self.translations[lang]['GoS'] in r_json['displayProperties']['name'] and \
                        not r_json['matchmaking']['requiresGuardianOath']:
                    info = {
                        'inline': True,
                        'name': r_json['originalDisplayProperties']['name'],
                        'value': u"\u2063"
                    }
                    mods = await self.get_modifiers(lang, r_json['hash'])
                    resp_time = datetime.utcnow().isoformat()
                    if mods:
                        info['value'] = mods[0]['name']
                    else:
                        info['value'] = self.data[lang]['api_is_down']['fields'][0]['name']
                    db_data.append({
                        'name': info['name'],
                        'description': info['value'].replace('\n', '<br>')
                    })
                    self.data[lang]['raids']['fields'].append(info)
            self.data[lang]['raids']['timestamp'] = resp_time
            await self.write_to_db(lang, 'raid_challenges', db_data, 'wide tall',
                                   self.translations[lang]['msg']['raids'], order=1, type='weekly')

    async def get_ordeal(self, langs, forceget=False):
        activities_resp = await self.get_activities_response('ordeal', force=forceget)
        if not activities_resp:
            for lang in langs:
                db_data = {
                    'name': self.data[lang]['ordeal']['fields'][0]['name'],
                    'description': self.data[lang]['ordeal']['fields'][0]['value']
                }
                await self.write_to_db(lang, 'ordeal', [db_data], name=self.translations[lang]['msg']['ordeal'],
                                       type='weekly')
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
                'title': self.translations[lang]['msg']['ordeal'],
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
                if local_types['ordeal'] in r_json['displayProperties']['name'] and \
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

            if len(self.data[lang]['ordeal']['fields']) > 0:
                for strike in strikes:
                    if strike['name'] in self.data[lang]['ordeal']['fields'][0]['name']:
                        self.data[lang]['ordeal']['fields'][0]['value'] = strike['description']
                        db_data[0]['description'] = strike['description']
                        break
            await self.write_to_db(lang, 'ordeal', db_data, name=self.translations[lang]['msg']['ordeal'], order=5,
                                   type='weekly')

    async def get_nightmares(self, langs, forceget=False):
        activities_resp = await self.get_activities_response('nightmares', force=forceget)
        if not activities_resp:
            for lang in langs:
                db_data = {
                    'name': self.data[lang]['nightmares']['fields'][0]['name'],
                    'description': self.data[lang]['nightmares']['fields'][0]['value']
                }
                await self.write_to_db(lang, 'nigtmare_hunts', [db_data],
                                       name=self.translations[lang]['site']['nightmares'], type='weekly')
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
                                   order=3, type='weekly')

    async def get_crucible_rotators(self, langs, forceget=False):
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
                if r_json['destinationHash'] == 2777041980:
                    if len(r_json['challenges']) > 0:
                        obj_def = 'DestinyObjectiveDefinition'
                        objective = await self.destiny.decode_hash(r_json['challenges'][0]['objectiveHash'], obj_def,
                                                                   lang)
                        if self.translations[lang]['rotator'] in objective['displayProperties']['name'] or r_json['challenges'][0]['objectiveHash'] == 1607758693:
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

    async def get_the_lie_progress(self, langs, forceget=True):
        url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/'.format(self.char_info['platform'],
                                                                                            self.char_info[
                                                                                                'membershipid'],
                                                                                            self.char_info['charid'][0])
        progression_json = await self.get_cached_json('objectives_{}'.format(self.char_info['charid'][0]),
                                                      'progressions', url, {'components': 301}, force=forceget)
        resp_time = progression_json['timestamp']
        progress = []

        if '1797229574' in progression_json['Response']['uninstancedItemComponents']['objectives']['data']:
            for lang in langs:
                quest_def = await self.destiny.decode_hash(1797229574, 'DestinyInventoryItemDefinition', language=lang)
                self.data[lang]['thelie'] = {
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
                for place in \
                progression_json['Response']['uninstancedItemComponents']['objectives']['data']['1797229574'][
                    'objectives']:
                    objective_def = await self.destiny.decode_hash(place['objectiveHash'], 'DestinyObjectiveDefinition',
                                                                   language=lang)
                    if place['complete']:
                        self.data[lang]['thelie']['fields'].append({
                            'inline': True,
                            'name': objective_def['progressDescription'],
                            'value': self.translations[lang]['msg']['complete']
                        })
                        if place['objectiveHash'] == 1851115127:
                            newrow[1] = 100
                            names[0] = objective_def['progressDescription']
                        elif place['objectiveHash'] == 1851115126:
                            newrow[2] = 100
                            names[1] = objective_def['progressDescription']
                        elif place['objectiveHash'] == 1851115125:
                            newrow[3] = 100
                            names[2] = objective_def['progressDescription']
                    else:
                        self.data[lang]['thelie']['fields'].append({
                            'inline': True,
                            'name': objective_def['progressDescription'],
                            'value': '{} ({:.2f}%)'.format(place['progress'],
                                                           place['progress'] / place['completionValue'] * 100)
                        })
                        if place['objectiveHash'] == 1851115127:
                            newrow[1] = place['progress'] / place['completionValue'] * 100
                            names[0] = objective_def['progressDescription']
                        elif place['objectiveHash'] == 1851115126:
                            newrow[2] = place['progress'] / place['completionValue'] * 100
                            names[1] = objective_def['progressDescription']
                        elif place['objectiveHash'] == 1851115125:
                            newrow[3] = place['progress'] / place['completionValue'] * 100
                            names[2] = objective_def['progressDescription']
                date = []
                edz = []
                moon = []
                io = []
                with open('thelie.csv', 'r') as csvfile:
                    plots = csv.reader(csvfile, delimiter=',')
                    for row in plots:
                        if len(row) < 4:
                            continue
                        diff = datetime.fromisoformat(row[0]) - datetime.fromisoformat('2020-05-12T17:00:00')
                        date.append(diff.total_seconds() / 86400)
                        edz.append(float(row[1]))
                        moon.append(float(row[2]))
                        io.append(float(row[3]))
                    csvfile.close()
                diff = datetime.fromisoformat(newrow[0]) - datetime.fromisoformat('2020-05-12T17:00:00')
                date.append(diff.total_seconds() / 86400)
                edz.append(float(newrow[1]))
                moon.append(float(newrow[2]))
                io.append(float(newrow[3]))
                with open('thelie.csv', 'a') as csvfile:
                    writer = csv.writer(csvfile, delimiter=',')
                    writer.writerow(newrow)
                    csvfile.close()
                fig = plt.figure()
                ax = plt.axes()
                for spine in ax.spines.values():
                    spine.set_visible(False)
                plt.plot(date, edz, label=names[0])
                plt.plot(date, moon, label=names[1])
                plt.plot(date, io, label=names[2])
                ax.set_xlabel(self.translations[lang]['graph']['datefromstart'], color='#226197')
                ax.set_ylabel(self.translations[lang]['graph']['percentage'], color='#226197')
                ax.tick_params(colors='#bdbdff', direction='out')
                for tick in ax.get_xticklabels():
                    tick.set_color('#226197')
                for tick in ax.get_yticklabels():
                    tick.set_color('#226197')
                plt.grid(color='#bdbdff', linestyle='solid', axis='y')
                plt.legend()
                plt.savefig('thelie-{}.png'.format(lang), format='png', transparent=True)
                plt.close(fig)
                self.data[lang]['thelie']['image'] = {
                    'url': 'attachment://thelie-{}.png'.format(lang)
                }

    async def decode_modifiers(self, key, lang):
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

    async def get_activities_response(self, name, lang=None, string=None, force=False):
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

    async def get_player_metric(self, membership_type, membership_id, metric, is_global=False):
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

    async def get_member_metric_wrapper(self, member, metric, is_global=False):
        member_id = member['destinyUserInfo']['membershipId']
        member_type = member['destinyUserInfo']['membershipType']
        return [member['destinyUserInfo']['LastSeenDisplayName'],
                await self.get_player_metric(member_type, member_id, metric, is_global)]

    async def get_osiris_predictions(self, langs, forceget=False, force_info = None):
        win3_rotation = ['?', '?', 'gloves', '?', '?', 'chest', '?', '?', 'boots', '?', '?', 'helmet', '?', '?', 'class']
        win5_rotation = ['?', '?', 'gloves', '?', '?', 'chest', '?', '?', 'boots', '?', '?', 'helmet', '?', '?', 'class']
        win7_rotation = ['?', 'gloves', '?', 'chest', '?', 'boots', '?', 'helmet', '?', 'class']
        flawless_rotation = ['gloves', 'chest', 'class', 'helmet', 'boots']

        week_n = datetime.now(tz=timezone.utc) - await self.get_season_start()
        week_n = int(week_n.days / 7)

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
            locale = self.translations[lang]['osiris']
            if force_info is None:
                self.data[lang]['osiris']['fields'] = [
                    {
                        'name': locale['map'],
                        'value': locale['?']
                    },
                    {
                        'name': locale['3win'],
                        'value': '{}?'.format(locale[win3_rotation[int((week_n - 1 if week_n > 0 else week_n) % len(win3_rotation))]])
                    },
                    {
                        'name': locale['5win'],
                        'value': '{}?'.format(locale[win5_rotation[int(week_n % len(win5_rotation))]])
                    },
                    {
                        'name': locale['7win'],
                        'value': '{}?'.format(locale[win7_rotation[int(week_n % len(win7_rotation))]])
                    },
                    {
                        'name': locale['flawless'],
                        'value': '{}?'.format(locale[flawless_rotation[int(week_n % len(flawless_rotation))]])
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
                            definition = await self.destiny.decode_hash(parameter, 'DestinyCollectibleDefinition', lang)
                            for parent in definition['parentNodeHashes']:
                                if str(parent) in self.translations[lang]['weapon_types'].keys():
                                    info.append('{} ({})'.format(definition['displayProperties']['name'], self.translations[lang]['weapon_types'][str(parent)]))
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
                        'name': locale['3win'],
                        'value': info[1]
                    },
                    {
                        'name': locale['5win'],
                        'value': info[2]
                    },
                    {
                        'name': locale['7win'],
                        'value': info[3]
                    },
                    {
                        'name': locale['flawless'],
                        'value': info[4]
                    }
                ]
            for field in self.data[lang]['osiris']['fields']:
                db_data.append({
                    'name': field['name'],
                    'description': field['value']
                })
            await self.write_to_db(lang, 'trials_of_osiris', db_data, order=5,
                                   name=self.translations[lang]['site']['osiris'])

    async def drop_osiris(self, langs):
        while True:
            try:
                data_db = self.data_pool.get_connection()
                data_db.auto_reconnect = True
                break
            except mariadb.PoolError:
                try:
                    self.data_pool.add_connection()
                except mariadb.PoolError:
                    pass
                await asyncio.sleep(0.125)
        data_cursor = data_db.cursor()

        for lang in langs:
            data_cursor.execute('''DELETE FROM `{}` WHERE id=?'''.format(lang), ('trials_of_osiris',))
        data_db.commit()
        data_cursor.close()
        data_db.close()

    async def get_cached_json(self, cache_id, name, url, params=None, lang=None, string=None, change_msg=True,
                              force=False, cache_only=False, expires_in=1800):
        while True:
            try:
                cache_connection = self.cache_pool.get_connection()
                cache_connection.auto_reconnect = True
                break
            except mariadb.PoolError:
                try:
                    self.cache_pool.add_connection()
                except mariadb.PoolError:
                    pass
                await asyncio.sleep(0.125)
        cache_cursor = cache_connection.cursor()

        try:
            cache_cursor.execute('''SELECT json, expires, timestamp from cache WHERE id=?''', (cache_id,))
            cached_entry = cache_cursor.fetchone()
            if cached_entry is not None:
                expired = datetime.now().timestamp() > cached_entry[1]
            else:
                expired = True
        except mariadb.Error:
            expired = True
            if cache_only:
                cache_cursor.close()
                cache_connection.close()
                return False

        if (expired or force) and not cache_only:
            response = await self.get_bungie_json(name, url, params, lang, string, change_msg)
            timestamp = datetime.utcnow().isoformat()
            if response:
                response_json = response
                try:
                    cache_cursor.execute(
                        '''CREATE TABLE cache (id text, expires integer, json text, timestamp text);''')
                    cache_cursor.execute('''CREATE UNIQUE INDEX cache_id ON cache(id(256))''')
                    cache_cursor.execute('''INSERT IGNORE INTO cache VALUES (?,?,?,?)''',
                                         (cache_id, int(datetime.now().timestamp() + expires_in), json.dumps(response_json),
                                          timestamp))
                except mariadb.Error:
                    try:
                        cache_cursor.execute('''ALTER TABLE cache ADD COLUMN timestamp text''')
                        cache_cursor.execute('''INSERT IGNORE INTO cache VALUES (?,?,?,?)''',
                                             (cache_id, int(datetime.now().timestamp() + expires_in),
                                              json.dumps(response_json), timestamp))
                    except mariadb.Error:
                        pass
                # try:
                cache_cursor.execute('''INSERT IGNORE INTO cache VALUES (?,?,?,?)''',
                                     (cache_id, int(datetime.now().timestamp() + expires_in), json.dumps(response_json),
                                      timestamp))
                # except mariadb.Error:
                #     pass
                # try:
                cache_cursor.execute('''UPDATE cache SET expires=?, json=?, timestamp=? WHERE id=?''',
                                     (int(datetime.now().timestamp() + expires_in), json.dumps(response_json), timestamp,
                                      cache_id))
                # except mariadb.Error:
                #     pass
            else:
                cache_cursor.close()
                cache_connection.close()
                return False
        else:
            if cached_entry is not None:
                timestamp = cached_entry[2]
                response_json = json.loads(cached_entry[0])
            else:
                cache_cursor.close()
                cache_connection.close()
                return False
        cache_cursor.close()
        cache_connection.commit()
        cache_connection.close()
        response_json['timestamp'] = timestamp
        return response_json

    async def get_clan_leaderboard(self, clan_ids, metric, number, is_time=False, is_kda=False, is_global=False):
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
                try:
                    for member in clan_json['Response']['results']:
                        metric_list.append(await self.get_member_metric_wrapper(member, metric, is_global))
                        if is_global:
                            metric_list[-1][0] = '{} [{}]'.format(metric_list[-1][0], tag)
                except KeyError:
                    pass

        if len(metric_list) > 0:
            try:
                if is_time:
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

    async def iterate_clans(self, max_id):
        clan_db = mariadb.connect(host=self.api_data['db_host'], user=self.api_data['cache_login'],
                                  password=self.api_data['pass'], port=self.api_data['db_port'],
                                  database=self.api_data['cache_name'])
        clan_cursor = clan_db.cursor()

        min_id = 1
        try:
            clan_cursor.execute('''CREATE TABLE clans (id INTEGER, json JSON)''')
            # clan_db.commit()
        except mariadb.Error:
            # clan_cursor = clan_db.cursor()
            clan_cursor.execute('''SELECT id FROM clans ORDER by id DESC''')
            min_id_tuple = clan_cursor.fetchall()
            if min_id_tuple is not None:
                min_id = min_id_tuple[0][0] + 1
        for clan_id in range(min_id, max_id+1):
            url = 'https://www.bungie.net/Platform/GroupV2/{}/'.format(clan_id)
            clan_resp = await self.get_cached_json('clan_{}'.format(clan_id), '{} clan info'.format(clan_id), url,
                                                   expires_in=86400)
            clan_json = clan_resp

            if not clan_json:
                clan_db.close()
                return 'unable to fetch clan {}'.format(clan_id)
            try:
                code = clan_json['ErrorCode']
                # print('{} ec {}'.format(clan_id, clan_json['ErrorCode']))
            except KeyError:
                code = 0
                clan_db.close()
                return '```{}```'.format(json.dumps(clan_json))
            if code in [621, 622, 686]:
                continue
            if code != 1:
                clan_db.close()
                return code
            # print('{} {}'.format(clan_id, clan_json['Response']['detail']['features']['capabilities'] & 16))
            if clan_json['Response']['detail']['features']['capabilities'] & 16:
                clan_cursor.execute('''INSERT INTO clans VALUES (?,?)''', (clan_id, json.dumps(clan_json)))
                # clan_db.commit()
        clan_db.close()
        return 'Finished'

    async def fetch_players(self):
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

    async def token_update(self):
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
