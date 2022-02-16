The bot supports slash commands. Use `/help` command to get current command list.

Here's the list of available commands
```
    online       Get the list of online clan members.
    top          Print top players for one of the available metrics.
    support      Get the link to the support server
    update       Get updates from Bungie for the selected types
    help         Print this message
    lfglist      Print your LFG list
    lfgcleanup   Delete expired LFG posts
    regnotifier  Register notifier channel
    rmnotifier   Deregister notifier channel
    setlang      Set server language
    setclan      Set Destiny 2 clan for the server.
    autopost     Autopost channel settings
    lfg          Create an LFG message
    editlfg      Edit LFG message
```

Features:

 - Gets updates from Bungie's API, such as weekly/daily reset info, Spider materials costs, Xur's location and inventory (requires setting up a notifier channel)
 - Organizes LFGs
 - Makes clan leaderboards for every emblem metric available in Destiny 2 (requires setting up clan for server)
 - Supports multiple languages (same as Destiny 2, but some lines might be untranslated).

You can help with the translations by going to the [POEditor](https://poeditor.com/join/project/r0GBXOfyqt) and joining the project.

P.S. Legacy commands are available with `{bot mention}` as prefix, but they are deprecated.


# Old

The bot's prefix defaults to `?` and `{bot mention}`. You can change it with `setprefix` command. Use `help` command to get current command list.

Here's the list of available commands
```
    top          Print top players for one of the available metrics.
    help         Print this message
    update       Get updates from Bungie for the given TYPE
    setlang      Set server language
    lfg          Create an LFG message
    rmnotifier   Deregister notifier channel
    edit_lfg     Edit LFG message
    lfglist      Print your LFG list
    setclan      Set Destiny 2 clan for the server.
    regnotifier  Register notifier channel
    setprefix    Set available prefixes
    prefix       Print available prefixes
    lfgcleanup   Delete groups that are unavailable or inactive
```

Features:

 - Gets updates from Bungie's API, such as weekly/daily reset info, Spider materials costs, Xur's location and inventory (requires setting up a notifier channel)
 - Organizes LFGs
 - Makes clan leaderboards for every emblem metric available in Destiny 2 (requires setting up clan for server)
 - Supports multiple languages (same as Destiny 2, but some lines might be untranslated). You can help with the translations by going to the [POEditor](https://poeditor.com/join/project/r0GBXOfyqt) and joining the project