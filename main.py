import json
import discord
import argparse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import asyncio
# import logging

import raid as lfg
import destiny2data as d2


# logging.basicConfig()
# logging.getLogger('apscheduler').setLevel(logging.DEBUG)

class ClanBot(discord.Client):

    sched = AsyncIOScheduler(timezone='UTC')
    curr_hist = False

    api_data_file = open('api.json', 'r')
    api_data = json.loads(api_data_file.read())

    lfgs = []

    channels = []

    args = ''

    translations = {}

    def __init__(self, **options):
        super().__init__(**options)
        self.get_args()
        translations_file = open('translations.json', 'r', encoding='utf-8')
        self.translations = json.loads(translations_file.read())
        translations_file.close()
        self.data = d2.D2data(self.translations, self.args.oauth)

    def get_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-nc', '--noclear', help='Don\'t clear last message of the type', action='store_true')
        parser.add_argument('-p', '--production', help='Use to launch in production mode', action='store_true')
        parser.add_argument('-nm', '--nomessage', help='Don\'t post any messages', action='store_true')
        parser.add_argument('-l', '--lang', type=str, help='Language of data', default='en')
        parser.add_argument('-t', '--type', type=str, help='Type of message. Use with -f')
        parser.add_argument('-tp', '--testprod', help='Use to launch in test production mode', action='store_true')
        parser.add_argument('-f', '--forceupdate', help='Force update right now', action='store_true')
        parser.add_argument('--oauth', help='Get Bungie access token', action='store_true')
        self.args = parser.parse_args()

    async def force_update(self, upd_type):
        if 'daily' in upd_type:
            await self.universal_update(self.data.get_heroic_story, 'heroicstory', 86400)
            await self.universal_update(self.data.get_forge, 'forge', 86400)
            await self.universal_update(self.data.get_strike_modifiers, 'vanguardstrikes', 86400)
            await self.universal_update(self.data.get_reckoning_modifiers, 'reckoning', 86400)
            await self.update_history()
        if 'weekly' in upd_type:
            await self.universal_update(self.data.get_nightfall820, 'nightfalls820', 604800)
            await self.universal_update(self.data.get_ordeal, 'ordeal', 604800)
            await self.universal_update(self.data.get_nightmares, 'nightmares', 604800)
            await self.universal_update(self.data.get_reckoning_boss, 'reckoningboss', 604800)
            await self.universal_update(self.data.get_crucible_rotators, 'cruciblerotators', 604800)
            await self.update_history()
        if 'spider' in upd_type:
            await self.universal_update(self.data.get_spider, 'spider', 86400)
            await self.update_history()
        if 'xur' in upd_type:
            await self.universal_update(self.data.get_xur, 'xur', 345600)
            await self.update_history()
        await self.logout()
        await self.close()

    async def on_ready(self):
        await self.data.token_update()
        await self.update_history()
        self.get_channels()
        self.data.get_chars()
        if self.args.forceupdate:
            await self.force_update(self.args.type)
        self.sched.add_job(self.universal_update, 'cron', hour='17', minute='0', second='30', misfire_grace_time=86300, args=[self.data.get_heroic_story, 'heroicstory', 86400])
        self.sched.add_job(self.universal_update, 'cron', hour='17', minute='0', second='30', misfire_grace_time=86300, args=[self.data.get_forge, 'forge', 86400])
        self.sched.add_job(self.universal_update, 'cron', hour='17', minute='0', second='30', misfire_grace_time=86300, args=[self.data.get_strike_modifiers, 'vanguardstrikes', 86400])
        self.sched.add_job(self.universal_update, 'cron', hour='17', minute='0', second='30', misfire_grace_time=86300, args=[self.data.get_reckoning_modifiers, 'reckoning', 86400])

        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='0', second='40', misfire_grace_time=86300, args=[self.data.get_nightfall820, 'nightfalls820', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='0', second='40', misfire_grace_time=86300, args=[self.data.get_ordeal, 'ordeal', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='0', second='40', misfire_grace_time=86300, args=[self.data.get_nightmares, 'nightmares', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='0', second='40', misfire_grace_time=86300, args=[self.data.get_reckoning_boss, 'reckoningboss', 604800])
        self.sched.add_job(self.universal_update, 'cron', day_of_week='tue', hour='17', minute='0', second='40', misfire_grace_time=86300, args=[self.data.get_crucible_rotators, 'cruciblerotators', 604800])

        self.sched.add_job(self.universal_update, 'cron', day_of_week='fri', hour='17', minute='5', second='0', misfire_grace_time=86300, args=[self.data.get_xur, 'xur', 345600])
        self.sched.add_job(self.universal_update, 'cron', hour='1', minute='0', second='10', misfire_grace_time=86300, args=[self.data.get_spider, 'spider', 86400])

        self.sched.add_job(self.update_history, 'cron', hour='2')
        self.sched.add_job(self.data.token_update, 'interval', hours=1)
        self.sched.start()

    async def check_ownership(self, message):
        bot_info = await self.application_info()
        is_owner = bot_info.owner == message.author
        if not is_owner:
            msg = '{}!'.format(message.author.mention)
            e = discord.Embed(title='I will not obey you.', type="rich",
                              url='https://www.youtube.com/watch?v=qn9FkoqYgI4')
            e.set_image(url='https://i.ytimg.com/vi/qn9FkoqYgI4/hqdefault.jpg')
            await message.channel.send(msg, embed=e)
        return is_owner

    async def on_reaction_remove(self, reaction, user):
        if user == self.user:
            return

        for group in self.lfgs:
            if group.is_raid(reaction.message):
                if str(reaction) != '👌':
                    return
                if user.mention in group.going:
                    group.going.pop(group.going.index(user.mention))
                    if len(group.wanters) > 0:
                        group.going.append(group.wanters[0])
                        group.wanters.pop(0)
                if user.mention in group.wanters:
                    group.wanters.pop(group.wanters.index(user.mention))
                await group.update_group_msg(reaction, user, self.translations[self.args.lang])

    async def on_reaction_add(self, reaction, user):
        if user == self.user:
            return

        for group in self.lfgs:
            if group.is_raid(reaction.message):
                if str(reaction) == '❌' and user == group.owner:
                    await reaction.message.delete()
                    self.lfgs.pop(self.lfgs.index(group))
                    self.sched.remove_job('{}_del'.format(group.group_id))
                    print(self.lfgs)
                    return
                if str(reaction) != '👌':
                    await reaction.remove(user)
                    return
                if len(group.going) < group.size:
                    group.going.append(user.mention)
                else:
                    group.wanters.append(user.mention)
                await group.update_group_msg(reaction, user, self.translations[self.args.lang])

    async def pause_for(self, message, delta):
        self.sched.pause()
        await asyncio.sleep(delta.total_seconds())
        self.sched.resume()
        await message.channel.send('should be after delay finish {}'.format(str(datetime.now())))
        return

    async def on_message(self, message):
        if message.author == self.user:
            return

        if 'stop' in message.content.lower() and (self.user in message.mentions or str(message.channel.type) == 'private'):
            if await self.check_ownership(message):
                msg = 'Ok, {}'.format(message.author.mention)
                await message.channel.send(msg)
                self.sched.shutdown(wait=True)
                await self.update_history()
                await self.logout()
                await self.close()
                return
            return

        if 'plan maintenance' in message.content.lower() and (self.user in message.mentions or str(message.channel.type) == 'private'):
            if await self.check_ownership(message):
                try:
                    content = message.content.splitlines()
                    start = datetime.strptime(content[1], "%d-%m-%Y %H:%M %z")
                    finish = datetime.strptime(content[2], "%d-%m-%Y %H:%M %z")
                    delta = finish-start
                    self.sched.add_job(self.pause_for, 'date', run_date=start, args=[message, delta], misfire_grace_time=600)
                except Exception as e:
                    await message.channel.send('exception `{}`\nUse following format:```plan maintenance\n<start time formatted %d-%m-%Y %H:%M %z>\n<finish time formatted %d-%m-%Y %H:%M %z>```'.format(str(e)))
                return
            return

        if str(message.channel.type) == 'private':
            msg = 'Can\'t do anything a private chat, {}'.format(message.author.mention)
            await message.channel.send(msg)
            return

        if 'lfg' in message.content.lower().splitlines()[0] and self.user in message.mentions:
            content = message.content.splitlines()
            raid = lfg.LFG(message)
            msg = "{}, {} {}\n{} {}\n{}".format(raid.the_role.mention, self.translations[self.args.lang]['lfg']['go'], raid.name, self.translations[self.args.lang]['lfg']['at'], raid.time.strftime("%d-%m-%Y %H:%M %Z"), raid.description)
            out = await message.channel.send(msg)
            end_time = raid.time + timedelta(seconds=3600)
            await out.add_reaction('👌')
            await out.add_reaction('❌')
            raid.group_id = out.id
            self.sched.add_job(out.delete, 'date', run_date=end_time, id='{}_del'.format(raid.group_id))
            self.sched.add_job(raid.ping_going, 'date', run_date=raid.time, id='{}_ping'.format(raid.group_id))
            self.lfgs.append(raid)

        if 'regnotifier' in message.content.lower() and self.user in message.mentions:
            if await self.check_ownership(message):
                await message.delete()
                self.channels.append(message.channel.id)
                self.channels = list(set(self.channels))
                f = open('channelList.dat', 'w')
                for channel in self.channels:
                    f.write('{}\n'.format(channel))
                f.close()
                msg = 'Got it, {}'.format(message.author.mention)
                await message.channel.send(msg, delete_after=10)
                return
            return

        if 'update' in message.content.lower() and self.user in message.mentions:
            content = message.content.lower().split()
            await message.delete()
            for upd_type in content[2:]:
                await self.force_update(upd_type)
            return

    def get_channels(self):
        try:
            f = open('channelList.dat', 'r')
            self.channels = f.readlines()
            f.close()
        except FileNotFoundError:
            pass

    async def update_history(self):
        game = discord.Game('updating history')
        await self.change_presence(activity=game)
        hist_saved = {}
        for server in self.guilds:
            history_file = str(server.id) + '_history.json'
            try:
                with open(history_file) as json_file:
                    hist_saved[str(server.id)] = json.loads(json_file.read())
                    json_file.close()
            except FileNotFoundError:
                with open("history.json") as json_file:
                    hist_saved[str(server.id)] = json.loads(json_file.read())
                    json_file.close()
        if self.curr_hist:
            for server in self.guilds:
                history_file = str(server.id) + '_history.json'
                f = open(history_file, 'w')
                f.write(json.dumps(self.curr_hist[str(server.id)]))
        else:
            self.curr_hist = hist_saved
        game = discord.Game('waiting')
        await self.change_presence(activity=game)

    async def universal_update(self, getter, name, time_to_delete):
        await self.wait_until_ready()
        game = discord.Game('updating {}'.format(name))
        await self.change_presence(activity=game)

        lang = self.args.lang

        await getter(lang)

        if not self.data.data['api_maintenance'] and not self.data.data['api_fucked_up']:
            if self.data.data[name]:
                await self.post_embed(name, self.data.data[name], time_to_delete)

        game = discord.Game('waiting')
        await self.change_presence(activity=game)

    async def post_embed(self, upd_type, src_dict, time_to_delete):
        hist = self.curr_hist

        if not self.args.nomessage:
            embed = discord.Embed.from_dict(src_dict)

            for server in self.guilds:
                hist[str(server.id)]['server_name'] = server.name.strip('\'')
                for channel in server.channels:
                    if '{}\n'.format(channel.id) in self.channels:
                        if hist[str(server.id)][upd_type] and \
                                not self.args.noclear:
                            try:
                                last = await channel.fetch_message(
                                    hist[str(server.id)][upd_type])
                            except discord.NotFound:
                                bot_info = await self.application_info()
                                await bot_info.owner.send('Not found at ```{}```. Channel ```{}``` of ```{}```'.format(upd_type, channel.name, server.name))
                            try:
                                await last.delete()
                            except:
                                pass
                        message = await channel.send(embed=embed, delete_after=time_to_delete)
                        hist[str(server.id)][upd_type] = message.id

    def start_up(self):
        self.get_args()
        token = self.api_data['token']
        print('hmm')
        self.run(token)


if __name__ == '__main__':
    b = ClanBot()
    b.start_up()
