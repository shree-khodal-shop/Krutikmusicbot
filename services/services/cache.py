import aiosqlite
from config import DATABASE_PATH

async def get_cached_track(url: str):
    async sql = "SELECT file_id, title, duration FROM track_cache WHERE url = ?"
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(sql, (url,)) as cursor:
            return await cursor.fetchone()

async def save_track_cache(url: str, file_id: str, title: str, duration: int):
    sql = "INSERT OR REPLACE INTO track_cache (url, file_id, title, duration) VALUES (?, ?, ?, ?)"
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(sql, (url, file_id, title, duration))
        await db.commit()
      
