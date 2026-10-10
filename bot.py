import os
import re
import time
import asyncio
import logging
import sqlite3
import shutil
from pathlib import Path
from collections import defaultdict, deque

import yt_dlp

from telegram import (
    Update,
    BotCommand,
    BotCommandScopeChat,
)
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from pyrogram import Client
import pyrogram.errors

if not hasattr(pyrogram.errors, "GroupcallForbidden"):
    pyrogram.errors.GroupcallForbidden = getattr(
        pyrogram.errors,
        "GroupCallForbidden",
        type("GroupcallForbidden", (Exception,), {})
    )
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream


# =========================================================
# KRUTIK CYBER MUSIC BOT
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
API_ID = os.getenv("API_ID", "").strip()
API_HASH = os.getenv("API_HASH", "").strip()
OWNER_ID = os.getenv("OWNER_ID", "").strip()

SESSION_NAME = os.getenv(
    "SESSION_NAME", "krutik_music_user"
)

DATA_DIR = Path(
    os.getenv("DATA_DIR", "./data")
).resolve()

DOWNLOAD_DIR = DATA_DIR / "downloads"
DATABASE = DATA_DIR / "musicbot.db"

BRAND = "KRUTIK CYBER DEVELOPER"

MAX_QUEUE = 20
MAX_PLAYLIST = 15
MAX_DURATION = 3600
REQUEST_COOLDOWN = 5

YOUTUBE_URL = re.compile(
    r"^https?://(www\.)?"
    r"(youtube\.com|youtu\.be|music\.youtube\.com)/",
    re.IGNORECASE,
)

if not BOT_TOKEN:
    raise SystemExit("ERROR: BOT_TOKEN is missing.")

if not API_ID.isdigit() or not API_HASH:
    raise SystemExit("ERROR: API_ID/API_HASH missing.")

if not OWNER_ID.isdigit():
    raise SystemExit("ERROR: OWNER_ID must be numeric.")

OWNER_ID = int(OWNER_ID)
API_ID = int(API_ID)

DATA_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

log = logging.getLogger("krutik_music")


# =========================================================
# DATABASE
# =========================================================

