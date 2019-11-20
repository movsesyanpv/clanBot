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

app = Flask(__name__)
client = discord.Client()

apidatafile = open('api.json', 'r')
apidata = json.loads(apidatafile.read())

#redirect to the static html page with the link
@app.route('/')
def main():
    return '<a href="https://www.bungie.net/en/oauth/authorize?client_id=' + apidata['id'] + '&response_type=code&state=asdf">Click me to authorize the script</a>'

#catch the oauth redirect
@app.route('/redirect')
def oauthredirect():
    #get the token/refreshtoken/expiration
    code = request.args.get('code')
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    params = {
        'grant_type': 'authorization_code',
        'client_id': apidata['id'],
        'client_secret': apidata['secret'],
        'code': code
    }
    r = requests.post('https://www.bungie.net/platform/app/oauth/token/', data=params, headers=headers)
    resp = r.json()
    
    #save refreshtoken/expiration in token.json
    token = {
        'refresh': resp['refresh_token'],
        'expires': time.time() + resp['refresh_expires_in']
    }
    tokenfile = open('token.json', 'w')
    tokenfile.write(json.dumps(token))
    return 'Got it, rerun the script!'

#spin up the flask server so we can oauth authenticate
def getoauth():
    print('No tokens saved, please authorize the app by going to localhost:4200')
    app.run(port=4200)

#refresh the saved token
def refreshtoken(retoken):
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    params = {
        'grant_type': 'refresh_token',
        'refresh_token': retoken,
        'client_id': apidata['id'],
        'client_secret': apidata['secret']
    }
    r = requests.post('https://www.bungie.net/platform/app/oauth/token/', data=params, headers=headers)
    resp = r.json()

    #save new refreshtoken/expiration in token.json
    token = {
        'refresh': resp['refresh_token'],
        'expires': time.time() + resp['refresh_expires_in']
    }
    tokenfile = open('token.json', 'w')
    tokenfile.write(json.dumps(token))

    #get data with new token
    return resp['access_token']

