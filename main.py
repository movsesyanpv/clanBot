from flask import Flask, request, session, redirect, url_for
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

app = Flask(__name__)
client = discord.Client()

api_data_file = open('api.json', 'r')
api_data = json.loads(api_data_file.read())


# redirect to the static html page with the link
@app.route('/')
def main():
    return '<a href="https://www.bungie.net/en/oauth/authorize?client_id=' + api_data[
        'id'] + '&response_type=code&state=asdf">Click me to authorize the script</a>'


# catch the oauth redirect
@app.route('/redirect')
def oauth_redirect():
    # get the token/refresh_token/expiration
    code = request.args.get('code')
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    params = {
        'grant_type': 'authorization_code',
        'client_id': api_data['id'],
        'client_secret': api_data['secret'],
        'code': code
    }
    r = requests.post('https://www.bungie.net/platform/app/oauth/token/', data=params, headers=headers)
    resp = r.json()

    # save refresh_token/expiration in token.json
    token = {
        'refresh': resp['refresh_token'],
        'expires': time.time() + resp['refresh_expires_in']
    }
    token_file = open('token.json', 'w')
    token_file.write(json.dumps(token))
    return 'Got it, rerun the script!'


# spin up the flask server so we can oauth authenticate
def get_oauth():
    print('No tokens saved, please authorize the app by going to localhost:4200')
    app.run(port=4200)


# refresh the saved token
def refresh_token(re_token):
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    params = {
        'grant_type': 'refresh_token',
        'refresh_token': re_token,
        'client_id': api_data['id'],
        'client_secret': api_data['secret']
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


def get_bungie_json(name, url, params, headers, data, wait_codes, max_retries):
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


async def get_spider(lang, data, char_info, vendor_params, headers, wait_codes, max_retries):
    destiny = pydest.Pydest(headers['X-API-Key'])

    spider_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/863940356/'. \
        format(char_info['platform'], char_info['membershipid'], char_info['charid'])
    spider_resp = get_bungie_json('spider', spider_url, vendor_params, headers, data, wait_codes, max_retries)
    if not spider_resp:
        await destiny.close()
        return
    spider_cats = spider_resp.json()['Response']['categories']['data']['categories']
    spider_sales = spider_resp.json()['Response']['sales']['data']

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
                'cost': currency_cost + ' ' + currency_item
            }
            data['spiderinventory'].append(item_data)
    await destiny.close()


async def get_xur(lang, translation, data, char_info, vendor_params, headers, wait_codes, max_retries):
    destiny = pydest.Pydest(headers['X-API-Key'])
    # this is gonna break monday-thursday
    # get xur inventory
    xur_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/2190858386/'. \
        format(char_info['platform'], char_info['membershipid'], char_info['charid'])
    xur_resp = get_bungie_json('xur', xur_url, vendor_params, headers, data, wait_codes, max_retries)
    if not xur_resp and not xur_resp.json()['ErrorCode'] == 1627:
        await destiny.close()
        return data

    if not xur_resp.json()['ErrorCode'] == 1627:
        data['xur'] = {
            'xurweapon': '',
            'xurarmor': []
        }
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
    banshee_resp = get_bungie_json('banshee', banshee_url, vendor_params, headers, data, wait_codes, max_retries)
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
    ada_resp = get_bungie_json('ada', ada_url, vendor_params, headers, data, wait_codes, max_retries)
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


async def decode_modifiers(key, destiny, lang):
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


