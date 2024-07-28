import asyncio

import discord
import aiosqlite
import os
import dateparser
from datetime import datetime, timezone, timedelta
from hashids import Hashids
from babel.dates import format_datetime, get_timezone_name, get_timezone, get_timezone_gmt
from babel import Locale
from cogs.utils.views import LFGModal, DMSelectLFG
from timeframe import TimeFrame

from typing import List, Union

from cogs.utils.converters import locale_2_lang, CtxLocale


class LFG:
    conn = ''
    hashids = Hashids()
    lfg_i = ['null', 'default', 'vanguard', 'raid', 'crucible', 'gambit']
    at = ['null', 'default', 'pve', 'raid', 'pvp', 'gambit']
    lfg_categories = {
        'null': {},
        'default': {},
        'vanguard': {
            "thumbnail": "https://www.bungie.net/common/destiny2_content/icons/3642cf9e2acd174dcab5b5f9e3a3a45d.png",
            "color": 7506394
        },
        'raid': {
            "thumbnail": "https://www.bungie.net/common/destiny2_content/icons/DestinyActivityModeDefinition_bfe80e3dafe6686a9dc42df0606bdc9b.png",
            "color": 0xF1C40F
        },
        'crucible': {
            "thumbnail": "https://www.bungie.net/common/destiny2_content/icons/d87bb6dbf6d9c5c851e1f06ef807b7d4.png",
            "color": 6629649
        },
        'gambit': {
            "thumbnail": "https://www.bungie.net/common/destiny2_content/icons/DestinyActivityModeDefinition_96f7e9009d4f26e30cfd60564021925e.png",
            "color": 1332799
        }
    }

    def __init__(self, bot, **options):
        super().__init__(**options)
        asyncio.run(self.set_up_db())
        self.bot = bot

    async def set_up_db(self) -> None:
        self.conn = await aiosqlite.connect('lfg.db')

        cursor = await self.conn.cursor()
        try:
            await cursor.execute('''CREATE TABLE alerts (user_id integer, user_locale text, timestamp integer, group_id integer)''')
            await cursor.execute('''CREATE UNIQUE INDEX alert_id ON alerts(group_id, user_id)''')
            await self.conn.commit()
        except aiosqlite.OperationalError:
            pass

        try:
            await cursor.execute('''CREATE TABLE priorities (host_id integer, low_priority text)''')
            await cursor.execute('''CREATE UNIQUE INDEX host_id ON priorities(host_id)''')
            await self.conn.commit()
        except aiosqlite.OperationalError:
            pass
        await cursor.close()

    async def add(self, message: discord.Message, lfg_string: str = None, args: dict = None) -> None:
        cursor = await self.conn.cursor()
        if lfg_string is None:
            content = message.content.splitlines()
        else:
            content = lfg_string.splitlines()

        if args is None:
            args = await self.parse_args(content, message, is_init=True)
        group_id = message.id
        owner = message.author.id
        nick = message.author.nick

        try:
            await cursor.execute('''CREATE TABLE raid
                     (group_id integer, size integer, name text, time integer, description text, owner integer, 
                     wanters text, going text, the_role text, group_mode text, dm_message integer, 
                     lfg_channel integer, channel_name text, server_name text, want_dm text, is_embed integer, 
                     length integer, server_id integer, group_role integer, group_channel integer, maybe_goers text, 
                     timezone text, owner_nick text, low_priority text)''')
        except aiosqlite.OperationalError:
            try:
                await cursor.execute('''ALTER TABLE raid ADD COLUMN is_embed integer''')
            except aiosqlite.OperationalError:
                try:
                    await cursor.execute('''ALTER TABLE raid ADD COLUMN length integer''')
                except aiosqlite.OperationalError:
                    try:
                        await cursor.execute('''ALTER TABLE raid ADD COLUMN server_id integer''')
                    except aiosqlite.OperationalError:
                        try:
                            await cursor.execute('''ALTER TABLE raid ADD COLUMN group_role integer''')
                            await cursor.execute('''ALTER TABLE raid ADD COLUMN group_channel integer''')
                        except aiosqlite.OperationalError:
                            try:
                                await cursor.execute('''ALTER TABLE raid ADD COLUMN maybe_goers text''')
                            except aiosqlite.OperationalError:
                                try:
                                    await cursor.execute('''ALTER TABLE raid ADD COLUMN timezone text''')
                                except aiosqlite.OperationalError:
                                    try:
                                        await cursor.execute('''ALTER TABLE raid ADD COLUMN owner_nick text''')
                                    except aiosqlite.OperationalError:
                                        try:
                                            await cursor.execute('''ALTER TABLE raid ADD COLUMN low_priority text''')
                                        except aiosqlite.OperationalError:
                                            pass

        newlfg = [(group_id, args['size'], args['name'], args['time'], args['description'],
                   owner, '[]', '[]', args['the_role'], args['group_mode'], 0, message.channel.id, message.channel.name,
                   message.guild.name, '[]', args['is_embed'], args['length'], message.guild.id, 0, 0, '[]',
                   args['timezone'], nick, '[]')]
        await cursor.executemany("INSERT INTO raid VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", newlfg)
        await self.conn.commit()
        await cursor.close()

    async def parse_args(self, content: List[str], message: Union[discord.Message, int], is_init: bool,
                   guild: discord.Guild = None) -> dict:
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
            if type(message) == discord.Message:
                text = message.content.split()
                hashids = Hashids()
                for word in text:
                    group_id = hashids.decode(word)
                    if len(group_id) > 0:
                        time_start = await self.get_cell('group_id', group_id[0], 'time')
            else:
                time_start = await self.get_cell('group_id', message, 'time')
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
                    args['time'] = datetime.strptime(time_str.lstrip(), "%d-%m-%Y %H:%M%z")
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

        if type(message) != discord.Message and guild is not None:
            args['the_role'] = await self.find_roles(is_init, guild, roles)
        else:
            args['the_role'] = await self.find_roles(is_init, message.guild, roles)
        return args

    async def parse_date(self, time, guild_id):
        try:
            time_t = datetime.strptime(time, "%d-%m-%Y %H:%M%z")
        except ValueError:
            tz = await self.bot.get_guild_timezone(guild_id)
            tz_elements = tz.strip('UTC').split(':')
            tz_obj = timezone(timedelta(hours=int(tz_elements[0]), minutes=int(tz_elements[1])))
            try:
                time_t = datetime.strptime(time, "%d-%m-%Y %H:%M")
                time = '{}{}{}'.format(time, tz_elements[0], tz_elements[1])
            except ValueError:
                try:
                    ts = dateparser.parse(time)
                    if ts.tzinfo is None:
                        #time = ts.astimezone(tz_obj).strftime('%d-%m-%Y %H:%M%z')
                        time = '{}{}{}'.format(ts.strftime('%d-%m-%Y %H:%M'), tz_elements[0], tz_elements[1])
                    else:
                        time = ts.strftime('%d-%m-%Y %H:%M%z')
                except AttributeError:
                    time = datetime.now().strftime("%d-%m-%Y %H:%M")
        return time

    async def parse_args_sl(self, name: str, description: str, time: str, size: str = None, length: str = None,
                      a_type: str = None, mode: str = 'basic', roles: List[discord.Role] = None,
                      guild_id: int = None) -> dict:
        args = {
            'group_mode': mode,
            'name': name,
            'size': 1,
            'time': await self.parse_date(time, guild_id),
            'timezone': await self.bot.get_guild_timezone(guild_id),
            'description': description,
            'the_role': '',
            'is_embed': self.at.index(a_type),
            'length': timedelta(seconds=0)
        }

        try:
            args['time'] = datetime.strptime(args['time'].lstrip(), "%d-%m-%Y %H:%M%z")
            args['timezone'] = str(args['time'].tzinfo)
        except ValueError:
            try:
                args['time'] = datetime.strptime(args['time'].lstrip(), "%d-%m-%Y %H:%M")
            except ValueError:
                time = datetime.now().strftime("%d-%m-%Y %H:%M")
                args['time'] = datetime.strptime(time, "%d-%m-%Y %H:%M")

        args['time'] = datetime.timestamp(args['time'])

        try:
            args['size'] = int(size)
        except ValueError:
            args['size'] = 3

        if length is not None:
            try:
                td_str = length.replace(',', '.').split(' ')
                td_arr = [0, 0]
                for td_part in td_str:
                    if 'h' in td_part.lower() or 'ч' in td_part.lower():
                        td_arr[0] = float(td_part[:-1])
                    if 'm' in td_part.lower() or 'м' in td_part.lower():
                        td_arr[1] = int(td_part[:-1])
                args['length'] = timedelta(hours=td_arr[0], minutes=td_arr[1])
            except ValueError:
                pass

        try:
            if type(args['length']) is datetime:
                args['length'] = timedelta(seconds=(args['length'].timestamp() - args['time']))
            args['length'] = args['length'].total_seconds()
        except KeyError:
            pass

        args['the_role'] = roles[0].mention
        for role in roles[1:]:
            args['the_role'] = '{}, {}'.format(args['the_role'], role.mention)
        if str(guild_id) in args['the_role']:
            args['the_role'] = args['the_role'].replace('<@&{}>'.format(guild_id), '@everyone')
        return args

    async def find_roles(self, is_init: bool, guild: discord.Guild, roles: List[str], group_id: discord.Message) -> str:
        if not is_init and roles[0] == '--':
            if group_id is not None:
                the_role_str = await self.get_cell('group_id', group_id.id, 'the_role')
        else:
            roles = [i.lower() for i in roles]
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
                the_role_str = '@everyone'
            else:
                the_role_str = the_role[0].mention
            for i in the_role[1:]:
                if len("{}, {}".format(the_role_str, i.mention)) < 2000:
                    the_role_str = "{}, {}".format(the_role_str, i.mention)
        return the_role_str

    async def del_entry(self, group_id: int) -> None:
        cursor = await self.conn.cursor()
        await cursor.executemany('''DELETE FROM raid WHERE group_id LIKE (?)''', [(group_id,)])
        await cursor.executemany('''DELETE FROM alerts WHERE group_id LIKE (?)''', [(group_id,)])
        await self.conn.commit()
        await cursor.close()

    async def set_id(self, new_id: int, group_id: int) -> None:
        cursor = await self.conn.cursor()
        await cursor.execute('''UPDATE raid SET group_id=? WHERE group_id=?''', (new_id, group_id))
        await self.conn.commit()
        await cursor.close()

    async def set_owner(self, new_owner: discord.Member, group_id: int) -> None:
        cursor = await self.conn.cursor()
        if new_owner.nick is None:
            nick = new_owner.name
        else:
            nick = new_owner.nick
        await cursor.execute('''UPDATE raid SET owner=?, owner_nick=? WHERE group_id=?''', (new_owner.id, nick, group_id))
        await self.conn.commit()
        await cursor.close()

    async def set_group_space(self, group_id: int, group_role: int, group_channel: int) -> None:
        cursor = await self.conn.cursor()
        await cursor.execute('''UPDATE raid SET group_role=?, group_channel=? WHERE group_id=?''', (group_role, group_channel, group_id))
        await self.conn.commit()
        await cursor.close()

    async def is_raid(self, message_id: int) -> bool:
        cursor = await self.conn.cursor()
        try:
            cell = await cursor.execute('SELECT group_id FROM raid WHERE group_id=?', (message_id,))
        except aiosqlite.OperationalError:
            await cursor.close()
            return False
        cell = await cell.fetchall()
        if len(cell) == 0:
            await cursor.close()
            return False
        else:
            cell = cell[0]
            await cursor.close()
            return message_id == cell[0]

    async def get_cell(self, search_field: str, group_id: int, field: str, table: str = 'raid') -> Union[str, int, None]:
        cursor = await self.conn.cursor()
        try:
            cell = await cursor.execute('SELECT {} FROM {} WHERE {}=?'.format(field, table, search_field), (group_id,))
            cell = await cell.fetchone()
        except aiosqlite.OperationalError:
            await cursor.close()
            return None
        if cell is not None:
            if len(cell) > 0:
                await cursor.close()
                return cell[0]
            else:
                await cursor.close()
                return None

    async def get_cell_array(self, search_field: str, group_id: int, field: str) -> List:
        cursor = await self.conn.cursor()
        try:
            arr = await cursor.execute('SELECT {} FROM raid WHERE {}=?'.format(field, search_field), (group_id,))
            arr = await arr.fetchone()
            arr = eval(arr[0])
        except aiosqlite.OperationalError:
            await cursor.close()
            return []
        except AttributeError:
            await cursor.close()
            return []

        await cursor.close()
        return arr

    async def add_low_priority(self, host_id: int, new_mentions: List) -> None:
        cursor = await self.conn.cursor()

        old_list = await cursor.execute('SELECT low_priority FROM priorities WHERE host_id=?', (host_id,))
        old_list = await old_list.fetchone()
        if old_list is None:
            old_list = []
        else:
            old_list = eval(old_list[0])
            if old_list is None:
                old_list = []
        new_list = [*old_list, *new_mentions]
        new_list = list(set(new_list))

        try:
            await cursor.execute('''INSERT INTO priorities VALUES (?,?)''', (host_id, str(new_list)))
        except aiosqlite.IntegrityError:
            await cursor.execute('''UPDATE priorities SET low_priority=? WHERE host_id=?''', (str(new_list), host_id))
        await self.conn.commit()
        await cursor.close()

    async def get_everyone(self, group_id: int, user_id: int) -> List:
        cursor = await self.conn.cursor()
        owner = await self.get_cell('group_id', group_id, 'owner')

        mb_goers = await cursor.execute('SELECT maybe_goers FROM raid WHERE group_id=?', (group_id,))
        mb_goers = await mb_goers.fetchone()
        mb_goers = eval(mb_goers[0])
        if mb_goers is None:
            mb_goers = []

        goers = await cursor.execute('SELECT going FROM raid WHERE group_id=?', (group_id,))
        goers = await goers.fetchone()
        goers = eval(goers[0])
        if goers is None:
            goers = []

        low_prio = await cursor.execute('SELECT low_priority FROM raid WHERE group_id=?', (group_id,))
        low_prio = await low_prio.fetchone()
        try:
            low_prio = eval(low_prio[0])
        except TypeError:
            low_prio = None
        if low_prio is None:
            low_prio = []

        wanters = await cursor.execute('SELECT wanters FROM raid WHERE group_id=?', (group_id,))
        wanters = await wanters.fetchone()
        wanters = eval(wanters[0])
        if wanters is None or owner != user_id:
            wanters = []

        await cursor.close()

        return [*mb_goers, *goers, *wanters, *low_prio]

    async def add_alert_jobs(self):
        cursor = await self.conn.cursor()
        alert_list = await cursor.execute('SELECT * FROM alerts ')
        alert_list = await alert_list.fetchall()
        alert_list = alert_list

        for alert in alert_list:
            guild_id = await self.get_cell('group_id', alert[3], 'server_id')
            if guild_id is not None:
                delta = await self.bot.get_lfg_alert(guild_id)
                timestamp = await self.get_cell('group_id', alert[3], 'time')
                timestamp -= delta * 60
                alert_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                self.bot.sched.add_job(self.send_alert, 'date', run_date=alert_time, args=[alert[3], alert[0]],
                                       misfire_grace_time=(delta - 1) * 60)
            else:
                await cursor.execute('DELETE FROM alerts WHERE group_id=? and user_id=?', (alert[3], alert[0]))
                await self.conn.commit()

        await cursor.close()

    async def add_alert(self, interaction: discord.Interaction) -> None:
        delta = await self.bot.get_lfg_alert(interaction.guild.id)
        timestamp = await self.get_cell('group_id', interaction.message.id, 'time')
        timestamp -= delta * 60
        alert_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)

        self.bot.sched.add_job(self.send_alert, 'date', run_date=alert_time, args=[interaction.message.id, interaction.user.id], misfire_grace_time=(delta-1)*60)

        cursor = await self.conn.cursor()

        ctxloc = CtxLocale(self.bot, interaction.locale)
        await cursor.execute('''INSERT or IGNORE INTO alerts VALUES (?,?,?,?)''', (interaction.user.id, await locale_2_lang(ctxloc), alert_time.timestamp(), interaction.message.id))
        await self.conn.commit()
        await cursor.close()

    async def send_alert(self, group_id, user_id):
        cursor = await self.conn.cursor()
        locale = await cursor.execute('SELECT user_locale FROM alerts WHERE user_id=? AND group_id=?', (user_id, group_id))
        locale = await locale.fetchone()
        locale = locale[0]
        group_name = await self.get_cell('group_id', group_id, 'name')
        time = datetime.fromtimestamp(await self.get_cell('group_id', group_id, 'time'), tz=timezone.utc)
        server_name = await self.get_cell('group_id', group_id, 'server_name')

        user = await self.bot.fetch_user(user_id)
        if user.dm_channel is None:
            await user.create_dm()
        await user.dm_channel.send(self.bot.translations[locale]['lfg']['reminder'].format(group_name=group_name, server_name=server_name, time=discord.utils.format_dt(time, 'R')))

        await cursor.execute('''DELETE FROM alerts WHERE group_id=? and user_id=?''', (group_id, user_id))
        await self.conn.commit()
        await cursor.close()

    async def add_mb_goers(self, group_id: int, user: discord.Member) -> None:
        cursor = await self.conn.cursor()

        mb_goers = await cursor.execute('SELECT maybe_goers FROM raid WHERE group_id=?', (group_id,))
        mb_goers = await mb_goers.fetchone()
        mb_goers = mb_goers[0]

        goers = await cursor.execute('SELECT going FROM raid WHERE group_id=?', (group_id,))
        goers = await goers.fetchone()
        goers = eval(goers[0])

        wanters = await cursor.execute('SELECT wanters FROM raid WHERE group_id=?', (group_id,))
        wanters = await wanters.fetchone()
        wanters = eval(wanters[0])

        w_dm = await cursor.execute('SELECT want_dm FROM raid WHERE group_id=?', (group_id,))
        w_dm = await w_dm.fetchone()
        w_dm = eval(w_dm[0])

        group_mode = await self.get_cell('group_id', group_id, 'group_mode')

        if mb_goers is None:
            mb_goers = []
        else:
            mb_goers = eval(mb_goers)

        if user.mention not in mb_goers:
            mb_goers.append(user.mention)
            if user.mention in goers:
                goers.pop(goers.index(user.mention))
                if len(wanters) > 0 and group_mode == 'basic':
                    goers.append(wanters[0])
                    wanters.pop(0)
                    if len(w_dm) > 0:
                        w_dm.pop(0)
            if user.mention in wanters:
                i = wanters.index(user.mention)
                wanters.pop(i)
                w_dm.pop(i)

        await cursor.execute('''UPDATE raid SET maybe_goers=? WHERE group_id=?''', (str(mb_goers), group_id))
        await cursor.execute('''UPDATE raid SET wanters=? WHERE group_id=?''', (str(wanters), group_id))
        await cursor.execute('''UPDATE raid SET want_dm=? WHERE group_id=?''', (str(w_dm), group_id))
        await cursor.execute('''UPDATE raid SET going=? WHERE group_id=?''', (str(goers), group_id))
        await self.conn.commit()
        await cursor.close()

    async def add_people(self, group_id: int, user: discord.Member) -> None:
        cursor = await self.conn.cursor()

        mb_goers = await cursor.execute('SELECT maybe_goers FROM raid WHERE group_id=?', (group_id,))
        mb_goers = await mb_goers.fetchone()
        mb_goers = mb_goers[0]

        goers = await cursor.execute('SELECT going FROM raid WHERE group_id=?', (group_id,))
        goers = await goers.fetchone()
        goers = eval(goers[0])

        wanters = await cursor.execute('SELECT wanters FROM raid WHERE group_id=?', (group_id,))
        wanters = await wanters.fetchone()
        wanters = eval(wanters[0])

        w_dm = await cursor.execute('SELECT want_dm FROM raid WHERE group_id=?', (group_id,))
        w_dm = await w_dm.fetchone()
        w_dm = eval(w_dm[0])

        size = await self.get_cell('group_id', group_id, 'size')
        group_mode = await self.get_cell('group_id', group_id, 'group_mode')

        if mb_goers is None:
            mb_goers = []
        else:
            mb_goers = eval(mb_goers)

        if user.mention in mb_goers:
            mb_goers.pop(mb_goers.index(user.mention))

        if user.id == await self.get_cell('group_id', group_id, 'owner') and user.mention not in goers:
            goers = [user.mention, *goers]
            if len(goers) > size:
                wanters = [goers[-1], *wanters]
                goers.pop(-1)

        if len(goers) < size and group_mode == 'basic':
            if user.mention not in goers:
                # goers.append(user.mention)
                goers = await self.add_with_priority(goers, user, group_id)
        else:
            if user.mention not in wanters and user.mention not in goers:
                # wanters.append(user.mention)
                if group_mode == 'basic':
                    goers = await self.add_with_priority(goers, user, group_id)
                    if len(goers) > size:
                        dropped = goers[-1]
                        goers = goers[:-1]
                        if dropped != user.mention:
                            wanters = await self.add_with_priority(wanters, dropped, group_id, is_dropped=True)
                        else:
                            wanters = await self.add_with_priority(wanters, user, group_id)
                else:
                    wanters = await self.add_with_priority(wanters, user, group_id)
                    w_dm.append(user.display_name)

        await cursor.execute('''UPDATE raid SET maybe_goers=? WHERE group_id=?''', (str(mb_goers), group_id))
        await cursor.execute('''UPDATE raid SET wanters=? WHERE group_id=?''', (str(wanters), group_id))
        await cursor.execute('''UPDATE raid SET want_dm=? WHERE group_id=?''', (str(w_dm), group_id))
        await cursor.execute('''UPDATE raid SET going=? WHERE group_id=?''', (str(goers), group_id))
        await self.conn.commit()
        await cursor.close()

    async def add_with_priority(self, users: list, member: discord.Member, group_id: int, is_dropped: bool = False) -> list:
        owner = await self.get_cell('group_id', group_id, 'owner')
        guild_id = await self.get_cell('group_id', group_id, 'server_id')
        low_priority_user = await self.get_cell('host_id', owner, 'low_priority', 'priorities')
        low_priority_guild = await self.get_cell('group_id', guild_id, 'low_priority', 'priorities')

        if low_priority_guild is None:
            low_priority_guild = []
        else:
            low_priority_guild = eval(low_priority_guild)

        if low_priority_user is None:
            low_priority_user = []
        else:
            low_priority_user = eval(low_priority_user)

        if type(member) == str:
            mention = member
        else:
            mention = member.mention

        if mention in low_priority_user and not is_dropped:
            users.append(mention)
        else:
            if len(users) == 0 or len(list(set(users).intersection(set(low_priority_user)))) == 0:
                users.append(mention)
            else:
                for user in users:
                    if user in low_priority_user:
                        users.insert(users.index(user), mention)
                        break
        return users

    async def rm_people(self, group_id: int, user: discord.Member, emoji: str = '') -> None:
        cursor = await self.conn.cursor()

        mb_goers = await cursor.execute('SELECT maybe_goers FROM raid WHERE group_id=?', (group_id,))
        mb_goers = await mb_goers.fetchone()
        mb_goers = eval(mb_goers[0])

        goers = await cursor.execute('SELECT going FROM raid WHERE group_id=?', (group_id,))
        goers = await goers.fetchone()
        goers = eval(goers[0])

        wanters = await cursor.execute('SELECT wanters FROM raid WHERE group_id=?', (group_id,))
        wanters = await wanters.fetchone()
        wanters = eval(wanters[0])

        w_dm = await cursor.execute('SELECT want_dm FROM raid WHERE group_id=?', (group_id,))
        w_dm = await w_dm.fetchone()
        w_dm = eval(w_dm[0])

        size = await self.get_cell('group_id', group_id, 'size')
        group_mode = await self.get_cell('group_id', group_id, 'group_mode')

        if user.mention in goers and emoji == '👌':
            goers.pop(goers.index(user.mention))
            if len(wanters) > 0 and group_mode == 'basic':
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

        await cursor.execute('''UPDATE raid SET maybe_goers=? WHERE group_id=?''', (str(mb_goers), group_id))
        await cursor.execute('''UPDATE raid SET wanters=? WHERE group_id=?''', (str(wanters), group_id))
        await cursor.execute('''UPDATE raid SET want_dm=? WHERE group_id=?''', (str(w_dm), group_id))
        await cursor.execute('''UPDATE raid SET going=? WHERE group_id=?''', (str(goers), group_id))
        await self.conn.commit()
        await cursor.close()

    async def make_embed(self, message: discord.Message, translations: dict, lang: str) -> discord.Embed:
        cursor = await self.conn.cursor()

        is_embed = await self.get_cell('group_id', message.id, 'is_embed')
        name = await self.get_cell('group_id', message.id, 'name')
        tz = await self.get_cell('group_id', message.id, 'timezone')
        if tz is None:
            tz = 'UTC+03:00'
        if tz == 'UTC':
            tz_elements = [0, 0]
        else:
            tz_elements = tz.strip('UTC+').split(':')
        ts = timezone(timedelta(hours=int(tz_elements[0]), minutes=int(tz_elements[1])))
        time = datetime.fromtimestamp(await self.get_cell('group_id', message.id, 'time'), tz=timezone.utc)#.replace(tzinfo=ts)
        description = await self.get_cell('group_id', message.id, 'description')
        dm_id = await self.get_cell('group_id', message.id, 'dm_message')
        size = await self.get_cell('group_id', message.id, 'size')
        group_mode = await self.get_cell('group_id', message.id, 'group_mode')
        goers = await cursor.execute('SELECT going FROM raid WHERE group_id=?', (message.id,))
        goers = await goers.fetchone()
        goers = eval(goers[0])
        wanters = await cursor.execute('SELECT wanters FROM raid WHERE group_id=?', (message.id,))
        wanters = await wanters.fetchone()
        wanters = eval(wanters[0])
        mb_goers = await cursor.execute('SELECT maybe_goers FROM raid WHERE group_id=?', (message.id,))
        mb_goers = await mb_goers.fetchone()
        mb_goers = eval(mb_goers[0])
        low_prio = await cursor.execute('SELECT low_priority FROM raid WHERE group_id=?', (message.id,))
        low_prio = await low_prio.fetchone()
        try:
            low_prio = eval(low_prio[0])
        except TypeError:
            low_prio = None
        if low_prio is None:
            low_prio = []
        low_prio_goers = 0
        if len(goers) < size and group_mode == 'basic':
            low_prio_goers = size - len(goers)
            goers = [*goers, *low_prio[:low_prio_goers]]
        wanters = [*wanters, *low_prio[low_prio_goers:]]

        length = await self.get_cell('group_id', message.id, 'length')
        owner = await self.get_cell('group_id', message.id, 'owner_nick')
        # owner = await message.guild.fetch_member(owner)
        if owner is None:
            nick = 'None'
        else:
            nick = owner
        #     if owner.nick is None:
        #         nick = owner.name
        #     else:
        #         nick = owner.nick

        embed = {
            'thumbnail': {
                'url': ''
            },
            'fields': [],
            'color': '',
            'type': 'rich',
            'title': name,
            'footer': {
                'text': translations['lfge']['footer'].format(self.hashids.encode(message.id), nick)
            }
        }

        if is_embed == 1:
            if message.guild.icon is not None:
                embed['thumbnail']['url'] = message.guild.icon.url.split('?')[0]
            embed['color'] = 0x000000
        else:
            embed['thumbnail']['url'] = self.lfg_categories[self.lfg_i[is_embed]]['thumbnail']
            embed['color'] = self.lfg_categories[self.lfg_i[is_embed]]['color']

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

        if lang == 'zh-cht':
            lang = 'zh'
        if await self.bot.guild_timezone_is_set(message.guild.id):
            time_str = discord.utils.format_dt(time)
        else:
            time_str = '{} {}'.format(format_datetime(time, 'medium', tzinfo=ts, locale=Locale.parse(lang, sep='-')), tz)
        embed['fields'].append({
            "inline": True,
            "name": translations['lfge']['date'],
            "value": time_str
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

        await cursor.close()
        return embed

    async def update_group_msg(self, message: discord.Message, translations: dict, lang: str) -> None:
        cursor = await self.conn.cursor()

        is_embed = await self.get_cell('group_id', message.id, 'is_embed')

        if is_embed and message.channel.permissions_for(message.guild.me).embed_links:
            embed = await self.make_embed(message, translations, lang)
            await message.edit(content=None, embed=embed)
            return

        role = await self.get_cell('group_id', message.id, 'the_role')
        name = await self.get_cell('group_id', message.id, 'name')
        time = datetime.fromtimestamp(await self.get_cell('group_id', message.id, 'time'))
        description = await self.get_cell('group_id', message.id, 'description')
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
        goers = await cursor.execute('SELECT going FROM raid WHERE group_id=?', (message.id,))
        goers = await goers.fetchone()
        goers = eval(goers[0])
        wanters = await cursor.execute('SELECT wanters FROM raid WHERE group_id=?', (message.id,))
        wanters = await wanters.fetchone()
        wanters = eval(wanters[0])

        if len(goers) > 0:
            msg = '{}\n{}'.format(msg, translations['lfg']['participants'])
            for participant in goers:
                msg = '{} {},'.format(msg, participant)
            msg = '{}.'.format(msg[:-1])
        dm_id = await self.get_cell('group_id', message.id, 'dm_message')
        if dm_id == 0:
            if len(wanters) > 0:
                msg = '{}\n{} '.format(msg, translations['lfg']['wanters'])
                for wanter in wanters:
                    msg = '{} {},'.format(msg, wanter)
                msg = '{}.'.format(msg[:-1])
        await message.edit(content=msg)
        await cursor.close()

    async def upd_dm(self, owner: Union[discord.User, discord.Member], group_id: int, translations: dict) -> None:
        cursor = await self.conn.cursor()

        wanters = await cursor.execute('SELECT want_dm FROM raid WHERE owner=? AND group_id=?', (owner.id, group_id))
        wanters = await wanters.fetchone()
        wanters = eval(wanters[0])

        dm_id = await cursor.execute('SELECT dm_message FROM raid WHERE owner=? AND group_id=?', (owner.id, group_id))
        dm_id = await dm_id.fetchone()
        dm_id = dm_id[0]

        emoji = ["{}\N{COMBINING ENCLOSING KEYCAP}".format(num) for num in range(1, 7)]

        lfg = await cursor.execute('SELECT group_id, name, time, channel_name, server_name FROM raid WHERE group_id=?',
                                   (group_id,))
        lfg = await lfg.fetchall()
        lfg = lfg[0]

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
            wanter_select = []
            for wanter in wanters:
                wanter_select.append(discord.SelectOption(label=wanter, value=str(i)))
                i += 1
                # if i < 6:
                #     msg = '{}\n{}. {}'.format(msg, emoji[i], wanter)
                #     await dm_message.edit(content=msg)
                #     await dm_message.add_reaction(emoji[i])
                #     i = i + 1
            view = DMSelectLFG(wanter_select, '{}'.format(group_id), self.bot)
            dm_message = await owner.dm_channel.send(content=msg, view=view)
            dm_id = dm_message.id

        await cursor.execute('''UPDATE raid SET dm_message=? WHERE owner=? AND group_id=?''', (dm_id, owner.id, group_id))
        await self.conn.commit()
        await cursor.close()

    async def add_going(self, group_id: int, numbers: Union[int, List[int]]) -> None:
        cursor = await self.conn.cursor()

        goers = await cursor.execute('SELECT going FROM raid WHERE group_id=?', (group_id,))
        goers = await goers.fetchone()

        if len(goers) > 0:
            goers = eval(goers[0])
        else:
            goers = []

        wanters = await cursor.execute('SELECT wanters FROM raid WHERE group_id=?', (group_id,))
        wanters = await wanters.fetchone()
        wanters = eval(wanters[0])

        w_dm = await cursor.execute('SELECT want_dm FROM raid WHERE group_id=?', (group_id,))
        w_dm = await w_dm.fetchone()
        w_dm = eval(w_dm[0])

        size = await self.get_cell('group_id', group_id, 'size')
        group_mode = await self.get_cell('group_id', group_id, 'group_mode')

        numbers = list(numbers)

        for number in numbers:
            if size > len(goers):
                if len(wanters) > number:
                    if not wanters[number] in goers:
                        goers.append(wanters[number])
        tmp_wanters = []
        tmp_w_dm = []
        for i in range(len(wanters)):
            if i not in numbers:
                tmp_wanters.append(wanters[i])
                tmp_w_dm.append(w_dm[i])
        wanters = tmp_wanters
        w_dm = tmp_w_dm

        await cursor.execute('''UPDATE raid SET wanters=? WHERE group_id=?''', (str(wanters), group_id))
        await cursor.execute('''UPDATE raid SET want_dm=? WHERE group_id=?''', (str(w_dm), group_id))
        await cursor.execute('''UPDATE raid SET going=? WHERE group_id=?''', (str(goers), group_id))
        await self.conn.commit()
        await cursor.close()

    async def dm_lfgs(self, user: Union[discord.Member, discord.User], translations: dict) -> Union[List, bool]:
        cursor = await self.conn.cursor()

        lfg_list = await cursor.execute('SELECT group_id, name, time, channel_name, server_name, timezone FROM raid WHERE owner=?',
                                        (user.id,))
        lfg_list = await lfg_list.fetchall()

        msg = translations['lfglist_head']
        i = 1
        for lfg in lfg_list:
            msg = translations['lfglist'].format(msg, i, lfg[1], datetime.fromtimestamp(lfg[2]), lfg[5],
                                                                  lfg[3], lfg[4], self.hashids.encode(lfg[0]))
            i = i + 1
        await cursor.close()
        if user.dm_channel is None:
            await user.create_dm()
        if len(lfg_list) > 0:
            await user.dm_channel.send(msg)
            return list(lfg_list)
        else:
            await user.dm_channel.send(translations['lfglist_empty'])
            return False

    async def edit(self, message: discord.Message, old_lfg: discord.Message, translations: dict, lang: str,
                   param_str: str = None) -> discord.Message:
        cursor = await self.conn.cursor()

        if param_str is not None:
            text = param_str.splitlines()
        else:
            text = message.content.splitlines()
        args = await self.parse_args(text, message, is_init=False)

        role_changed = False
        for item in args:
            await cursor.execute('''UPDATE raid SET {}=? WHERE group_id=?'''.format(item), (args[item], old_lfg.id))
            if item == 'the_role':
                role_changed = True
        await self.conn.commit()

        if message.channel.id != old_lfg.channel.id or role_changed:
            new_lfg = await message.channel.send(await self.get_cell('group_id', old_lfg.id, 'the_role'))

            await cursor.execute('''UPDATE raid SET group_id=? WHERE group_id=?''', (new_lfg.id, old_lfg.id))
            await cursor.execute('''UPDATE raid SET lfg_channel=? WHERE group_id=?''', (message.channel.id, new_lfg.id))
            await old_lfg.delete()
        else:
            new_lfg = old_lfg
        try:
            if message.id != new_lfg.id:
                await message.delete()
        except discord.NotFound:
            pass
        await self.update_group_msg(new_lfg, translations, lang)
        await self.conn.commit()
        await cursor.close()
        return new_lfg

    async def edit_info(self, old_lfg: discord.Message, args: dict, new_lfg: discord.Message = None) -> None:
        cursor = await self.conn.cursor()
        await cursor.execute(
            '''UPDATE raid 
            SET size=?, name=?, time=?, description=?, the_role=?, group_mode=?, is_embed=?, length=?, timezone=? 
            WHERE group_id=?''', (args['size'], args['name'], args['time'], args['description'], args['the_role'],
                                  args['group_mode'], args['is_embed'], args['length'], args['timezone'], old_lfg.id))
        if new_lfg is not None:
            await cursor.execute(
                '''UPDATE raid 
                SET group_id=?, lfg_channel=?, channel_name=?, server_name=?, server_id=? 
                WHERE group_id=?''', (new_lfg.id, new_lfg.channel.id, new_lfg.channel.name, new_lfg.guild.name,
                                      new_lfg.guild.id, old_lfg.id)
            )
        await self.conn.commit()
        await cursor.close()

    async def make_edits(self, bot, interaction, message, translations):
        tz = await self.get_cell('group_id', message.id, 'timezone')
        if tz is None:
            tz = 'UTC+03:00'
        if tz == 'UTC':
            tz_elements = [0, 0]
        else:
            tz_elements = tz.strip('UTC+').split(':')
        ts = timezone(timedelta(hours=int(tz_elements[0]), minutes=int(tz_elements[1])))
        time = datetime.fromtimestamp(await self.get_cell('group_id', message.id, 'time'))
        data = {
            'name': await self.get_cell('group_id', message.id, 'name'),
            'description': await self.get_cell('group_id', message.id, 'description'),
            'time': time.astimezone(ts).strftime('%d-%m-%Y %H:%M%z'),
            'size': str(await self.get_cell('group_id', message.id, 'size')),
            'length': '{}m'.format(int(await self.get_cell('group_id', message.id, 'length') / 60))
        }
        modal = LFGModal(bot, interaction.locale, translations, is_edit=True, data=data, message=message)
        await interaction.response.send_modal(modal)

    async def purge_guild(self, guild_id: int) -> None:
        cursor = await self.conn.cursor()
        group_list = await cursor.execute('SELECT group_id FROM raid WHERE server_id=?', (guild_id,))
        group_list = await group_list.fetchall()
        await cursor.executemany('''DELETE FROM alerts WHERE group_id LIKE(?)''', group_list)
        await cursor.executemany('''DELETE FROM raid WHERE server_id LIKE (?)''', [(guild_id,)])
        await self.conn.commit()
        await cursor.close()

    async def get_all(self) -> List:
        cursor = await self.conn.cursor()
        lfg_list = await cursor.execute('SELECT group_id, lfg_channel, time, server_id, length, dm_message, owner FROM raid')
        lfg_list = await lfg_list.fetchall()
        await cursor.close()

        return list(lfg_list)

    async def is_goer(self, message: discord.Message, user: discord.Member) -> bool:
        cursor = await self.conn.cursor()
        goers = await cursor.execute('SELECT going FROM raid WHERE group_id=?', (message.id,))
        goers = await goers.fetchone()
        goers = eval(goers[0])
        await cursor.close()

        return user.mention in goers

    async def is_wanter(self, message: discord.Message, user: discord.Member) -> bool:
        cursor = await self.conn.cursor()
        wanters = await cursor.execute('SELECT wanters FROM raid WHERE group_id=?', (message.id,))
        wanters = await wanters.fetchone()
        wanters = eval(wanters[0])
        await cursor.close()

        return user.mention in wanters

    async def is_mb_goer(self, message: discord.Message, user: discord.Member) -> bool:
        cursor = await self.conn.cursor()
        goers = await cursor.execute('SELECT maybe_goers FROM raid WHERE group_id=?', (message.id,))
        goers = await goers.fetchone()
        goers = eval(goers[0])

        return user.mention in goers

    async def is_low_priority(self, message: discord.Message, user: discord.Member) -> bool:
        cursor = await self.conn.cursor()
        low_prio = await cursor.execute('SELECT low_priority FROM raid WHERE group_id=?', (message.id,))
        low_prio = await low_prio.fetchone()
        low_prio = eval(low_prio[0])

        return user.mention in low_prio

    @staticmethod
    def group_frame(start, length):
        if length == 0:
            group_frame = TimeFrame(datetime.fromtimestamp(start), datetime.fromtimestamp(start + 3600))
        else:
            group_frame = TimeFrame(datetime.fromtimestamp(start), datetime.fromtimestamp(start + length))
        return group_frame

    async def check_overlaps(self, group_id: int, user_id: int) -> list:
        cursor = await self.conn.cursor()
        persons_groups = await cursor.execute('''SELECT time, length, timezone, name, server_name FROM raid WHERE (going LIKE '%{}%' or wanters like '%{}%' or maybe_goers like '%{}%') and group_id!=? '''.format(user_id, user_id, user_id), (group_id,))
        persons_groups = await persons_groups.fetchall()

        current_group = await cursor.execute('''SELECT time, length FROM raid WHERE group_id=?''', (group_id,))
        current_group = await current_group.fetchone()

        current_frame = self.group_frame(current_group[0], current_group[1])

        overlaps = []
        for group in persons_groups:
            if group[1] == 0 or current_group[1] == 0:
                potential = True
            else:
                potential = False
            group_frame = self.group_frame(group[0], group[1])
            if (group_frame * current_frame).duration > 0:
                overlaps.append((group, potential))

        await cursor.close()
        return overlaps
