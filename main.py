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


async def get_data(token):
    print('hmmmmmmm')
    headers = {
        'X-API-Key': api_data['key'],
        'Authorization': 'Bearer ' + token
    }

    lang = "en"

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
        'spiderinventory': [],
        'bansheeinventory': [],
        'adainventory': [],
        'activenightfalls': [],
        'guidedgamenightfall': []
    }

    destiny = pydest.Pydest(api_data['key'])

    # get spider's inventory
    vendor_params = {
        'components': '401,402'
    }
    spider_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/863940356'.\
        format(platform, membership_id, char_id)
    spider_resp = requests.get(spider_url, params=vendor_params, headers=headers)
    spider_cats = spider_resp.json()['Response']['categories']['data']['categories']
    spider_sales = spider_resp.json()['Response']['sales']['data']

    # if spider inventory breaks, look here
    items_to_get = spider_cats[0]['itemIndexes']

    # iterate through keys in spidersales, except masterwork cores (everyone knows about those)
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

    # this is gonna break monday-thursday
    # get xur inventory
    xur_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/534869653'.\
        format(platform, membership_id, char_id)
    xur_resp = requests.get(xur_url, params=vendor_params, headers=headers)
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
                item_def_url = 'https://www.bungie.net/platform/Destiny2/Manifest/DestinyInventoryItemDefinition/{}'.\
                    format(item_hash)
                item_resp = requests.get(item_def_url, headers=headers)
                item_name = item_resp.json()['Response']['displayProperties']['name']
                if item_resp.json()['Response']['itemType'] == 2:
                    item_sockets = item_resp.json()['Response']['sockets']['socketEntries']
                    plugs = []
                    for s in item_sockets:
                        if len(s['reusablePlugItems']) > 0 and s['plugSources'] == 2:
                            plugs.append(s['reusablePlugItems'][0]['plugItemHash'])

                    perks = []

                    for p in plugs[2:]:
                        plug_url = 'https://www.bungie.net/platform/Destiny2/Manifest/DestinyInventoryItemDefinition/{}'.\
                            format(item_hash)
                        plug_resp = requests.get(plug_url, headers=headers)
                        perk = {
                            'name': plug_resp.json()['Response']['displayProperties']['name'],
                            'desc': plug_resp.json()['Response']['displayProperties']['description']
                        }
                        perks.append(perk)

                    exotic = {
                        'name': item_name,
                        'perks': perks
                    }

                    if item_resp.json()['Response']['classType'] == 0:
                        exotic['class'] = 'Titan'
                    elif item_resp.json()['Response']['classType'] == 1:
                        exotic['class'] = 'Hunter'
                    elif item_resp.json()['Response']['classType'] == 2:
                        exotic['class'] = 'Warlock'

                    data['xur']['xurarmor'].append(exotic)
                else:
                    data['xur']['xurweapon'] = item_name
    else:
        # do something if xur isn't here
        pass

    banshee_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/672118013'.\
        format(platform, membership_id, char_id)
    banshee_resp = requests.get(banshee_url, params=vendor_params, headers=headers)
    banshee_sales = banshee_resp.json()['Response']['sales']['data']

    for key in sorted(banshee_sales):
        item_hash = banshee_sales[key]['itemHash']
        definition = 'DestinyInventoryItemDefinition'

        if not item_hash == 2731650749 and not item_hash == 1493877378:
            r_json = await destiny.decode_hash(item_hash, definition, language=lang)

            # query bungie api for name of item and name of currency
            item_name = r_json['displayProperties']['name']
            try:
                itemperkhash = r_json['perks'][0]['perkHash']
                definition = 'DestinySandboxPerkDefinition'
                perkresp = await destiny.decode_hash(itemperkhash, definition, language=lang)
                itemdesc = perkresp['displayProperties']['description']
            except IndexError:
                itemdesc = ""

            mod = {
                'name': item_name,
                'desc': itemdesc
            }

            # put result in a well formatted string in the data dict
            data['bansheeinventory'].append(mod)

    ada_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/Vendors/2917531897'.\
        format(platform, membership_id, char_id)
    ada_resp = requests.get(ada_url, params=vendor_params, headers=headers)
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

    nightfall_url = 'https://www.bungie.net/platform/Destiny2/{}/Profile/{}/Character/{}/?components=204'.\
        format(platform, membership_id, char_id)
    nightfall_resp = requests.get(nightfall_url, headers=headers)
    # print(json.dumps(nightfallresp.json()['Response']['activities']['data']['availableActivities'], indent = 4, sort_keys=True)+"\n")

    for key in nightfall_resp.json()['Response']['activities']['data']['availableActivities']:
        item_hash = key['activityHash']
        try:
            recommended_light = key['recommendedLight']
            if recommended_light == 820:
                definition = 'DestinyActivityDefinition'
                r_json = await destiny.decode_hash(item_hash, definition, language=lang)
                if r_json['matchmaking']['requiresGuardianOath']:
                    data['guidedgamenightfall'].append(r_json['displayProperties']['name'])
                else:
                    data['activenightfalls'].append(r_json['displayProperties']['name'])
                # print(itemhash," ",rjson['displayProperties']['name'])
                # print(json.dumps(rjson, indent = 4, sort_keys=True)+"\n")
        except KeyError:
            continue

    await destiny.close()

    return data

async def create_updates(raw_data, type):
    table = []

    if type == 'spider':
        msg = 'Spider sells this:\n```'
        for item in raw_data['spiderinventory']:
            table.append([item['name'], item['cost']])
    if type == 'nightfall':
        msg = 'Current 820 nightfalls are:\n```'
        for item in raw_data['activenightfalls']:
            table.append(['Usual', item])
        table.append(['Guided game', raw_data['guidedgamenightfall'][0]])

    msg = msg + str(tabulate(table, tablefmt="fancy_grid")) + "```"
    return msg

@client.event
async def on_ready():
    parser = argparse.ArgumentParser()
    parser.add_argument('--noclear', action='store_true')
    parser.add_argument('--production', action='store_true')
    parser.add_argument('--type', type=str, help='What to post', required=True)
    args = parser.parse_args()

    bungie_data = await upd()

    msg = await create_updates(bungie_data, args.type)

    for server in client.guilds:
        for channel in server.channels:
            if channel.name == 'resetbot':
                if hist[args.type] and not args.noclear:
                    last = await channel.fetch_message(hist[args.type])
                    await last.delete()
                message = await channel.send(msg)
                hist[args.type] = message.id
                print('yay ', message.id)
            if args.production:
                post_type = args.type + 'Prod'
                if channel.name == 'd2resetpreview':
                    if hist[post_type]:
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


async def upd():
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
        data = await get_data(refresh)

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
        "nightfall": False,
        "nightfallProd": False
    }

discord_post()
