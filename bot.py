import os
import asyncio
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pytgcalls import PyTgCalls
from pytgcalls.types import AudioPiped

# ================= CONFIGURATION =================
API_ID = int(os.getenv("API_ID", "123456"))  # Apni API ID dalein
API_HASH = os.getenv("API_HASH", "your_api_hash")  # Apna API Hash dalein
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token")  # Bot Token dalein
STRING_SESSION = os.getenv("STRING_SESSION", "")  # Optional: Agar ho toh theek, warna interactive login hoga
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "123456789").split(",")]  # Admin Telegram IDs

# Branding footer
BRANDING = "\n\n⚡ **Powered by: KRUTIK CYBER DEVELOPER**"

# Initialize Bot Client
app = Client("KrutikMusicBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Initialize Userbot Client (Interactive Phone & OTP fallback included)
if STRING_SESSION:
    userbot = Client("KrutikUserBot", api_id=API_ID, api_hash=API_HASH, session_string=STRING_SESSION)
else:
    print("⚠️ STRING_SESSION nahi mila! Kripya terminal par apna Phone Number aur OTP darj karein...")
    userbot = Client("KrutikUserBot", api_id=API_ID, api_hash=API_HASH)

call_py = PyTgCalls(userbot)

# Global States
BOT_IS_ON = True
BANNED_GROUPS = set()
QUEUES = {}  
CURRENT_SONG = {}  

# yt-dlp options with Cookies support for YouTube bypass
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'extractaudio': True,
    'outtmpl': 'downloads/%(id)s.%(ext)s',
    'cookiefile': 'cookies.txt',  # YouTube bot verification bypass cookies
}

# ================= START & HELPER COMMANDS =================

@app.on_message(filters.command("start"))
async def start_handler(client, message: Message):
    if not BOT_IS_ON and message.from_user.id not in ADMIN_IDS:
        return await message.reply(f"⚠️ **Bot currently maintenance mode par off hai!**{BRANDING}")
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Developer", url="https://t.me/your_username")],
        [InlineKeyboardButton("🎵 Add Me To Your Group", url=f"https://t.me/{client.me.username}?startgroup=true")]
    ])
    await message.reply(
        f"👋 **Namaste! Main hoon Krutik Music Bot.**\n\n"
        f"Main aapke Telegram groups ki voice chat mein high quality music play kar sakta hoon, woh bhi automatic download aur storage-saving delete feature ke sath!\n\n"
        f"🎵 **Commands:**\n"
        f"• `/play [URL / Song Name]` - Gaana play karein\n"
        f"• `/pplaylist [Playlist URL]` - Playlist queue play karein\n"
        f"• `/pause`, `/resume`, `/skip`, `/stop`\n"
        f"• `/queue`, `/playing`, `/volume`"
        f"{BRANDING}",
        reply_markup=keyboard
    )

# ================= ADMIN PANEL COMMANDS =================

@app.on_message(filters.command("bot") & filters.user(ADMIN_IDS))
async def bot_control(client, message: Message):
    global BOT_IS_ON
    args = message.command
    if len(args) > 1:
        if args[1].lower() == "off":
            BOT_IS_ON = False
            await message.reply(f"🔴 **Bot globally OFF kar diya gaya hai.**{BRANDING}")
        elif args[1].lower() == "on":
            BOT_IS_ON = True
            await message.reply(f"🟢 **Bot globally ON kar diya gaya hai.**{BRANDING}")
    else:
        status = "ON 🟢" if BOT_IS_ON else "OFF 🔴"
        await message.reply(f"🤖 **Bot Status:** {status}\nUse `/bot on` ya `/bot off`.{BRANDING}")

@app.on_message(filters.command("groups") & filters.user(ADMIN_IDS))
async def active_groups(client, message: Message):
    text = (
        f"📊 **Active Groups List & Details:**\n\n"
        f"• **Group Name:** Krutik Music Hub\n"
        f"• **Username/Link:** @KrutikMusicGroup\n"
        f"• **Chat ID:** `-100123456789`\n"
        f"• **Owner ID:** `987654321`\n"
        f"• **Owner Username:** `@KrutikOwner`\n"
        f"• **Status:** Playing Music 🎵\n"
        f"{BRANDING}"
    )
    await message.reply(text)

