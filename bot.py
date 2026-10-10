import os
import re
import asyncio
import logging
import tempfile
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlparse

from pyrogram import Client
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ==========================================
# KRUTIK CYBER MUSIC BOT
# KRUTIK CYBER DEVELOPER
# ==========================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
API_ID = os.getenv("API_ID", "").strip()
API_HASH = os.getenv("API_HASH", "").strip()
OWNER_ID = os.getenv("OWNER_ID", "").strip()

SESSION_NAME = os.getenv("SESSION_NAME", "krutik_music_user")
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

MAX_QUEUE = 15
MAX_PLAYLIST = 10
MAX_DURATION = 60 * 20

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("KRUTIK-MUSIC")

if not BOT_TOKEN or not API_ID or not API_HASH:
    raise SystemExit(
        "Missing BOT_TOKEN, API_ID, or API_HASH environment variables."
    )

try:
    API_ID = int(API_ID)
    OWNER_ID = int(OWNER_ID) if OWNER_ID else 0
except ValueError:
    raise SystemExit("API_ID and OWNER_ID must be numeric.")

# User MTProto client: required for voice-chat playback.
user_client = Client(
    SESSION_NAME,
    api_id=API_ID,
    api_hash=API_HASH,
)

calls = PyTgCalls(user_client)

# Telegram bot state
queues = defaultdict(deque)
current = {}
paused = set()
bot_enabled = True
allowed_groups = set()
banned_users = set()
temporary_files = defaultdict(set)
locks = defaultdict(asyncio.Lock)


def is_owner(update: Update) -> bool:
    return bool(
        update.effective_user
        and update.effective_user.id == OWNER_ID
        and OWNER_ID != 0
    )


def group_id_of(update: Update):
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        return None
    return chat.id


async def allowed(update: Update) -> bool:
    if not bot_enabled and not is_owner(update):
        if update.effective_message:
            await update.effective_message.reply_text(
                "⛔ Music bot is temporarily disabled."
            )
        return False

    user = update.effective_user
    if user and user.id in banned_users and not is_owner(update):
        await update.effective_message.reply_text(
            "⛔ You are not allowed to use this bot."
        )
        return False

    gid = group_id_of(update)
    if gid is None:
        await update.effective_message.reply_text(
            "❌ Use this command in a Telegram group."
        )
        return False

    if allowed_groups and gid not in allowed_groups and not is_owner(update):
        await update.effective_message.reply_text(
            "⛔ This group is not approved."
        )
        return False

    return True


def valid_youtube_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        return (
            parsed.scheme in ("http", "https")
            and (
                host == "youtu.be"
                or host == "youtube.com"
                or host.endswith(".youtube.com")
                or host == "youtube-nocookie.com"
                or host.endswith(".youtube-nocookie.com")
            )
        )
    except Exception:
        return False


async def get_video_info(url: str) -> dict:
    def run():
        import yt_dlp

        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "extract_flat": False,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    return await asyncio.to_thread(run)


async def download_audio(url: str) -> str:
    def run():
        import yt_dlp

        output_template = str(
            DOWNLOAD_DIR / "%(id)s_%(epoch)s.%(ext)s"
        )
        opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "retries": 2,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            mp3_path = str(Path(filename).with_suffix(".mp3"))

            if not Path(mp3_path).exists():
                raise FileNotFoundError("Downloaded audio file not found.")

            return mp3_path

    return await asyncio.to_thread(run)


async def start_track(chat_id: int, track: dict):
    path = await download_audio(track["url"])

    try:
        await calls.play(
            chat_id,
            MediaStream(path),
        )
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise

    current[chat_id] = {
        **track,
        "path": path,
    }
    temporary_files[chat_id].add(path)
    paused.discard(chat_id)


async def play_next(chat_id: int):
    async with locks[chat_id]:
        while queues[chat_id]:
            track = queues[chat_id].popleft()

            try:
                await start_track(chat_id, track)
                return track
            except Exception as exc:
                log.exception("Playback failed: %s", exc)
                try:
                    os.remove(current.get(chat_id, {}).get("path", ""))
                except OSError:
                    pass

        current.pop(chat_id, None)
        return None


async def clean_track(chat_id: int):
    track = current.pop(chat_id, None)
    if not track:
        return

    path = track.get("path")
    if path:
        temporary_files[chat_id].discard(path)
        try:
            os.remove(path)
        except OSError:
            pass


async def start_voice_call(chat_id: int):
    # The group voice chat must already be active.
    # PyTgCalls joins an existing voice chat through play().
    return


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "🎵 KRUTIK CYBER MUSIC BOT\n"
        "👨‍💻 KRUTIK CYBER DEVELOPER\n\n"
        "Commands:\n"
        "/play <YouTube URL>\n"
        "/playlist <YouTube playlist URL>\n"
        "/pause\n"
        "/resume\n"
        "/skip\n"
        "/stop\n"
        "/queue\n"
        "/nowplaying\n"
        "/clear\n"
        "/help"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


