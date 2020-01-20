import discord
import json
import sqlite3
from datetime import datetime


class LFG():
    conn = ''

    def __init__(self, **options):
        super().__init__(**options)
        self.conn = sqlite3.connect('lfg.db')

    def add(self, message: discord.Message):
        content = message.content.splitlines()
        name = content[1]
        try:
            time = datetime.strptime(content[3], "%d-%m-%Y %H:%M %z")
        except ValueError:
            time = datetime.now().strftime("%d-%m-%Y %H:%M")
            time = datetime.strptime(time, "%d-%m-%Y %H:%M")
        description = content[5]
        size = int(content[7])
        group_id = message.id
        owner = message.author.id
        group_mode = 'basic'
        if len(content) >= 9:
            group_mode = content[8]
        the_role = message.guild.get_role(message.guild.id)
        for role in message.guild.roles:
            if role.name.lower() == 'guardian':
                the_role = role
        c = self.conn.cursor()

        try:
            c.execute('''CREATE TABLE raid
                     (group_id integer, size integer, name text, time integer, description text, owner integer, 
                     wanters text, going text, the_role integer, group_mode text, dm_message integer, 
                     lfg_channel integer, want_dm text)''')
        except sqlite3.OperationalError:
            pass

        newlfg = [(group_id, size, name, datetime.timestamp(time), description,
                   owner, '[]', '[]', the_role.id, group_mode, 0, message.channel.id, '[]')]
        c.executemany("INSERT INTO raid VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", newlfg)
        self.conn.commit()

    def del_entry(self, group_id):
        c = self.conn.cursor()
        c.executemany('''DELETE FROM raid WHERE group_id LIKE (?)''', [(group_id,)])
        self.conn.commit()

    def set_id(self, new_id, group_id):
        c = self.conn.cursor()
        c.execute('''UPDATE raid SET group_id=? WHERE group_id=?''', (new_id, group_id))
        self.conn.commit()

    def is_raid(self, message):
        c = self.conn.cursor()
        cell = c.execute('SELECT group_id FROM raid WHERE group_id=?', (message.id,))
        cell = cell.fetchall()
        if len(cell) == 0:
            return False
        else:
            cell = cell[0]
            return message.id == cell[0]

    def get_cell(self, search_field, group_id, field):
        c = self.conn.cursor()
        cell = c.execute('SELECT {} FROM raid WHERE {}=?'.format(field, search_field), (group_id,)).fetchone()
        if len(cell) > 0:
            return cell[0]
        else:
            return None

    def add_people(self, group_id, user):
        c = self.conn.cursor()
        goers = c.execute('SELECT going FROM raid WHERE group_id=?', (group_id,))
        goers = eval(goers.fetchone()[0])

        wanters = c.execute('SELECT wanters FROM raid WHERE group_id=?', (group_id,))
        wanters = eval(wanters.fetchone()[0])

        w_dm = c.execute('SELECT want_dm FROM raid WHERE group_id=?', (group_id,))
        w_dm = eval(w_dm.fetchone()[0])

        size = self.get_cell('group_id', group_id, 'size')
        group_mode = self.get_cell('group_id', group_id, 'group_mode')

        if len(goers) < size and group_mode == 'basic':
            if not user.mention in goers:
                goers.append(user.mention)
        else:
            if not user in wanters:
                wanters.append(user.mention)
                w_dm.append(user.display_name)

        c.execute('''UPDATE raid SET wanters=? WHERE group_id=?''', (str(wanters), group_id))
        c.execute('''UPDATE raid SET want_dm=? WHERE group_id=?''', (str(w_dm), group_id))
        c.execute('''UPDATE raid SET going=? WHERE group_id=?''', (str(goers), group_id))
        self.conn.commit()

    def rm_people(self, group_id, user):
        c = self.conn.cursor()
        goers = c.execute('SELECT going FROM raid WHERE group_id=?',(group_id,))
        goers = eval(goers.fetchone()[0])

        wanters = c.execute('SELECT wanters FROM raid WHERE group_id=?',(group_id,))
        wanters = eval(wanters.fetchone()[0])

        w_dm = c.execute('SELECT want_dm FROM raid WHERE group_id=?', (group_id,))
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

        c.execute('''UPDATE raid SET wanters=? WHERE group_id=?''', (str(wanters), group_id))
        c.execute('''UPDATE raid SET want_dm=? WHERE group_id=?''', (str(w_dm), group_id))
        c.execute('''UPDATE raid SET going=? WHERE group_id=?''', (str(goers), group_id))
        self.conn.commit()

    async def update_group_msg(self, message, translations):
        c = self.conn.cursor()

        role = message.guild.get_role(self.get_cell('group_id', message.id, 'the_role'))
        name = self.get_cell('group_id', message.id, 'name')
        time = datetime.fromtimestamp(self.get_cell('group_id', message.id, 'time'))
        description = self.get_cell('group_id', message.id, 'description')
        msg = "{}, {} {}\n{} {}\n{}".\
            format(role.mention, translations['lfg']['go'], name, translations['lfg']['at'], time, description)
        goers = c.execute('SELECT going FROM raid WHERE group_id=?',(message.id,))
        goers = eval(goers.fetchone()[0])
        wanters = c.execute('SELECT wanters FROM raid WHERE group_id=?',(message.id,))
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

    async def upd_dm(self, owner, translations):
        c = self.conn.cursor()

        wanters = c.execute('SELECT want_dm FROM raid WHERE owner=?', (owner.id,))
        wanters = eval(wanters.fetchone()[0])

        dm_id = self.get_cell('owner', owner.id, 'dm_message')

        emoji = ["{}\N{COMBINING ENCLOSING KEYCAP}".format(num) for num in range(1, 7)]

        msg = translations['lfg']['newBlood']
        if owner.dm_channel is None:
            await owner.create_dm()
        if dm_id == 0:
            dm_message = await owner.dm_channel.send(msg)
        else:
            dm_message = await owner.dm_channel.fetch_message(dm_id)

        await dm_message.delete()
        dm_id = 0
        if len(wanters) > 0:
            i = 0
            for wanter in wanters:
                if i < 6:
                    msg = '{}\n{}. {}'.format(msg, emoji[i], wanter)
                    dm_message = await owner.dm_channel.send(msg)
                    dm_id = dm_message.id
                    await dm_message.add_reaction(emoji[i])
                    i = i + 1
        
        c.execute('''UPDATE raid SET dm_message=? WHERE owner=?''', (dm_id, owner.id))
        self.conn.commit()

    async def dm_new_people(self, group_id, owner, translations):
        c = self.conn.cursor()

        wanters = c.execute('SELECT want_dm FROM raid WHERE group_id=?', (group_id,))
        wanters = eval(wanters.fetchone()[0])

        dm_id = self.get_cell('group_id', group_id, 'dm_message')

        emoji = ["{}\N{COMBINING ENCLOSING KEYCAP}".format(num) for num in range(1, 7)]

        msg = translations['lfg']['newBlood']
        if owner.dm_channel is None:
            await owner.create_dm()
        if dm_id == 0:
            dm_message = await owner.dm_channel.send(msg)
        else:
            dm_message = await owner.dm_channel.fetch_message(dm_id)

        if len(wanters) > 0:
            i = 0
            for wanter in wanters:
                if i < 6:
                    msg = '{}\n{}. {}'.format(msg, emoji[i], wanter)
                    await dm_message.edit(content=msg)
                    await dm_message.add_reaction(emoji[i])
                    i = i + 1

        c.execute('''UPDATE raid SET dm_message=? WHERE group_id=?''', (dm_message.id, group_id))
        self.conn.commit()

    async def add_going(self, group_id, number):
        c = self.conn.cursor()
        goers = c.execute('SELECT going FROM raid WHERE group_id=?', (group_id,)).fetchone()

        if len(goers) > 0:
            goers = eval(goers[0])
        else:
            goers = []

        wanters = c.execute('SELECT wanters FROM raid WHERE group_id=?', (group_id,))
        wanters = eval(wanters.fetchone()[0])

        w_dm = c.execute('SELECT want_dm FROM raid WHERE group_id=?', (group_id,))
        w_dm = eval(w_dm.fetchone()[0])

        size = self.get_cell('group_id', group_id, 'size')
        group_mode = self.get_cell('group_id', group_id, 'group_mode')

        if size > len(goers):
            if not wanters[number] in goers:
                goers.append(wanters[number])
                wanters.pop(number)
                w_dm.pop(number)

        c.execute('''UPDATE raid SET wanters=? WHERE group_id=?''', (str(wanters), group_id))
        c.execute('''UPDATE raid SET want_dm=? WHERE group_id=?''', (str(w_dm), group_id))
        c.execute('''UPDATE raid SET going=? WHERE group_id=?''', (str(goers), group_id))
        self.conn.commit()