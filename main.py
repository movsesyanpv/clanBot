import requests
import json
import time
from urllib.parse import quote
import sys
import pydest
import discord
import argparse
from bs4 import BeautifulSoup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import asyncio
# import logging

import oauth
import raid as lfg


# logging.basicConfig()
# logging.getLogger('apscheduler').setLevel(logging.DEBUG)

class ClanBot(discord.Client):

    sched = AsyncIOScheduler(timezone='UTC')
    curr_hist = False

    api_data_file = open('api.json', 'r')
    api_data = json.loads(api_data_file.read())

    icon_prefix = "https://www.bungie.net"

    token = {}

    headers = {}

    data = {
        'api_fucked_up': False,
        'api_maintenance': False,
        'spider': [],
        'bansheeinventory': [],
        'adainventory': [],
        'heroicstory': [],
        'forge': [],
        'nightfalls820': [],
        'ordeal': [],
        'nightmares': [],
        'reckoning': [],
        'reckoningboss': [],
        'vanguardstrikes': [],
        'cruciblerotators': []
    }

    lfgs = []

    channels = []

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

    args = ''

    char_info = {}

    translations = {}

    def __init__(self, **options):
        super().__init__(**options)
        self.get_args()
        translations_file = open('translations.json', 'r', encoding='utf-8')
        self.translations = json.loads(translations_file.read())
        translations_file.close()

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
                print("3. Battle.net")
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
            char_id = chars[sorted(chars.keys())[0]]['characterId']
            self.char_info['charid'] = char_id

            char_file = open('char.json', 'w')
            char_file.write(json.dumps(self.char_info))

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
        self.args = parser.parse_args()

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

    def get_bungie_json(self, name, url, params):
        resp = requests.get(url, params=params, headers=self.headers)
        resp_code = resp.json()['ErrorCode']
        print('getting {}'.format(name))
        curr_try = 2
        while resp_code in self.wait_codes and curr_try <= self.max_retries:
            print('{}, attempt {}'.format(resp_code, curr_try))
            resp = requests.get(url, params=params, headers=self.headers)
            resp_code = resp.json()['ErrorCode']
            if resp_code == 5:
                self.data['api_maintenance'] = True
                curr_try -= 1
            curr_try += 1
            time.sleep(5)
        if not resp:
            resp_code = resp.json()['ErrorCode']
            if resp_code == 5:
                self.data['api_maintenance'] = True
                return resp
            print("{} get error".format(name), json.dumps(resp.json(), indent=4, sort_keys=True) + "\n")
            self.data['api_fucked_up'] = True
            return resp
        return resp

    async def get_spider(self, lang):
        char_info = self.char_info
        destiny = pydest.Pydest(self.headers['X-API-Key'])

        spider_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/863940356/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'])
        spider_resp = self.get_bungie_json('spider', spider_url, self.vendor_params)
        if not spider_resp:
            await destiny.close()
            return
        spider_cats = spider_resp.json()['Response']['categories']['data']['categories']
        spider_sales = spider_resp.json()['Response']['sales']['data']

        spider_def = await destiny.decode_hash(863940356, 'DestinyVendorDefinition', language=lang)

        self.data['spider'] = {
            'thumbnail': {
                'url': self.icon_prefix + spider_def['displayProperties']['smallTransparentIcon']
            },
            'fields': [],
            'color': 7102001,
            'type': "rich",
            'title': self.translations[lang]['msg']['spider'],
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
                item_resp = await destiny.decode_hash(item_hash, definition, language=lang)
                currency_resp = await destiny.decode_hash(currency['itemHash'], definition, language=lang)

                # query bungie api for name of item and name of currency
                item_name_list = item_resp['displayProperties']['name'].split()[1:]
                item_name = ' '.join(item_name_list)
                currency_cost = str(currency['quantity'])
                currency_item = currency_resp['displayProperties']['name']

                # put result in a well formatted string in the data dict
                item_data = {
                    'inline': True,
                    'name': item_name.capitalize(),
                    'value': "{}: {} {}".format(self.translations[lang]['msg']['cost'], currency_cost,
                                                currency_item.capitalize())
                }
                self.data['spider']['fields'].append(item_data)
        await destiny.close()

    @staticmethod
    def get_xur_loc():
        url = 'https://wherethefuckisxur.com/'
        r = requests.get(url)
        soup = BeautifulSoup(r.text, features="html.parser")
        modifier_list = soup.find('img', {'id': 'map'})
        location_str = modifier_list.attrs['src']
        location = location_str.replace('/images/', '').replace('_map_light.png', '').capitalize()
        return location

    async def get_xur(self, lang):
        char_info = self.char_info
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        # this is gonna break monday-thursday
        # get xur inventory
        xur_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/2190858386/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'])
        xur_resp = self.get_bungie_json('xur', xur_url, self.vendor_params)
        if not xur_resp and xur_resp.json()['ErrorCode'] != 1627:
            await destiny.close()

        xur_def = await destiny.decode_hash(2190858386, 'DestinyVendorDefinition', language=lang)
        self.data['xur'] = {
            'thumbnail': {
                'url': self.icon_prefix + xur_def['displayProperties']['smallTransparentIcon']
            },
            'fields': [],
            'color': 15844367,
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
                self.data['xur']['fields'].append(loc_field)
            except:
                pass
            xur_sales = xur_resp.json()['Response']['sales']['data']

            self.data['xur']['fields'].append(weapon)

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

                        perks = []

                        for p in plugs[2:]:
                            plug_resp = await destiny.decode_hash(str(p), definition, language=lang)
                            perk = {
                                'name': plug_resp['displayProperties']['name'],
                                'desc': plug_resp['displayProperties']['description']
                            }
                            perks.append(perk)

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

                        self.data['xur']['fields'].append(exotic)
                    else:
                        i = 0
                        for item in self.data['xur']['fields']:
                            if item['name'] == self.translations[lang]['msg']['weapon']:
                                self.data['xur']['fields'][i]['value'] = item_name
                            i += 1
        else:
            self.data['api_fucked_up'] = False
            loc_field = {
                "inline": False,
                "name": self.translations[lang]['msg']['xurloc'],
                "value": self.translations[lang]['xur']['noxur']
            }
            self.data['xur']['fields'].append(loc_field)
        await destiny.close()

    async def get_heroic_story(self, lang):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        activities_resp = await self.get_activities_response('heroic story missions')
        local_types = self.translations[lang]
        if not activities_resp:
            await destiny.close()

        self.data['heroicstory'] = {
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
                self.data['heroicstory']['fields'].append(info)
        await destiny.close()

    async def get_forge(self, lang):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        activities_resp = await self.get_activities_response('forge')
        local_types = self.translations[lang]
        if not activities_resp:
            await destiny.close()

        self.data['forge'] = {
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
                self.data['forge']['thumbnail']['url'] = self.icon_prefix + r_json['displayProperties']['icon']
                info = {
                    "inline": True,
                    "name": r_json['displayProperties']['name'],
                    "value": place['displayProperties']['name']
                }
                self.data['forge']['fields'].append(info)
        await destiny.close()

    async def get_strike_modifiers(self, lang):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        activities_resp = await self.get_activities_response('strike modifiers')
        local_types = self.translations[lang]
        if not activities_resp:
            await destiny.close()

        self.data['vanguardstrikes'] = {
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
                self.data['vanguardstrikes']['fields'] = await self.decode_modifiers(key, destiny, lang)
            if self.translations[lang]['strikes'] in r_json['displayProperties']['name']:
                self.data['vanguardstrikes']['thumbnail']['url'] = self.icon_prefix +\
                                                                   r_json['displayProperties']['icon']
        await destiny.close()

    async def get_reckoning_modifiers(self, lang):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        activities_resp = await self.get_activities_response('reckoning modifiers')
        local_types = self.translations[lang]
        if not activities_resp:
            await destiny.close()

        self.data['reckoning'] = {
            'thumbnail': {
                'url': "https://www.bungie.net/common/destiny2_content/icons/DestinyActivityModeDefinition_"
                       "e74b3385c5269da226372df8ae7f500d.png"
            },
            'fields': [],
            'color': 1332799,
            'type': 'rich',
            'title': self.translations[lang]['msg']['reckoningmods']
        }

        for key in activities_resp.json()['Response']['activities']['data']['availableActivities']:
            item_hash = key['activityHash']
            definition = 'DestinyActivityDefinition'
            r_json = await destiny.decode_hash(item_hash, definition, language=lang)

            if self.translations[lang]['reckoning'] in r_json['displayProperties']['name']:
                self.data['reckoning']['fields'] = await self.decode_modifiers(key, destiny, lang)
        await destiny.close()

    async def get_nightfall820(self, lang):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        activities_resp = await self.get_activities_response('820 nightfalls')
        local_types = self.translations[lang]
        if not activities_resp:
            await destiny.close()

        self.data['nightfalls820'] = {
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
                    self.data['nightfalls820']['thumbnail']['url'] = self.icon_prefix +\
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
                    self.data['nightfalls820']['fields'].append(info)
            except KeyError:
                pass

        await destiny.close()

    async def get_ordeal(self, lang):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        activities_resp = await self.get_activities_response('ordeal')
        local_types = self.translations[lang]
        if not activities_resp:
            await destiny.close()

        self.data['ordeal'] = {
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
                self.data['ordeal']['fields'].append(info)

        if len(self.data['ordeal']['fields']) > 0:
            for strike in strikes:
                if strike['name'] in self.data['ordeal']['fields'][0]['name']:
                    self.data['ordeal']['fields'][0]['value'] = strike['description']
                    break
        await destiny.close()

    async def get_nightmares(self, lang):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        activities_resp = await self.get_activities_response('nightmares')
        local_types = self.translations[lang]
        if not activities_resp:
            await destiny.close()

        self.data['nightmares'] = {
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
                self.data['nightmares']['fields'].append(info)
        await destiny.close()

    async def get_reckoning_boss(self, lang):
        first_reset_time = 1539709200
        seconds_since_first = time.time() - first_reset_time
        weeks_since_first = seconds_since_first // 604800
        reckoning_bosses = ['swords', 'oryx']

        self.data['reckoningboss'] = {
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

    async def get_crucible_rotators(self, lang):
        destiny = pydest.Pydest(self.headers['X-API-Key'])
        activities_resp = await self.get_activities_response('crucible rotators')
        local_types = self.translations[lang]
        if not activities_resp:
            await destiny.close()

        self.data['cruciblerotators'] = {
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
                        if not self.data['cruciblerotators']['thumbnail']['url']:
                            self.data['cruciblerotators']['thumbnail']['url'] = self.icon_prefix + \
                                                                               r_json['displayProperties']['icon']
                        info = {
                            'inline': True,
                            "name": r_json['displayProperties']['name'],
                            "value": r_json['displayProperties']['description']
                        }
                        self.data['cruciblerotators']['fields'].append(info)
        await destiny.close()

    async def get_banshee(self, lang, vendor_params, wait_codes, max_retries):
        char_info = self.char_info
        destiny = pydest.Pydest(self.headers['X-API-Key'])

        banshee_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/672118013/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'])
        banshee_resp = self.get_bungie_json('banshee', banshee_url, vendor_params)
        if not banshee_resp:
            await destiny.close()

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

    async def get_ada(self, vendor_params, wait_codes, max_retries):
        char_info = self.char_info
        destiny = pydest.Pydest(self.headers['X-API-Key'])

        ada_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/2917531897/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'])
        ada_resp = self.get_bungie_json('ada', ada_url, vendor_params)
        if not ada_resp:
            await destiny.close()

        ada_cats = ada_resp.json()['Response']['categories']['data']['categories']
        ada_sales = ada_resp.json()['Response']['sales']['data']

        items_to_get = ada_cats[0]['itemIndexes']

        for key in items_to_get:
            item_hash = ada_sales[str(key)]['itemHash']
            item_def_url = 'https://www.bungie.net/platform/Destiny2/Manifest/DestinyInventoryItemDefinition/' + str(
                item_hash) + '/'
            item_resp = requests.get(item_def_url, headers=self.headers)

            # query bungie api for name of item and name of currency
            item_name_list = item_resp.json()['Response']['displayProperties']['name'].split()
            if 'Powerful' in item_name_list:
                item_name_list = item_name_list[1:]
            item_name = ' '.join(item_name_list)

            self.data['adainventory'].append(item_name)
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

    async def get_activities_response(self, name):
        char_info = self.char_info

        activities_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'])
        activities_resp = self.get_bungie_json(name, activities_url, self.activities_params)
        return activities_resp

    async def force_update(self, upd_type):
        if upd_type == 'daily':
            await self.universal_update(self.get_heroic_story, 'heroicstory', 86400)
            await self.universal_update(self.get_forge, 'forge', 86400)
            await self.universal_update(self.get_strike_modifiers, 'vanguardstrikes', 86400)
            await self.universal_update(self.get_reckoning_modifiers, 'reckoning', 86400)
            await self.update_history()
        if upd_type == 'weekly':
            await self.universal_update(self.get_nightfall820, 'nightfalls820', 604800)
            await self.universal_update(self.get_ordeal, 'ordeal', 604800)
            await self.universal_update(self.get_nightmares, 'nightmares', 604800)
            await self.universal_update(self.get_reckoning_boss, 'reckoningboss', 604800)
            await self.universal_update(self.get_crucible_rotators, 'cruciblerotators', 604800)
            await self.update_history()
        if upd_type == 'spider':
            await self.universal_update(self.get_spider, 'spider', 86400)
            await self.update_history()
        if upd_type == 'xur':
            await self.universal_update(self.get_xur, 'xur', 345600)
            await self.update_history()

    async def on_ready(self):
        await self.token_update()
        await self.update_history()
        self.get_channels()
        self.get_chars()
        if self.args.forceupdate:
            await self.force_update(self.args.type)
        self.sched.add_job(self.universal_update, 'cron', hour='17', minute='0', second='30', misfire_grace_time=86300, args=[self.get_heroic_story, 'heroicstory', 86400])
        self.sched.add_job(self.universal_update, 'cron', hour='17', minute='0', second='30', misfire_grace_time=86300, args=[self.get_forge, 'forge', 86400])
        self.sched.add_job(self.universal_update, 'cron', hour='17', minute='0', second='30', misfire_grace_time=86300, args=[self.get_strike_modifiers, 'vanguardstrikes', 86400])
        self.sched.add_job(self.universal_update, 'cron', hour='17', minute='0', second='30', misfire_grace_time=86300, args=[self.get_reckoning_modifiers, 'reckoning', 86400])

        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='0', second='40', misfire_grace_time=86300, args=[self.get_nightfall820, 'nightfalls820', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='0', second='40', misfire_grace_time=86300, args=[self.get_ordeal, 'ordeal', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='0', second='40', misfire_grace_time=86300, args=[self.get_nightmares, 'nightmares', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='0', second='40', misfire_grace_time=86300, args=[self.get_reckoning_boss, 'reckoningboss', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='0', second='40', misfire_grace_time=86300, args=[self.get_crucible_rotators, 'cruciblerotators', 604800])

        self.sched.add_job(self.universal_update, 'cron', day_of_week='fri', hour='17', minute='5', second='0', misfire_grace_time=86300, args=[self.get_xur, 'xur', 345600])
        self.sched.add_job(self.universal_update, 'cron', hour='1', minute='0', second='10', misfire_grace_time=86300, args=[self.get_spider, 'spider', 86400])

        self.sched.add_job(self.update_history, 'cron', hour='2')
        self.sched.add_job(self.token_update, 'interval', hours=1)
        self.sched.start()

    async def check_ownership(self, message):
        bot_info = await self.application_info()
        is_owner = bot_info.owner == message.author
        if not is_owner:
            msg = '{}!'.format(message.author.mention)
            e = discord.Embed(title='I will not obey you.', type="rich",
                              url='https://www.youtube.com/watch?v=qn9FkoqYgI4')
            e.set_image(url='https://i.ytimg.com/vi/qn9FkoqYgI4/hqdefault.jpg')
            await message.channel.send(msg, embed=e)
        return is_owner

    async def on_reaction_remove(self, reaction, user):
        if user == self.user:
            return

        for group in self.lfgs:
            if group.is_raid(reaction.message):
                if str(reaction) != '👌':
                    return
                if user.mention in group.going:
                    group.going.pop(group.going.index(user.mention))
                    if len(group.wanters) > 0:
                        group.going.append(group.wanters[0])
                        group.wanters.pop(0)
                if user.mention in group.wanters:
                    group.wanters.pop(group.wanters.index(user.mention))
                await group.update_group_msg(reaction, user, self.translations[self.args.lang])

    async def on_reaction_add(self, reaction, user):
        if user == self.user:
            return

        for group in self.lfgs:
            if group.is_raid(reaction.message):
                if str(reaction) == '❌' and user == group.owner:
                    await reaction.message.delete()
                    self.lfgs.pop(self.lfgs.index(group))
                    self.sched.remove_job('{}_del'.format(group.group_id))
                    print(self.lfgs)
                    return
                if str(reaction) != '👌':
                    await reaction.remove(user)
                    return
                if len(group.going) < group.size:
                    group.going.append(user.mention)
                else:
                    group.wanters.append(user.mention)
                await group.update_group_msg(reaction, user, self.translations[self.args.lang])

    async def pause_for(self, message, delta):
        self.sched.pause()
        await asyncio.sleep(delta.total_seconds())
        self.sched.resume()
        await message.channel.send('should be after delay finish {}'.format(str(datetime.now())))
        return

    async def on_message(self, message):
        if message.author == self.user:
            return

        if 'stop' in message.content.lower() and (self.user in message.mentions or str(message.channel.type) == 'private'):
            if await self.check_ownership(message):
                msg = 'Ok, {}'.format(message.author.mention)
                await message.channel.send(msg)
                self.sched.shutdown(wait=True)
                await self.update_history()
                await self.logout()
                await self.close()
                return
            return

        if 'plan maintenance' in message.content.lower() and (self.user in message.mentions or str(message.channel.type) == 'private'):
            try:
                content = message.content.splitlines()
                start = datetime.strptime(content[1], "%d-%m-%Y %H:%M %z")
                finish = datetime.strptime(content[2], "%d-%m-%Y %H:%M %z")
                delta = finish-start
                self.sched.add_job(self.pause_for, 'date', run_date=start, args=[message, delta], misfire_grace_time=600)
            except Exception as e:
                await message.channel.send('exception `{}`\nUse following format:```plan maintenance\n<start time formatted %d-%m-%Y %H:%M %z>\n<finish time formatted %d-%m-%Y %H:%M %z>```'.format(str(e)))
            return

        if str(message.channel.type) == 'private':
            msg = 'Can\'t do anything a private chat, {}'.format(message.author.mention)
            await message.channel.send(msg)
            return

        if 'lfg' in message.content.lower().splitlines()[0] and self.user in message.mentions:
            content = message.content.splitlines()
            raid = lfg.LFG(message)
            msg = "{}, {} {}\n{} {}\n{}".format(raid.the_role.mention, self.translations[self.args.lang]['lfg']['go'], raid.name, self.translations[self.args.lang]['lfg']['at'], raid.time.strftime("%d-%m-%Y %H:%M %Z"), raid.description)
            out = await message.channel.send(msg)
            end_time = raid.time + timedelta(seconds=3600)
            await out.add_reaction('👌')
            await out.add_reaction('❌')
            raid.group_id = out.id
            self.sched.add_job(out.delete, 'date', run_date=end_time, id='{}_del'.format(raid.group_id))
            self.sched.add_job(raid.ping_going, 'date', run_date=raid.time, id='{}_ping'.format(raid.group_id))
            self.lfgs.append(raid)

        if 'regnotifier' in message.content.lower() and self.user in message.mentions:
            if await self.check_ownership(message):
                await message.delete()
                self.channels.append(message.channel.id)
                self.channels = list(set(self.channels))
                f = open('channelList.dat', 'w')
                for channel in self.channels:
                    f.write('{}\n'.format(channel))
                f.close()
                msg = 'Got it, {}'.format(message.author.mention)
                await message.channel.send(msg, delete_after=10)
                return
            return

        if 'update' in message.content.lower() and self.user in message.mentions:
            content = message.content.lower().split()
            await message.delete()
            for upd_type in content[2:]:
                await self.force_update(upd_type)
            return

    def get_channels(self):
        try:
            f = open('channelList.dat', 'r')
            self.channels = f.readlines()
            f.close()
        except FileNotFoundError:
            pass

    async def update_history(self):
        game = discord.Game('updating history')
        await self.change_presence(activity=game)
        hist_saved = {}
        for server in self.guilds:
            history_file = str(server.id) + '_history.json'
            try:
                with open(history_file) as json_file:
                    hist_saved[str(server.id)] = json.loads(json_file.read())
                    json_file.close()
            except FileNotFoundError:
                with open("history.json") as json_file:
                    hist_saved[str(server.id)] = json.loads(json_file.read())
                    json_file.close()
        if self.curr_hist:
            for server in self.guilds:
                history_file = str(server.id) + '_history.json'
                f = open(history_file, 'w')
                f.write(json.dumps(self.curr_hist[str(server.id)]))
        else:
            self.curr_hist = hist_saved
        game = discord.Game('waiting')
        await self.change_presence(activity=game)

    async def universal_update(self, getter, name, time_to_delete):
        await self.wait_until_ready()
        game = discord.Game('updating {}'.format(name))
        await self.change_presence(activity=game)

        lang = self.args.lang

        await getter(lang)

        if not self.data['api_maintenance'] and not self.data['api_fucked_up']:
            if self.data[name]:
                await self.post_embed(name, self.data[name], time_to_delete)

        game = discord.Game('waiting')
        await self.change_presence(activity=game)

    async def token_update(self):
        # check to see if token.json exists, if not we have to start with oauth
        try:
            f = open('token.json', 'r')
        except FileNotFoundError:
            if '--oauth' in sys.argv:
                oauth.get_oauth(self.api_data)
            else:
                print('token file not found!  run the script with --oauth or add a valid token.js file!')
                return False

        try:
            f = open('token.json', 'r')
            self.token = json.loads(f.read())
        except json.decoder.JSONDecodeError:
            if '--oauth' in sys.argv:
                oauth.get_oauth(self.api_data)
            else:
                print('token file invalid!  run the script with --oauth or add a valid token.js file!')
                return False

        # check if token has expired, if so we have to oauth, if not just refresh the token
        if self.token['expires'] < time.time():
            if '--oauth' in sys.argv:
                oauth.get_oauth(self.api_data)
            else:
                print('refresh token expired!  run the script with --oauth or add a valid token.js file!')
                return False
        else:
            self.refresh_token(self.token['refresh'])

    async def post_embed(self, upd_type, src_dict, time_to_delete):
        hist = self.curr_hist

        if not self.args.nomessage:
            embed = discord.Embed.from_dict(src_dict)

            for server in self.guilds:
                hist[str(server.id)]['server_name'] = server.name.strip('\'')
                for channel in server.channels:
                    if '{}\n'.format(channel.id) in self.channels:
                        if hist[str(server.id)][upd_type] and \
                                not self.args.noclear:
                            try:
                                last = await channel.fetch_message(
                                    hist[str(server.id)][upd_type])
                            except discord.NotFound:
                                bot_info = await self.application_info()
                                await bot_info.owner.send('Not found at ```{}```. Channel ```{}``` of ```{}```'.format(upd_type, channel.name, server.name))
                            try:
                                await last.delete()
                            except:
                                pass
                        message = await channel.send(embed=embed, delete_after=time_to_delete)
                        hist[str(server.id)][upd_type] = message.id

    def start_up(self):
        self.get_args()
        token = self.api_data['token']
        print('hmm')
        self.run(token)


if __name__ == '__main__':
    b = ClanBot()
    b.start_up()
