from discord.ext import commands
import discord
from tabulate import tabulate
import mariadb
import pydest


class Public(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        aliases=['gtop', 'globaltop']
    )
    @commands.guild_only()
    async def top(self, ctx, metric, number=10):
        ctx.bot.guild_cursor.execute('''SELECT clan_id FROM clans WHERE server_id=?''', (ctx.guild.id,))
        clan_id = ctx.bot.guild_cursor.fetchone()
        lang = ctx.bot.guild_lang(ctx.message.guild.id)
        translations = ctx.bot.translations[lang]['top']
        if ctx.invoked_with in ['gtop', 'globaltop']:
            is_global = True
        else:
            is_global = False
        if clan_id is None:
            clan_id = [0]
        if clan_id[0] == 0:
            await ctx.channel.send(translations['no_clan'], delete_after=60)
            return
        if len(clan_id) > 0:
            clan_ids = [clan_id[0]]
            try:
                int(metric)
                is_time = False
                is_kda = False
            except ValueError:
                try:
                    internal_db = mariadb.connect(host=ctx.bot.api_data['db_host'], user=ctx.bot.api_data['cache_login'],
                                                  password=ctx.bot.api_data['pass'], port=ctx.bot.api_data['db_port'],
                                                  database='metrics')
                    internal_cursor = internal_db.cursor()
                    internal_cursor.execute('''SELECT hash FROM seasonsmetrics WHERE name=?
                    UNION ALL
                    SELECT hash FROM accountmetrics WHERE name=?
                    UNION ALL
                    SELECT hash FROM cruciblemetrics WHERE name=?
                    UNION ALL
                    SELECT hash FROM destinationmetrics WHERE name=?
                    UNION ALL
                    SELECT hash FROM gambitmetrics WHERE name=?
                    UNION ALL
                    SELECT hash FROM raidsmetrics WHERE name=?
                    UNION ALL 
                    SELECT hash FROM strikesmetrics WHERE name=?
                    UNION ALL
                    SELECT hash FROM trialsofosirismetrics WHERE name=? ''', (metric.lower(), metric.lower(),
                                                                              metric.lower(), metric.lower(),
                                                                              metric.lower(), metric.lower(),
                                                                              metric.lower(), metric.lower()))
                    metric_id = internal_cursor.fetchone()
                    if 'kda' in metric.lower():
                        is_kda = True
                    else:
                        is_kda = False
                    if 'speed' in metric.lower():
                        is_time = True
                    else:
                        is_time = False
                    if metric_id is not None:
                        if len(metric_id) > 0:
                            metric = metric_id[0]
                        else:
                            internal_db.close()
                            raise mariadb.Error
                    else:
                        internal_db.close()
                        raise mariadb.Error
                    internal_db.close()
                except mariadb.Error:
                    await ctx.channel.send(translations['unknown_metric'].format(metric), delete_after=10)
                    if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
                        await ctx.message.delete()
                    return
            try:
                top_name = await ctx.bot.data.destiny.decode_hash(metric, 'DestinyMetricDefinition', language=lang)
            except pydest.pydest.PydestException:
                await ctx.channel.send(translations['unknown_metric'].format(metric), delete_after=10)
                if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
                    await ctx.message.delete()
                return
            await ctx.channel.send(translations['in_progress'], delete_after=30)
            if is_global:
                clan_ids_c = ctx.bot.guild_cursor.execute('''SELECT clan_id FROM clans''')
                clan_ids_c = clan_ids_c.fetchall()
                clan_ids = []
                for clan_id in clan_ids_c:
                    clan_ids.append(clan_id[0])
            top_list = await ctx.bot.data.get_clan_leaderboard(clan_ids, metric, number, is_time, is_kda, is_global)
            max_len = min(number, len(top_list))
            if len(top_list) > 0:
                msg = '{}```{}```'.format(top_name['displayProperties']['description'], tabulate(top_list, tablefmt='plain', colalign=('left', 'left')))
                if len(msg) > 2000:
                    msg_strs = msg.splitlines()
                    msg = ''
                    for line in msg_strs:
                        if len(msg) + len(line) <= 1990:
                            msg = '{}{}\n'.format(msg, line)
                        else:
                            msg = '{}```'.format(msg)
                            await ctx.channel.send(msg)
                            msg = '```{}\n'.format(line)
                    if len(msg) > 0:
                        msg = '{}'.format(msg)
                        await ctx.channel.send(msg)
                else:
                    await ctx.channel.send(msg)
            else:
                await ctx.channel.send(translations['no_data'])
        else:
            await ctx.channel.send(translations['no_clan'], delete_after=10)
        if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
            await ctx.message.delete()

    @commands.command()
    @commands.guild_only()
    async def prefix(self, ctx):
        lang = ctx.bot.guild_lang(ctx.message.guild.id)
        prefixes = ctx.bot.guild_prefix(ctx.guild.id)
        if len(prefixes) > 0:
            msg = '{}\n'.format(ctx.bot.translations[lang]['msg']['prefixes'].format(ctx.message.guild.me.display_name, prefixes[0]))
            prefix_list = ''
            for prefix in prefixes:
                prefix_list = '{} {},'.format(prefix_list, prefix)
            prefix_list = prefix_list[1:-1]
            msg = '{}```{}```'.format(msg, prefix_list)
        else:
            msg = '{}\n'.format(ctx.bot.translations[lang]['msg']['no_prefixes'].format(ctx.message.guild.me.display_name))
        await ctx.message.channel.send(msg)
        if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
            await ctx.message.delete()

    @commands.command()
    async def support(self, ctx):
        await ctx.channel.send('https://discord.gg/JEbzECp')

    @commands.command()
    @commands.guild_only()
    async def online(self, ctx):
        ctx.bot.guild_cursor.execute('''SELECT clan_id FROM clans WHERE server_id=?''', (ctx.guild.id,))
        clan_id = ctx.bot.guild_cursor.fetchone()
        lang = ctx.bot.guild_lang(ctx.message.guild.id)
        translations = ctx.bot.translations[lang]['top']
        if clan_id is None:
            clan_id = [0]
        if clan_id[0] == 0:
            await ctx.channel.send(translations['no_clan'], delete_after=60)
            return
        if len(clan_id) > 0:
            clan_ids = clan_id[0]
            data = await ctx.bot.data.get_online_clan_members(clan_ids, lang)
            msg = '```{}```'.format(tabulate(data, tablefmt='simple', colalign=('left', 'left'), headers='firstrow'))
            if len(msg) > 2000:
                msg_strs = msg.splitlines()
                msg = ''
                for line in msg_strs:
                    if len(msg) + len(line) <= 1990:
                        msg = '{}{}\n'.format(msg, line)
                    else:
                        msg = '{}```'.format(msg)
                        await ctx.channel.send(msg)
                        msg = '```{}\n'.format(line)
                if len(msg) > 0:
                    msg = '{}'.format(msg)
                    await ctx.channel.send(msg)
            else:
                await ctx.channel.send(msg)
        else:
            await ctx.channel.send(translations['no_clan'], delete_after=10)


def setup(bot):
    bot.add_cog(Public(bot))
