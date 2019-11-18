# Work with Python 3.6
import discord
import requests
import json
import time

def refreshtoken(retoken):
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    params = {
        'grant_type': 'refresh_token',
        'refresh_token': retoken,
        'client_id': data['bungieid'],
        'client_secret': data['bungiesecret']
    }
    # r = requests.post("https://www.bungie.net/en/oauth/authorize?client_id=" + data['bungieid'] + "&response_type=code&state=asdf")
    r = requests.post('https://www.bungie.net/platform/app/oauth/token/', data=params, headers=headers)
    resp = r.json()

    inventoryItemStr = json.dumps(resp, indent = 4, sort_keys=True)
    print(inventoryItemStr)

    #save new refreshtoken/expiration in token.json
    token = {
        'refresh': resp['refresh_token'],
        'expires': time.time() + resp['refresh_expires_in']
    }
    tokenfile = open('token.json', 'w')
    tokenfile.write(json.dumps(token))

    #get data with new token
    return resp['access_token']

with open('auth.json') as json_file:
    data = json.load(json_file)

with open('hashes.json') as json_file:
    hashes = json.load(json_file)

with open('token.json') as json_file:
    token = json.load(json_file)

TOKEN = data['token']

retoken = refreshtoken(token['refresh'])

HEADERS = {
    "X-API-Key":data['bungieapi'],
    "Authorization":'Bearer ' + retoken
}

print(HEADERS)


# r = requests.get("https://www.bungie.net/Platform/Destiny2/Manifest/DestinyMilestoneDefinition/1342567285/", headers=HEADERS);
r = requests.get("https://www.bungie.net/Platform/Destiny2/4/Profile/4611686018477175293/Character/2305843009367074233/Vendors/534869653?components=401,402", headers=HEADERS);
# r = requests.post("https://www.bungie.net/en/oauth/authorize?client_id=" + data['bungieid'] + "&response_type=code&state=asdf")
# print(r)
# r = requests.get("https://www.bungie.net/Platform/Destiny2/4/Profile/4611686018474971535/Character/2305843009339205184?components=204", headers=HEADERS);
# r = requests.get("https://www.bungie.net/Platform/Destiny2/3/Account/4611686018477175293/Stats?components=100", headers=HEADERS);
# r = requests.get("https://www.bungie.net/Platform/Destiny2/Stats/Leaderboards/3/4611686018477175293/2305843009367074233/", headers=HEADERS);
# r = requests.get("https://www.bungie.net/Platform/Destiny2/Milestones/", headers=HEADERS);
# r = requests.get("https://www.bungie.net/Platform/Destiny2/SearchDestinyPlayer/-1/HAPPY VODKA/", headers=HEADERS);

#convert the json object we received into a Python dictionary object
#and print the name of the item
inventoryItem = r.json()
inventoryItemStr = json.dumps(inventoryItem, indent = 4, sort_keys=True)
print(inventoryItemStr)

client = discord.Client()

@client.event
async def on_message(message):
    # we do not want the bot to reply to itself
    if message.author == client.user:
        return

    if message.content.lower().startswith('!hello'):
        msg = 'Hello {0.author.mention}'.format(message)
        await client.send_message(message.channel, msg)

    if message.content.lower().startswith('!item'):
        searchItem = "https://www.bungie.net/Platform/Destiny2/Armory/Search/DestinyInventoryItemDefinition/" + message.content.strip('!item')

        r = requests.get(searchItem, headers=HEADERS);

        inventoryItem = r.json()
        response = inventoryItem['Response']
        inventoryItem = inventoryItem['Response']['results']['results']
        inventoryItemStr = json.dumps(response, indent = 4, sort_keys=True)
        # print(inventoryItemStr)
        imgurl = "https://www.bungie.net/" + inventoryItem[0]['displayProperties']['icon']
        embed = discord.Embed()
        embed.set_image(url=imgurl)
        msg = '{.author.mention}, found {}:\n{}'.format(message,inventoryItem[0]['displayProperties']['name'],inventoryItem[0]['displayProperties']['description'])
        await client.send_message(message.channel, msg, embed=embed)

    if message.content.lower().startswith('!xur') or message.content.lower().startswith('чгк'):
        url = "https://www.bungie.net/Platform/Destiny2/Milestones/" + hashes['xur'] + "/Content"
        r = requests.get(url, headers=HEADERS);
        info = r.json()['Response']
        msg = '{.author.mention}, {}\nStatus: {}\n{}'.format(message,info['about'],info['status'],info['tips'][0])
        await client.send_message(message.channel, msg)

@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')

client.run(TOKEN)