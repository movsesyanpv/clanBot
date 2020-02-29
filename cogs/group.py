from discord.ext import commands
import discord
from datetime import datetime, timedelta, timezone
from hashids import Hashids


class Group(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.dm_only()
    async def lfglist(self, ctx):
        await ctx.bot.raid.dm_lfgs(ctx.author)
        return

    async def guild_lfg(self, ctx, message):
        ctx.bot.raid.add(message)
        role = ctx.bot.raid.get_cell('group_id', message.id, 'the_role')
        name = ctx.bot.raid.get_cell('group_id', message.id, 'name')
        time = datetime.fromtimestamp(ctx.bot.raid.get_cell('group_id', message.id, 'time'))
        is_embed = ctx.bot.raid.get_cell('group_id', message.id, 'is_embed')
        description = ctx.bot.raid.get_cell('group_id', message.id, 'description')
        msg = "{}, {} {}\n{} {}\n{}".format(role, ctx.bot.translations[ctx.bot.args.lang]['lfg']['go'], name,
                                            ctx.bot.translations[ctx.bot.args.lang]['lfg']['at'], time, description)
        if is_embed:
            embed = ctx.bot.raid.make_embed(message, ctx.bot.translations[ctx.bot.args.lang])
            out = await message.channel.send(content=msg)
            await out.edit(content=None, embed=embed)
        else:
            out = await message.channel.send(msg)
        end_time = time + timedelta(seconds=ctx.bot.raid.get_cell('group_id', message.id, 'length'))
        await out.add_reaction('👌')
        await out.add_reaction('❌')
        ctx.bot.raid.set_id(out.id, message.id)
        await ctx.bot.raid.update_group_msg(out, ctx.bot.translations[ctx.bot.args.lang])
        # self.sched.add_job(out.delete, 'date', run_date=end_time, id='{}_del'.format(out.id))
        await message.delete()
        return out.id

    async def dm_lfg(self, ctx):
        def check(ms):
            return ms.channel == ctx.author.dm_channel and ms.author == ctx.message.author

        if ctx.author.dm_channel is None:
            await ctx.author.create_dm()
        dm = ctx.author.dm_channel

        translations = ctx.bot.translations[ctx.bot.args.lang]['lfg']

        await dm.send(content=translations['name'])
        msg = await self.bot.wait_for('message', check=check)
        name = msg.content

        await dm.send(content=translations['description'])
        msg = await self.bot.wait_for('message', check=check)
        description = msg.content

        await dm.send(content=translations['time'])
        msg = await self.bot.wait_for('message', check=check)
        time = msg.content

        await dm.send(content=translations['size'])
        msg = await self.bot.wait_for('message', check=check)
        size = msg.content

        await dm.send(content=translations['length'])
        msg = await self.bot.wait_for('message', check=check)
        length = msg.content

        await dm.send(content=translations['type'])
        msg = await self.bot.wait_for('message', check=check)
        a_type = msg.content

        await dm.send(content=translations['mode'])
        msg = await self.bot.wait_for('message', check=check)
        mode = msg.content

        await dm.send(content=translations['role'])
        msg = await self.bot.wait_for('message', check=check)
        role = msg.content

        at = ['default', 'vanguard', 'raid', 'crucible', 'gambit']
        ts = datetime.now(timezone(timedelta(0))).astimezone()
        args = ctx.bot.raid.parse_args('lfg\n-n:{}\n-d:{}\n-t:{}\n-s:{}\n-l:{}\n-at:{}\n-m:{}\n-r:{}'.format(name, description, time, size, length, a_type, mode, role).splitlines(), ctx.message, True)
        ts = datetime.fromtimestamp(args['time']).replace(tzinfo=ts.tzinfo)
        await dm.send(translations['check']
                      .format(args['name'], args['description'], ts, args['size'],
                              args['length']/3600, at[args['is_embed']], args['group_mode'], role))
        msg = await self.bot.wait_for('message', check=check)
        if msg.content.lower() == translations['no']:
            await dm.send(translations['again'])
            await ctx.message.delete()
            return

        tmp = await ctx.send('lfg\n-n:{}\n-d:{}\n-t:{}\n-s:{}\n-l:{}\n-at:{}\n-m:{}\n-r:{}'.format(name, description, time, size, length, at[args['is_embed']], mode, role))
        group_id = await self.guild_lfg(ctx, tmp)
        ctx.bot.raid.set_owner(ctx.author.id, group_id)
        await ctx.message.delete()

        return

    @commands.command(aliases=['сбор', 'лфг'])
    @commands.guild_only()
    async def lfg(self, ctx):
        if len(ctx.message.content.splitlines()) > 1:
            await self.guild_lfg(ctx, ctx.message)
        else:
            await self.dm_lfg(ctx)

    @commands.command(aliases=['editlfg', 'editLfg', 'editLFG'])
    @commands.guild_only()
    async def edit_lfg(self, ctx, arg_id, *args):
        message = ctx.message
        text = message.content.split()
        hashids = Hashids()
        group_id = hashids.decode(arg_id)
        if len(group_id) > 0:
            old_lfg = ctx.bot.raid.get_cell('group_id', group_id[0], 'lfg_channel')
            old_lfg = ctx.bot.get_channel(old_lfg)
            owner = ctx.bot.raid.get_cell('group_id', group_id[0], 'owner')
            if old_lfg is not None and owner is not None:
                old_lfg = await old_lfg.fetch_message(group_id[0])
                if owner == message.author.id:
                    await ctx.bot.raid.edit(message, old_lfg, ctx.bot.translations[ctx.bot.args.lang])
                else:
                    await ctx.bot.check_ownership(message)
                    await message.delete()
            else:
                await message.delete()
        return


def setup(bot):
    bot.add_cog(Group(bot))