async def cmd_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return

    gid = group_id_of(update)
    if not context.args:
        await update.effective_message.reply_text(
            "Usage: /play <YouTube URL>"
        )
        return

    url = context.args[0].strip()
    if not valid_youtube_url(url):
        await update.effective_message.reply_text(
            "❌ Please provide a valid YouTube URL."
        )
        return

    msg = await update.effective_message.reply_text(
        "🔎 Fetching track information..."
    )

    try:
        info = await get_video_info(url)
        duration = int(info.get("duration") or 0)

        if duration > MAX_DURATION:
            await msg.edit_text(
                "❌ Track is longer than the 20-minute limit."
            )
            return

        track = {
            "title": str(info.get("title") or "Unknown title"),
            "url": url,
            "duration": duration,
            "requester": update.effective_user.full_name,
        }

        if current.get(gid):
            if len(queues[gid]) >= MAX_QUEUE:
                await msg.edit_text("❌ Queue is full.")
                return

            queues[gid].append(track)
            await msg.edit_text(
                f"➕ Added to queue: {track['title']}\n"
                f"Position: {len(queues[gid])}"
            )
            return

        await msg.edit_text("⬇️ Downloading audio...")
        await start_track(gid, track)
        await msg.edit_text(
            f"🎶 Now playing: {track['title']}\n"
            f"Requested by: {track['requester']}"
        )

    except Exception as exc:
        log.exception("Play command failed")
        await msg.edit_text(
            "❌ Could not start playback.\n"
            "Make sure the group voice chat is active and "
            "the user session is authorized.\n"
            f"Error: {str(exc)[:250]}"
        )


async def cmd_playlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return

    gid = group_id_of(update)
    if not context.args:
        await update.effective_message.reply_text(
            "Usage: /playlist <YouTube playlist URL>"
        )
        return

    url = context.args[0].strip()
    if not valid_youtube_url(url):
        await update.effective_message.reply_text(
            "❌ Please provide a valid YouTube playlist URL."
        )
        return

    msg = await update.effective_message.reply_text(
        "🔎 Loading playlist..."
    )

    def extract_playlist():
        import yt_dlp

        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlistend": MAX_PLAYLIST,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        data = await asyncio.to_thread(extract_playlist)
        entries = data.get("entries") or []

        added = 0
        for item in entries[:MAX_PLAYLIST]:
            video_url = item.get("url") or item.get("webpage_url")
            if not video_url:
                continue

            if not str(video_url).startswith("http"):
                video_url = f"https://www.youtube.com/watch?v={video_url}"

            if len(queues[gid]) >= MAX_QUEUE:
                break

            queues[gid].append({
                "title": str(item.get("title") or "Playlist track"),
                "url": video_url,
                "duration": int(item.get("duration") or 0),
                "requester": update.effective_user.full_name,
            })
            added += 1

        if not current.get(gid) and queues[gid]:
            await play_next(gid)

        await msg.edit_text(
            f"✅ Added {added} playlist tracks to the queue."
        )

    except Exception as exc:
        log.exception("Playlist failed")
        await msg.edit_text(
            f"❌ Could not load playlist: {str(exc)[:200]}"
        )


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return

    gid = group_id_of(update)
    try:
        await calls.pause(gid)
        paused.add(gid)
        await update.effective_message.reply_text("⏸️ Playback paused.")
    except Exception as exc:
        await update.effective_message.reply_text(
            f"❌ Pause failed: {str(exc)[:200]}"
        )


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return

    gid = group_id_of(update)
    try:
        await calls.resume(gid)
        paused.discard(gid)
        await update.effective_message.reply_text("▶️ Playback resumed.")
    except Exception as exc:
        await update.effective_message.reply_text(
            f"❌ Resume failed: {str(exc)[:200]}"
        )


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return

    gid = group_id_of(update)

    try:
        await calls.leave_call(gid)
    except Exception:
        pass

    await clean_track(gid)
    track = await play_next(gid)

    if track:
        await update.effective_message.reply_text(
            f"⏭️ Skipped. Now playing: {track['title']}"
        )
    else:
        await update.effective_message.reply_text(
            "⏹️ Queue is empty."
        )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return

    gid = group_id_of(update)

    queues[gid].clear()
    try:
        await calls.leave_call(gid)
    except Exception:
        pass

    await clean_track(gid)
    paused.discard(gid)

    await update.effective_message.reply_text("⏹️ Playback stopped.")


async def cmd_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return

    gid = group_id_of(update)
    lines = []

    if gid in current:
        lines.append(f"🎶 Now: {current[gid]['title']}")

    for index, track in enumerate(list(queues[gid])[:10], start=1):
        lines.append(f"{index}. {track['title']}")

    await update.effective_message.reply_text(
        "\n".join(lines) if lines else "📭 Queue is empty."
    )


