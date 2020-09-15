import discord
import sqlite3
import os
from datetime import datetime, timezone, timedelta
from hashids import Hashids
from babel.dates import format_datetime, get_timezone_name, get_timezone, get_timezone_gmt


class LFG:
    conn = ''
    c = ''
    hashids = Hashids()
    lfg_i = ['null', 'default', 'vanguard', 'raid', 'crucible', 'gambit']
    lfg_categories = {
        'null': {},
        'default': {},
        'vanguard': {
            "thumbnail": "https://www.bungie.net/common/destiny2_content/icons/f2154b781b36b19760efcb23695c66fe.png",
            "color": 7506394
        },
        'raid': {
            "thumbnail": "https://www.bungie.net/common/destiny2_content/icons/8b1bfd1c1ce1cab51d23c78235a6e067.png",
            "color": 0xF1C40F
        },
        'crucible': {
            "thumbnail": "https://www.bungie.net//common/destiny2_content/icons/cc8e6eea2300a1e27832d52e9453a227.png",
            "color": 6629649
        },
        'gambit': {
            "thumbnail": "https://www.bungie.net/common/destiny2_content/icons/fc31e8ede7cc15908d6e2dfac25d78ff.png",
            "color": 1332799
        }
    }

    def __init__(self, **options):
        super().__init__(**options)
        self.conn = sqlite3.connect('lfg.db')
        self.c = self.conn.cursor()

    def add(self, message: discord.Message, lfg_string=None):
        if lfg_string is None:
            content = message.content.splitlines()
        else:
            content = lfg_string.splitlines()

        args = self.parse_args(content, message, is_init=True)
        group_id = message.id
        owner = message.author.id

        try:
            self.c.execute('''CREATE TABLE raid
                     (group_id integer, size integer, name text, time integer, description text, owner integer, 
                     wanters text, going text, the_role text, group_mode text, dm_message integer, 
                     lfg_channel integer, channel_name text, server_name text, want_dm text, is_embed integer, 
                     length integer, server_id integer, group_role integer, group_channel integer, maybe_goers text, timezone text)''')
        except sqlite3.OperationalError:
            try:
                self.c.execute('''ALTER TABLE raid ADD COLUMN is_embed integer''')
            except sqlite3.OperationalError:
                try:
                    self.c.execute('''ALTER TABLE raid ADD COLUMN length integer''')
                except sqlite3.OperationalError:
                    try:
                        self.c.execute('''ALTER TABLE raid ADD COLUMN server_id integer''')
                    except sqlite3.OperationalError:
                        try:
                            self.c.execute('''ALTER TABLE raid ADD COLUMN group_role integer''')
                            self.c.execute('''ALTER TABLE raid ADD COLUMN group_channel integer''')
                        except sqlite3.OperationalError:
                            try:
                                self.c.execute('''ALTER TABLE raid ADD COLUMN maybe_goers text''')
                            except sqlite3.OperationalError:
                                try:
                                    self.c.execute('''ALTER TABLE raid ADD COLUMN timezone text''')
                                except sqlite3.OperationalError:
                                    pass

        newlfg = [(group_id, args['size'], args['name'], args['time'], args['description'],
                   owner, '[]', '[]', args['the_role'], args['group_mode'], 0, message.channel.id, message.channel.name,
                   message.guild.name, '[]', args['is_embed'], args['length'], message.guild.id, 0, 0, '[]', args['timezone'])]
        self.c.executemany("INSERT INTO raid VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", newlfg)
        self.conn.commit()

    def parse_args(self, content, message, is_init):
        time = datetime.now()

        def merge_arg(str_args):
            arg = str_args[1]
            if len(str_args) > 2:
                for fragment in str_args[2:]:
                    arg = '{}:{}'.format(arg, fragment)
            return arg

        args = {}
        roles = []
        if is_init:
            args = {
                'group_mode': 'basic',
                'name': '',
                'size': 1,
                'time': datetime.timestamp(time),
                'timezone': 'UTC+03:00',
                'description': '',
                'the_role': '',
                'is_embed': 0,
                'length': timedelta(seconds=-1)
            }
        else:
            text = message.content.split()
            hashids = Hashids()
            for word in text:
                group_id = hashids.decode(word)
                if len(group_id) > 0:
                    time_start = self.get_cell('group_id', group_id[0], 'time')
        for string in content:
            str_arg = string.split(':')
            if len(str_arg) < 2:
                continue
            if 'name:' in string or '-n:' in string:
                name = merge_arg(str_arg)
                args['name'] = name.lstrip()
            if 'time:' in string or '-t:' in string:
                try:
                    if len(str_arg) < 3:
                        raise ValueError
                    time_str = '{}:{}'.format(str_arg[1], str_arg[2])
                    args['time'] = datetime.strptime(time_str.lstrip(), "%d-%m-%Y %H:%M %z")
                    args['timezone'] = str(args['time'].tzinfo)
                except ValueError:
                    try:
                        if len(str_arg) < 3:
                            raise ValueError
                        time_str = '{}:{}'.format(str_arg[1], str_arg[2])
                        args['time'] = datetime.strptime(time_str.lstrip(), "%d-%m-%Y %H:%M")
                    except ValueError:
                        time = datetime.now().strftime("%d-%m-%Y %H:%M")
                        args['time'] = datetime.strptime(time, "%d-%m-%Y %H:%M")
                args['time'] = datetime.timestamp(args['time'])
            if 'description:' in string or '-d:' in string:
                description = merge_arg(str_arg)
                args['description'] = description.lstrip()
            if 'size:' in string or '-s:' in string:
                try:
                    args['size'] = int(str_arg[1])
                except ValueError:
                    args['size'] = 3
            if 'mode:' in string or '-m:' in string:
                args['group_mode'] = str_arg[1].lstrip()
                if args['group_mode'] != 'manual':
                    args['group_mode'] = 'basic'
            if 'role:' in string or '-r:' in string:
                roles = [role.strip() for role in str_arg[1].split(';')]
            if 'embed:' in string or '-e:' in string:
                if 'true' in str_arg[1].lower():
                    if 'is_embed' in args:
                        if args['is_embed'] == 0:
                            args['is_embed'] = 1
            if 'type:' in string or '-at:' in string:
                if 'default' in string.lower():
                    args['is_embed'] = 1
                if 'vanguard' in string.lower() or 'pve' in string.lower():
                    args['is_embed'] = 2
                if 'raid' in string.lower():
                    args['is_embed'] = 3
                if 'crucible' in string.lower() or 'pvp' in string.lower():
                    args['is_embed'] = 4
                if 'gambit' in string.lower() or 'reckoning' in string.lower():
                    args['is_embed'] = 5
            if 'end:' in string or '-te:' in string:
                try:
                    time_str = '{}:{}'.format(str_arg[1], str_arg[2])
                    args['length'] = datetime.strptime(time_str.lstrip(), "%d-%m-%Y %H:%M %z")
                except (ValueError, IndexError) as e:
                    continue
            if 'length:' in string or '-l:' in string:
                try:
                    td_str = str_arg[1].replace(',', '.').split(' ')
                    td_arr = [0, 0]
                    for td_part in td_str:
                        if 'h' in td_part.lower() or 'ч' in td_part.lower():
                            td_arr[0] = float(td_part[:-1])
                        if 'm' in td_part.lower() or 'м' in td_part.lower():
                            td_arr[1] = int(td_part[:-1])
                    args['length'] = timedelta(hours=td_arr[0], minutes=td_arr[1])
                except ValueError:
                    continue

        try:
            if type(args['length']) is datetime:
                if is_init:
                    args['length'] = timedelta(seconds=(args['length'].timestamp() - args['time']))
                else:
                    args['length'] = timedelta(seconds=(args['length'].timestamp() - time_start))
            args['length'] = args['length'].total_seconds()
        except KeyError:
            pass

        if not is_init:
            if len(roles) == 0:
                return args

        args['the_role'] = self.find_roles(is_init, message.guild, roles)
        return args

    def find_roles(self, is_init, guild, roles):
        for i in [0, 1]:
            the_role = []
            if len(roles) == 0 and is_init or len(the_role) > 0:
                roles = ['guardian', 'recruit', 'destiny', 'friend sot']
            for role in guild.roles:
                if role.name.lower() in roles:
                    the_role.append(role)
            if len(the_role) == 0:
                roles.clear()
        if len(the_role) == 0:
            the_role.append(guild.default_role)
        the_role_str = the_role[0].mention
        for i in the_role[1:]:
            if len("{}, {}".format(the_role_str, i.mention)) < 2000:
                the_role_str = "{}, {}".format(the_role_str, i.mention)
        return the_role_str

    def del_entry(self, group_id):
        self.c.executemany('''DELETE FROM raid WHERE group_id LIKE (?)''', [(group_id,)])
        self.conn.commit()

    def set_id(self, new_id, group_id):
        self.c.execute('''UPDATE raid SET group_id=? WHERE group_id=?''', (new_id, group_id))
        self.conn.commit()

    def set_owner(self, new_owner, group_id):
        self.c.execute('''UPDATE raid SET owner=? WHERE group_id=?''', (new_owner, group_id))
        self.conn.commit()

    def set_group_space(self, group_id, group_role, group_channel):
        self.c.execute('''UPDATE raid SET group_role=?, group_channel=? WHERE group_id=?''', (group_role, group_channel, group_id))
        self.conn.commit()

    def is_raid(self, message_id):
        try:
            cell = self.c.execute('SELECT group_id FROM raid WHERE group_id=?', (message_id,))
        except sqlite3.OperationalError:
            return False
        cell = cell.fetchall()
        if len(cell) == 0:
            return False
        else:
            cell = cell[0]
            return message_id == cell[0]

    def get_cell(self, search_field, group_id, field):
        try:
            cell = self.c.execute('SELECT {} FROM raid WHERE {}=?'.format(field, search_field), (group_id,)).fetchone()
        except sqlite3.OperationalError:
            return None
        if cell is not None:
            if len(cell) > 0:
                return cell[0]
            else:
                return None

    def get_cell_array(self, search_field, group_id, field):
        try:
            arr = self.c.execute('SELECT {} FROM raid WHERE {}=?'.format(field, search_field), (group_id,))
            arr = eval(arr.fetchone()[0])
        except sqlite3.OperationalError:
            return []
        except AttributeError:
            return []

        return arr

    def add_mb_goers(self, group_id, user):
        mb_goers = self.c.execute('SELECT maybe_goers FROM raid WHERE group_id=?', (group_id,))
        mb_goers = mb_goers.fetchone()[0]

        goers = self.c.execute('SELECT going FROM raid WHERE group_id=?', (group_id,))
        goers = eval(goers.fetchone()[0])

        wanters = self.c.execute('SELECT wanters FROM raid WHERE group_id=?', (group_id,))
        wanters = eval(wanters.fetchone()[0])

        w_dm = self.c.execute('SELECT want_dm FROM raid WHERE group_id=?', (group_id,))
        w_dm = eval(w_dm.fetchone()[0])

        if mb_goers is None:
            mb_goers = []
        else:
            mb_goers = eval(mb_goers)

        if user.mention not in mb_goers:
            mb_goers.append(user.mention)
            if user.mention in goers:
                goers.pop(goers.index(user.mention))
            if user.mention in wanters:
                i = wanters.index(user.mention)
                wanters.pop(i)
                w_dm.pop(i)

        self.c.execute('''UPDATE raid SET maybe_goers=? WHERE group_id=?''', (str(mb_goers), group_id))
        self.c.execute('''UPDATE raid SET wanters=? WHERE group_id=?''', (str(wanters), group_id))
        self.c.execute('''UPDATE raid SET want_dm=? WHERE group_id=?''', (str(w_dm), group_id))
        self.c.execute('''UPDATE raid SET going=? WHERE group_id=?''', (str(goers), group_id))
        self.conn.commit()

    def add_people(self, group_id, user):
        goers = self.c.execute('SELECT going FROM raid WHERE group_id=?', (group_id,))
        goers = eval(goers.fetchone()[0])

        wanters = self.c.execute('SELECT wanters FROM raid WHERE group_id=?', (group_id,))
        wanters = eval(wanters.fetchone()[0])

        w_dm = self.c.execute('SELECT want_dm FROM raid WHERE group_id=?', (group_id,))
        w_dm = eval(w_dm.fetchone()[0])

        size = self.get_cell('group_id', group_id, 'size')
        group_mode = self.get_cell('group_id', group_id, 'group_mode')

        if user.id == self.get_cell('group_id', group_id, 'owner') and user.mention not in goers:
            goers = [user.mention, *goers]
            if len(goers) > size:
                wanters = [goers[-1], *wanters]
                goers.pop(-1)

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

    def rm_people(self, group_id, user, emoji=''):
        goers = self.c.execute('SELECT going FROM raid WHERE group_id=?', (group_id,))
        goers = eval(goers.fetchone()[0])

        mb_goers = self.c.execute('SELECT maybe_goers FROM raid WHERE group_id=?', (group_id,))
        mb_goers = eval(mb_goers.fetchone()[0])

        wanters = self.c.execute('SELECT wanters FROM raid WHERE group_id=?', (group_id,))
        wanters = eval(wanters.fetchone()[0])

        w_dm = self.c.execute('SELECT want_dm FROM raid WHERE group_id=?', (group_id,))
        w_dm = eval(w_dm.fetchone()[0])

        size = self.get_cell('group_id', group_id, 'size')

        if user.mention in goers and emoji == '👌':
            goers.pop(goers.index(user.mention))
            if len(wanters) > 0:
                goers.append(wanters[0])
                wanters.pop(0)
                if len(w_dm) > 0:
                    w_dm.pop(0)
        if user.mention in wanters and emoji == '👌':
            i = wanters.index(user.mention)
            wanters.pop(i)
            if len(w_dm) > 0:
                w_dm.pop(i)
        if user.mention in mb_goers and emoji == '❓':
            mb_goers.pop(mb_goers.index(user.mention))

        self.c.execute('''UPDATE raid SET wanters=? WHERE group_id=?''', (str(wanters), group_id))
        self.c.execute('''UPDATE raid SET want_dm=? WHERE group_id=?''', (str(w_dm), group_id))
        self.c.execute('''UPDATE raid SET going=? WHERE group_id=?''', (str(goers), group_id))
        self.c.execute('''UPDATE raid SET maybe_goers=? WHERE group_id=?''', (str(mb_goers), group_id))
        self.conn.commit()

    def make_embed(self, message, translations, lang):
        is_embed = self.get_cell('group_id', message.id, 'is_embed')
        name = self.get_cell('group_id', message.id, 'name')
        tz = self.get_cell('group_id', message.id, 'timezone')
        if tz is None:
            tz = 'UTC+03:00'
        if tz == 'UTC':
            tz_elements = [0, 0]
        else:
            tz_elements = tz.strip('UTC+').split(':')
        ts = timezone(timedelta(hours=int(tz_elements[0]), minutes=int(tz_elements[1])))
        time = datetime.utcfromtimestamp(self.get_cell('group_id', message.id, 'time'))#.replace(tzinfo=ts)
        description = self.get_cell('group_id', message.id, 'description')
        dm_id = self.get_cell('group_id', message.id, 'dm_message')
        size = self.get_cell('group_id', message.id, 'size')
        goers = self.c.execute('SELECT going FROM raid WHERE group_id=?', (message.id,))
        goers = eval(goers.fetchone()[0])
        wanters = self.c.execute('SELECT wanters FROM raid WHERE group_id=?', (message.id,))
        wanters = eval(wanters.fetchone()[0])
        mb_goers = self.c.execute('SELECT maybe_goers FROM raid WHERE group_id=?', (message.id,))
        mb_goers = eval(mb_goers.fetchone()[0])
        length = self.get_cell('group_id', message.id, 'length')
        group_mode = self.get_cell('group_id', message.id, 'group_mode')
        owner = self.get_cell('group_id', message.id, 'owner')
        owner = message.guild.get_member(owner)
        if owner.nick is None:
            nick = owner.name
        else:
            nick = owner.nick

        if is_embed == 1:
            self.lfg_categories[self.lfg_i[is_embed]] = {
                'thumbnail': str(message.guild.icon_url_as(format='png', static_format='png', size=1024)).split('?')[0],
                'color': 0x000000
            }

        embed = {
            'thumbnail': {
                'url': self.lfg_categories[self.lfg_i[is_embed]]['thumbnail']
            },
            'fields': [],
            'color': self.lfg_categories[self.lfg_i[is_embed]]['color'],
            'type': 'rich',
            'title': name,
            'footer': {
                'text': translations['lfge']['footer'].format(self.hashids.encode(message.id), nick)
            }
        }

        embed_length = len(name) + len(embed['footer']['text'])
        if len(description) > 0:
            if len(description) < 1024:
                embed['fields'].append({
                    "inline": False,
                    "name": translations['lfge']['description'],
                    "value": description})
                embed_length = embed_length + len(description) + len(translations['lfge']['description'])
            else:
                embed['description'] = description
                embed_length = embed_length + len(description)

        embed['fields'].append({
            "inline": True,
            "name": translations['lfge']['date'],
            # "value": '{} {}'.format(time.strftime('%d-%m-%Y %H:%M'), tz)
            "value": '{} {}'.format(format_datetime(time, 'medium', tzinfo=ts, locale=lang), tz)
        })
        embed_length = embed_length + len(embed['fields'][-1]['name']) + len(embed['fields'][-1]['value'])

        if length > 0:
            embed['fields'].append({"inline": True,
                                    "name": translations['lfge']['length'],
                                    "value": str(timedelta(seconds=length))})
            embed_length = embed_length + len(translations['lfge']['length']) + len(str(timedelta(seconds=length)))

        if len(goers) > 43:
            embed['fields'].append({"inline": True,
                                    "name": translations['lfge']['total_goers'],
                                    "value": '{}/{}'.format(len(goers), size)})
            embed_length = embed_length + len(translations['lfge']['total_goers']) + len('{}/{}'.format(len(goers), size))
            if len(wanters) > 0:
                embed['fields'].append({"inline": True,
                                        "name": translations['lfge']['total_wanters'],
                                        "value": '{}'.format(len(wanters))})
                embed_length = embed_length + len(translations['lfge']['total_wanters']) + len('{}'.format(len(wanters)))
        if len(wanters) > 43 and embed['fields'][-1]['value'] != str(len(wanters)):
            embed['fields'].append({"inline": True,
                                    "name": translations['lfge']['total_wanters'],
                                    "value": '{}'.format(len(wanters))})
            embed_length = embed_length + len(translations['lfge']['total_wanters']) + len('{}'.format(len(wanters)))

        if len(goers) > 0:
            embed['fields'].append({"inline": False, "name": translations['lfge']['goers'], "value": ""})
            embed_length = embed_length + len(translations['lfge']['goers'])
            for participant in goers:
                if len('{} {},'.format(embed['fields'][-1]['value'], participant)) > 1024 and len(embed['fields']) < 25:
                    if len(translations['lfge']['goers']) + embed_length > 5550:
                        break
                    embed_length = embed_length + len(embed['fields'][-1]['value'])
                    embed['fields'].append({"inline": False, "name": translations['lfge']['goers'], "value": ""})
                    embed_length = embed_length + len(translations['lfge']['goers'])
                if embed_length + len('{} {},'.format(embed['fields'][-1]['value'], participant)) < 6000:
                    embed['fields'][-1]['value'] = '{} {},'.format(embed['fields'][-1]['value'], participant)
            embed['fields'][-1]['value'] = '{}'.format(embed['fields'][-1]['value'][:-1])
            embed_length = embed_length + len(embed['fields'][-1]['value'])

        if group_mode == 'basic':
            if len(wanters) > 0 and embed_length < 5550 and len(embed['fields']) < 25:
                if embed_length + len(translations['lfge']['wanters']) < 5550:
                    embed['fields'].append({"inline": False, "name": translations['lfge']['wanters'], "value": ""})
                    embed_length = embed_length + len(translations['lfge']['wanters'])
                    for wanter in wanters:
                        if len('{} {},'.format(embed['fields'][-1]['value'], wanter)) > 1024 and len(
                                embed['fields']) < 25:
                            if len(translations['lfge']['wanters']) + embed_length > 5550:
                                break
                            embed_length = embed_length + len(embed['fields'][-1]['value'])
                            embed['fields'].append({"inline": False, "name": translations['lfge']['wanters'], "value": ""})
                            embed_length = embed_length + len(translations['lfge']['wanters'])
                        if embed_length + len('{} {},'.format(embed['fields'][-1]['value'], wanter)) < 6000:
                            embed['fields'][-1]['value'] = '{} {},'.format(embed['fields'][-1]['value'], wanter)
                    embed['fields'][-1]['value'] = '{}'.format(embed['fields'][-1]['value'][:-1])
                    embed_length = embed_length + len(embed['fields'][-1]['value'])

        if len(mb_goers) > 0:
            if len(mb_goers) > 0 and embed_length < 5550 and len(embed['fields']) < 25:
                if embed_length + len(translations['lfge']['mb_goers']) < 5550:
                    embed['fields'].append({"inline": False, "name": translations['lfge']['mb_goers'], "value": ""})
                    embed_length = embed_length + len(translations['lfge']['wanters'])
                    for wanter in mb_goers:
                        if len('{} {},'.format(embed['fields'][-1]['value'], wanter)) > 1024 and len(
                                embed['fields']) < 25:
                            if len(translations['lfge']['mb_goers']) + embed_length > 5550:
                                break
                            embed_length = embed_length + len(embed['fields'][-1]['value'])
                            embed['fields'].append(
                                {"inline": False, "name": translations['lfge']['mb_goers'], "value": ""})
                            embed_length = embed_length + len(translations['lfge']['goers'])
                        if embed_length + len('{} {},'.format(embed['fields'][-1]['value'], wanter)) < 6000:
                            embed['fields'][-1]['value'] = '{} {},'.format(embed['fields'][-1]['value'], wanter)
                    embed['fields'][-1]['value'] = '{}'.format(embed['fields'][-1]['value'][:-1])
                    embed_length = embed_length + len(embed['fields'][-1]['value'])

        while embed_length > 6000:
            embed_length = embed_length - len(embed['fields'][-1]['value']) - len(embed['fields'][-1]['name'])
            embed['fields'] = embed['fields'][:-1]

        embed = discord.Embed.from_dict(embed)
        embed.timestamp = time

        print(embed_length)

        return embed

    async def update_group_msg(self, message, translations, lang):
        is_embed = self.get_cell('group_id', message.id, 'is_embed')

        if is_embed and message.guild.me.permissions_in(message.channel).embed_links:
            embed = self.make_embed(message, translations, lang)
            await message.edit(content=None, embed=embed)
            return

        role = self.get_cell('group_id', message.id, 'the_role')
        name = self.get_cell('group_id', message.id, 'name')
        time = datetime.fromtimestamp(self.get_cell('group_id', message.id, 'time'))
        description = self.get_cell('group_id', message.id, 'description')
        msg = "{}, {} {}\n{} {}\n{}". \
            format(role, translations['lfg']['go'], name, translations['lfg']['at'], time, description)
        if len(msg) > 2000:
            msg = "{}, {} {}".format(role, translations['lfg']['go'], name)
            if len(msg) > 2000:
                msg = role
                if len(msg) > 2000:
                    parts = msg.split(', ')
                    msg = ''
                    while len(msg) < 1900:
                        msg = '{} {},'.format(msg, parts[0])
                        parts.pop(0)
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
            try:
                dm_message = await owner.dm_channel.fetch_message(dm_id)
                await dm_message.delete()
            except discord.NotFound:
                pass
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
            if len(wanters) > number:
                if not wanters[number] in goers:
                    goers.append(wanters[number])
                    wanters.pop(number)
                    w_dm.pop(number)

        self.c.execute('''UPDATE raid SET wanters=? WHERE group_id=?''', (str(wanters), group_id))
        self.c.execute('''UPDATE raid SET want_dm=? WHERE group_id=?''', (str(w_dm), group_id))
        self.c.execute('''UPDATE raid SET going=? WHERE group_id=?''', (str(goers), group_id))
        self.conn.commit()

    async def dm_lfgs(self, user, translations):
        lfg_list = self.c.execute('SELECT group_id, name, time, channel_name, server_name, timezone FROM raid WHERE owner=?',
                                  (user.id,))
        lfg_list = lfg_list.fetchall()

        msg = translations['lfglist_head']
        i = 1
        for lfg in lfg_list:
            msg = translations['lfglist'].format(msg, i, lfg[1], datetime.fromtimestamp(lfg[2]), lfg[5],
                                                                  lfg[3], lfg[4], self.hashids.encode(lfg[0]))
            i = i + 1
        if user.dm_channel is None:
            await user.create_dm()
        if len(lfg_list) > 0:
            await user.dm_channel.send(msg)
            return lfg_list
        else:
            await user.dm_channel.send(translations['lfglist_empty'])
            return False

    async def edit(self, message, old_lfg, translations, lang, param_str=None):
        if param_str is not None:
            text = param_str.splitlines()
        else:
            text = message.content.splitlines()
        args = self.parse_args(text, message, is_init=False)

        role_changed = False
        for item in args:
            self.c.execute('''UPDATE raid SET {}=? WHERE group_id=?'''.format(item), (args[item], old_lfg.id))
            if item == 'the_role':
                role_changed = True
        self.conn.commit()

        if message.channel.id != old_lfg.channel.id or role_changed:
            new_lfg = await message.channel.send(self.get_cell('group_id', old_lfg.id, 'the_role'))
            await new_lfg.add_reaction('👌')
            await new_lfg.add_reaction('❓')
            await new_lfg.add_reaction('❌')

            self.c.execute('''UPDATE raid SET group_id=? WHERE group_id=?''', (new_lfg.id, old_lfg.id))
            self.c.execute('''UPDATE raid SET lfg_channel=? WHERE group_id=?''', (message.channel.id, new_lfg.id))
            await old_lfg.delete()
        else:
            new_lfg = old_lfg
        await message.delete()
        await self.update_group_msg(new_lfg, translations, lang)
        self.conn.commit()

    def purge_guild(self, guild_id):
        self.c.executemany('''DELETE FROM raid WHERE server_id LIKE (?)''', [(guild_id,)])
        self.conn.commit()

    def get_all(self):
        lfg_list = self.c.execute('SELECT group_id, lfg_channel, time, server_id, length FROM raid')
        lfg_list = lfg_list.fetchall()

        return lfg_list

    def is_goer(self, message, user):
        goers = self.c.execute('SELECT going FROM raid WHERE group_id=?', (message.id,))
        goers = eval(goers.fetchone()[0])

        return user.mention in goers

    def is_mb_goer(self, message, user):
        goers = self.c.execute('SELECT maybe_goers FROM raid WHERE group_id=?', (message.id,))
        goers = eval(goers.fetchone()[0])

        return user.mention in goers
