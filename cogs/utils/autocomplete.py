import mariadb
import json


api_data_file = open('api.json', 'r')
api_data = json.loads(api_data_file.read())


async def metric_picker(interaction, value):
    internal_db = mariadb.connect(host=api_data['db_host'], user=api_data['cache_login'],
                                  password=api_data['pass'], port=api_data['db_port'],
                                  database='metrics')
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
                            ('%{}%'.format(value), '%{}%'.format(value), '%{}%'.format(value), '%{}%'.format(value),
                             '%{}%'.format(value), '%{}%'.format(value), '%{}%'.format(value),
                             '%{}%'.format(value)))
    metric_id = internal_cursor.fetchall()
    metric_list = [metric[0] for metric in metric_id]
    if len(metric_list) > 25:
        return metric_list[:25]
    else:
        return metric_list
