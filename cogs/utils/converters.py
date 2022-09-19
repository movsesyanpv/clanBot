from typing import Union
from discord import ApplicationContext, Interaction


class CtxLocale:
    def __init__(self, bot, locale):
        self.bot = bot
        self.locale = locale


async def locale_2_lang(ctx: Union[ApplicationContext, CtxLocale, Interaction]) -> str:
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


def lang_2_locale(lang: str) -> str:
    if 'en' in lang:
        locale = 'en-US'
    elif 'es' in lang:
        locale = 'es-ES'
    elif lang == 'pt-br':
        locale = 'pt-BR'
    elif lang == 'zh-cht':
        locale = 'zh-TW'
    elif lang == 'zh-chs':
        locale = 'zh-CN'
    else:
        locale = lang

    return locale
