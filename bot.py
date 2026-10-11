import logging
import asyncio
from pyrogram import Client
from pytgcalls import PyTgCalls
from config import BOT_TOKEN, API_ID, API_HASH, SESSION_STRING, LOG_LEVEL
from database import init_db
from handlers.commands import *
from handlers.playback import setup_playback_handlers
from handlers.admin import *

logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(__name__)

app = Client(
    "krutikmusicbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    session_string=SESSION_STRING if SESSION_STRING else None
)

pytgcalls = PyTgCalls(app)
setup_playback_handlers(pytgcalls)

async def main():
    await init_db()
    await app.start()
    await pytgcalls.start()
    logger.info("KRUTIK CYBER MUSIC BOT started successfully!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
