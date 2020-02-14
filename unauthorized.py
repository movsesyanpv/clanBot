import discord
import sqlite3
import json


def get_unauth_response():
    try:
        conn = sqlite3.connect('internal.db')
        c = conn.cursor()
        e = c.execute('''SELECT embed FROM \'401responses\' ORDER BY RANDOM() LIMIT 1;''').fetchone()
        e = discord.Embed.from_dict(json.loads(e[0]))
        conn.close()
    except sqlite3.OperationalError:
        e = discord.Embed(title='I will not obey you.', type="rich",
                          url='https://www.youtube.com/watch?v=qn9FkoqYgI4')
        e.set_image(url='https://i.ytimg.com/vi/qn9FkoqYgI4/hqdefault.jpg')
    return e
