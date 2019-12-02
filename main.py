import requests
import json
import time
from urllib.parse import quote
import os
from git import Repo
import shutil
from datetime import datetime
import sys
import pydest
import asyncio
import discord
from tabulate import tabulate
import argparse
from bs4 import BeautifulSoup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
# import logging

import oauth

# logging.basicConfig()
# logging.getLogger('apscheduler').setLevel(logging.DEBUG)

class ClanBot(discord.Client):
    sched = AsyncIOScheduler(timezone='UTC')
    curr_hist = False

    api_data_file = open('api.json', 'r')
    api_data = json.loads(api_data_file.read())

    icon_prefix = "https://www.bungie.net"

    token = {}

    args = ''

    def get_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-nc', '--noclear', help='Don\'t clear last message of the type', action='store_true')
        parser.add_argument('-p', '--production', help='Use to launch in production mode', action='store_true')
        parser.add_argument('-nm', '--nomessage', help='Don\'t post any messages', action='store_true')
        parser.add_argument('-l', '--lang', type=str, help='Language of data', default='en')
        parser.add_argument('-t', '--type', type=str, help='Type of message. Use with -f')
        parser.add_argument('-tp', '--testprod', help='Use to launch in test production mode', action='store_true')
        parser.add_argument('-f', '--forceupdate', help='Force update right now', action='store_true')
        parser.add_argument('--oauth', action='store_true')
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

        # get data with new token
        return resp['access_token']


    def get_bungie_json(self, name, url, params, headers, data, wait_codes, max_retries):
        resp = requests.get(url, params=params, headers=headers)
        resp_code = resp.json()['ErrorCode']
        print('getting {}'.format(name))
        curr_try = 2
        while resp_code in wait_codes and curr_try <= max_retries:
            print('{}, attempt {}'.format(resp_code, curr_try))
            resp = requests.get(url, params=params, headers=headers)
            resp_code = resp.json()['ErrorCode']
            if resp_code == 5:
                data['api_maintenance'] = True
                curr_try -= 1
            curr_try += 1
            time.sleep(5)
        if not resp:
            resp_code = resp.json()['ErrorCode']
            if resp_code == 5:
                data['api_maintenance'] = True
                return resp
            print("{} get error".format(name), json.dumps(resp.json(), indent=4, sort_keys=True) + "\n")
            data['api_fucked_up'] = True
            return resp
        return resp


    async def get_records(self, lang, data, char_info, params, headers, wait_codes, max_retries):
        destiny = pydest.Pydest(headers['X-API-Key'])
        records_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/'. \
            format(char_info['platform'], char_info['membershipid'])

        records_resp = self.get_bungie_json('records', records_url, params, headers, data, wait_codes, max_retries)

        seal_resp = await destiny.decode_hash(1652422747, 'DestinyPresentationNodeDefinition', language=lang)

        seals = {
            "id": "",
            "seals": []
        }

        correction = False
        records_nodes = records_resp.json()['Response']['profilePresentationNodes']['data']['nodes']
        mmxix_node = records_resp.json()['Response']['characterRecords']['data'][char_info['charid']]['records']
        for record in mmxix_node:
            if record == "1492080644" and mmxix_node['1492080644']['objectives'][0]['complete']:
                correction = True
                break

        for seal in seal_resp['children']['presentationNodes']:
            for record in records_resp.json()['Response']['profilePresentationNodes']['data']['nodes']:
                if str(seal['presentationNodeHash']) == record:
                    corr_value = 0
                    if record == "1002334440" and correction:
                        corr_value = 1
                    if records_nodes[record]['progressValue'] + corr_value == records_nodes[record]['completionValue']:
                        seals['seals'].append(record)

        await destiny.close()

        return seals


    async def get_spider(self, lang, data, char_info, vendor_params, headers, wait_codes, max_retries):
        destiny = pydest.Pydest(headers['X-API-Key'])

        spider_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/863940356/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'])
        spider_resp = self.get_bungie_json('spider', spider_url, vendor_params, headers, data, wait_codes, max_retries)
        if not spider_resp:
            await destiny.close()
            return
        spider_cats = spider_resp.json()['Response']['categories']['data']['categories']
        spider_sales = spider_resp.json()['Response']['sales']['data']

        spider_def = await destiny.decode_hash(863940356, 'DestinyVendorDefinition', language=lang)

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
                    'name': item_name,
                    'cost': currency_cost + ' ' + currency_item,
                    'icon': spider_def['displayProperties']['smallTransparentIcon']
                }
                data['spiderinventory'].append(item_data)
        await destiny.close()


    def get_xur_loc():
        url = 'https://wherethefuckisxur.com/'
        r = requests.get(url)
        soup = BeautifulSoup(r.text, features="html.parser")
        modifier_list = soup.find('img', {'id': 'map'})
        location_str = modifier_list.attrs['src']
        location = location_str.replace('/images/', '').replace('_map_light.png', '').capitalize()
        return location


    async def get_xur(self, lang, translation, data, char_info, vendor_params, headers, wait_codes, max_retries):
        destiny = pydest.Pydest(headers['X-API-Key'])
        # this is gonna break monday-thursday
        # get xur inventory
        xur_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/2190858386/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'])
        xur_resp = self.get_bungie_json('xur', xur_url, vendor_params, headers, data, wait_codes, max_retries)
        if not xur_resp and not xur_resp.json()['ErrorCode'] == 1627:
            await destiny.close()
            return data

        if not xur_resp.json()['ErrorCode'] == 1627:
            xur_def = await destiny.decode_hash(2190858386, 'DestinyVendorDefinition', language=lang)
            data['xur'] = {
                'location': 'NULL',
                'xurweapon': '',
                'xurarmor': [],
                'icon': xur_def['displayProperties']['smallTransparentIcon']
            }
            try:
                data['xur']['location'] = get_xur_loc()
            except:
                pass
            xur_sales = xur_resp.json()['Response']['sales']['data']

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
                            'name': item_name,
                            'perks': perks
                        }

                        if item_resp['classType'] == 0:
                            exotic['class'] = translation[lang]['Titan']
                        elif item_resp['classType'] == 1:
                            exotic['class'] = translation[lang]['Hunter']
                        elif item_resp['classType'] == 2:
                            exotic['class'] = translation[lang]['Warlock']

                        data['xur']['xurarmor'].append(exotic)
                    else:
                        data['xur']['xurweapon'] = item_name
        else:
            # do something if xur isn't here
            pass
        await destiny.close()


    async def get_banshee(lang, data, char_info, vendor_params, headers, wait_codes, max_retries):
        destiny = pydest.Pydest(headers['X-API-Key'])

        banshee_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/672118013/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'])
        banshee_resp = self.get_bungie_json('banshee', banshee_url, vendor_params, headers, data, wait_codes, max_retries)
        if not banshee_resp:
            await destiny.close()
            return data

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
                data['bansheeinventory'].append(mod)
        await destiny.close()


    async def get_ada(lang, data, char_info, vendor_params, headers, wait_codes, max_retries):
        destiny = pydest.Pydest(headers['X-API-Key'])

        ada_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/2917531897/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'])
        ada_resp = self.get_bungie_json('ada', ada_url, vendor_params, headers, data, wait_codes, max_retries)
        if not ada_resp:
            await destiny.close()
            return data

        ada_cats = ada_resp.json()['Response']['categories']['data']['categories']
        ada_sales = ada_resp.json()['Response']['sales']['data']

        items_to_get = ada_cats[0]['itemIndexes']

        for key in items_to_get:
            item_hash = ada_sales[str(key)]['itemHash']
            item_def_url = 'https://www.bungie.net/platform/Destiny2/Manifest/DestinyInventoryItemDefinition/' + str(
                item_hash) + '/'
            item_resp = requests.get(item_def_url, headers=headers)

            # query bungie api for name of item and name of currency
            item_name_list = item_resp.json()['Response']['displayProperties']['name'].split()
            if 'Powerful' in item_name_list:
                item_name_list = item_name_list[1:]
            item_name = ' '.join(item_name_list)

            data['adainventory'].append(item_name)
        await destiny.close()


    async def decode_modifiers(self, key, destiny, lang):
        data = []
        for mod_key in key['modifierHashes']:
            mod_def = 'DestinyActivityModifierDefinition'
            mod_json = await destiny.decode_hash(mod_key, mod_def, lang)
            mod = {
                "name": mod_json['displayProperties']['name'],
                "description": mod_json['displayProperties']['description']
            }
            data.append(mod)

        return data


    async def get_activities(self, lang, translation, data, char_info, activities_params, headers, wait_codes, max_retries):
        destiny = pydest.Pydest(headers['X-API-Key'])

        activities_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/'. \
            format(char_info['platform'], char_info['membershipid'], char_info['charid'])
        activities_resp = self.get_bungie_json('activities', activities_url, activities_params, headers, data, wait_codes,
                                          max_retries)
        local_types = translation[lang]
        if not activities_resp:
            await destiny.close()
            return data

        strikes = []

        for key in activities_resp.json()['Response']['activities']['data']['availableActivities']:
            item_hash = key['activityHash']
            definition = 'DestinyActivityDefinition'
            r_json = await destiny.decode_hash(item_hash, definition, language=lang)
            try:
                recommended_light = key['recommendedLight']
                if recommended_light == 820:
                    info = {
                        'name': r_json['selectionScreenDisplayProperties']['name'],
                        'description': r_json['selectionScreenDisplayProperties']['description'],
                        'icon': r_json['displayProperties']['icon']
                    }
                    if r_json['matchmaking']['requiresGuardianOath']:
                        data['guidedgamenightfall'].append(info)
                    else:
                        data['activenightfalls'].append(info)
            except KeyError:
                pass
            if local_types['heroicstory'] in r_json['displayProperties']['name']:
                info = {
                    "name": r_json['selectionScreenDisplayProperties']['name'],
                    "description": r_json['selectionScreenDisplayProperties']['description'],
                    "icon": r_json['displayProperties']['icon']
                }
                data['vanguardstrikes'] = await self.decode_modifiers(key, destiny, lang)
                data['heroicstory'].append(info)
            if local_types['forge'] in r_json['displayProperties']['name']:
                forge_def = 'DestinyDestinationDefinition'
                place = await destiny.decode_hash(r_json['destinationHash'], forge_def, language=lang)
                data['forge'].append({"name": r_json['displayProperties']['name'], "loc": place['displayProperties']['name'], "icon": r_json['displayProperties']['icon']})
            if local_types['ordeal'] in r_json['displayProperties']['name'] and \
                    local_types['adept'] in r_json['displayProperties']['name']:
                info = {
                    'title': r_json['originalDisplayProperties']['name'],
                    'name': r_json['originalDisplayProperties']['description'],
                    'description': "",
                    'icon': r_json['displayProperties']['icon']
                }
                data['ordeal'].append(info)
            if r_json['activityTypeHash'] == 4110605575:
                strikes.append({"name": r_json['displayProperties']['name'], "description": r_json['displayProperties']['description']})
            if local_types['nightmare'] in r_json['displayProperties']['name'] and \
                    local_types['adept'] in r_json['displayProperties']['name']:
                info = {
                    'name': r_json['displayProperties']['name'].replace(local_types['adept'], ""),
                    'description': r_json['displayProperties']['description'],
                    'icon': r_json['displayProperties']['icon']
                }
                data['nightmare'].append(info)
            if translation[lang]['strikes'] in r_json['displayProperties']['name']:
                data['vanguardstrikes'][0]['icon'] = r_json['displayProperties']['icon']
            if translation[lang]['reckoning'] in r_json['displayProperties']['name']:
                data['reckoning'] = await self.decode_modifiers(key, destiny, lang)
                data['reckoning'][0]['icon'] = r_json['displayProperties']['icon']
            if r_json['isPvP']:
                if len(r_json['challenges']) > 0:
                    obj_def = 'DestinyObjectiveDefinition'
                    objective = await destiny.decode_hash(r_json['challenges'][0]['objectiveHash'], obj_def, lang)
                    if translation[lang]['rotator'] in objective['displayProperties']['name']:
                        info = {
                            "name": r_json['displayProperties']['name'],
                            "description": r_json['displayProperties']['description'],
                            'icon': r_json['displayProperties']['icon']
                        }
                        data['cruciblerotator'].append(info)

            for strike in strikes:
                if strike['name'] in data['ordeal'][0]['name']:
                    data['ordeal'][0]['description'] = strike['description']
                    break

        await destiny.close()


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
        return modifiers


    async def get_seals(token, lang, char_info):
        headers = {
            'X-API-Key': api_data['key'],
            'Authorization': 'Bearer ' + token
        }

        wait_codes = [1672]
        max_retries = 10

        record_params = {
            "components": "900,700"
        }

        data = {
            'api_fucked_up': False,
            'api_maintenance': False,
            'char': char_info
        }

        seals = await self.get_records(lang, data, char_info, record_params, headers, wait_codes, max_retries)

        data['seals'] = seals

        return data


    async def get_data(self, token, translation, lang, get_type):
        print('hmmmmmmm')
        headers = {
            'X-API-Key': self.api_data['key'],
            'Authorization': 'Bearer ' + token
        }

        wait_codes = [1672]
        max_retries = 10
        first_reset_time = 1539709200
        seconds_since_first = time.time() - first_reset_time
        weeks_since_first = seconds_since_first // 604800
        reckoning_bosses = ['swords', 'oryx']

        char_info = {}
        platform = 0
        membership_id = ''
        char_id = ''
        try:
            char_file = open('char.json', 'r')
            char_info = json.loads(char_file.read())
            platform = char_info['platform']
            membership_id = char_info['membershipid']
            char_id = char_info['charid']
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
            char_info['platform'] = platform

            valid_input = False
            while not valid_input:
                name = input("What's the name of your account on there? (include # numbers): ")
                search_url = 'https://www.bungie.net/platform/Destiny2/SearchDestinyPlayer/' + str(platform) + '/' + quote(
                    name) + '/'
                search_resp = requests.get(search_url, headers=headers)
                search = search_resp.json()['Response']
                if len(search) > 0:
                    valid_input = True
                    membership_id = search[0]['membershipId']
                    char_info['membershipid'] = membership_id

            # get the first character and just roll with that
            char_search_url = 'https://www.bungie.net/platform/Destiny2/' + platform + '/Profile/' + membership_id + '/'
            char_search_params = {
                'components': '200'
            }
            char_search_resp = requests.get(char_search_url, params=char_search_params, headers=headers)
            chars = char_search_resp.json()['Response']['characters']['data']
            char_id = chars[sorted(chars.keys())[0]]['characterId']
            char_info['charid'] = char_id

            char_file = open('char.json', 'w')
            char_file.write(json.dumps(char_info))

        # create data.json dict
        data = {
            'api_fucked_up': False,
            'api_maintenance': False,
            'spiderinventory': [],
            'bansheeinventory': [],
            'adainventory': [],
            'heroicstory': [],
            'forge': [],
            'activenightfalls': [],
            'guidedgamenightfall': [],
            'ordeal': [],
            'nightmare': [],
            'reckoning': [],
            'vanguardstrikes': [],
            'cruciblerotator': []
        }

        vendor_params = {
            'components': '400,401,402'
        }

        activities_params = {
            'components': '204'
        }

        record_params = {
            "components": "900,700"
        }

        if get_type == 'spider':
            await self.get_spider(lang, data, char_info, vendor_params, headers, wait_codes, max_retries)
        if get_type == 'xur':
            await self.get_xur(lang, translation, data, char_info, vendor_params, headers, wait_codes, max_retries)
        if get_type == 'daily':
            await self.get_activities(lang, translation, data, char_info, activities_params, headers, wait_codes, max_retries)
        if get_type == 'weekly':
            await self.get_activities(lang, translation, data, char_info, activities_params, headers, wait_codes, max_retries)
            data['reckoning'] = {"boss": reckoning_bosses[int(weeks_since_first % 2)], "desc": translation[lang]['r_desc']}

        return data


    def create_embeds(self, raw_data, msg_type, lang, translation):
        tr = translation[lang]['msg']

        embed = [discord.Embed(type="rich")]

        if raw_data['api_fucked_up']:
            embed[0].title = tr['noapi']
            embed[0].color = discord.Color.red()
            return embed
        if raw_data['api_maintenance']:
            embed[0].title = tr['maintenance']
            embed[0].color = discord.Color.orange()
            return embed

        if msg_type == 'spider':
            embed[0].color = discord.Color(0x6C5E31)
            embed[0].title = tr['spider']
            embed[0].set_thumbnail(url=self.icon_prefix+raw_data['spiderinventory'][0]['icon'])
            for item in raw_data['spiderinventory']:
                embed[0].add_field(name=item['name'].capitalize(), value="{}: {}".format(tr['cost'], item['cost'].capitalize()), inline=True)
        if msg_type == 'xur':
            embed[0].color = discord.Color.gold()
            embed[0].set_thumbnail(url=self.icon_prefix+raw_data['xur']['icon'])
            embed[0].title = tr['xurtitle']
            embed[0].add_field(name=tr['xurloc'], value=translation[lang]['xur'][raw_data['xur']['location']], inline=False)
            embed[0].add_field(name=tr['weapon'], value=raw_data['xur']['xurweapon'], inline=False)
            for item in raw_data['xur']['xurarmor']:
                embed[0].add_field(name=item['class'], value=item['name'], inline=True)
        if msg_type == 'daily':
            embed[0].title = tr['heroicstory']
            embed[0].color = discord.Color.greyple()
            embed[0].set_thumbnail(url=self.icon_prefix+raw_data['heroicstory'][0]['icon'])
            for item in raw_data['heroicstory']:
                embed[0].add_field(name=item['name'], value=item['description'], inline=True)
            embed.append(discord.Embed(type="rich"))
            embed[1].color = discord.Color(0x382229)
            embed[1].title = tr['forge']
            embed[1].set_thumbnail(url=self.icon_prefix+raw_data['forge'][0]['icon'])
            embed[1].add_field(name=raw_data['forge'][0]['name'], value=raw_data['forge'][0]['loc'], inline=True)
            embed.append(discord.Embed(type="rich"))
            embed[2].title = tr['strikesmods']
            embed[2].set_thumbnail(url=self.icon_prefix+raw_data['vanguardstrikes'][0]['icon'])
            embed[2].color = discord.Color.blurple()
            for item in raw_data['vanguardstrikes']:
                embed[2].add_field(name=item['name'], value=item['description'], inline=True)
            embed.append(discord.Embed(type="rich"))
            embed[3].title = tr['reckoningmods']
            embed[3].color = discord.Color(0x14563f)
            embed[3].set_thumbnail(url=self.icon_prefix + "/common/destiny2_content/icons"
                                                     "/DestinyActivityModeDefinition_e74b3385c5269da226372df8ae7f500d.png")
            for item in raw_data['reckoning']:
                embed[3].add_field(name=item['name'], value=item['description'], inline=True)
        if msg_type == 'weekly':
            embed[0].color = discord.Color.blurple()
            embed[0].set_thumbnail(url=self.icon_prefix+raw_data['activenightfalls'][0]['icon'])
            embed[0].title = tr['nightfalls820']
            for item in raw_data['activenightfalls']:
                embed[0].add_field(name=item['name'], value=item['description'], inline=True)
            embed[0].add_field(name=tr['guidedgamenightfall'], value=raw_data['guidedgamenightfall'][0]['name'])
            embed.append(discord.Embed(type="rich"))
            embed[1].color = discord.Color(0x515A77)
            embed[1].set_thumbnail(url=self.icon_prefix+"/common/destiny2_content/icons"
                                                   "/DestinyMilestoneDefinition_a72e5ce5c66e21f34a420271a30d7ec3.png")
            embed[1].title = raw_data['ordeal'][0]['title']
            embed[1].add_field(name=raw_data['ordeal'][0]['name'], value=raw_data['ordeal'][0]['description'])
            embed.append(discord.Embed(type="rich"))
            embed[2].color = discord.Color(0x5C1E1F)
            embed[2].set_thumbnail(url=self.icon_prefix+"/common/destiny2_content/icons"
                                                   "/DestinyActivityModeDefinition_48ad57129cd0c46a355ef8bcaa1acd04.png")
            embed[2].title = tr['nightmares']
            for item in raw_data['nightmare']:
                embed[2].add_field(name=item['name'], value=item['description'], inline=True)
            embed.append(discord.Embed(type="rich"))
            embed[3].color = discord.Color(0x14563f)
            embed[3].set_thumbnail(url=self.icon_prefix+"/common/destiny2_content/icons"
                                                   "/DestinyActivityModeDefinition_e74b3385c5269da226372df8ae7f500d.png")
            embed[3].title = tr['reckoningboss']
            embed[3].add_field(name=translation[lang][raw_data['reckoning']['boss']], value=raw_data["reckoning"]['desc'])
            embed.append(discord.Embed(type="rich"))
            embed[4].color = discord.Color(0x652911)
            embed[4].set_thumbnail(url=self.icon_prefix+raw_data['cruciblerotator'][0]['icon'])
            embed[4].title = tr['cruciblerotators']
            for item in raw_data['cruciblerotator']:
                embed[4].add_field(name=item['name'], value=item['description'])

        return embed


    async def on_ready(self):
        lang = self.args.lang

        await self.token_update()
        await self.update_history()
        if self.args.forceupdate:
            if self.args.type == 'daily':
                await self.daily_update()
            if self.args.type == 'weekly':
                await self.weekly_update()
            if self.args.type == 'spider':
                await self.spider_update()
            if self.args.type == 'xur':
                await self.xur_update()
        self.sched.add_job(self.daily_update, 'cron', hour='17', minute='0', second='30')
        self.sched.add_job(self.spider_update, 'cron', hour='1', minute='0', second='10')
        self.sched.add_job(self.weekly_update, 'cron', day_of_week='tue', hour='17', minute='0', second='40')
        self.sched.add_job(self.xur_update, 'cron', day_of_week='fri', hour='17', minute='5')
        self.sched.add_job(self.update_history, 'cron', hour='2')
        self.sched.add_job(self.token_update, 'interval', hours=1)
        self.sched.start()


    async def on_message(self, message):
        if message.author == self.user:
            return

        if message.content.startswith('!stop'):
            bot_info = await self.application_info()
            if bot_info.owner == message.author:
                msg = 'Ok, {}'.format(message.author.mention)
                await message.channel.send(msg)
                self.sched.shutdown(wait=True)
                await self.update_history()
                await self.logout()
                await self.close()
                return
            else:
                msg = '{}!'.format(message.author.mention)
                e = discord.Embed(title='I will not obey you.', type="rich",
                                  url='https://www.youtube.com/watch?v=qn9FkoqYgI4')
                e.set_image(url='https://i.ytimg.com/vi/qn9FkoqYgI4/hqdefault.jpg')
                await message.channel.send(msg, embed=e)
                return


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


    async def daily_update(self):
        await self.wait_until_ready()
        game = discord.Game('updating daily')
        await self.change_presence(activity=game)
        translations_file = open('translations.json', 'r', encoding='utf-8')
        translations = json.loads(translations_file.read())
        translations_file.close()

        lang = self.args.lang
        upd_type = 'daily'

        bungie_data = await self.upd(translations, lang, upd_type)

        if bungie_data:
            await self.post_updates(bungie_data, upd_type, translations)

            if self.args.forceupdate:
                await self.update_history()

        game = discord.Game('waiting')
        await self.change_presence(activity=game)


    async def weekly_update(self):
        await self.wait_until_ready()
        game = discord.Game('updating weekly')
        await self.change_presence(activity=game)
        translations_file = open('translations.json', 'r', encoding='utf-8')
        translations = json.loads(translations_file.read())
        translations_file.close()

        lang = self.args.lang
        upd_type = 'weekly'

        bungie_data = await self.upd(translations, lang, upd_type)

        if bungie_data:
            await self.post_updates(bungie_data, upd_type, translations)

            if self.args.forceupdate:
                await self.update_history()

        game = discord.Game('waiting')
        await self.change_presence(activity=game)


    async def spider_update(self):
        await self.wait_until_ready()
        game = discord.Game('updating spider')
        await self.change_presence(activity=game)
        translations_file = open('translations.json', 'r', encoding='utf-8')
        translations = json.loads(translations_file.read())
        translations_file.close()

        lang = self.args.lang
        upd_type = 'spider'

        bungie_data = await self.upd(translations, lang, upd_type)

        if bungie_data:
            await self.post_updates(bungie_data, upd_type, translations)

            if self.args.forceupdate:
                await self.update_history()

        game = discord.Game('waiting')
        await self.change_presence(activity=game)


    async def xur_update(self):
        await self.wait_until_ready()
        game = discord.Game('updating xur')
        await self.change_presence(activity=game)
        translations_file = open('translations.json', 'r', encoding='utf-8')
        translations = json.loads(translations_file.read())
        translations_file.close()

        lang = self.args.lang
        upd_type = 'xur'

        bungie_data = await self.upd(translations, lang, upd_type)

        if bungie_data:
            await self.post_updates(bungie_data, upd_type, translations)

            if self.args.forceupdate:
                await self.update_history()

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
            refresh = self.refresh_token(self.token['refresh'])


    async def post_updates(self, bungie_data, upd_type, translations):
        lang = self.args.lang
        hist = self.curr_hist

        if not self.args.nomessage:
            embed = self.create_embeds(bungie_data, upd_type, lang, translations)

            for server in self.guilds:
                hist[str(server.id)]['server_name'] = server.name.strip('\'')
                for channel in server.channels:
                    if channel.name == 'resetbot':
                        i = 0
                        for item in embed:
                            if hist[str(server.id)][translations["{}embeds".format(upd_type)][str(i)]] and not self.args.noclear:
                                last = await channel.fetch_message(hist[str(server.id)][translations["{}embeds".format(upd_type)][str(i)]])
                                await last.delete()
                            if upd_type == 'weekly' and hist[str(server.id)]['xur']:
                                xur_last = await channel.fetch_message(hist[str(server.id)]['xur'])
                                await xur_last.delete()
                                hist[str(server.id)]['xur'] = False
                            message = await channel.send(embed=item)
                            hist[str(server.id)][translations["{}embeds".format(upd_type)][str(i)]] = message.id
                            i += 1


    def start_up(self):
        self.get_args()
        token = self.api_data['token']
        print('hmm')
        self.run(token)


    async def upd(self, activity_types, lang, get_type):
        # check if token has expired, if so we have to oauth, if not just refresh the token
        if self.token['expires'] < time.time():
            if '--oauth' in sys.argv:
                oauth.get_oauth(self.api_data)
            else:
                print('refresh token expired!  run the script with --oauth or add a valid token.js file!')
                return False
        else:
            refresh = self.refresh_token(self.token['refresh'])
            data = await self.get_data(refresh, activity_types, lang, get_type)

        return data


if __name__ == '__main__':
    b = ClanBot()
    b.start_up()