import os
import asyncio
import yt_dlp
from config import DOWNLOAD_DIR

ytdl_opts = {
    'format': 'bestaudio/best',
    'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
    'geo_bypass': True,
    'nocheckcertificate': True,
    'quiet': True,
    'no_warnings': True,
}

ytdl = yt_dlp.YoutubeDL(ytdl_opts)

async def extract_audio_info(query: str):
    loop = asyncio.get_running_loop()
    def extract():
        search_query = f"ytsearch:{query}" if not query.startswith("http") else query
        info = ytdl.extract_info(search_query, download=False)
        if 'entries' in info:
            if not info['entries']:
                return None
            info = info['entries'][0]
        return {
            'title': info.get('title', 'Unknown Title'),
            'url': info.get('webpage_url') or query,
            'duration': info.get('duration'),
        }
    try:
        return await loop.run_in_executor(None, extract)
    except Exception:
        return None

async def download_audio(url: str):
    loop = asyncio.get_running_loop()
    def download():
        info = ytdl.extract_info(url, download=True)
        if 'entries' in info:
            info = info['entries'][0]
        filename = ytdl.prepare_filename(info)
        return filename, info.get('title', 'Unknown'), info.get('duration', 0)
    try:
        return await loop.run_in_executor(None, download)
    except Exception:
        return None, None, None
      
