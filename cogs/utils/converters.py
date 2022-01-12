async def locale_2_lang(ctx):
    locale = ctx.locale

    if 'en' in locale:
        lang = 'en'
    elif 'zh' in locale:
        lang = 'zh-cht'
    elif 'es' in locale:
        lang = 'es'
    elif locale.lower() in ctx.bot.langs:
        lang = locale.lower()
    else:
        lang = 'en'

    return lang
