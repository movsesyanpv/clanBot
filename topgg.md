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
 - Supports multiple languages (same as Destiny 2, but some lines might be untranslated).

You can help with the translations by going to the [POEditor](https://poeditor.com/join/project/r0GBXOfyqt) and joining the project.