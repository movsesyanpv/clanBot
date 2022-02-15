# Indeedstor v3.0 changelog

## Discord.py 1.7.3 -> Pycord 2.0

- Buttons and selects are added to lfg commands.
- If the bot has `use_threads` and `manage_threads` permissions, it will not ask you about the group in DMs, it will create a thread instead, when using a regular command.
- Support for slash commands. Regular commands, that have a slash version are now deprecated.

## New features

- Channel registration rework. You can now use `/autopost` command to register a channel for automatic posts.
- Added a message command for editing LFGs.
- The bot will try to respond in your language, when you are using slash commands

### LFG changes

- Initial LFG post creation should be faster.
- Modal windows, buttons and select menus are utilized in the creation process.
- Buttons are used to control the post. Now you can add any reactions to LFG posts without the bot removing them.

### Top command changes

- Metric names are available as autocomplete results. This should provide an easier experience when using the command.
- Added pagination for huge leaderboards.

### Other command changes

- `setlang` and `update` commands no longer need arguments. The bot will respond with options you can choose instead.
- Regular commands are now deprecated and will add a warning to responses.
- Most of the command responses are in embeds now. That allows the bot to send longer responses if necessary.