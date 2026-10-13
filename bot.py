import os
import asyncio
from pyrogram import Client, filters, idle
from pytgcalls import PyTgCalls
from pytgcalls.types import AudioPiped
import yt_dlp

# Environment variables se credentials lena
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not API_ID or not API_HASH or not BOT_TOKEN:
    print("❌ Error: API_ID, API_HASH, ya BOT_TOKEN set nahi hain! Pehle 'export' command se set karein.")
    exit(1)

# Bot aur PyTgCalls setup
app = Client(
    "MusicBot",
    api_id=int(API_ID),
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)
call_py = PyTgCalls(app)

def get_audio_url(url):
    """YouTube URL se direct audio streaming link nikalne ke liye"""
    ydl_opts = {'format': 'bestaudio', 'noplaylist': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info['url']

# 1. Single Song Play Command -> /play [YouTube URL]
@app.on_message(filters.command("play") & filters.group)
async def play_song(client, message):
    if len(message.command) < 2:
        await message.reply("❌ Kripya YouTube URL dein!\nUsage: `/play <YouTube_URL>`")
        return
    
    url = message.command[1]
    chat_id = message.chat.id
    
    msg = await message.reply("🎵 Gaana process ho raha hai, kripya intezaar karein...")
    try:
        audio_stream = get_audio_url(url)
        await call_py.join_group_call(
            chat_id,
            AudioPiped(audio_stream)
        )
        await msg.edit("▶️ **Live Stream / Voice Chat mein gaana shuru ho gaya hai!**")
    except Exception as e:
        await msg.edit(f"❌ Error aa gaya: `{e}`")

# 2. Playlist Command (Khas Feature) -> /playlist [YouTube Playlist URL]
@app.on_message(filters.command("playlist") & filters.group)
async def play_playlist(client, message):
    if len(message.command) < 2:
        await message.reply("❌ Kripya YouTube Playlist ka URL dein!\nUsage: `/playlist <Playlist_URL>`")
        return
    
    playlist_url = message.command[1]
    chat_id = message.chat.id
    
    msg = await message.reply("📜 Playlist fetch ki ja rahi hai, thoda waqt lag sakta hai...")
    
    ydl_opts = {
        'extract_flat': True,
        'skip_download': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            playlist_info = ydl.extract_info(playlist_url, download=False)
            
        if 'entries' not in playlist_info:
            await msg.edit("❌ Playlist se gaane fetch nahi ho paye.")
            return
            
        entries = playlist_info['entries']
        await msg.edit(f"✅ Total **{len(entries)}** gaane mil gaye hain! Ek-ek karke play karna shuru kar rahe hain...")
        
        for index, entry in enumerate(entries):
            song_url = entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id')}"
            title = entry.get('title', f"Song {index + 1}")
            
            try:
                audio_stream = get_audio_url(song_url)
                
                try:
                    await call_py.change_stream(chat_id, AudioPiped(audio_stream))
                except:
                    await call_py.join_group_call(chat_id, AudioPiped(audio_stream))
                
                await client.send_message(chat_id, f"🎶 **[Playlist] Abhi baj raha hai:** {title}")
                await asyncio.sleep(30) 
            except Exception as e:
                continue
                
        await client.send_message(chat_id, "✅ Playlist ke sabhi gaane khatam ho gaye hain!")
        
    except Exception as e:
        await msg.edit(f"❌ Playlist load karne mein error aaya: `{e}`")

# 3. Pause Command -> /pause
@app.on_message(filters.command("pause") & filters.group)
async def pause_song(client, message):
    chat_id = message.chat.id
    try:
        await call_py.pause_stream(chat_id)
        await message.reply("⏸️ Music ko **Pause** kar diya gaya hai.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")

# 4. Resume Command -> /resume
@app.on_message(filters.command("resume") & filters.group)
async def resume_song(client, message):
    chat_id = message.chat.id
    try:
        await call_py.resume_stream(chat_id)
        await message.reply("▶️ Music ko **Resume** kar diya gaya hai.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")

# 5. Next Song / Stop Command -> /next ya /stop
@app.on_message(filters.command(["next", "stop", "leave"]) & filters.group)
async def stop_song(client, message):
    chat_id = message.chat.id
    try:
        await call_py.leave_group_call(chat_id)
        await message.reply("⏹️ Stream rok di gayi hai aur bot voice chat se bahar aa gaya hai.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")

# Bot aur PyTgCalls ko run karne ka main function
async def main():
    print("Bot start ho raha hai...")
    await app.start()
    await call_py.start()
    print("🎉 Bot aur Voice Client dono successfully online ho chuke hain!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
