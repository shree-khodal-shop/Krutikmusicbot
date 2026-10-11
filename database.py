import aiosqlite
from config import DATABASE_PATH

async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS approved_groups (
                chat_id INTEGER PRIMARY KEY
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS track_cache (
                url TEXT PRIMARY KEY,
                file_id TEXT,
                title TEXT,
                duration INTEGER
            )
        """)
        await db.execute("""
            INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('maintenance', 'false')
        """)
        await db.execute("""
            INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('bot_status', 'true')
        """)
        await db.commit()

async def get_setting(key: str) -> str:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()

async def is_user_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT 1 FROM banned_users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone() is not None
          
