from pyrogram import Client, filters
from pyrogram.types import Message
from database import is_user_banned, get_setting
from services.music import extract_audio_info, download_audio
from services.queue import queue_manager, QueueItem
from pytgcalls import PyTgCalls
from pytgcalls.types import AudioPiped

current_playing = {}

def setup_playback_handlers(pytgcalls_client: PyTgCalls):
    @Client.on_message(filters.command("play") & filters.group)
    async def play_command(client: Client, message: Message):
        chat_id = message.chat.id
        if await is_user_banned(message.from_user.id):
            return

        if await get_setting("maintenance") == "true":
            await message.reply_text("⚠️ Bot is under maintenance.")
            return

        if len(message.command) < 2:
            await message.reply_text("❌ Provide a song name or YouTube URL!\nExample: `/play Faded`")
            return

        query = " ".join(message.command[1:])
        status_msg = await message.reply_text("🔍 Processing track...")

        info = await extract_audio_info(query)
        if not info:
            await status_msg.edit_text("❌ Failed to fetch track information.")
            return

        filepath, title, duration = await download_audio(info['url'])
        if not filepath:
            await status_msg.edit_text("❌ Download failed.")
            return

        item = QueueItem(title=title, url=info['url'], duration=duration, user_name=message.from_user.first_name, user_id=message.from_user.id, file_path=filepath)

        queue = await queue_manager.get_queue(chat_id)
        if not queue and chat_id not in current_playing:
            await queue_manager.add_item(chat_id, item)
            next_item = await queue_manager.get_next(chat_id)
            current_playing[chat_id] = next_item
            try:
                await pytgcalls_client.join_group_call(chat_id, AudioPiped(next_item.file_path))
                await status_msg.edit_text(f"🎵 **Playing:** `{next_item.title}`")
            except Exception:
                await status_msg.edit_text("❌ Failed to join voice chat. Make sure it's active.")
                current_playing.pop(chat_id, None)
        else:
            await queue_manager.add_item(chat_id, item)
            await status_msg.edit_text(f"➕ **Added to Queue:** `{item.title}`")

    @Client.on_message(filters.command("skip") & filters.group)
    async def skip_command(client: Client, message: Message):
        chat_id = message.chat.id
        if chat_id not in current_playing:
            await message.reply_text("❌ Nothing playing.")
            return
        next_item = await queue_manager.get_next(chat_id)
        if next_item:
            current_playing[chat_id] = next_item
            await pytgcalls_client.change_stream(chat_id, AudioPiped(next_item.file_path))
            await message.reply_text(f"⏭ **Now Playing:** `{next_item.title}`")
        else:
            current_playing.pop(chat_id, None)
            try:
                await pytgcalls_client.leave_group_call(chat_id)
            except:
                pass
            await message.reply_text("⏭ Queue empty, left voice chat.")

    @Client.on_message(filters.command("stop") & filters.group)
    async def stop_command(client: Client, message: Message):
        chat_id = message.chat.id
        current_playing.pop(chat_id, None)
        await queue_manager.clear_queue(chat_id)
        try:
            await pytgcalls_client.leave_group_call(chat_id)
        except:
            pass
        await message.reply_text("⏹ Stopped playback.")
      
