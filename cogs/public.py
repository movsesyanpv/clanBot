from discord.ext import commands
import discord
from tabulate import tabulate
import sqlite3
import pydest


class Public(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.guild_only()
    async def top(self, ctx, metric, number=10):
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
            clan_id = clan_id[0]
            try:
                int(metric)
                is_time = False
                is_kda = False
            except ValueError:
                try:
                    internal_db = sqlite3.connect('internal.db')
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
                            raise sqlite3.OperationalError
                    else:
                        raise sqlite3.OperationalError
                except sqlite3.OperationalError:
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
            top_list = await ctx.bot.data.get_clan_leaderboard(clan_id, metric, number, is_time, is_kda)
            max_len = min(number, len(top_list))
            if len(top_list) > 0:
                await ctx.channel.send('{}```{}```'.format(top_name['displayProperties']['description'], tabulate(top_list, tablefmt='plain', colalign=('left', 'left'))))
            else:
                await ctx.channel.send(translations['no_data'])
        else:
            await ctx.channel.send(translations['no_clan'], delete_after=10)
        if ctx.guild.me.permissions_in(ctx.message.channel).manage_messages:
            await ctx.message.delete()


def setup(bot):
    bot.add_cog(Public(bot))
