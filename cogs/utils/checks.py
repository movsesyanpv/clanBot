import discord
from discord import ApplicationContext


async def message_permissions(ctx: ApplicationContext, lang) -> bool:
    send_msg = ctx.channel.permissions_for(ctx.guild.me).send_messages
    embed_links = ctx.channel.permissions_for(ctx.guild.me).embed_links

    translations = ctx.bot.translations[lang]['msg']

    if send_msg and embed_links:
        return True
    try:
        await ctx.defer(ephemeral=True)
    except discord.InteractionResponded:
        pass
    response_embed = discord.Embed(colour=discord.Colour.red(), title=translations['perm_check_title'],
                                   description=translations['perm_check_description'])
    response_embed.add_field(name=translations['perm_send_msg'].format('✅' if send_msg else '❌'), value=u"\u2063", inline=False)
    response_embed.add_field(name=translations['perm_embed_links'].format('✅' if embed_links else '❌'), value=u"\u2063", inline=False)

    await ctx.respond(embed=response_embed, ephemeral=True)
    return False
