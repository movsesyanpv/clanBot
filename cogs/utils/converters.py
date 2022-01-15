from typing import Union
from discord import ApplicationContext


class CtxLocale:
    def __init__(self, bot, locale):
        self.bot = bot
        self.locale = locale


async def locale_2_lang(ctx: Union[ApplicationContext, CtxLocale]) -> str:
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