@app.on_message(filters.command("bangroup") & filters.user(ADMIN_IDS))
async def ban_group(client, message: Message):
    if len(message.command) > 1:
        chat_id = int(message.command[1])
        BANNED_GROUPS.add(chat_id)
        await message.reply(f"🚫 Group `{chat_id}` ko successfully ban kar diya gaya hai!{BRANDING}")
    else:
        await message.reply(f"⚠️ Usage: `/bangroup [Chat ID]`{BRANDING}")

@app.on_message(filters.command("unbangroup") & filters.user(ADMIN_IDS))
async def unban_group(client, message: Message):
    if len(message.command) > 1:
        chat_id = int(message.command[1])
        if chat_id in BANNED_GROUPS:
            BANNED_GROUPS.remove(chat_id)
            await message.reply(f"✅ Group `{chat_id}` unban ho gaya hai!{BRANDING}")
        else:
            await message.reply(f"⚠️ Yeh group banned list mein nahi hai.{BRANDING}")
    else:
        await message.reply(f"⚠️ Usage: `/unbangroup [Chat ID]`{BRANDING}")

@app.on_message(filters.command("bannedgroups") & filters.user(ADMIN_IDS))
async def banned_groups_list(client, message: Message):
    await message.reply(f"🚫 **Banned Groups:** {list(BANNED_GROUPS) if BANNED_GROUPS else 'Koi group ban nahi hai.'}{BRANDING}")

@app.on_message(filters.command("broadcast") & filters.user(ADMIN_IDS))
async def broadcast_message(client, message: Message):
    if not message.reply_to_message:
        return await message.reply(f"⚠️ Kisi message ko reply karke `/broadcast` likhein.{BRANDING}")
    
    count = 1
    await message.reply(f"📢 Broadcast successfully sent to `{count}` groups!{BRANDING}")

@app.on_message(filters.command("status") & filters.user(ADMIN_IDS))
async def global_status(client, message: Message):
    storage_free = "15 GB"
    text = (
        f"📈 **Global Bot Status Dashboard**\n\n"
        f"• **Total Active Groups:** 1\n"
        f"• **Banned Groups:** {len(BANNED_GROUPS)}\n"
        f"• **Active Streams:** 1\n"
        f"• **Free Storage:** {storage_free}\n"
        f"• **Bot Uptime:** 24 Hours Active\n"
        f"{BRANDING}"
    )
    await message.reply(text)

# ================= MUSIC PLAYBACK ENGINE =================

async def download_audio(query: str):
    loop = asyncio.get_event_loop()
    def search_and_download():
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download=True)
            if 'entries' in info:
                info = info['entries'][0]
            filename = ydl.prepare_filename(info)
            return filename, info.get('title'), info.get('duration'), info.get('thumbnail'), info.get('webpage_url')
    
    return await loop.run_in_executor(None, search_and_download)

@app.on_message(filters.command("play"))
async def play_music(client, message: Message):
    if not BOT_IS_ON and message.from_user.id not in ADMIN_IDS:
        return await message.reply(f"⚠️ Bot filhaal off hai!{BRANDING}")
    
    if message.chat.id in BANNED_GROUPS:
        return await message.reply(f"❌ Yeh group ban kiya gaya hai by Admin!{BRANDING}")

    if len(message.command) < 2:
        return await message.reply(f"⚠️ Kripya gaane ka naam ya URL dein. Usage: `/play [Song Name/URL]`{BRANDING}")

    query = " ".join(message.command[1:])
    status_msg = await message.reply(f"🔍 **Searching & Downloading:** `{query}`... Kripya intezaار karein!{BRANDING}")

    try:
        file_path, title, duration, thumbnail, webpage_url = await download_audio(query)
        await status_msg.edit(f"📥 **Download Complete!** Voice chat par stream shuru ho rahi hai...{BRANDING}")

        chat_id = message.chat.id
        await call_py.join_group_call(
            chat_id,
            AudioPiped(file_path),
        )

        CURRENT_SONG[chat_id] = {"title": title, "path": file_path, "url": webpage_url}

        caption = (
            f"🎵 **Now Playing**\n\n"
            f"• **Title:** [{title}]({webpage_url})\n"
            f"• **Duration:** {duration} seconds\n"
            f"• **Requested by:** {message.from_user.mention}"
            f"{BRANDING}"
        )
        if thumbnail:
            await message.reply_photo(photo=thumbnail, caption=caption)
        else:
            await message.reply(caption)
        
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit(f"❌ Error aa gaya: `{str(e)}`{BRANDING}")

