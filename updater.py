import os
import sqlite3


def go():
    print('this is even newer')
    migrate_db()


def migrate_db():
    lfg_db = sqlite3.connect('lfg.db')
    lfg_cursor = lfg_db.cursor()

    try:
        lfg_cursor.execute('''ALTER TABLE raid ADD COLUMN maybe_goers text''')
        lfg_db.commit()
    except sqlite3.OperationalError:
        pass

    try:
        lfg_cursor.execute('''ALTER TABLE raid ADD COLUMN timezone text''')
        lfg_db.commit()
    except sqlite3.OperationalError:
        pass
    