async def get_activities(lang, translation, data, char_info, activities_params, headers, wait_codes, max_retries):
    destiny = pydest.Pydest(headers['X-API-Key'])

    activities_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/'. \
        format(char_info['platform'], char_info['membershipid'], char_info['charid'])
    activities_resp = get_bungie_json('activities', activities_url, activities_params, headers, data, wait_codes,
                                      max_retries)
    local_types = translation[lang]
    if not activities_resp:
        await destiny.close()
        return data

    for key in activities_resp.json()['Response']['activities']['data']['availableActivities']:
        item_hash = key['activityHash']
        definition = 'DestinyActivityDefinition'
        r_json = await destiny.decode_hash(item_hash, definition, language=lang)
        try:
            recommended_light = key['recommendedLight']
            if recommended_light == 820:
                if r_json['matchmaking']['requiresGuardianOath']:
                    data['guidedgamenightfall'].append(r_json['displayProperties']['name'])
                else:
                    data['activenightfalls'].append(r_json['displayProperties']['name'])
        except KeyError:
            pass
        if local_types['heroicstory'] in r_json['displayProperties']['name']:
            data['heroicstory'].append(r_json['displayProperties']['name'].replace(local_types['heroicstory'], ""))
        if local_types['forge'] in r_json['displayProperties']['name']:
            data['forge'].append(r_json['displayProperties']['name'])
        if local_types['ordeal'] in r_json['displayProperties']['name'] and \
                local_types['adept'] in r_json['displayProperties']['name']:
            info = {
                'name': r_json['displayProperties']['name'].replace(local_types['adept'], ""),
                'description': r_json['displayProperties']['description']
            }
            data['ordeal'].append(info)
        if local_types['nightmare'] in r_json['displayProperties']['name'] and \
                local_types['adept'] in r_json['displayProperties']['name']:
            info = {
                'name': r_json['displayProperties']['name'].replace(local_types['adept'], ""),
                'description': r_json['displayProperties']['description']
            }
            data['nightmare'].append(info)
        if translation[lang]['strikes'] in r_json['displayProperties']['name']:
            data['vanguardstrikes'] = await decode_modifiers(key, destiny, lang)
        if translation[lang]['reckoning'] in r_json['displayProperties']['name']:
            data['reckoning'] = await decode_modifiers(key, destiny, lang)
        if r_json['isPvP']:
            if len(r_json['challenges']) > 0:
                obj_def = 'DestinyObjectiveDefinition'
                objective = await destiny.decode_hash(r_json['challenges'][0]['objectiveHash'], obj_def, lang)
                if translation[lang]['rotator'] in objective['displayProperties']['name']:
                    data['cruciblerotator'].append(r_json['displayProperties']['name'])

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


async def get_data(token, translation, lang, get_type):
    print('hmmmmmmm')
    headers = {
        'X-API-Key': api_data['key'],
        'Authorization': 'Bearer ' + token
    }

    wait_codes = [1672]
    max_retries = 10
    first_reset_time = 1539709200
    seconds_since_first = time.time() - first_reset_time
    weeks_since_first = seconds_since_first // 604800
    reckoning_bosses = ['Knights', 'Oryx']

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
        # if platform == 3:
        #     platform = 4
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

    if get_type == 'spider':
        await get_spider(lang, data, char_info, vendor_params, headers, wait_codes, max_retries)
    if get_type == 'xur':
        await get_xur(lang, translation, data, char_info, vendor_params, headers, wait_codes, max_retries)
    if get_type == 'daily':
        await get_activities(lang, translation, data, char_info, activities_params, headers, wait_codes, max_retries)
        # data['vanguardstrikes'] = get_modifiers(lang, 4252456044)
        # data['reckoning'] = get_modifiers(lang, 1446606128)
    if get_type == 'weekly':
        await get_activities(lang, translation, data, char_info, activities_params, headers, wait_codes, max_retries)
        data['reckoning'] = reckoning_bosses[int(weeks_since_first % 2)]

    return data


def create_updates(raw_data, msg_type):
    if raw_data['api_fucked_up']:
        msg = 'Bungie API is unavailable'
        return msg
    if raw_data['api_maintenance']:
        msg = 'Bungie API is brought down for maintenance'
        return msg

    if msg_type == 'spider':
        table = []
        msg = 'Spider sells this:\n```'
        for item in raw_data['spiderinventory']:
            table.append([item['name'], item['cost']])
        msg = msg + str(tabulate(table, tablefmt="fancy_grid"))
    if msg_type == 'xur':
        msg = 'Xur sells this:\n```Weapon: {}\n'.format(raw_data['xur']['xurweapon'])
        for item in raw_data['xur']['xurarmor']:
            msg += '{}: {}\n'.format(item['class'], item['name'])
    if msg_type == 'daily':
        msg = 'Current heroic story missions are:\n```'
        i = 1
        for item in raw_data['heroicstory']:
            msg = msg + "{}. {}\n".format(i, item)
            i += 1
        msg = msg + '```Current forge is:\n```{}'.format(raw_data['forge'][0])
        msg += "```Current Vanguard strikes modifiers:\n```"
        for item in raw_data['vanguardstrikes']:
            msg += "{}: {}\n".format(item['name'], item['description'])
        msg += "```Current Reckoning modifiers:\n```"
        for item in raw_data['reckoning']:
            msg += "{}: {}\n".format(item['name'], item['description'])
    if msg_type == 'weekly':
        msg = 'Current 820 nightfalls are:\n```'
        i = 1
        for item in raw_data['activenightfalls']:
            msg += "{}. {}\n".format(i, item)
            i += 1
        msg += "```Current guided game nightfall:\n```{}```".format(raw_data['guidedgamenightfall'][0])
        msg += "Current ordeal:\n```{}```".format(raw_data['ordeal'][0]['description'])
        msg += "Current nightmare hunts are:\n```"
        i = 1
        for item in raw_data['nightmare']:
            msg += "{}. {}\n  {}\n".format(i, item['name'], item['description'])
            i += 1
        msg += "```The Reckoning boss is:```{}".format(raw_data['reckoning'])
        msg += "```Crucible rotators are:\n```"
        i = 1
        for item in raw_data['cruciblerotator']:
            msg += "{}. {}\n".format(i, item)
            i += 1

    msg = msg + "```"
    return msg


