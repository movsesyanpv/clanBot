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
        announcement_msg = message
        the_role = message.guild.get_role(message.guild.id)
        for role in message.guild.roles:
            if role.name.lower() == 'guardian':
                the_role = role
        c = self.conn.cursor()

        try:
            c.execute('''CREATE TABLE raid
                     (group_id int, size int, name text, time int, description text, owner int, wanters text, going text, the_role int, announcement_msg int)''')
        except sqlite3.OperationalError:
            pass

        newlfg = [(group_id, size, name, datetime.timestamp(time), description, owner,'[]','[]', the_role.id, announcement_msg.id)]
        c.executemany("INSERT INTO raid VALUES (?,?,?,?,?,?,?,?,?,?)",newlfg)
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

    def get_cell(self, group_id, field):
        c = self.conn.cursor()
        cell = c.execute('SELECT {} FROM raid WHERE group_id=?'.format(field), (group_id,)).fetchone()[0]
        return cell

    def add_people(self, group_id, user):
        c = self.conn.cursor()
        goers = c.execute('SELECT going FROM raid WHERE group_id=?',(group_id,))
        goers = eval(goers.fetchone()[0])

        wanters = c.execute('SELECT wanters FROM raid WHERE group_id=?',(group_id,))
        wanters = eval(wanters.fetchone()[0])

        size = self.get_cell(group_id, 'size')

        if len(goers) < size:
            if not user.mention in goers:
                goers.append(user.mention)
        else:
            if not user.mention in wanters:
                wanters.append(user.mention)

        c.execute('''UPDATE raid SET wanters=? WHERE group_id=?''', (str(wanters), group_id))
        c.execute('''UPDATE raid SET going=? WHERE group_id=?''', (str(goers), group_id))
        self.conn.commit()

    def rm_people(self, group_id, user):
        c = self.conn.cursor()
        goers = c.execute('SELECT going FROM raid WHERE group_id=?',(group_id,))
        goers = eval(goers.fetchone()[0])

        wanters = c.execute('SELECT wanters FROM raid WHERE group_id=?',(group_id,))
        wanters = eval(wanters.fetchone()[0])

        size = self.get_cell(group_id, 'size')

        if user.mention in goers:
            goers.pop(goers.index(user.mention))
            if len(wanters) > 0:
                goers.append(wanters[0])
                wanters.pop(0)
        if user.mention in wanters:
            wanters.pop(wanters.index(user.mention))

        c.execute('''UPDATE raid SET wanters=? WHERE group_id=?''', (str(wanters), group_id))
        c.execute('''UPDATE raid SET going=? WHERE group_id=?''', (str(goers), group_id))
        self.conn.commit()

    async def update_group_msg(self, message, translations):
        c = self.conn.cursor()

        role = message.guild.get_role(self.get_cell(message.id, 'the_role'))
        name = self.get_cell(message.id, 'name')
        time = datetime.fromtimestamp(self.get_cell(message.id, 'time'))
        description = self.get_cell(message.id, 'description')
        msg = "{}, {} {}\n{} {}\n{}: ".format(role.mention, translations['lfg']['go'], name, translations['lfg']['at'], time, description)
        goers = c.execute('SELECT going FROM raid WHERE group_id=?',(message.id,))
        goers = eval(goers.fetchone()[0])
        wanters = c.execute('SELECT wanters FROM raid WHERE group_id=?',(message.id,))
        wanters = eval(wanters.fetchone()[0])

        if len(goers) > 0:
            msg = '{}\n{}'.format(msg, translations['lfg']['participants'])
        for participant in goers:
            msg = '{} {}'.format(msg, participant)
        if len(wanters) > 0:
            msg = '{}\n{}: '.format(msg, translations['lfg']['wanters'])
            for wanter in wanters:
                msg = '{} {}'.format(msg, wanter)
        await message.edit(content=msg)
