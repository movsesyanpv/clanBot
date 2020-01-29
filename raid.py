import discord
import sqlite3
from datetime import datetime
from hashids import Hashids


class LFG():
    conn = ''
    c = ''
    hashids = Hashids()

    def __init__(self, **options):
        super().__init__(**options)
        self.conn = sqlite3.connect('lfg.db')
        self.c = self.conn.cursor()

    def add(self, message: discord.Message):
        content = message.content.splitlines()

        args = self.parse_args(content, message, is_init=True)
        group_id = message.id
        owner = message.author.id

        try:
            self.c.execute('''CREATE TABLE raid
                     (group_id integer, size integer, name text, time integer, description text, owner integer, 
                     wanters text, going text, the_role text, group_mode text, dm_message integer, 
                     lfg_channel integer, channel_name text, server_name text, want_dm text)''')
        except sqlite3.OperationalError:
            pass

        newlfg = [(group_id, args['size'], args['name'], args['time'], args['description'],
                   owner, '[]', '[]', args['the_role'], args['group_mode'], 0, message.channel.id, message.channel.name,
                   message.guild.name, '[]')]
        self.c.executemany("INSERT INTO raid VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", newlfg)
        self.conn.commit()

    @staticmethod
    def parse_args(content, message, is_init):
        time = datetime.now().strftime("%d-%m-%Y %H:%M")

        args = {}
        roles = []
        if is_init:
            args = {
                'group_mode': 'basic',
                'name': '',
                'size': 1,
                'time': datetime.strptime(time, "%d-%m-%Y %H:%M"),
                'description': '',
                'the_role': ''
            }
        for string in content:
            str_arg = string.split(':')
            if len(str_arg) < 2:
                continue
            if 'name:' in string or '-n:' in string:
                args['name'] = str_arg[1].lstrip()
            if 'time:' in string or '-t:' in string:
                try:
                    time_str = '{}:{}'.format(str_arg[1], str_arg[2])
                    args['time'] = datetime.strptime(time_str.lstrip(), "%d-%m-%Y %H:%M %z")
                except ValueError:
                    time = datetime.now().strftime("%d-%m-%Y %H:%M")
                    args['time'] = datetime.strptime(time, "%d-%m-%Y %H:%M")
                args['time'] = datetime.timestamp(args['time'])
            if 'description:' in string or '-d:' in string:
                args['description'] = str_arg[1].lstrip()
            if 'size:' in string or '-s:' in string:
                args['size'] = int(str_arg[1])
            if 'mode:' in string or '-m:' in string:
                args['group_mode'] = str_arg[1].lstrip()
            if 'role:' in string or '-r:' in string:
                roles = [role.strip() for role in str_arg[1].split(';')]

        if not is_init:
            if len(roles) == 0:
                return args

        the_role = []
        if len(roles) == 0 and is_init:
            roles = ['guardian', 'recruit']
        for role in message.guild.roles:
            if role.name.lower() in roles:
                the_role.append(role)
        if len(the_role) == 0:
            the_role.append(message.guild.get_role(message.guild.id))
        the_role_str = the_role[0].mention
        for i in the_role[1:]:
            the_role_str = "{}, {}".format(the_role_str, i.mention)
        args['the_role'] = the_role_str
        return args

    def del_entry(self, group_id):
        self.c.executemany('''DELETE FROM raid WHERE group_id LIKE (?)''', [(group_id,)])
        self.conn.commit()

    def set_id(self, new_id, group_id):
        self.c.execute('''UPDATE raid SET group_id=? WHERE group_id=?''', (new_id, group_id))
        self.conn.commit()

    def is_raid(self, message_id):
        cell = self.c.execute('SELECT group_id FROM raid WHERE group_id=?', (message_id,))
        cell = cell.fetchall()
        if len(cell) == 0:
            return False
        else:
            cell = cell[0]
            return message_id == cell[0]

    def get_cell(self, search_field, group_id, field):
        cell = self.c.execute('SELECT {} FROM raid WHERE {}=?'.format(field, search_field), (group_id,)).fetchone()
        if cell is not None:
            if len(cell) > 0:
                return cell[0]
            else:
                return None

    def add_people(self, group_id, user):
        goers = self.c.execute('SELECT going FROM raid WHERE group_id=?', (group_id,))
        goers = eval(goers.fetchone()[0])

        wanters = self.c.execute('SELECT wanters FROM raid WHERE group_id=?', (group_id,))
        wanters = eval(wanters.fetchone()[0])

        w_dm = self.c.execute('SELECT want_dm FROM raid WHERE group_id=?', (group_id,))
        w_dm = eval(w_dm.fetchone()[0])

        size = self.get_cell('group_id', group_id, 'size')
        group_mode = self.get_cell('group_id', group_id, 'group_mode')

        if len(goers) < size and group_mode == 'basic':
            if user.mention not in goers:
                goers.append(user.mention)
        else:
            if user.mention not in wanters and user.mention not in goers:
                wanters.append(user.mention)
                w_dm.append(user.display_name)

        self.c.execute('''UPDATE raid SET wanters=? WHERE group_id=?''', (str(wanters), group_id))
        self.c.execute('''UPDATE raid SET want_dm=? WHERE group_id=?''', (str(w_dm), group_id))
        self.c.execute('''UPDATE raid SET going=? WHERE group_id=?''', (str(goers), group_id))
        self.conn.commit()

    def rm_people(self, group_id, user):
        goers = self.c.execute('SELECT going FROM raid WHERE group_id=?', (group_id,))
        goers = eval(goers.fetchone()[0])

        wanters = self.c.execute('SELECT wanters FROM raid WHERE group_id=?', (group_id,))
        wanters = eval(wanters.fetchone()[0])

        w_dm = self.c.execute('SELECT want_dm FROM raid WHERE group_id=?', (group_id,))
        w_dm = eval(w_dm.fetchone()[0])

        size = self.get_cell('group_id', group_id, 'size')

        if user.mention in goers:
            goers.pop(goers.index(user.mention))
            if len(wanters) > 0:
                goers.append(wanters[0])
                wanters.pop(0)
                w_dm.pop(0)
        if user.mention in wanters:
            i = wanters.index(user.mention)
            wanters.pop(i)
            w_dm.pop(i)

        self.c.execute('''UPDATE raid SET wanters=? WHERE group_id=?''', (str(wanters), group_id))
        self.c.execute('''UPDATE raid SET want_dm=? WHERE group_id=?''', (str(w_dm), group_id))
        self.c.execute('''UPDATE raid SET going=? WHERE group_id=?''', (str(goers), group_id))
        self.conn.commit()

    async def update_group_msg(self, message, translations):
        role = self.get_cell('group_id', message.id, 'the_role')
        name = self.get_cell('group_id', message.id, 'name')
        time = datetime.fromtimestamp(self.get_cell('group_id', message.id, 'time'))
        description = self.get_cell('group_id', message.id, 'description')
        msg = "{}, {} {}\n{} {}\n{}". \
            format(role, translations['lfg']['go'], name, translations['lfg']['at'], time, description)
        goers = self.c.execute('SELECT going FROM raid WHERE group_id=?', (message.id,))
        goers = eval(goers.fetchone()[0])
        wanters = self.c.execute('SELECT wanters FROM raid WHERE group_id=?', (message.id,))
        wanters = eval(wanters.fetchone()[0])

        if len(goers) > 0:
            msg = '{}\n{}'.format(msg, translations['lfg']['participants'])
            for participant in goers:
                msg = '{} {},'.format(msg, participant)
            msg = '{}.'.format(msg[:-1])
        dm_id = self.get_cell('group_id', message.id, 'dm_message')
        if dm_id == 0:
            if len(wanters) > 0:
                msg = '{}\n{} '.format(msg, translations['lfg']['wanters'])
                for wanter in wanters:
                    msg = '{} {},'.format(msg, wanter)
                msg = '{}.'.format(msg[:-1])
        await message.edit(content=msg)

    async def upd_dm(self, owner, group_id, translations):
        wanters = self.c.execute('SELECT want_dm FROM raid WHERE owner=? AND group_id=?', (owner.id, group_id))
        wanters = eval(wanters.fetchone()[0])

        dm_id = self.c.execute('SELECT dm_message FROM raid WHERE owner=? AND group_id=?', (owner.id, group_id))
        dm_id = dm_id.fetchone()[0]

        emoji = ["{}\N{COMBINING ENCLOSING KEYCAP}".format(num) for num in range(1, 7)]

        lfg = self.c.execute('SELECT group_id, name, time, channel_name, server_name FROM raid WHERE group_id=?',
                             (group_id,))
        lfg = lfg.fetchall()[0]

        msg = "{}\n{}.\n{} {}, #{} {} {}".format(translations['lfg']['newBlood'], lfg[1],
                                                 translations['lfg']['at'].lower(),
                                                 datetime.fromtimestamp(lfg[2]), lfg[3],
                                                 translations['lfg']['server'], lfg[4],
                                                 self.hashids.encode(lfg[0]))
        if owner.dm_channel is None:
            await owner.create_dm()
        if dm_id != 0:
            dm_message = await owner.dm_channel.fetch_message(dm_id)
            await dm_message.delete()
            dm_id = 0

        if len(wanters) > 0:
            i = 0
            dm_message = await owner.dm_channel.send(msg)
            dm_id = dm_message.id
            for wanter in wanters:
                if i < 6:
                    msg = '{}\n{}. {}'.format(msg, emoji[i], wanter)
                    await dm_message.edit(content=msg)
                    await dm_message.add_reaction(emoji[i])
                    i = i + 1

        self.c.execute('''UPDATE raid SET dm_message=? WHERE owner=? AND group_id=?''', (dm_id, owner.id, group_id))
        self.conn.commit()

    async def add_going(self, group_id, number):
        goers = self.c.execute('SELECT going FROM raid WHERE group_id=?', (group_id,)).fetchone()

        if len(goers) > 0:
            goers = eval(goers[0])
        else:
            goers = []

        wanters = self.c.execute('SELECT wanters FROM raid WHERE group_id=?', (group_id,))
        wanters = eval(wanters.fetchone()[0])

        w_dm = self.c.execute('SELECT want_dm FROM raid WHERE group_id=?', (group_id,))
        w_dm = eval(w_dm.fetchone()[0])

        size = self.get_cell('group_id', group_id, 'size')
        group_mode = self.get_cell('group_id', group_id, 'group_mode')

        if size > len(goers):
            if not wanters[number] in goers:
                goers.append(wanters[number])
                wanters.pop(number)
                w_dm.pop(number)

        self.c.execute('''UPDATE raid SET wanters=? WHERE group_id=?''', (str(wanters), group_id))
        self.c.execute('''UPDATE raid SET want_dm=? WHERE group_id=?''', (str(w_dm), group_id))
        self.c.execute('''UPDATE raid SET going=? WHERE group_id=?''', (str(goers), group_id))
        self.conn.commit()

    async def dm_lfgs(self, user):
        lfg_list = self.c.execute('SELECT group_id, name, time, channel_name, server_name FROM raid WHERE owner=?',
                                  (user.id,))
        lfg_list = lfg_list.fetchall()

        msg = "Your LFGs:\n"
        i = 1
        for lfg in lfg_list:
            msg = "{}{}. {} @ {} in #{} of {}, ID: `{}`\n".format(msg, i, lfg[1], datetime.fromtimestamp(lfg[2]),
                                                                  lfg[3], lfg[4], self.hashids.encode(lfg[0]))
            i = i + 1
        if user.dm_channel is None:
            await user.create_dm()
        await user.dm_channel.send(msg)

    async def edit(self, message, old_lfg, translations):
        args = self.parse_args(message.content.splitlines(), message, is_init=False)

        for item in args:
            self.c.execute('''UPDATE raid SET {}=? WHERE group_id=?'''.format(item), (args[item], old_lfg.id))
        self.conn.commit()

        new_lfg = await message.channel.send(self.get_cell('group_id', old_lfg.id, 'the_role'))
        await new_lfg.add_reaction('👌')
        await new_lfg.add_reaction('❌')

        self.c.execute('''UPDATE raid SET group_id=? WHERE group_id=?''', (new_lfg.id, old_lfg.id))
        self.c.execute('''UPDATE raid SET lfg_channel=? WHERE group_id=?''', (message.channel.id, new_lfg.id))
        await old_lfg.delete()
        await message.delete()
        await self.update_group_msg(new_lfg, translations)
        self.conn.commit()
