import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
OWNER_ID = int(os.getenv("OWNER_ID", "8221567311"))
SESSION_STRING = os.getenv("SESSION_STRING", "")
STORAGE_CHANNEL_ID = os.getenv("STORAGE_CHANNEL_ID")
if STORAGE_CHANNEL_ID:
    STORAGE_CHANNEL_ID = int(STORAGE_CHANNEL_ID)

DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/musicbot.db")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "./downloads")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs("logs", exist_ok=True)

if not BOT_TOKEN or not API_ID or not API_HASH:
    raise ValueError("CRITICAL ERROR: BOT_TOKEN, API_ID, and API_HASH must be set in environment variables.")
  
