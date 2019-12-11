import discord
import json
from datetime import datetime

class LFG():
    group_id = 0
    size = 0
    name = ''
    time = 0
    description = ''
    owner = ''
    wanters = []
    going = []
    the_role = ''
    announcement_msg = ''

    def __init__(self, message, **options):
        super().__init__(**options)
        content = message.content.splitlines()
        self.name = content[1]
        self.time = datetime.strptime(content[3], "%d-%m-%Y %H:%M %z")
        self.description = content[5]
        self.size = int(content[7])
        self.group_id = message.id
        self.owner = message.author
        self.announcement_msg = message
        self.the_role = message.guild.get_role(message.guild.id)
        for role in message.guild.roles:
            if role.name.lower() == 'guardian':
                self.the_role = role

    def set_id(self, new_id):
        self.group_id = new_id

    def is_raid(self, message):
        return message.id == self.group_id

    async def update_group_msg(self, reaction, user, translations):
        msg = "{}, {} {}\n{} {}\n{}\n{}: ".format(self.the_role.mention, translations['lfg']['go'], self.name, translations['lfg']['at'], self.time, self.description, translations['lfg']['participants'])
        for participant in self.going:
            msg = '{} {}'.format(msg, participant)
        if len(self.wanters) > 0:
            msg = '{}\n{}: '.format(msg, translations['lfg']['wanters'])
            for wanter in self.wanters:
                msg = '{} {}'.format(msg, wanter)
        await reaction.message.edit(content=msg)

    async def ping_going(self):
        msg = "time!\n"
        announcement = await self.announcement_msg.channel.fetch_message(self.group_id)
        for participant in self.going:
            msg = '{} {}'.format(msg, participant)
        await announcement.channel.send(msg, delete_after=3600)
