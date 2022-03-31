![Discord Bots](https://top.gg/api/widget/servers/677145368894373965.svg)

It would be awesome if you just add the bot to your server, and not actually self-host it. Anyways, the instructions for self-hosting are below.

# Translations

If you speak a language other than English that Destiny supports, a huge help with the development is to provide translations. To help with the translations, go to [POEditor](https://poeditor.com/join/project/r0GBXOfyqt) and join the project.

# Prerequisites

* Flask and Requests installed
* A file called `api.json` in the root of the folder, with the format:

`{
    "token": "discord api key",
    "key": "apikey",
    "id": "client id",
    "secret": "client secret"
}`

# Tutorial

Make sure you install all the packages required, either using pipenv or the requirements.txt file.  Also make sure that git has been setup properly (this script might not even work if git doesn't remember your username/password for github).

Go and register an application at [Bungie's developer portal](https://www.bungie.net/en/Application) and create an app.  The required settings are: 

```
OAuth Client Type is set to Confidential
Redirect URL is set to localhost:4200/redirect or https://YOURDOMAIN:4200/redirect
and all of the scopes are checked (this definitely excessive but hey, it works).
```

Create the file `api.json` in the folder with the script and fill it out with all the necessary info from your application's page (the template for the file is above).

On first run, the script will launch a flask server and tell you to navigate to `localhost:4200`.  When you navigate to there, you must open the developer console and open to the network tab.  Click the link, scroll to the bottom of bungie's page, and click the authorize button.  When you do so, nothing will happen, but you'll see a redirect network event that is cancelled.  You need to copy the link that was attempted to direct to, and go there directly.  If all is well, the script will proceed to the next stage.
When using https, just navigate to `https://YOURDOMAIN:4200` and the rest is pretty straightforward.

Notes: the files `token.json` and `char.json` can be transferred to another machine along with the script to let the script run without any input at all.

# Launch

Python 3.7+ is required (3.6, if you don't need to use `datetime.fromisoformat`)

```
usage: main.py [-h] [-nc] [-p] [-nm] [-l LANG] [-t TYPE] [-tp] [-f] [--oauth]
               [-k KEY] [-c CERT]

optional arguments:
  -h, --help            show this help message and exit
  -nc, --noclear        Don't clear last message of the type
  -p, --production      Use to launch in production mode
  -nm, --nomessage      Don't post any messages
  -l LANG, --lang LANG  Language of data
  -t TYPE, --type TYPE  Type of message. Use with -f
  -tp, --testprod       Use to launch in test production mode
  -f, --forceupdate     Force update right now
  --oauth               Get Bungie access token
  -k KEY, --key KEY     SSL key
  -c CERT, --cert CERT  SSL certificate
```