@client.event
async def on_ready():
    parser = argparse.ArgumentParser()
    parser.add_argument('--noclear', action='store_true')
    parser.add_argument('--production', action='store_true')
    parser.add_argument('--nomessage', action='store_true')
    parser.add_argument('--type', type=str, help='What to post', required=True)
    args = parser.parse_args()

    lang = 'en'

    translations_file = open('translations.json', 'r', encoding='utf-8')
    translations = json.loads(translations_file.read())
    translations_file.close()

    bungie_data = await upd(translations, lang, args.type)

    if not args.nomessage:
        msg = create_updates(bungie_data, args.type)

        for server in client.guilds:
            for channel in server.channels:
                if channel.name == 'resetbot':
                    if hist[args.type] and not args.noclear:
                        if args.type == 'weekly' and hist['xur']:
                            xur_last = await channel.fetch_message(hist['xur'])
                            await xur_last.delete()
                            hist['xur'] = False
                        last = await channel.fetch_message(hist[args.type])
                        await last.delete()
                    message = await channel.send(msg)
                    hist[args.type] = message.id
                    print('yay ', message.id)
                if args.production:
                    post_type = args.type + 'Prod'
                    if channel.name == 'd2resetpreview':
                        if hist[post_type] and not args.noclear:
                            if args.type == 'weekly' and hist['xurProd']:
                                xur_last = await channel.fetch_message(hist['xurProd'])
                                await xur_last.delete()
                                hist['xurProd'] = False
                            last = await channel.fetch_message(hist[post_type])
                            await last.delete()
                        message = await channel.send(msg)
                        hist[post_type] = message.id

        f = open('history.json', 'w')
        f.write(json.dumps(hist))

    await client.logout()
    await client.close()


def discord_post():
    with open('auth.json') as json_file:
        data = json.load(json_file)
    token = data['token']
    print('hmm')
    client.run(token)


async def upd(activity_types, lang, get_type):
    # check to see if token.json exists, if not we have to start with oauth
    try:
        f = open('token.json', 'r')
    except FileNotFoundError:
        if '--oauth' in sys.argv:
            get_oauth()
        else:
            print('token file not found!  run the script with --oauth or add a valid token.js file!')
            return

    try:
        token = json.loads(f.read())
    except json.decoder.JSONDecodeError:
        if '--oauth' in sys.argv:
            get_oauth()
        else:
            print('token file invalid!  run the script with --oauth or add a valid token.js file!')
            return

    # check if token has expired, if so we have to oauth, if not just refresh the token
    if token['expires'] < time.time():
        if '--oauth' in sys.argv:
            get_oauth()
        else:
            print('refresh token expired!  run the script with --oauth or add a valid token.js file!')
            return
    else:
        refresh = refresh_token(token['refresh'])
        data = await get_data(refresh, activity_types, lang, get_type)

        print(json.dumps(data, ensure_ascii=False))

        if '--update-repo' in sys.argv:
            # write data dict to the data.json file
            f = open('databack.json', 'w')
            f.write(json.dumps(data, ensure_ascii=False))

    return data


# if __name__ == '__main__':
#     loop = asyncio.get_event_loop()
#     loop.run_until_complete(discordPost())
#     loop.close()

try:
    with open('history.json') as json_file:
        hist = json.load(json_file)
except FileNotFoundError:
    hist = {
        "spider": False,
        "spiderProd": False,
        "weekly": False,
        "weeklyProd": False,
        "daily": False,
        "dailyProd": False,
        "xur": False,
        "xurProd": False
    }

discord_post()
