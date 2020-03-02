import requests
import json
import time
from urllib.parse import quote
import pydest
from bs4 import BeautifulSoup
from bungied2auth import BungieOAuth
from datetime import datetime, timezone, timedelta
from dateutil.parser import *


class D2data:
    api_data_file = open('api.json', 'r')
    api_data = json.loads(api_data_file.read())

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
            self.oauth = BungieOAuth(self.api_data['id'], self.api_data['secret'], context=context, host='0.0.0.0', port='4200')
        else:
            self.oauth = BungieOAuth(self.api_data['id'], self.api_data['secret'], host='localhost', port='4200')

    def get_chars(self):
        platform = 0
        membership_id = ''
        try:
            char_file = open('char.json', 'r')
            self.char_info = json.loads(char_file.read())
        except FileNotFoundError:
            valid_input = False
            while not valid_input:
                print("What platform are you playing on?")
                print("1. Xbox")
                print("2. Playstation")
                print("3. Steam")
                platform = int(input())
                if 3 >= platform >= 1:
                    valid_input = True
            platform = str(platform)
            self.char_info['platform'] = platform

            valid_input = False
            while not valid_input:
                name = input("What's the name of your account on there? (include # numbers): ")
                search_url = 'https://www.bungie.net/platform/Destiny2/SearchDestinyPlayer/' + str(
                    platform) + '/' + quote(
                    name) + '/'
                search_resp = requests.get(search_url, headers=self.headers)
                search = search_resp.json()['Response']
                if len(search) > 0:
                    valid_input = True
                    membership_id = search[0]['membershipId']
                    self.char_info['membershipid'] = membership_id

            # get the first character and just roll with that
            char_search_url = 'https://www.bungie.net/platform/Destiny2/' + platform + '/Profile/' + membership_id + '/'
            char_search_params = {
                'components': '200'
            }
            char_search_resp = requests.get(char_search_url, params=char_search_params, headers=self.headers)
            chars = char_search_resp.json()['Response']['characters']['data']
            char_ids = []
            for key in sorted(chars.keys()):
                char_ids.append(chars[key]['characterId'])
            self.char_info['charid'] = char_ids

            char_file = open('char.json', 'w')
            char_file.write(json.dumps(self.char_info))

    # refresh the saved token
    def refresh_token(self, re_token):
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        params = {
            'grant_type': 'refresh_token',
            'refresh_token': re_token,
            'client_id': self.api_data['id'],
            'client_secret': self.api_data['secret']
        }
        r = requests.post('https://www.bungie.net/platform/app/oauth/token/', data=params, headers=headers)
        while not r:
            print("re_token get error", json.dumps(r.json(), indent=4, sort_keys=True) + "\n")
            r = requests.post('https://www.bungie.net/platform/app/oauth/token/', data=params, headers=headers)
            if not r:
                if not r.json()['error_description'] == 'DestinyThrottledByGameServer':
                    break
            time.sleep(5)
        if not r:
            print("re_token get error", json.dumps(r.json(), indent=4, sort_keys=True) + "\n")
            return
        resp = r.json()

        # save new refresh_token/expiration in token.json
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

    def get_bungie_json(self, name, url, params, lang):
        try:
            resp = requests.get(url, params=params, headers=self.headers)
        except:
            self.data[lang][name] = self.data[lang]['api_is_down']
            return False
        try:
            resp_code = resp.json()['ErrorCode']
        except KeyError:
            resp_code = 1
        print('getting {} {}'.format(name, lang))
        curr_try = 2
        while resp_code in self.wait_codes and curr_try <= self.max_retries:
            print('{}, attempt {}'.format(resp_code, curr_try))
            resp = requests.get(url, params=params, headers=self.headers)
            resp_code = resp.json()['ErrorCode']
            if resp_code == 5:
                self.data[lang][name] = self.data[lang]['api_maintenance']
                curr_try -= 1
            curr_try += 1
            time.sleep(5)
        if not resp:
            resp_code = resp.json()['ErrorCode']
            if resp_code == 5:
                self.data[lang][name] = self.data[lang]['api_maintenance']
                return resp
            print("{} get error".format(name), json.dumps(resp.json(), indent=4, sort_keys=True) + "\n")
            self.data[lang][name] = self.data[lang]['api_is_down']
            return resp
        return resp

    async def get_vendor_sales(self, lang, vendor_resp, cats, exceptions=[]):
        destiny = pydest.Pydest(self.headers['X-API-Key'])

        embed_sales = []

        tess_sales = vendor_resp.json()['Response']['sales']['data']
        for key in cats:
            item = tess_sales[str(key)]
            item_hash = item['itemHash']
            if item_hash not in exceptions:
                currency = item['costs'][0]
                definition = 'DestinyInventoryItemDefinition'
                item_resp = await destiny.decode_hash(item_hash, definition, language=lang)
                currency_resp = await destiny.decode_hash(currency['itemHash'], definition, language=lang)

                item_name_list = item_resp['displayProperties']['name'].split()
                item_name = ' '.join(item_name_list)
                currency_cost = str(currency['quantity'])
                currency_item = currency_resp['displayProperties']['name']

                item_data = {
                    'inline': True,
                    'name': item_name.capitalize(),
                    'value': "{}: {} {}".format(self.translations[lang]['msg']['cost'], currency_cost,
                                                currency_item.capitalize())
                }
                embed_sales.append(item_data)
        await destiny.close()
        return embed_sales

    async def get_featured_bd(self, langs):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        for lang in langs:
            tess_def = await destiny.decode_hash(3361454721, 'DestinyVendorDefinition', language=lang)
            self.data[lang]['featured_bd'] = {
                'thumbnail': {
                    'url': self.icon_prefix + tess_def['displayProperties']['smallTransparentIcon']
                },
                'fields': [],
                'color': 0x38479F,
                'type': "rich",
                'title': self.translations[lang]['msg']['featured_bd'],
            }

            char_info = self.char_info

            tmp_fields = []
            for char in char_info["charid"]:
                tess_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/3361454721/'. \
                    format(char_info['platform'], char_info['membershipid'], char)
                tess_resp = self.get_bungie_json('featured bright dust for {}'.format(char), tess_url, self.vendor_params, lang)
                if not tess_resp:
                    await destiny.close()
                    return
                tess_cats = tess_resp.json()['Response']['categories']['data']['categories']

                items_to_get = tess_cats[3]['itemIndexes']  # 5 - featured silver, 3 - featured BD, 4, 11 - BD items
                tmp_fields = tmp_fields + await self.get_vendor_sales(lang, tess_resp, items_to_get, [353932628, 3260482534, 3536420626])

            for i in range(0, len(tmp_fields)):
                if tmp_fields[i] not in tmp_fields[i+1:]:
                    self.data[lang]['featured_bd']['fields'].append(tmp_fields[i])

        await destiny.close()

    async def get_bd(self, langs):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        for lang in langs:
            tess_def = await destiny.decode_hash(3361454721, 'DestinyVendorDefinition', language=lang)
            self.data[lang]['bd'] = {
                'thumbnail': {
                    'url': self.icon_prefix + tess_def['displayProperties']['smallTransparentIcon']
                },
                'fields': [],
                'color': 0x38479F,
                'type': "rich",
                'title': self.translations[lang]['msg']['bd'],
            }

            char_info = self.char_info

            tmp_fields = []
            for char in char_info["charid"]:
                tess_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/3361454721/'. \
                    format(char_info['platform'], char_info['membershipid'], char)
                tess_resp = self.get_bungie_json('bright dust for {}'.format(char), tess_url, self.vendor_params, lang)
                if not tess_resp:
                    await destiny.close()
                    return
                tess_cats = tess_resp.json()['Response']['categories']['data']['categories']

                items_to_get = tess_cats[4]['itemIndexes'] + tess_cats[11]['itemIndexes']
                tmp_fields = tmp_fields + await self.get_vendor_sales(lang, tess_resp, items_to_get, [353932628, 3260482534, 3536420626])

            for i in range(0, len(tmp_fields)):
                if tmp_fields[i] not in tmp_fields[i+1:]:
                    self.data[lang]['bd']['fields'].append(tmp_fields[i])

        await destiny.close()

    async def get_featured_silver(self, langs):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        for lang in langs:
            tess_def = await destiny.decode_hash(3361454721, 'DestinyVendorDefinition', language=lang)
            self.data[lang]['silver'] = {
                'thumbnail': {
                    'url': self.icon_prefix + tess_def['displayProperties']['smallTransparentIcon']
                },
                'fields': [],
                'color': 0x38479F,
                'type': "rich",
                'title': self.translations[lang]['msg']['silver'],
            }

            char_info = self.char_info

            tmp_fields = []
            for char in char_info["charid"]:
                tess_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/3361454721/'. \
                    format(char_info['platform'], char_info['membershipid'], char)
                tess_resp = self.get_bungie_json('featured silver for {}'.format(char), tess_url, self.vendor_params, lang)
                if not tess_resp:
                    await destiny.close()
                    return
                tess_cats = tess_resp.json()['Response']['categories']['data']['categories']

                items_to_get = tess_cats[5]['itemIndexes']  # 5 - featured silver, 3 - featured BD, 4, 11 - BD items
                tmp_fields = tmp_fields + await self.get_vendor_sales(lang, tess_resp, items_to_get, [827183327])

            for i in range(0, len(tmp_fields)):
                if tmp_fields[i] not in tmp_fields[i+1:]:
                    self.data[lang]['silver']['fields'].append(tmp_fields[i])

        await destiny.close()

    async def get_seasonal_eververse(self, langs):
        start = self.get_season_start()
        await self.get_seasonal_bd(langs, start)
        await self.get_seasonal_consumables(langs, start)
        await self.get_seasonal_featured_bd(langs, start)
        await self.get_seasonal_featured_silver(langs, start)

        for lang in langs:
            for i in range(0, len(self.data[lang]['seasonal_consumables'])):
                self.data[lang]['seasonal_eververse'].append(self.data[lang]['seasonal_silver'][i])
                self.data[lang]['seasonal_eververse'].append(self.data[lang]['seasonal_featured_bd'][i])
                self.data[lang]['seasonal_eververse'].append(self.data[lang]['seasonal_bd'][i])
                self.data[lang]['seasonal_eververse'].append(self.data[lang]['seasonal_consumables'][i])

    def get_season_start(self):
        manifest_url = 'https://www.bungie.net/Platform/Destiny2/Manifest/'
        manifest_json = self.get_bungie_json('default', manifest_url, {}, '')
        season_url = 'https://www.bungie.net{}'.format(manifest_json.json()['Response']['jsonWorldComponentContentPaths']['en']['DestinySeasonDefinition'])
        season_json = self.get_bungie_json('default', season_url, {}, '').json()

        for season in season_json:
            try:
                start = isoparse(season_json[season]['startDate'])
                end = isoparse(season_json[season]['endDate'])
                if start <= datetime.now(tz=timezone.utc) <= end:
                    current_season = season
                    return start
            except KeyError:
                pass

    async def get_seasonal_featured_silver(self, langs, start):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        tess_def = await destiny.decode_hash(3361454721, 'DestinyVendorDefinition')

        for lang in langs:
            self.data[lang]['seasonal_silver'].clear()

            data = {
                'thumbnail': {
                    'url': self.icon_prefix + tess_def['displayProperties']['smallTransparentIcon']
                },
                'fields': [],
                'color': 0x38479F,
                'type': "rich",
                'title': self.translations[lang]['msg']['silver'],
            }

            n_items = 0
            curr_week = dict.copy(data)
            i_week = 1
            class_items = 0
            for i, item in enumerate(tess_def['itemList']):
                if n_items >= 5 and n_items - class_items / 3 * 2 >= 5:
                    curr_week['title'] = '{}{} {}'.format(self.translations[lang]['msg']['silver'],
                                                          self.translations[lang]['msg']['week'], i_week)
                    curr_week['timestamp'] = datetime.utcfromtimestamp(start.timestamp() + (i_week - 1) * 604800).isoformat()
                    i_week = i_week + 1
                    self.data[lang]['seasonal_silver'].append(dict.copy(curr_week))
                    n_items = 0
                    curr_week['fields'] = []
                    class_items = 0
                if item['displayCategoryIndex'] == 3 and item['itemHash'] != 827183327:
                    definition = 'DestinyInventoryItemDefinition'
                    next_def = await destiny.decode_hash(tess_def['itemList'][i + 1]['itemHash'], definition, language=lang)
                    item_def = await destiny.decode_hash(item['itemHash'], definition, language=lang)
                    currency_resp = await destiny.decode_hash(item['currencies'][0]['itemHash'], definition, language=lang)
                    currency_cost = str(item['currencies'][0]['quantity'])
                    currency_item = currency_resp['displayProperties']['name']
                    item_data = {
                        'inline': True,
                        'name': item_def['displayProperties']['name'],
                        'value': "{}: {} {}".format(self.translations[lang]['msg']['cost'], currency_cost,
                                                    currency_item.capitalize())
                    }
                    curr_week['fields'].append(item_data)
                    n_items = n_items + 1
                    if item_def['classType'] < 3 or any(
                            class_name in item_def['itemTypeDisplayName'].lower() for class_name in
                            ['hunter', 'warlock', 'titan']):
                        class_items = class_items + 1
        await destiny.close()

    async def get_seasonal_featured_bd(self, langs, start):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        tess_def = await destiny.decode_hash(3361454721, 'DestinyVendorDefinition')

        for lang in langs:
            self.data[lang]['seasonal_featured_bd'].clear()

            data = {
                'thumbnail': {
                    'url': self.icon_prefix + tess_def['displayProperties']['smallTransparentIcon']
                },
                'fields': [],
                'color': 0x38479F,
                'type': "rich",
                'title': self.translations[lang]['msg']['featured_bd']
            }

            n_items = 0
            curr_week = dict.copy(data)
            i_week = 1
            class_items = 0
            for i, item in enumerate(tess_def['itemList']):
                if n_items >= 4 and n_items - class_items / 3 * 2 >= 4:
                    curr_week['title'] = '{}{} {}'.format(self.translations[lang]['msg']['featured_bd'],
                                                          self.translations[lang]['msg']['week'], i_week)
                    curr_week['timestamp'] = datetime.utcfromtimestamp(start.timestamp() + (i_week - 1) * 604800).isoformat()
                    i_week = i_week + 1
                    self.data[lang]['seasonal_featured_bd'].append(dict.copy(curr_week))
                    n_items = 0
                    curr_week['fields'] = []
                    class_items = 0
                if item['displayCategoryIndex'] == 4 and item['itemHash'] not in [353932628, 3260482534, 3536420626]:
                    definition = 'DestinyInventoryItemDefinition'
                    next_def = await destiny.decode_hash(tess_def['itemList'][i + 1]['itemHash'], definition, language=lang)
                    item_def = await destiny.decode_hash(item['itemHash'], definition, language=lang)
                    currency_resp = await destiny.decode_hash(item['currencies'][0]['itemHash'], definition, language=lang)
                    currency_cost = str(item['currencies'][0]['quantity'])
                    currency_item = currency_resp['displayProperties']['name']
                    item_data = {
                        'inline': True,
                        'name': item_def['displayProperties']['name'],
                        'value': "{}: {} {}".format(self.translations[lang]['msg']['cost'], currency_cost,
                                                    currency_item.capitalize())
                    }
                    curr_week['fields'].append(item_data)
                    n_items = n_items + 1
                    if item_def['classType'] < 3 or any(
                            class_name in item_def['itemTypeDisplayName'].lower() for class_name in
                            ['hunter', 'warlock', 'titan']):
                        class_items = class_items + 1
        await destiny.close()

    async def get_seasonal_consumables(self, langs, start):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        tess_def = await destiny.decode_hash(3361454721, 'DestinyVendorDefinition')

        for lang in langs:
            self.data[lang]['seasonal_consumables'].clear()

            data = {
                'thumbnail': {
                    'url': self.icon_prefix + tess_def['displayProperties']['smallTransparentIcon']
                },
                'fields': [],
                'color': 0x38479F,
                'type': "rich",
                'title': self.translations[lang]['msg']['bd_consumables'],
            }

            n_items = 0
            curr_week = dict.copy(data)
            i_week = 1
            class_items = 0
            for i, item in enumerate(tess_def['itemList']):
                if n_items >= 4 and n_items - class_items / 3 * 2 >= 4:
                    curr_week['title'] = '{}{} {}'.format(self.translations[lang]['msg']['bd_consumables'],
                                                          self.translations[lang]['msg']['week'], i_week)
                    curr_week['timestamp'] = datetime.utcfromtimestamp(start.timestamp() + (i_week - 1) * 604800).isoformat()
                    i_week = i_week + 1
                    self.data[lang]['seasonal_consumables'].append(dict.copy(curr_week))
                    n_items = 0
                    curr_week['fields'] = []
                    class_items = 0
                if item['displayCategoryIndex'] == 10 and item['itemHash'] not in [353932628, 3260482534, 3536420626]:
                    definition = 'DestinyInventoryItemDefinition'
                    next_def = await destiny.decode_hash(tess_def['itemList'][i + 1]['itemHash'], definition, language=lang)
                    item_def = await destiny.decode_hash(item['itemHash'], definition, language=lang)
                    currency_resp = await destiny.decode_hash(item['currencies'][0]['itemHash'], definition, language=lang)
                    currency_cost = str(item['currencies'][0]['quantity'])
                    currency_item = currency_resp['displayProperties']['name']
                    item_data = {
                        'inline': True,
                        'name': item_def['displayProperties']['name'],
                        'value': "{}: {} {}".format(self.translations[lang]['msg']['cost'], currency_cost,
                                                    currency_item.capitalize())
                    }
                    curr_week['fields'].append(item_data)
                    n_items = n_items + 1
                    if item_def['classType'] < 3 or any(
                            class_name in item_def['itemTypeDisplayName'].lower() for class_name in
                            ['hunter', 'warlock', 'titan']):
                        class_items = class_items + 1
        await destiny.close()

    async def get_seasonal_bd(self, langs, start):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        tess_def = await destiny.decode_hash(3361454721, 'DestinyVendorDefinition')

        for lang in langs:
            self.data[lang]['seasonal_bd'].clear()

            data = {
                'thumbnail': {
                    'url': self.icon_prefix + tess_def['displayProperties']['smallTransparentIcon']
                },
                'fields': [],
                'color': 0x38479F,
                'type': "rich",
                'title': self.translations[lang]['msg']['bd'],
            }

            n_items = 0
            curr_week = dict.copy(data)
            i_week = 1
            class_items = 0
            for i, item in enumerate(tess_def['itemList']):
                if n_items >= 7 and n_items - class_items/3*2 >= 7:
                    curr_week['title'] = '{}{} {}'.format(self.translations[lang]['msg']['bd'], self.translations[lang]['msg']['week'], i_week)
                    curr_week['timestamp'] = datetime.utcfromtimestamp(start.timestamp() + (i_week - 1) * 604800).isoformat()
                    i_week = i_week + 1
                    self.data[lang]['seasonal_bd'].append(dict.copy(curr_week))
                    n_items = 0
                    curr_week['fields'] = []
                    class_items = 0
                if item['displayCategoryIndex'] == 9 and item['itemHash'] not in [353932628, 3260482534, 3536420626]:
                    definition = 'DestinyInventoryItemDefinition'
                    next_def = await destiny.decode_hash(tess_def['itemList'][i+1]['itemHash'], definition, language=lang)
                    item_def = await destiny.decode_hash(item['itemHash'], definition, language=lang)
                    currency_resp = await destiny.decode_hash(item['currencies'][0]['itemHash'], definition, language=lang)
                    currency_cost = str(item['currencies'][0]['quantity'])
                    currency_item = currency_resp['displayProperties']['name']
                    item_data = {
                        'inline': True,
                        'name': item_def['displayProperties']['name'],
                        'value': "{}: {} {}".format(self.translations[lang]['msg']['cost'], currency_cost,
                                                    currency_item.capitalize())
                    }
                    curr_week['fields'].append(item_data)
                    n_items = n_items + 1
                    if item_def['classType'] < 3 or any(class_name in item_def['itemTypeDisplayName'].lower() for class_name in self.translations[lang]['classnames']):
                        class_items = class_items + 1
        await destiny.close()

    async def get_spider(self, lang):
        char_info = self.char_info
        destiny = pydest.Pydest(self.headers['X-API-Key'])

        spider_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/863940356/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'][0])
        for locale in lang:
            spider_resp = self.get_bungie_json('spider', spider_url, self.vendor_params, locale)
            if not spider_resp:
                await destiny.close()
                return
            spider_cats = spider_resp.json()['Response']['categories']['data']['categories']
            spider_sales = spider_resp.json()['Response']['sales']['data']

            spider_def = await destiny.decode_hash(863940356, 'DestinyVendorDefinition', language=locale)

            self.data[locale]['spider'] = {
                'thumbnail': {
                    'url': self.icon_prefix + spider_def['displayProperties']['smallTransparentIcon']
                },
                'fields': [],
                'color': 7102001,
                'type': "rich",
                'title': self.translations[locale]['msg']['spider'],
            }

            # if spider inventory breaks, look here
            items_to_get = spider_cats[0]['itemIndexes']

            # iterate through keys in spider_sales, except masterwork cores (everyone knows about those)
            for key in items_to_get:
                item = spider_sales[str(key)]
                item_hash = item['itemHash']
                if not item_hash == 1812969468:
                    currency = item['costs'][0]
                    definition = 'DestinyInventoryItemDefinition'
                    item_resp = await destiny.decode_hash(item_hash, definition, language=locale)
                    currency_resp = await destiny.decode_hash(currency['itemHash'], definition, language=locale)

                    # query bungie api for name of item and name of currency
                    item_name_list = item_resp['displayProperties']['name'].split()[1:]
                    item_name = ' '.join(item_name_list)
                    currency_cost = str(currency['quantity'])
                    currency_item = currency_resp['displayProperties']['name']

                    # put result in a well formatted string in the data dict
                    item_data = {
                        'inline': True,
                        'name': item_name.capitalize(),
                        'value': "{}: {} {}".format(self.translations[locale]['msg']['cost'], currency_cost,
                                                    currency_item.capitalize())
                    }
                    self.data[locale]['spider']['fields'].append(item_data)
        await destiny.close()

    @staticmethod
    def get_xur_loc():
        url = 'https://wherethefuckisxur.com/'
        r = requests.get(url)
        soup = BeautifulSoup(r.text, features="html.parser")
        modifier_list = soup.find('div', {'class': 'xur-location'})
        loc = modifier_list.find('h1', {'class': 'page-title'})
        location = loc.text.split(' >')
        return location[0]

    async def get_xur(self, langs):
        char_info = self.char_info
        destiny = pydest.Pydest(self.headers['X-API-Key'])

        xur_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/2190858386/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'][0])
        for lang in langs:
            xur_resp = self.get_bungie_json('xur', xur_url, self.vendor_params, lang)
            if not xur_resp and xur_resp.json()['ErrorCode'] != 1627:
                await destiny.close()
                return

            xur_def = await destiny.decode_hash(2190858386, 'DestinyVendorDefinition', language=lang)
            self.data[lang]['xur'] = {
                'thumbnail': {
                    'url': self.icon_prefix + xur_def['displayProperties']['smallTransparentIcon']
                },
                'fields': [],
                'color': 0x3DD5D6,
                'type': "rich",
                'title': self.translations[lang]['msg']['xurtitle'],
            }

            if not xur_resp.json()['ErrorCode'] == 1627:
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
                    loc_field['value'] = self.translations[lang]['xur'][self.get_xur_loc()]
                    self.data[lang]['xur']['fields'].append(loc_field)
                except:
                    pass
                xur_sales = xur_resp.json()['Response']['sales']['data']

                self.data[lang]['xur']['fields'].append(weapon)

                # go through keys in xur inventory (except the first one, that's 5 of swords and is there every week)
                for key in sorted(xur_sales.keys()):
                    item_hash = xur_sales[key]['itemHash']
                    if not item_hash == 4285666432:
                        definition = 'DestinyInventoryItemDefinition'
                        item_resp = await destiny.decode_hash(item_hash, definition, language=lang)
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
                # self.data['api_is_down'] = False
                loc_field = {
                    "inline": False,
                    "name": self.translations[lang]['msg']['xurloc'],
                    "value": self.translations[lang]['xur']['noxur']
                }
                self.data[lang]['xur']['fields'].append(loc_field)
        await destiny.close()

    async def get_heroic_story(self, langs):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        for lang in langs:
            activities_resp = await self.get_activities_response('heroic story missions', lang)
            local_types = self.translations[lang]
            if not activities_resp:
                await destiny.close()
                return

            self.data[lang]['heroicstory'] = {
                'thumbnail': {
                    'url': "https://www.bungie.net/common/destiny2_content/icons/DestinyActivityModeDefinition_"
                    "5f8a923a0d0ac1e4289ae3be03f94aa2.png"
                },
                'fields': [],
                'color': 10070709,
                'type': 'rich',
                'title': self.translations[lang]['msg']['heroicstory']
            }

            for key in activities_resp.json()['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await destiny.decode_hash(item_hash, definition, language=lang)

                if local_types['heroicstory'] in r_json['displayProperties']['name']:
                    info = {
                        'inline': True,
                        "name": r_json['selectionScreenDisplayProperties']['name'],
                        "value": r_json['selectionScreenDisplayProperties']['description']
                    }
                    self.data[lang]['heroicstory']['fields'].append(info)
        await destiny.close()

    async def get_forge(self, langs):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        for lang in langs:
            activities_resp = await self.get_activities_response('forge', lang)
            local_types = self.translations[lang]
            if not activities_resp:
                await destiny.close()
                return

            self.data[lang]['forge'] = {
                'thumbnail': {
                    'url': ''
                },
                'fields': [],
                'color': 3678761,
                'type': 'rich',
                'title': self.translations[lang]['msg']['forge']
            }

            for key in activities_resp.json()['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await destiny.decode_hash(item_hash, definition, language=lang)

                if local_types['forge'] in r_json['displayProperties']['name']:
                    forge_def = 'DestinyDestinationDefinition'
                    place = await destiny.decode_hash(r_json['destinationHash'], forge_def, language=lang)
                    self.data[lang]['forge']['thumbnail']['url'] = self.icon_prefix + r_json['displayProperties']['icon']
                    info = {
                        "inline": True,
                        "name": r_json['displayProperties']['name'],
                        "value": place['displayProperties']['name']
                    }
                    self.data[lang]['forge']['fields'].append(info)
        await destiny.close()

    async def get_strike_modifiers(self, langs):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        for lang in langs:
            activities_resp = await self.get_activities_response('strike modifiers', lang)
            local_types = self.translations[lang]
            if not activities_resp:
                await destiny.close()
                return

            self.data[lang]['vanguardstrikes'] = {
                'thumbnail': {
                    'url': ''
                },
                'fields': [],
                'color': 7506394,
                'type': 'rich',
                'title': self.translations[lang]['msg']['strikesmods']
            }

            for key in activities_resp.json()['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await destiny.decode_hash(item_hash, definition, language=lang)

                if local_types['heroicstory'] in r_json['displayProperties']['name']:
                    self.data[lang]['vanguardstrikes']['fields'] = await self.decode_modifiers(key, destiny, lang)
                if self.translations[lang]['strikes'] in r_json['displayProperties']['name']:
                    self.data[lang]['vanguardstrikes']['thumbnail']['url'] = self.icon_prefix +\
                                                                       r_json['displayProperties']['icon']
        await destiny.close()

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
            "title": self.translations[lang]['msg']['reckoningboss']
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

        return data

    async def get_reckoning_modifiers(self, langs):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        for lang in langs:
            activities_resp = await self.get_activities_response('reckoning modifiers', lang)
            local_types = self.translations[lang]
            if not activities_resp:
                await destiny.close()
                return

            self.data[lang]['reckoning'] = {
                'thumbnail': {
                    'url': "https://www.bungie.net/common/destiny2_content/icons/DestinyActivityModeDefinition_"
                           "e74b3385c5269da226372df8ae7f500d.png"
                },
                'fields': [],
                'color': 1332799,
                'type': 'rich',
                'title': self.translations[lang]['msg']['reckoningmods']
            }

            self.data[lang]['reckoning']['fields'] = self.add_reckoning_boss(lang)

            for key in activities_resp.json()['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await destiny.decode_hash(item_hash, definition, language=lang)

                if self.translations[lang]['reckoning'] in r_json['displayProperties']['name']:
                    mods = await self.decode_modifiers(key, destiny, lang)
                    self.data[lang]['reckoning']['fields'] = [*self.data[lang]['reckoning']['fields'], *mods]
        await destiny.close()

    async def get_nightfall820(self, langs):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        for lang in langs:
            activities_resp = await self.get_activities_response('820 nightfalls', lang)
            local_types = self.translations[lang]
            if not activities_resp:
                await destiny.close()
                return

            self.data[lang]['nightfalls820'] = {
                'thumbnail': {
                    'url': ''
                },
                'fields': [],
                'color': 7506394,
                'type': 'rich',
                'title': self.translations[lang]['msg']['nightfalls820']
            }

            for key in activities_resp.json()['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await destiny.decode_hash(item_hash, definition, language=lang)
                try:
                    recommended_light = key['recommendedLight']
                    if recommended_light == 820:
                        self.data[lang]['nightfalls820']['thumbnail']['url'] = self.icon_prefix +\
                                                                         r_json['displayProperties']['icon']
                        if r_json['matchmaking']['requiresGuardianOath']:
                            info = {
                                'inline': True,
                                'name': self.translations[lang]['msg']['guidedgamenightfall'],
                                'value': r_json['selectionScreenDisplayProperties']['name']
                            }
                        else:
                            info = {
                                'inline': True,
                                'name': r_json['selectionScreenDisplayProperties']['name'],
                                'value': r_json['selectionScreenDisplayProperties']['description']
                            }
                        self.data[lang]['nightfalls820']['fields'].append(info)
                except KeyError:
                    pass

        await destiny.close()

    @staticmethod
    def get_modifiers(lang, act_hash):
        url = 'https://www.bungie.net/{}/Explore/Detail/DestinyActivityDefinition/{}'.format(lang, act_hash)
        r = requests.get(url)
        soup = BeautifulSoup(r.text, features="html.parser")
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

    async def get_raids(self, langs):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        for lang in langs:
            activities_resp = await self.get_activities_response('raids', lang)
            local_types = self.translations[lang]
            if not activities_resp:
                await destiny.close()
                return

            self.data[lang]['raids'] = {
                'thumbnail': {
                    'url': 'https://www.bungie.net/common/destiny2_content/icons/8b1bfd1c1ce1cab51d23c78235a6e067.png'
                },
                'fields': [],
                'color': 0xF1C40F,
                'type': 'rich',
                'title': self.translations[lang]['msg']['raids']
            }

            first_reset_time = 1580230800
            seconds_since_first = time.time() - first_reset_time
            weeks_since_first = seconds_since_first // 604800
            last_wish_challenges = [1250327262, 3871581136, 1568895666, 4007940282, 2836954349]
            sotp_challenges = [1348944144, 3415614992, 1381881897]
            cos_challenges = [2459033425, 2459033426, 2459033427]
            eow_loadout = int(weeks_since_first % 6)

            for key in activities_resp.json()['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await destiny.decode_hash(item_hash, definition, language=lang)
                if str(r_json['hash']) in self.translations[lang]['levi_order'] and \
                        not r_json['matchmaking']['requiresGuardianOath']:
                    info = {
                        'inline': True,
                        'name': r_json['originalDisplayProperties']['name'],
                        'value': self.translations[lang]['levi_order'][str(r_json['hash'])]
                    }
                    self.data[lang]['raids']['fields'].append(info)
                if self.translations[lang]["EoW"] in r_json['displayProperties']['name'] and \
                        not r_json['matchmaking']['requiresGuardianOath']:
                    info = {
                        'inline': False,
                        'name': self.translations[lang]['lairs'],
                        'value': u"\u2063"
                    }
                    mods = self.get_modifiers(lang, r_json['hash'])
                    if mods:
                        info['value'] = '{}: {}\n\n{}:\n{}'.format(mods[0]['name'], mods[0]['description'], mods[1]['name'],
                                                                   self.translations[lang]['armsmaster'][eow_loadout])
                    else:
                        info['value'] = self.data[lang]['api_is_down']['fields'][0]['name']
                    self.data[lang]['raids']['fields'].append(info)
                if self.translations[lang]['LW'] in r_json['displayProperties']['name'] and \
                        not r_json['matchmaking']['requiresGuardianOath']:
                    info = {
                        'inline': True,
                        'name': r_json['originalDisplayProperties']['name'],
                        'value': u"\u2063"
                    }
                    curr_challenge = last_wish_challenges[int(weeks_since_first % 5)]
                    curr_challenge = await destiny.decode_hash(curr_challenge, 'DestinyInventoryItemDefinition',
                                                               language=lang)
                    info['value'] = curr_challenge['displayProperties']['name']
                    self.data[lang]['raids']['fields'].append(info)
                if self.translations[lang]['SotP'] in r_json['displayProperties']['name'] and \
                        not r_json['matchmaking']['requiresGuardianOath']:
                    info = {
                        'inline': True,
                        'name': r_json['originalDisplayProperties']['name'],
                        'value': u"\u2063"
                    }
                    curr_challenge = sotp_challenges[int(weeks_since_first % 3)]
                    curr_challenge = await destiny.decode_hash(curr_challenge, 'DestinyInventoryItemDefinition',
                                                               language=lang)
                    info['value'] = curr_challenge['displayProperties']['name']
                    self.data[lang]['raids']['fields'].append(info)
                if self.translations[lang]['CoS'] in r_json['displayProperties']['name'] and \
                        not r_json['matchmaking']['requiresGuardianOath']:
                    info = {
                        'inline': True,
                        'name': r_json['originalDisplayProperties']['name'],
                        'value': u"\u2063"
                    }
                    curr_challenge = cos_challenges[int(weeks_since_first % 3)]
                    curr_challenge = await destiny.decode_hash(curr_challenge, 'DestinyInventoryItemDefinition',
                                                               language=lang)
                    info['value'] = curr_challenge['displayProperties']['name']
                    self.data[lang]['raids']['fields'].append(info)
                if self.translations[lang]['GoS'] in r_json['displayProperties']['name'] and \
                        not r_json['matchmaking']['requiresGuardianOath']:
                    info = {
                        'inline': True,
                        'name': r_json['originalDisplayProperties']['name'],
                        'value': u"\u2063"
                    }
                    mods = self.get_modifiers(lang, r_json['hash'])
                    if mods:
                        info['value'] = mods[0]['name']
                    else:
                        info['value'] = self.data[lang]['api_is_down']['fields'][0]['name']
                    self.data[lang]['raids']['fields'].append(info)

    async def get_ordeal(self, langs):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        for lang in langs:
            activities_resp = await self.get_activities_response('ordeal', lang)
            local_types = self.translations[lang]
            if not activities_resp:
                await destiny.close()
                return

            self.data[lang]['ordeal'] = {
                'thumbnail': {
                    'url': 'https://www.bungie.net/common/destiny2_content/icons/DestinyMilestoneDefinition'
                           '_a72e5ce5c66e21f34a420271a30d7ec3.png'
                },
                'fields': [],
                'color': 5331575,
                'type': 'rich',
                'title': self.translations[lang]['msg']['ordeal']
            }

            strikes = []

            for key in activities_resp.json()['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await destiny.decode_hash(item_hash, definition, language=lang)
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

            if len(self.data[lang]['ordeal']['fields']) > 0:
                for strike in strikes:
                    if strike['name'] in self.data[lang]['ordeal']['fields'][0]['name']:
                        self.data[lang]['ordeal']['fields'][0]['value'] = strike['description']
                        break
        await destiny.close()

    async def get_nightmares(self, langs):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        for lang in langs:
            activities_resp = await self.get_activities_response('nightmares', lang)
            local_types = self.translations[lang]
            if not activities_resp:
                await destiny.close()
                return

            self.data[lang]['nightmares'] = {
                'thumbnail': {
                    'url': 'https://www.bungie.net/common/destiny2_content/icons/DestinyActivityModeDefinition_'
                           '48ad57129cd0c46a355ef8bcaa1acd04.png'
                },
                'fields': [],
                'color': 6037023,
                'type': 'rich',
                'title': self.translations[lang]['msg']['nightmares']
            }

            for key in activities_resp.json()['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await destiny.decode_hash(item_hash, definition, language=lang)
                if local_types['nightmare'] in r_json['displayProperties']['name'] and \
                        local_types['adept'] in r_json['displayProperties']['name']:
                    info = {
                        'inline': True,
                        'name': r_json['displayProperties']['name'].replace(local_types['adept'], ""),
                        'value': r_json['displayProperties']['description']
                    }
                    self.data[lang]['nightmares']['fields'].append(info)
        await destiny.close()

    async def get_crucible_rotators(self, langs):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        for lang in langs:
            activities_resp = await self.get_activities_response('crucible rotators', lang)
            local_types = self.translations[lang]
            if not activities_resp:
                await destiny.close()
                return

            self.data[lang]['cruciblerotators'] = {
                'thumbnail': {
                    'url': False
                },
                'fields': [],
                'color': 6629649,
                'type': 'rich',
                'title': self.translations[lang]['msg']['cruciblerotators']
            }

            for key in activities_resp.json()['Response']['activities']['data']['availableActivities']:
                item_hash = key['activityHash']
                definition = 'DestinyActivityDefinition'
                r_json = await destiny.decode_hash(item_hash, definition, language=lang)
                if r_json['destinationHash'] == 2777041980:
                    if len(r_json['challenges']) > 0:
                        obj_def = 'DestinyObjectiveDefinition'
                        objective = await destiny.decode_hash(r_json['challenges'][0]['objectiveHash'], obj_def, lang)
                        if self.translations[lang]['rotator'] in objective['displayProperties']['name']:
                            if not self.data[lang]['cruciblerotators']['thumbnail']['url']:
                                if 'icon' in r_json['displayProperties']:
                                    self.data[lang]['cruciblerotators']['thumbnail']['url'] = self.icon_prefix + \
                                                                                   r_json['displayProperties']['icon']
                                else:
                                    self.data[lang]['cruciblerotators']['thumbnail']['url'] = self.icon_prefix + \
                                                                                    '/common/destiny2_content/icons/' \
                                                                                    'cc8e6eea2300a1e27832d52e9453a227.png'
                            info = {
                                'inline': True,
                                "name": r_json['displayProperties']['name'],
                                "value": r_json['displayProperties']['description']
                            }
                            self.data[lang]['cruciblerotators']['fields'].append(info)
        await destiny.close()

    async def get_banshee(self, lang, vendor_params, wait_codes, max_retries):
        char_info = self.char_info
        destiny = pydest.Pydest(self.headers['X-API-Key'])

        banshee_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/672118013/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'][0])
        banshee_resp = self.get_bungie_json('banshee', banshee_url, vendor_params)
        if not banshee_resp:
            await destiny.close()
            return

        banshee_sales = banshee_resp.json()['Response']['sales']['data']

        for key in sorted(banshee_sales):
            item_hash = banshee_sales[key]['itemHash']
            definition = 'DestinyInventoryItemDefinition'

            if not item_hash == 2731650749 and not item_hash == 1493877378:
                r_json = await destiny.decode_hash(item_hash, definition, language=lang)

                # query bungie api for name of item and name of currency
                item_name = r_json['displayProperties']['name']
                try:
                    item_perk_hash = r_json['perks'][0]['perkHash']
                    definition = 'DestinySandboxPerkDefinition'
                    perk_resp = await destiny.decode_hash(item_perk_hash, definition, language=lang)
                    item_desc = perk_resp['displayProperties']['description']
                except IndexError:
                    item_desc = ""

                mod = {
                    'name': item_name,
                    'desc': item_desc
                }

                # put result in a well formatted string in the data dict
                self.data['bansheeinventory'].append(mod)
        await destiny.close()

    @staticmethod
    async def decode_modifiers(key, destiny, lang):
        data = []
        for mod_key in key['modifierHashes']:
            mod_def = 'DestinyActivityModifierDefinition'
            mod_json = await destiny.decode_hash(mod_key, mod_def, lang)
            mod = {
                'inline': True,
                "name": mod_json['displayProperties']['name'],
                "value": mod_json['displayProperties']['description']
            }
            data.append(mod)
        return data

    async def get_activities_response(self, name, lang):
        char_info = self.char_info

        activities_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'][0])
        activities_resp = self.get_bungie_json(name, activities_url, self.activities_params, lang)
        return activities_resp

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
            self.refresh_token(self.token['refresh'])