async def getdata(token):
    print('hmmmmmmm')
    headers = {
        'X-API-Key': apidata['key'],
        'Authorization': 'Bearer ' + token
    }

    lang = "en"

    charinfo = {}
    platform = 0
    membershipid = ''
    charid = ''
    try:
        charfile = open('char.json', 'r')
        charinfo = json.loads(charfile.read())
        platform = charinfo['platform']
        membershipid = charinfo['membershipid']
        charid = charinfo['charid']
    except FileNotFoundError:
        validinput = False
        while not validinput:
            print("What platform are you playing on?")
            print("1. Xbox")
            print("2. Playstation")
            print("3. Battle.net")
            platform = int(input())
            if platform <= 3 and platform >= 1:
                validinput = True
        # if platform == 3:
        #     platform = 4
        platform = str(platform)
        charinfo['platform'] = platform
        
        validinput = False
        while not validinput:
            name = input("What's the name of your account on there? (include # numbers): ")
            searchurl = 'https://www.bungie.net/platform/Destiny2/SearchDestinyPlayer/' + str(platform) + '/' + quote(name) + '/'
            searchresp = requests.get(searchurl, headers=headers)
            search = searchresp.json()['Response']
            if len(search) > 0:
                validinput = True
                membershipid = search[0]['membershipId']
                charinfo['membershipid'] = membershipid

        #get the first character and just roll with that
        charsearchurl = 'https://www.bungie.net/platform/Destiny2/' + platform + '/Profile/' + membershipid + '/'
        charsearchparams = {
            'components': '200'
        }
        charsearchresp = requests.get(charsearchurl, params=charsearchparams, headers=headers)
        chars = charsearchresp.json()['Response']['characters']['data']
        charid = chars[sorted(chars.keys())[0]]['characterId']
        charinfo['charid'] = charid

        charfile = open('char.json', 'w')
        charfile.write(json.dumps(charinfo))

    #create data.json dict
    data = {
        'spiderinventory': [],
        'bansheeinventory': [],
        'adainventory': [],
        'activenightfalls': [],
        'guidedgamenightfall': []
    }

    destiny = pydest.Pydest(apidata['key'])

    #get spider's inventory
    vendorparams = {
        'components': '401,402'
    }
    spiderurl = 'https://www.bungie.net/platform/Destiny2/' + platform + '/Profile/' + membershipid + '/Character/' + charid + '/Vendors/863940356'
    spiderresp = requests.get(spiderurl, params=vendorparams, headers=headers)
    spidercats = spiderresp.json()['Response']['categories']['data']['categories']
    spidersales = spiderresp.json()['Response']['sales']['data']

    #if spider inventory breaks, look here
    itemstoget = spidercats[0]['itemIndexes']
    
    #iterate through keys in spidersales, except masterwork cores (everyone knows about those)
    for key in itemstoget:
        item = spidersales[str(key)]
        itemhash = item['itemHash']
        if not itemhash == 1812969468:
            currency = item['costs'][0]
            definition = 'DestinyInventoryItemDefinition'
            itemresp = await destiny.decode_hash(itemhash, definition, language=lang)
            currencyresp = await destiny.decode_hash(currency['itemHash'], definition, language=lang)

            #query bungie api for name of item and name of currency
            itemnamelist = itemresp['displayProperties']['name'].split()[1:]
            itemname = ' '.join(itemnamelist)
            currencycost = str(currency['quantity'])
            currencyitem = currencyresp['displayProperties']['name']

            #put result in a well formatted string in the data dict
            itemdata = {
                'name': itemname,
                'cost': currencycost + ' ' + currencyitem
            }
            data['spiderinventory'].append(itemdata)

    #this is gonna break monday-thursday
    #get xur inventory
    xururl = 'https://www.bungie.net/platform/Destiny2/' + platform + '/Profile/' + membershipid + '/Character/' + charid + '/Vendors/534869653'
    xurresp = requests.get(xururl, params=vendorparams, headers=headers)
    if not xurresp.json()['ErrorCode'] == 1627:
        data['xur'] = {
            'xurweapon': '',
            'xurarmor': []
        }
        xursales = xurresp.json()['Response']['sales']['data']

        #go through keys in xur inventory (except the first one, that's 5 of swords and is there every week)
        for key in sorted(xursales.keys()):
            itemhash = xursales[key]['itemHash']
            if not itemhash == 4285666432:
                itemdefurl = 'https://www.bungie.net/platform/Destiny2/Manifest/DestinyInventoryItemDefinition/' + str(itemhash) + '/'
                itemresp = requests.get(itemdefurl, headers=headers)
                itemname = itemresp.json()['Response']['displayProperties']['name']
                if itemresp.json()['Response']['itemType'] == 2:
                    itemsockets = itemresp.json()['Response']['sockets']['socketEntries']
                    plugs = []
                    for s in itemsockets:
                        if len(s['reusablePlugItems']) > 0 and s['plugSources'] == 2:
                            plugs.append(s['reusablePlugItems'][0]['plugItemHash'])

                    perks = []

                    for p in plugs[2:]:
                        plugurl = 'https://www.bungie.net/platform/Destiny2/Manifest/DestinyInventoryItemDefinition/' + str(p) + '/'
                        plugresp = requests.get(plugurl, headers=headers)
                        perk = {
                            'name': plugresp.json()['Response']['displayProperties']['name'],
                            'desc': plugresp.json()['Response']['displayProperties']['description']
                        }
                        perks.append(perk)
                    
                    exotic = {
                        'name': itemname,
                        'perks': perks
                    }

                    if itemresp.json()['Response']['classType'] == 0:
                        exotic['class'] = 'Titan'
                    elif itemresp.json()['Response']['classType'] == 1:
                        exotic['class'] = 'Hunter'
                    elif itemresp.json()['Response']['classType'] == 2:
                        exotic['class'] = 'Warlock'

                    data['xur']['xurarmor'].append(exotic)
                else:
                    data['xur']['xurweapon'] = itemname
    else:
        #do something if xur isn't here
        pass

    bansheeurl = 'https://www.bungie.net/platform/Destiny2/' + platform + '/Profile/' + membershipid + '/Character/' + charid + '/Vendors/672118013'
    bansheeresp = requests.get(bansheeurl, params=vendorparams, headers=headers)
    bansheesales = bansheeresp.json()['Response']['sales']['data']

    for key in sorted(bansheesales):
        itemhash = bansheesales[key]['itemHash']
        definition = 'DestinyInventoryItemDefinition'
        
        if not itemhash == 2731650749 and not itemhash == 1493877378:
            rjson = await destiny.decode_hash(itemhash, definition, language=lang)

            #query bungie api for name of item and name of currency
            itemname = rjson['displayProperties']['name']
            try:
                itemperkhash = rjson['perks'][0]['perkHash']
                definition = 'DestinySandboxPerkDefinition'
                perkresp = await destiny.decode_hash(itemperkhash, definition, language=lang)
                itemdesc = perkresp['displayProperties']['description']
            except IndexError:
                itemdesc = ""

            mod = {
                'name': itemname,
                'desc': itemdesc
            }

            #put result in a well formatted string in the data dict
            data['bansheeinventory'].append(mod)

    adaurl = 'https://www.bungie.net/platform/Destiny2/' + platform + '/Profile/' + membershipid + '/Character/' + charid + '/Vendors/2917531897'
    adaresp = requests.get(adaurl, params=vendorparams, headers=headers)
    adacats = adaresp.json()['Response']['categories']['data']['categories']
    adasales = adaresp.json()['Response']['sales']['data']

    itemstoget = adacats[0]['itemIndexes']

    for key in itemstoget:
        itemhash = adasales[str(key)]['itemHash']
        itemdefurl = 'https://www.bungie.net/platform/Destiny2/Manifest/DestinyInventoryItemDefinition/' + str(itemhash) + '/'
        itemresp = requests.get(itemdefurl, headers=headers)

        #query bungie api for name of item and name of currency
        itemnamelist = itemresp.json()['Response']['displayProperties']['name'].split()
        if 'Powerful' in itemnamelist:
            itemnamelist = itemnamelist[1:]
        itemname = ' '.join(itemnamelist)

        data['adainventory'].append(itemname)

    nightfallurl = 'https://www.bungie.net/platform/Destiny2/' + platform + '/Profile/' + membershipid + '/Character/' + charid + '?components=204'
    nightfallresp = requests.get(nightfallurl, headers=headers)
    # print(json.dumps(nightfallresp.json()['Response']['activities']['data']['availableActivities'], indent = 4, sort_keys=True)+"\n")

    for key in nightfallresp.json()['Response']['activities']['data']['availableActivities']:
        itemhash = key['activityHash']
        try:
            recommendedLight = key['recommendedLight']
            if recommendedLight == 820:
                definition = 'DestinyActivityDefinition'
                rjson = await destiny.decode_hash(itemhash, definition, language=lang)
                if rjson['matchmaking']['requiresGuardianOath']:
                    data['guidedgamenightfall'].append(rjson['displayProperties']['name'])
                else:
                    data['activenightfalls'].append(rjson['displayProperties']['name'])
                # print(itemhash," ",rjson['displayProperties']['name'])
                # print(json.dumps(rjson, indent = 4, sort_keys=True)+"\n")
        except KeyError:
            continue

    await destiny.close()

    return data