def connect_db():
    con = sqlite3.connect(
        DATABASE,
        timeout=20,
    )
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with connect_db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                chat_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS bans (
                user_id INTEGER PRIMARY KEY
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS tracks (
                video_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                file_path TEXT
            )
        """)

        con.execute("""
            INSERT OR IGNORE INTO settings(key, value)
            VALUES ('bot_enabled', '1')
        """)


def get_setting(key, default=""):
    with connect_db() as con:
        row = con.execute(
            "SELECT value FROM settings WHERE key=?",
            (key,),
        ).fetchone()

    return row["value"] if row else default


def set_setting(key, value):
    with connect_db() as con:
        con.execute("""
            INSERT INTO settings(key, value)
            VALUES (?, ?)
            ON CONFLICT(key)
            DO UPDATE SET value=excluded.value
        """, (key, str(value)))


def add_group_db(chat_id):
    with connect_db() as con:
        con.execute("""
            INSERT INTO groups(chat_id, enabled)
            VALUES (?, 1)
            ON CONFLICT(chat_id)
            DO UPDATE SET enabled=1
        """, (chat_id,))


def remove_group_db(chat_id):
    with connect_db() as con:
        con.execute(
            "DELETE FROM groups WHERE chat_id=?",
            (chat_id,),
        )


def allowed_group(chat_id):
    with connect_db() as con:
        row = con.execute("""
            SELECT enabled FROM groups
            WHERE chat_id=?
        """, (chat_id,)).fetchone()

    return bool(row and row["enabled"] == 1)


def banned_user(user_id):
    with connect_db() as con:
        row = con.execute(
            "SELECT 1 FROM bans WHERE user_id=?",
            (user_id,),
        ).fetchone()

    return row is not None


def bot_enabled():
    return get_setting("bot_enabled", "1") == "1"


# =========================================================
# TELEGRAM USER CLIENT + VOICE ENGINE
# =========================================================

user_client = Client(
    SESSION_NAME,
    api_id=API_ID,
    api_hash=API_HASH,
)

voice = PyTgCalls(user_client)

application = None

# Separate queue and playback state for each group.
queues = defaultdict(deque)
now_playing = {}
play_tasks = {}
group_locks = defaultdict(asyncio.Lock)
last_request = {}


# =========================================================
# COMMON HELPERS
# =========================================================

async def reply(update, text):
    if update.effective_message:
        await update.effective_message.reply_text(
            text,
            disable_web_page_preview=True,
        )


async def check_access(update, owner_only=False):
    user = update.effective_user
    chat = update.effective_chat

    if not user:
        return False

    if banned_user(user.id):
        await reply(update, "⛔ Your access is blocked.")
        return False

    if owner_only and user.id != OWNER_ID:
        await reply(update, "⛔ Owner-only command.")
        return False

    if user.id == OWNER_ID and owner_only:
        return True

    if not chat:
        return False

    if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if not bot_enabled():
            await reply(update, "🔴 Music bot is currently OFF.")
            return False

        if not allowed_group(chat.id):
            await reply(
                update,
                "⛔ This group is not approved by the owner.\n"
                "Ask the bot owner to enable this group.",
            )
            return False

        return True

    await reply(
        update,
        "🎵 Use music commands inside an approved group.",
    )
    return False


def extract_video(url):
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 2,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise ValueError("Could not read this YouTube URL.")

    duration = info.get("duration")

    if duration and duration > MAX_DURATION:
        raise ValueError(
            f"Track is too long. Maximum is {MAX_DURATION // 60} minutes."
        )

    return {
        "id": str(info.get("id", "")),
        "title": info.get("title", "Unknown title"),
        "url": info.get("webpage_url") or url,
        "duration": int(duration or 0),
    }


def extract_playlist(url):
    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "socket_timeout": 20,
        "playlistend": MAX_PLAYLIST,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise ValueError("Could not read this playlist.")

    result = []

    for entry in info.get("entries") or []:
        if not entry:
            continue

        video_id = entry.get("id")
        if not video_id:
            continue

        result.append({
            "id": str(video_id),
            "title": entry.get("title") or "YouTube track",
            "url": (
                entry.get("url")
                if str(entry.get("url", "")).startswith("http")
                else f"https://www.youtube.com/watch?v={video_id}"
            ),
            "duration": int(entry.get("duration") or 0),
        })

    return result[:MAX_PLAYLIST]


def download_track(track):
    video_id = track["id"]

    if not video_id:
        raise ValueError("Invalid YouTube video ID.")

    # Reuse an existing local cached audio file when available.
    with connect_db() as con:
        row = con.execute("""
            SELECT file_path FROM tracks
            WHERE video_id=?
        """, (video_id,)).fetchone()

    if row and row["file_path"]:
        cached = Path(row["file_path"])

        if cached.is_file() and cached.stat().st_size > 0:
            return str(cached)

    options = {
        "format": "bestaudio/best",
        "outtmpl": str(DOWNLOAD_DIR / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 2,
        "fragment_retries": 2,
        "overwrites": False,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(
            track["url"],
            download=True,
        )

        output = Path(
            ydl.prepare_filename(info)
        ).with_suffix(".mp3")

    if not output.is_file():
        candidates = list(
            DOWNLOAD_DIR.glob(f"{video_id}.*")
        )
        candidates = [
            p for p in candidates
            if p.is_file() and p.stat().st_size > 0
        ]

        if not candidates:
            raise RuntimeError("Audio download failed.")

        output = candidates[0]

    with connect_db() as con:
        con.execute("""
            INSERT INTO tracks(video_id, title, file_path)
            VALUES (?, ?, ?)
            ON CONFLICT(video_id)
            DO UPDATE SET
                title=excluded.title,
                file_path=excluded.file_path
        """, (
            video_id,
            track["title"],
            str(output),
        ))

    return str(output)


async def download_track_async(track):
    return await asyncio.to_thread(download_track, track)


async def stop_voice(chat_id):
    try:
        await voice.leave_call(chat_id)
    except Exception as exc:
        log.info(
            "Voice call already stopped or unavailable for %s: %s",
            chat_id,
            exc,
        )


# =========================================================
# PLAYBACK ENGINE
# =========================================================

async def playback_worker(chat_id, context):
    """
    Each group has one worker. Tracks are played sequentially.
    """
    try:
        while (
            queues[chat_id]
            and bot_enabled()
            and allowed_group(chat_id)
        ):
            async with group_locks[chat_id]:
                if not queues[chat_id]:
                    break

                track = queues[chat_id].popleft()
                now_playing[chat_id] = track

            try:
                if not track.get("duration"):
                    info = await asyncio.to_thread(
                        extract_video,
                        track["url"],
                    )
                    track["duration"] = info["duration"]
                    track["title"] = info["title"]

                file_path = await download_track_async(track)

                # PyTgCalls current MediaStream interface.
                # IGNORE prevents the audio file from being treated as video.
                await voice.play(
                    chat_id,
                    MediaStream(
                        file_path,
                        video_flags=MediaStream.Flags.IGNORE,
                    ),
                )

                await context.bot.send_message(
                    chat_id,
                    f"🎶 NOW PLAYING\n\n"
                    f"{track['title']}\n\n"
                    f"Requested by: {track['requested_by']}\n"
                    f"⚡ {BRAND}",
                )

                duration = int(track.get("duration") or 180)

                # Conservative fallback timer. The next track starts after
                # the estimated duration; skip/stop can cancel this worker.
                await asyncio.sleep(max(5, duration) + 2)

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                log.exception(
                    "Playback failed in group %s",
                    chat_id,
                )

                try:
                    await context.bot.send_message(
                        chat_id,
                        "⚠️ Playback failed.\n"
                        f"Details: {str(exc)[:250]}",
                    )
                except Exception:
                    pass

            finally:
                now_playing.pop(chat_id, None)

    except asyncio.CancelledError:
        raise

    finally:
        play_tasks.pop(chat_id, None)


async def ensure_worker(chat_id, context):
    current = play_tasks.get(chat_id)

    if current and not current.done():
        return

    task = asyncio.create_task(
        playback_worker(chat_id, context)
    )
    play_tasks[chat_id] = task


async def enqueue_track(update, context, track):
    chat_id = update.effective_chat.id
    user = update.effective_user

    track["requested_by"] = (
        user.username
        and f"@{user.username}"
        or user.first_name
        or str(user.id)
    )

    if len(queues[chat_id]) >= MAX_QUEUE:
        await reply(
            update,
            f"⛔ Queue full. Maximum {MAX_QUEUE} upcoming tracks.",
        )
        return

    queues[chat_id].append(track)

    await reply(
        update,
        f"✅ Added to queue\n\n"
        f"🎵 {track['title']}\n"
        f"📋 Position: {len(queues[chat_id])}",
    )

    await ensure_worker(chat_id, context)


# =========================================================
# USER COMMANDS
# =========================================================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(
        update,
        "🎧 KRUTIK CYBER MUSIC BOT\n\n"
        "Use this bot in an owner-approved Telegram group.\n\n"
        "/play URL — Play one YouTube track\n"
        "/playlist URL — Queue a playlist\n"
        "/pause — Pause playback\n"
        "/resume — Resume playback\n"
        "/skip — Skip current track\n"
        "/stop — Stop playback\n"
        "/queue — View queue\n"
        "/nowplaying — Current track\n"
        "/clear — Clear upcoming tracks\n"
        "/help — Help\n\n"
        f"⚡ {BRAND}",
    )


async def help_cmd(update, context):
    await start_cmd(update, context)


async def play_cmd(update, context):
    if not await check_access(update):
        return

    if update.effective_chat.type not in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    ):
        await reply(update, "Use /play in an approved group.")
        return

    if not context.args:
        await reply(
            update,
            "Usage:\n/play https://www.youtube.com/watch?v=VIDEO_ID",
        )
        return

    url = context.args[0].strip()

    if not YOUTUBE_URL.match(url):
        await reply(update, "❌ Please provide a YouTube URL.")
        return

    user_id = update.effective_user.id
    now = time.time()

    if now - last_request.get(user_id, 0) < REQUEST_COOLDOWN:
        await reply(update, "⏳ Please wait before requesting again.")
        return

    last_request[user_id] = now

    try:
        track = await asyncio.to_thread(extract_video, url)
        await enqueue_track(update, context, track)

    except Exception as exc:
        log.exception("Could not inspect requested video")
        await reply(
            update,
            f"❌ Could not read video: {str(exc)[:250]}",
        )


async def playlist_cmd(update, context):
    if not await check_access(update):
        return

    if update.effective_chat.type not in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    ):
        await reply(update, "Use /playlist in an approved group.")
        return

    if not context.args:
        await reply(
            update,
            "Usage:\n/playlist https://www.youtube.com/playlist?list=...",
        )
        return

    url = context.args[0].strip()

    if not YOUTUBE_URL.match(url):
        await reply(update, "❌ Please provide a YouTube playlist URL.")
        return

    status = await reply(
        update,
        f"⏳ Reading playlist. Maximum {MAX_PLAYLIST} tracks...",
    )

    try:
        tracks = await asyncio.to_thread(extract_playlist, url)

        if not tracks:
            await status.edit_text("❌ No playable tracks found.")
            return

        chat_id = update.effective_chat.id
        user = update.effective_user

        added = 0

        async with group_locks[chat_id]:
            available = MAX_QUEUE - len(queues[chat_id])

            for track in tracks[:available]:
                track["requested_by"] = (
                    f"@{user.username}"
                    if user.username
                    else user.first_name or str(user.id)
                )
                queues[chat_id].append(track)
                added += 1

        await status.edit_text(
            f"✅ Playlist processed.\n"
            f"Added: {added}\n"
            f"Queue limit: {MAX_QUEUE}",
        )

        await ensure_worker(chat_id, context)

    except Exception as exc:
        log.exception("Playlist processing failed")
        await status.edit_text(
            f"❌ Playlist error: {str(exc)[:250]}"
        )


async def pause_cmd(update, context):
    if not await check_access(update):
        return

    chat_id = update.effective_chat.id

    try:
        await voice.pause(chat_id)
        await reply(update, "⏸️ Playback paused.")
    except Exception as exc:
        await reply(update, f"⚠️ Cannot pause: {str(exc)[:200]}")


async def resume_cmd(update, context):
    if not await check_access(update):
        return

    chat_id = update.effective_chat.id

    try:
        await voice.resume(chat_id)
        await reply(update, "▶️ Playback resumed.")
    except Exception as exc:
        await reply(update, f"⚠️ Cannot resume: {str(exc)[:200]}")


async def skip_cmd(update, context):
    if not await check_access(update):
        return

    chat_id = update.effective_chat.id

    await stop_voice(chat_id)

    task = play_tasks.get(chat_id)
    if task and not task.done():
        task.cancel()

    await asyncio.sleep(0.3)

    await reply(update, "⏭️ Skipping current track.")

    await ensure_worker(chat_id, context)


async def stop_cmd(update, context):
    if not await check_access(update):
        return

    chat_id = update.effective_chat.id

    queues[chat_id].clear()
    await stop_voice(chat_id)

    task = play_tasks.get(chat_id)
    if task and not task.done():
        task.cancel()

    await reply(update, "⏹️ Playback stopped and queue cleared.")


async def queue_cmd(update, context):
    if not await check_access(update):
        return

    chat_id = update.effective_chat.id
    items = list(queues[chat_id])

    if not items:
        await reply(update, "📭 Queue is empty.")
        return

    lines = [
        f"{index}. {track['title']}"
        for index, track in enumerate(items[:15], start=1)
    ]

    await reply(
        update,
        "📋 UPCOMING QUEUE\n\n" + "\n".join(lines),
    )


async def nowplaying_cmd(update, context):
    if not await check_access(update):
        return

    track = now_playing.get(update.effective_chat.id)

    if not track:
        await reply(update, "🎵 Nothing is playing right now.")
        return

    await reply(
        update,
        f"🎶 NOW PLAYING\n\n{track['title']}",
    )


async def clear_cmd(update, context):
    if not await check_access(update):
        return

    queues[update.effective_chat.id].clear()
    await reply(update, "🧹 Upcoming queue cleared.")


# =========================================================
# OWNER COMMANDS
# =========================================================

async def admin_cmd(update, context):
    if not await check_access(update, owner_only=True):
        return

    await reply(
        update,
        "🛡️ KRUTIK MUSIC OWNER PANEL\n\n"
        "/boton — Enable bot globally\n"
        "/botoff — Disable bot globally\n"
        "/addgroup CHAT_ID — Approve a group\n"
        "/removegroup CHAT_ID — Remove a group\n"
        "/ban USER_ID — Block a user\n"
        "/unban USER_ID — Unblock a user\n"
        "/stats — Bot statistics\n"
        "/groups — List approved groups\n\n"
        f"⚡ {BRAND}",
    )


async def boton_cmd(update, context):
    if not await check_access(update, owner_only=True):
        return

    set_setting("bot_enabled", "1")
    await reply(update, "🟢 Bot enabled globally.")


async def botoff_cmd(update, context):
    if not await check_access(update, owner_only=True):
        return

    set_setting("bot_enabled", "0")

    for chat_id, task in list(play_tasks.items()):
        await stop_voice(chat_id)

        if not task.done():
            task.cancel()

    await reply(update, "🔴 Bot disabled globally.")


async def addgroup_cmd(update, context):
    if not await check_access(update, owner_only=True):
        return

    if not context.args:
        await reply(update, "Usage: /addgroup -1001234567890")
        return

    try:
        chat_id = int(context.args[0])
        add_group_db(chat_id)
        await reply(update, f"✅ Approved group: {chat_id}")
    except ValueError:
        await reply(update, "❌ Group ID must be numeric.")


async def removegroup_cmd(update, context):
    if not await check_access(update, owner_only=True):
        return

    if not context.args:
        await reply(update, "Usage: /removegroup -1001234567890")
        return

    try:
        chat_id = int(context.args[0])
        remove_group_db(chat_id)
        queues[chat_id].clear()
        await stop_voice(chat_id)

        task = play_tasks.get(chat_id)
        if task and not task.done():
            task.cancel()

        await reply(update, f"🗑️ Removed group: {chat_id}")

    except ValueError:
        await reply(update, "❌ Group ID must be numeric.")


async def ban_cmd(update, context):
    if not await check_access(update, owner_only=True):
        return

    if not context.args:
        await reply(update, "Usage: /ban USER_ID")
        return

    try:
        user_id = int(context.args[0])

        with connect_db() as con:
            con.execute(
                "INSERT OR IGNORE INTO bans(user_id) VALUES (?)",
                (user_id,),
            )

        await reply(update, f"⛔ User blocked: {user_id}")

    except ValueError:
        await reply(update, "❌ User ID must be numeric.")


async def unban_cmd(update, context):
    if not await check_access(update, owner_only=True):
        return

    if not context.args:
        await reply(update, "Usage: /unban USER_ID")
        return

    try:
        user_id = int(context.args[0])

        with connect_db() as con:
            con.execute(
                "DELETE FROM bans WHERE user_id=?",
                (user_id,),
            )

        await reply(update, f"✅ User unblocked: {user_id}")

    except ValueError:
        await reply(update, "❌ User ID must be numeric.")


async def groups_cmd(update, context):
    if not await check_access(update, owner_only=True):
        return

    with connect_db() as con:
        rows = con.execute("""
            SELECT chat_id FROM groups
            WHERE enabled=1 ORDER BY chat_id
        """).fetchall()

    if not rows:
        await reply(update, "No approved groups.")
        return

    result = "\n".join(
        str(row["chat_id"]) for row in rows[:50]
    )

    await reply(update, "🛡️ APPROVED GROUPS\n\n" + result)


async def stats_cmd(update, context):
    if not await check_access(update, owner_only=True):
        return

    with connect_db() as con:
        groups_count = con.execute(
            "SELECT COUNT(*) FROM groups WHERE enabled=1"
        ).fetchone()[0]

        banned_count = con.execute(
            "SELECT COUNT(*) FROM bans"
        ).fetchone()[0]

    active_count = sum(
        1 for task in play_tasks.values()
        if task and not task.done()
    )

    await reply(
        update,
        "📊 MUSIC BOT STATS\n\n"
        f"Bot enabled: {bot_enabled()}\n"
        f"Approved groups: {groups_count}\n"
        f"Active playback workers: {active_count}\n"
        f"Banned users: {banned_count}\n"
        f"Queue limit per group: {MAX_QUEUE}\n"
        f"Playlist limit: {MAX_PLAYLIST}\n\n"
        f"⚡ {BRAND}",
    )


# =========================================================
# TELEGRAM COMMAND MENU
# =========================================================

async def post_init(application):
    commands = [
        BotCommand("start", "Start music bot"),
        BotCommand("play", "Play a YouTube track"),
        BotCommand("playlist", "Play a YouTube playlist"),
        BotCommand("pause", "Pause playback"),
        BotCommand("resume", "Resume playback"),
        BotCommand("skip", "Skip current track"),
        BotCommand("stop", "Stop playback"),
        BotCommand("queue", "Show queue"),
        BotCommand("nowplaying", "Current track"),
        BotCommand("clear", "Clear upcoming queue"),
        BotCommand("help", "Show help"),
        BotCommand("admin", "Owner panel"),
    ]

    await application.bot.set_my_commands(commands)

    # Owner commands are available in the owner's private menu.
    await application.bot.set_my_commands(
        commands + [
            BotCommand("boton", "Enable bot"),
            BotCommand("botoff", "Disable bot"),
            BotCommand("addgroup", "Approve group"),
            BotCommand("removegroup", "Remove group"),
            BotCommand("ban", "Block user"),
            BotCommand("unban", "Unblock user"),
            BotCommand("groups", "List approved groups"),
            BotCommand("stats", "Bot statistics"),
        ],
        scope=BotCommandScopeChat(chat_id=OWNER_ID),
    )


# =========================================================
# STARTUP AND SHUTDOWN
# =========================================================

async def post_shutdown(application):
    for chat_id in list(play_tasks):
        await stop_voice(chat_id)

    try:
        await voice.stop()
    except Exception:
        log.exception("Error stopping PyTgCalls")

    try:
        await user_client.stop()
    except Exception:
        log.exception("Error stopping Pyrogram client")


def main():
    global application

    init_db()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    handlers = [
        ("start", start_cmd),
        ("help", help_cmd),
        ("play", play_cmd),
        ("playlist", playlist_cmd),
        ("pause", pause_cmd),
        ("resume", resume_cmd),
        ("skip", skip_cmd),
        ("stop", stop_cmd),
        ("queue", queue_cmd),
        ("nowplaying", nowplaying_cmd),
        ("clear", clear_cmd),
        ("admin", admin_cmd),
        ("boton", boton_cmd),
        ("botoff", botoff_cmd),
        ("addgroup", addgroup_cmd),
        ("removegroup", removegroup_cmd),
        ("ban", ban_cmd),
        ("unban", unban_cmd),
        ("groups", groups_cmd),
        ("stats", stats_cmd),
    ]

    for command, callback in handlers:
        application.add_handler(
            CommandHandler(command, callback)
        )

    log.info("Starting Pyrogram user client...")
    user_client.start()

    log.info("Starting PyTgCalls voice engine...")
    voice.start()

    log.info("Starting %s...", "KRUTIK CYBER MUSIC BOT")

    try:
        application.run_polling(
            drop_pending_updates=False,
            allowed_updates=Update.ALL_TYPES,
        )
    finally:
        try:
            voice.stop()
        except Exception:
            pass

        try:
            user_client.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
