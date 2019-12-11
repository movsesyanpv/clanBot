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
Redirect URL is set to localhost:4200/redirect
and all of the scopes are checked (this definitely excessive but hey, it works).
```

Create the file `api.json` in the folder with the script and fill it out with all the necessary info from your application's page (the template for the file is above).

On first run, the script will launch a flask server and tell you to navigate to localhost:4200.  When you navigate to there, you must open the developer console and open to the network tab.  Click the link, scroll to the bottom of bungie's page, and click the authorize button.  When you do so, nothing will happen, but you'll see a redirect network event that is cancelled.  You need to copy the link that was attempted to direct to, and go there directly.  If all is well, the script will proceed to the next stage.

Now that you've got oauth taken care of, when you run the script no flask server will kick up, instead it will simply ask what platform you play on (answer with 1, 2, or 3) and for your platform's username.  Once it has this info, it'll go and do its thing, building a data file and committing it to the repository.

Notes: the files `token.json` and `char.json` can be transferred to another machine along with the script to let the script run without any input at all.

# Launch

Python 3.6+ is required

```
usage: main.py [-h] [-nc] [-p] [-nm] [-l LANG] [-t TYPE] [-tp] [-f] [--oauth]

  -h, --help            show this help message and exit
  -nc, --noclear        Don't clear last message of the type
  -p, --production      Use to launch in production mode
  -nm, --nomessage      Don't post any messages
  -l LANG, --lang LANG  Language of data
  -t TYPE, --type TYPE  Type of message. Use with -f
  -tp, --testprod       Use to launch in test production mode
  -f, --forceupdate     Force update right now
  --oauth               Get Bungie access token
```

# Bot commands

## DMable commands

1. `[bot mention] stop` - stop the bot. Mention is required in non-dm channels. Available only to the bot's owner.

## Group channel commands

These don't work in dm channels.

2. `{bot mention} lfg {lfg details}` - create lfg.
3. `{bot mention} regnotifier` - register current channel as reset notifier channel.
4. `{bot mention} update {[daily] [weekly] [spider] [xur]}` - force updates in notifier channels.

# Reset info

To begin receiving Destiny 2 reset information a notifier channel should be registered. After that the bot will be automatically posting daily weekly spider and xur updates. The bot will also try to clean up old messages. If the deletion fails it will inform it's owner about that.

# LFG

LFG creation message has the following syntax:

```
{bot mention} lfg
{lfg name or planned activity}
time:
{time of the activity start}
additional info:
{description of the activity}
size:
{size of the group}
```

Note, that "time:", "additional info:" and "size:" lines are just for readability purposes but are required to be present in some way, e.g. the line "time:" can be anything but the time itself must be on the fourth line of the message. The description should not have any line breaks inside.

When the time comes, the bot will mention every participant and none from reserves. The posts will be automatically deleted after an hour.
