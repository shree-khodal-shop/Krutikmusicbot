import time
from pyrogram import Client, filters
from pyrogram.types import Message
from database import is_user_banned

start_time = time.time()

@Client.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    if await is_user_banned(message.from_user.id):
        return
    await message.reply_text(
        "🎶 **Welcome to KRUTIK CYBER MUSIC BOT!**\n\n"
        "Use /help to explore all available commands.\n\n"
        "**Brand:** KRUTIK CYBER DEVELOPER"
    )

@Client.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    if await is_user_banned(message.from_user.id):
        return
    await message.reply_text(
        "📖 **KRUTIK CYBER MUSIC BOT - COMMANDS**\n\n"
        "/play <query> - Play audio in voice chat\n"
        "/pause - Pause stream\n"
        "/resume - Resume stream\n"
        "/skip - Skip current track\n"
        "/stop - Stop playback & clear queue\n"
        "/queue - View queue\n"
        "/ping - Check latency\n"
        "/stats - View statistics"
    )

@Client.on_message(filters.command("ping"))
async def ping_command(client: Client, message: Message):
    start = time.time()
    m = await message.reply_text("Pinging...")
    end = time.time()
    await m.edit_text(f"🏓 **Pong!** Latency: `{round((end - start) * 1000, 2)} ms`")

@Client.on_message(filters.command("stats"))
async def stats_command(client: Client, message: Message):
    uptime = int(time.time() - start_time)
    await message.reply_text(f"📊 **KRUTIK CYBER MUSIC BOT Stats**\n• Uptime: `{uptime}s`\n• Developer: `KRUTIK CYBER DEVELOPER`")
  