async def cmd_nowplaying(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await allowed(update):
        return

    gid = group_id_of(update)
    track = current.get(gid)

    if not track:
        await update.effective_message.reply_text(
            "Nothing is playing right now."
        )
        return

    await update.effective_message.reply_text(
        f"🎶 Now playing: {track['title']}\n"
        f"Requested by: {track['requester']}"
    )


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return

    gid = group_id_of(update)
    queues[gid].clear()
    await update.effective_message.reply_text("🧹 Queue cleared.")


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        await update.effective_message.reply_text(
            "⛔ Owner only."
        )
        return

    await update.effective_message.reply_text(
        "🛡️ KRUTIK CYBER MUSIC ADMIN\n\n"
        "/boton — Enable bot\n"
        "/botoff — Disable bot\n"
        "/approve <group_id> — Approve group\n"
        "/unapprove <group_id> — Remove group\n"
        "/ban <user_id> — Ban user\n"
        "/unban <user_id> — Unban user\n"
        "/stats — Show statistics"
    )


async def cmd_boton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_enabled

    if not is_owner(update):
        return

    bot_enabled = True
    await update.effective_message.reply_text("✅ Bot enabled.")


async def cmd_botoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_enabled

    if not is_owner(update):
        return

    bot_enabled = False
    await update.effective_message.reply_text("⛔ Bot disabled for users.")


async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Usage: /approve <group_id>"
        )
        return

    try:
        gid = int(context.args[0])
        allowed_groups.add(gid)
        await update.effective_message.reply_text(
            f"✅ Approved group {gid}"
        )
    except ValueError:
        await update.effective_message.reply_text("Invalid group ID.")


async def cmd_unapprove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Usage: /unapprove <group_id>"
        )
        return

    try:
        gid = int(context.args[0])
        allowed_groups.discard(gid)
        await update.effective_message.reply_text(
            f"Removed group {gid} from approvals."
        )
    except ValueError:
        await update.effective_message.reply_text("Invalid group ID.")


async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Usage: /ban <user_id>"
        )
        return

    try:
        uid = int(context.args[0])
        banned_users.add(uid)
        await update.effective_message.reply_text(f"🚫 Banned user {uid}")
    except ValueError:
        await update.effective_message.reply_text("Invalid user ID.")


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Usage: /unban <user_id>"
        )
        return

    try:
        uid = int(context.args[0])
        banned_users.discard(uid)
        await update.effective_message.reply_text(
            f"✅ Unbanned user {uid}"
        )
    except ValueError:
        await update.effective_message.reply_text("Invalid user ID.")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    active = sum(1 for item in current.values() if item)
    queued = sum(len(queue) for queue in queues.values())

    await update.effective_message.reply_text(
        f"🛡️ Bot enabled: {bot_enabled}\n"
        f"Approved groups: {len(allowed_groups)}\n"
        f"Banned users: {len(banned_users)}\n"
        f"Active playback records: {active}\n"
        f"Queued tracks: {queued}"
    )


async def post_init(application: Application):
    commands = [
        BotCommand("start", "Start bot"),
        BotCommand("play", "Play a YouTube track"),
        BotCommand("playlist", "Queue playlist tracks"),
        BotCommand("pause", "Pause playback"),
        BotCommand("resume", "Resume playback"),
        BotCommand("skip", "Skip current track"),
        BotCommand("stop", "Stop playback"),
        BotCommand("queue", "Show queue"),
        BotCommand("nowplaying", "Current track"),
        BotCommand("clear", "Clear queue"),
        BotCommand("help", "Show commands"),
        BotCommand("admin", "Owner admin panel"),
    ]
    await application.bot.set_my_commands(commands)


async def post_shutdown(application: Application):
    for gid in list(current.keys()):
        try:
            await calls.leave_call(gid)
        except Exception:
            pass

        await clean_track(gid)

    try:
        await calls.stop()
    except Exception:
        pass

    try:
        await user_client.stop()
    except Exception:
        pass


def main():
    async def run_bot():
        await user_client.start()
        await calls.start()

        application = (
            Application.builder()
            .token(BOT_TOKEN)
            .post_init(post_init)
            .post_shutdown(post_shutdown)
            .build()
        )

        handlers = [
            ("start", cmd_start),
            ("help", cmd_help),
            ("play", cmd_play),
            ("playlist", cmd_playlist),
            ("pause", cmd_pause),
            ("resume", cmd_resume),
            ("skip", cmd_skip),
            ("stop", cmd_stop),
            ("queue", cmd_queue),
            ("nowplaying", cmd_nowplaying),
            ("clear", cmd_clear),
            ("admin", cmd_admin),
            ("boton", cmd_boton),
            ("botoff", cmd_botoff),
            ("approve", cmd_approve),
            ("unapprove", cmd_unapprove),
            ("ban", cmd_ban),
            ("unban", cmd_unban),
            ("stats", cmd_stats),
        ]

        for command, callback in handlers:
            application.add_handler(CommandHandler(command, callback))

        log.info("KRUTIK CYBER MUSIC BOT starting...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling()

        try:
            await asyncio.Event().wait()
        finally:
            await application.updater.stop()
            await application.stop()
            await application.shutdown()

    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
