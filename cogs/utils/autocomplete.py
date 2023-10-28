import mariadb
import json
import pytz
import zoneinfo
from zoneinfo import ZoneInfo
from datetime import datetime


api_data_file = open('api.json', 'r')
api_data = json.loads(api_data_file.read())


async def metric_picker(interaction, value):
    internal_db = mariadb.connect(host=api_data['db_host'], user=api_data['cache_login'],
                                  password=api_data['pass'], port=api_data['db_port'],
                                  database='metrics')
    search_str = value.value
    internal_cursor = internal_db.cursor()
    internal_cursor.execute('''SELECT name FROM seasonsmetrics WHERE name LIKE ? and is_working=1
                            UNION
                            SELECT name FROM accountmetrics WHERE name LIKE ? and is_working=1
                            UNION
                            SELECT name FROM cruciblemetrics WHERE name LIKE ? and is_working=1
                            UNION
                            SELECT name FROM destinationmetrics WHERE name LIKE ? and is_working=1
                            UNION
                            SELECT name FROM gambitmetrics WHERE name LIKE ? and is_working=1
                            UNION
                            SELECT name FROM raidsmetrics WHERE name LIKE ? and is_working=1
                            UNION
                            SELECT name FROM strikesmetrics WHERE name LIKE ? and is_working=1
                            UNION
                            SELECT name FROM trialsofosirismetrics WHERE name LIKE ?  and is_working=1
                            ORDER BY NAME asc''',
                            ('%{}%'.format(search_str), '%{}%'.format(search_str),
                             '%{}%'.format(search_str), '%{}%'.format(search_str),
                             '%{}%'.format(search_str), '%{}%'.format(search_str),
                             '%{}%'.format(search_str), '%{}%'.format(search_str)))
    metric_id = internal_cursor.fetchall()
    metric_list = [metric[0] for metric in metric_id]
    if len(metric_list) > 25:
        return metric_list[:25]
    else:
        return metric_list


async def timezone_picker(interaction, value):
    tz_list = []

    for tz in zoneinfo.available_timezones():
        try:
            offset = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(pytz.timezone(tz)).utcoffset().total_seconds()
            sign = '-' if offset < 0 or 'GMT-' in tz else '+'
            tz_list.append(f'{tz} (UTC{sign}{abs(int(offset//3600)):02}:{abs(int(offset%60)):02})')
        except pytz.exceptions.UnknownTimeZoneError:
            pass
    matching = [tz for tz in tz_list if value.value.lower() in tz.lower()]

    if len(matching) > 25:
        return matching[:25]
    else:
        return matching
