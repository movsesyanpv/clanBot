from discord.ext import commands, pages
from discord.commands import Option, option
import discord
#from discord_slash import cog_ext, SlashContext, manage_commands, error
from tabulate import tabulate
import mariadb
import pydest

import cogs.utils.autocomplete
from cogs.utils.autocomplete import metric_picker
from cogs.utils.converters import locale_2_lang


class Public(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        name='top',
        description='Print top players for one of the available metrics.',
        guild_only=True
    )
    async def top_sl(self, ctx,
                     metric: Option(str, "Metric to make a leaderboard", required=True, autocomplete=metric_picker),
                     number: Option(int, "Max number of positions to display", required=False, default=10, min_value=1),
                     is_global: Option(bool, "Make a leaderboard across all tracked clans", required=False,
                                       default=False)
                     ):
        await ctx.defer()
        lang = await locale_2_lang(ctx)
        if ctx.guild is None:
            await ctx.respond(ctx.bot.translations[lang]['no_dm'])
            return
        ctx.bot.guild_cursor.execute('''SELECT clan_id FROM clans WHERE server_id=?''', (ctx.guild.id,))
        clan_id = ctx.bot.guild_cursor.fetchone()
        translations = ctx.bot.translations[lang]['top']
        if clan_id is None:
            clan_id = [0]
        if clan_id[0] == 0:
            await ctx.respond(translations['no_clan'])
            return
        if len(clan_id) > 0:
            clan_ids = [clan_id[0]]
            try:
                int(metric)
                is_time = False
                is_kda = False
            except ValueError:
                try:
                    internal_db = mariadb.connect(host=ctx.bot.api_data['db_host'],
                                                  user=ctx.bot.api_data['cache_login'],
                                                  password=ctx.bot.api_data['pass'], port=ctx.bot.api_data['db_port'],
                                                  database='metrics')
                    internal_cursor = internal_db.cursor()
                    internal_cursor.execute('''SELECT hash FROM seasonsmetrics WHERE name=? and is_working=1
                                            UNION ALL
                                            SELECT hash FROM accountmetrics WHERE name=? and is_working=1
                                            UNION ALL
                                            SELECT hash FROM cruciblemetrics WHERE name=? and is_working=1
                                            UNION ALL
                                            SELECT hash FROM destinationmetrics WHERE name=? and is_working=1
                                            UNION ALL
                                            SELECT hash FROM gambitmetrics WHERE name=? and is_working=1
                                            UNION ALL
                                            SELECT hash FROM raidsmetrics WHERE name=? and is_working=1
                                            UNION ALL 
                                            SELECT hash FROM strikesmetrics WHERE name=? and is_working=1
                                            UNION ALL
                                            SELECT hash FROM trialsofosirismetrics WHERE name=?  and is_working=1''',
                                            (metric.lower(), metric.lower(),
                                             metric.lower(), metric.lower(),
                                             metric.lower(), metric.lower(),
                                             metric.lower(), metric.lower()))
                    metric_id = internal_cursor.fetchone()
                    if 'kda' in metric.lower():
                        is_kda = True
                    else:
                        is_kda = False
                    if 'ranking' in metric.lower():
                        is_ranking = True
                    else:
                        is_ranking = False
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
                    await ctx.respond(translations['unknown_metric'].format(metric))
                    return
            try:
                top_name = await ctx.bot.data.destiny.decode_hash(metric, 'DestinyMetricDefinition', language=lang)
            except pydest.pydest.PydestException:
                await ctx.respond(translations['unknown_metric'].format(metric))
                return
            # if is_global:
            #     clan_ids_c = ctx.bot.guild_cursor.execute('''SELECT clan_id FROM clans''')
            #     clan_ids_c = clan_ids_c.fetchall()
            #     clan_ids = []
            #     for clan_id in clan_ids_c:
            #         if clan_id[0] not in clan_ids:
            #             clan_ids.append(clan_id[0])
            if is_global:
                top_list = await ctx.bot.data.get_global_leaderboard(metric, number, is_time, is_kda, is_ranking)
            else:
                top_list = await ctx.bot.data.get_clan_leaderboard(clan_ids, metric, number, is_time, is_kda, is_ranking, is_global)
            max_len = min(number, len(top_list))
            if len(top_list) > 0:
                metric_description = top_name['displayProperties']['description'].splitlines()
                if len(metric_description) > 2:
                    metric_description.pop(metric_description.index(''))
                msg = ''
                long_desc = False
                if len(metric_description[0]) > 256:
                    msg = top_name['displayProperties']['description']
                    long_desc = True
                    embeds = [discord.Embed()]
                else:
                    embeds = [discord.Embed(title=metric_description[0])]
                msg = '{}```{}```'.format(msg, tabulate(top_list, tablefmt='plain', colalign=('left', 'left')))
                if len(msg) > 4096:
                    msg_strs = msg.splitlines()
                    msg = ''
                    for line in msg_strs:
                        if len(msg) + len(line) <= 4090:
                            msg = '{}{}\n'.format(msg, line)
                        else:
                            msg = '{}```'.format(msg)
                            embeds[-1].description = msg
                            embeds.append(discord.Embed())
                            msg = '```{}\n'.format(line)
                    if len(msg) > 0:
                        msg = '{}'.format(msg)
                        embeds[-1].description = msg
                else:
                    embeds[0].description = msg
                if len(metric_description) > 1 and not long_desc:
                    embeds[-1].set_footer(text=metric_description[1])
                if len(embeds) > 1:
                    paginator = pages.Paginator(pages=embeds, show_disabled=False, show_indicator=True)
                    await paginator.respond(ctx.interaction)
                else:
                    await ctx.respond(embeds=embeds)
            else:
                await ctx.respond(translations['no_data'])
        else:
            await ctx.respond(translations['no_clan'])

    @commands.command()
    async def noslash(self, ctx: discord.ext.commands.Context):
        if ctx.guild is None:
            lang = 'en'
        else:
            lang = ctx.bot.guild_lang(ctx.guild.id)
        await ctx.message.reply(ctx.bot.translations[lang]['msg']['noslash'])

    @commands.slash_command(
        name="support",
        description='Get the link to the support server'
    )
    async def support_sl(self, ctx):
        await ctx.respond('https://discord.gg/JEbzECp')

    @commands.slash_command(
        name="online",
        description="Get the list of online clan members.",
        guild_only=True
    )
    @commands.guild_only()
    async def online_sl(self, ctx):
        await ctx.defer()
        lang = await locale_2_lang(ctx)
        if ctx.guild is None:
            await ctx.respond(ctx.bot.translations[lang]['no_dm'])
            return
        ctx.bot.guild_cursor.execute('''SELECT clan_id FROM clans WHERE server_id=?''', (ctx.guild.id,))
        clan_id = ctx.bot.guild_cursor.fetchone()
        translations = ctx.bot.translations[lang]['top']
        embeds = [discord.Embed(title=ctx.bot.translations[lang]['online']['title'])]
        if clan_id is None:
            clan_id = [0]
        if clan_id[0] == 0:
            await ctx.respond(translations['no_clan'])
            return
        if len(clan_id) > 0:
            clan_ids = clan_id[0]
            data = await ctx.bot.data.get_online_clan_members(clan_ids, lang)
            data.pop(0)
            for member in data:
                embeds[-1].add_field(name=member[0], value=member[1], inline=False)
                if len(embeds[-1].fields) == 25 and data.index(member) != (len(data) - 1):
                    embeds.append(discord.Embed())
            await ctx.respond(embeds=embeds)
        else:
            await ctx.respond(translations['no_clan'])


def setup(bot):
    bot.add_cog(Public(bot))