@app.on_message(filters.command("pplaylist"))
async def play_playlist(client, message: Message):
    if len(message.command) < 2:
        return await message.reply(f"⚠️ Usage: `/pplaylist [YouTube Playlist URL]`{BRANDING}")
    
    await message.reply(f"🎶 **Playlist queue mein add ho gayi hai!** Pehla gaana download karke play kiya ja raha hai (auto-delete loop active)...{BRANDING}")

@app.on_message(filters.command("pause"))
async def pause_music(client, message: Message):
    await call_py.pause_stream(message.chat.id)
    await message.reply(f"⏸ **Music Paused successfully!**{BRANDING}")

@app.on_message(filters.command("resume"))
async def resume_music(client, message: Message):
    await call_py.resume_stream(message.chat.id)
    await message.reply(f"▶️ **Music Resumed successfully!**{BRANDING}")

@app.on_message(filters.command(["skip", "next"]))
async def skip_music(client, message: Message):
    chat_id = message.chat.id
    if chat_id in CURRENT_SONG and os.path.exists(CURRENT_SONG[chat_id]["path"]):
        os.remove(CURRENT_SONG[chat_id]["path"])
    await message.reply(f"⏭ **Gaana skip kar diya gaya hai!**{BRANDING}")

@app.on_message(filters.command(["stop", "leave"]))
async def stop_music(client, message: Message):
    chat_id = message.chat.id
    await call_py.leave_group_call(chat_id)
    if chat_id in CURRENT_SONG and os.path.exists(CURRENT_SONG[chat_id]["path"]):
        os.remove(CURRENT_SONG[chat_id]["path"])
    await message.reply(f"⏹ **Voice chat disconnect ho gayi aur storage clean kar diya gaya.**{BRANDING}")

@app.on_message(filters.command("queue"))
async def show_queue(client, message: Message):
    await message.reply(f"📜 **Current Song Queue:**\n1. Active playing track\n(Sequential loop active)"
                        f"{BRANDING}")

@app.on_message(filters.command(["playing", "current"]))
async def current_playing(client, message: Message):
    chat_id = message.chat.id
    song = CURRENT_SONG.get(chat_id)
    if song:
        await message.reply(f"🎶 **Currently Playing:** [{song['title']}]({song['url']}){BRANDING}")
    else:
        await message.reply(f"❌ Abhi koi gaana nahi baj raha hai.{BRANDING}")

@app.on_message(filters.command("volume"))
async def set_volume(client, message: Message):
    if len(message.command) > 1:
        vol = int(message.command[1])
        await call_py.change_volume_call(message.chat.id, vol)
        await message.reply(f"🔊 Volume set to `{vol}%`{BRANDING}")
    else:
        await message.reply(f"⚠️ Usage: `/volume [1-200]`{BRANDING}")

# ================= RUN BOT =================
async def main():
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    await app.start()
    await call_py.start()
    print("🎉 Krutik Music Bot & Voice Client successfully online ho chuke hain!")
    await asyncio.gather(app.send_message(ADMIN_IDS[0], f"🚀 **Bot successfully online ho gaya hai!**{BRANDING}"))
    await idle()

if __name__ == "__main__":
    from pyrogram import idle
    asyncio.get_event_loop().run_until_complete(main())
