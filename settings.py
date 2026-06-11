"""
Central config for NC Market Terminal.
Paths and .env values. Import first before other project modules.
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---- Paths ----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PRICES_JSON_PATH = os.getenv("PRICES_JSON_PATH", os.path.join(BASE_DIR, "prices.json"))
PRICES_CARD_STATE = os.path.join(DATA_DIR, "prices_card_only.json")
INGAME_PRICES_JSON = os.getenv("INGAME_PRICES_JSON", os.path.join(BASE_DIR, "ingame_prices.json"))

# ---- From .env (Discord bot) ----
TOKEN = os.getenv("DISCORD_TOKEN")
DEFAULT_TZ_NAME = os.getenv("DEFAULT_TZ", "Europe/Moscow")
PRICES_ENABLED = os.getenv("PRICES_ENABLED", "true").lower() in ("1", "true", "on", "yes")
PRICES_CHANNEL_ID = int(os.getenv("PRICES_CHANNEL_ID", "0") or "0")
PRICES_REFRESH_SEC = int(os.getenv("PRICES_REFRESH_SEC", "20") or "20")
PRICES_TITLE = os.getenv("PRICES_TITLE", "Night Crows prices")
USD_BASE = float(os.getenv("USD_BASE", "100"))
DEX_TAKER_FEE = float(os.getenv("DEX_TAKER_FEE", "0.06"))
INGAME_MARKET_FEE = float(os.getenv("INGAME_MARKET_FEE", "0.05"))