def updaterepo(data):
    repo = None
    try:
        repo = Repo('wherethefuckisxur')
        repo.remote().pull()
    except:
        repo = Repo.clone_from('https://github.com/dorkthrone/wherethefuckisxur.git', 'wherethefuckisxur')

    f = open('wherethefuckisxur/data.json', 'w')
    f.write(json.dumps(data))
    f.close()
    index = repo.index
    index.add(['data.json'])
    index.commit('Update data for ' + datetime.today().strftime('%I:%M %p %m/%d'))
    repo.remote().push()

@client.event
async def on_ready():
    bungiedata = await upd()

    table = []
    msg = 'Spider sells this:\n```'
    for item in bungiedata['spiderinventory']:
        table.append([item['name'],item['cost']])
    msg = msg + str(tabulate(table, tablefmt="fancy_grid")) + "```"

    for server in client.guilds:
        for channel in server.channels:
            if channel.name == 'resetbot':
                if hist['spider']:
                    last = await channel.fetch_message(hist['spider'])
                    await last.delete()
                message = await channel.send(msg)
                hist['spider'] = message.id
                print('yay ', message.id)
            if '--production' in sys.argv:
                if channel.name == 'd2resetpreview':
                    if hist['spiderProd']:
                        last = await channel.fetch_message(hist['spiderProd'])
                        await last.delete()
                    message = await channel.send(msg)
                    hist['spiderProd'] = message.id

    f = open('history.json', 'w')
    f.write(json.dumps(hist))
    await client.logout()
    await client.close()

def discordPost():
    with open('auth.json') as json_file:
        data = json.load(json_file)
    TOKEN = data['token']
    print('hmm')
    client.run(TOKEN)

async def upd():
    #check to see if token.json exists, if not we have to start with oauth
    try:
        f = open('token.json', 'r')
    except FileNotFoundError:
        if '--oauth' in sys.argv:
            getoauth()
        else:
            print('token file not found!  run the script with --oauth or add a valid token.js file!')
            return

    try:
        token = json.loads(f.read())
    except json.decoder.JSONDecodeError:
        if '--oauth' in sys.argv:
            getoauth()
        else:
            print('token file invalid!  run the script with --oauth or add a valid token.js file!')
            return


    #check if token has expired, if so we have to oauth, if not just refresh the token
    if token['expires'] < time.time():
        if '--oauth' in sys.argv:
            getoauth()
        else:
            print('refresh token expired!  run the script with --oauth or add a valid token.js file!')
            return
    else:
        refresh = refreshtoken(token['refresh'])
        data = await getdata(refresh)

        print(json.dumps(data, ensure_ascii=False))
    
        if '--update-repo' in sys.argv:
            #write data dict to the data.json file
            f = open('databack.json', 'w')
            f.write(json.dumps(data, ensure_ascii=False))

            # updaterepo(data)
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
        "spiderProd": False
    }

discordPost()