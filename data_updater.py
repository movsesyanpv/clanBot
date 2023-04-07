import asyncio
from typing import List, Union, Callable
import aiosqlite
import logging
from logging.handlers import RotatingFileHandler
import destiny2data as d2
import argparse
import threading
import os
from datetime import datetime, timedelta
import time


def timeit(func):
    async def process(func, *args, **params):
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **params)
        else:
            return func(*args, **params)

    async def helper(*args, **params):
        print('{}.time'.format(func.__name__))
        start = time.time()
        result = await process(func, *args, **params)

        print('Execution time is ', time.time() - start)
        return result

    return helper


@timeit
async def update_metrics(args: argparse.Namespace):
    try:
        data = d2.D2data(None, [], args.oauth, args.production,
                         (args.cert, args.key))
        await data.token_update()
        cursor = await data.bot_data_db.cursor()
        clan_ids_c = await cursor.execute('''SELECT clan_id FROM clans''')
        clan_ids_c = await clan_ids_c.fetchall()
        clan_ids = []
        for clan_id in clan_ids_c:
            clan_ids.append(clan_id[0])
        clan_ids = list(set(clan_ids))
        member_number = await data.update_clan_metrics(clan_ids)
        # await self.data.get_clan_leaderboard(clan_ids, 1572939289, 10)
        await cursor.close()
        nonmember_number = await data.update_members_without_tracked_clans()

        print('Updated users: {}'.format(member_number))
        print('Updated users without a clan: {}'.format(nonmember_number))
        print('Total users updated: {}'.format(member_number+nonmember_number))

        await data.session.close()
        await data.bot_data_db.close()
    except (Exception, KeyboardInterrupt) as e:
        print('ERROR', str(e))
        exit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--production', help='Use to launch in production mode', action='store_true')
    # parser.add_argument('-l', '--lang', nargs='+', help='Language of data', default=self.langs)
    parser.add_argument('-t', '--type', nargs='+', help='Type of message. Use with -f')
    parser.add_argument('-tp', '--testprod', help='Use to launch in test production mode', action='store_true')
    parser.add_argument('--oauth', help='Get Bungie access token', action='store_true')
    parser.add_argument('-k', '--key', help='SSL key', type=str, default='')
    parser.add_argument('-c', '--cert', help='SSL certificate', type=str, default='')
    args = parser.parse_args()

    try:
        asyncio.run(update_metrics(args))
    finally:
        print('done')
        os._exit(0)