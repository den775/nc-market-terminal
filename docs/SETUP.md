# Setup

## Requirements

- Python 3.10+
- Discord bot application and token
- (Optional) Tesseract OCR for `/scan_price`

## Install

```bash
cd nc_market_terminal
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Configure

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Description |
|----------|-------------|
| `DISCORD_TOKEN` | Bot token from Discord Developer Portal |
| `PRICES_CHANNEL_ID` | Channel ID for auto price card |
| `PRICES_ENABLED` | `true` to enable auto card |
| `PRICES_REFRESH_SEC` | Card refresh interval (seconds) |
| `PRICES_JSON_PATH` | Path to `prices.json` (default: project root) |
| `INGAME_PRICES_JSON` | Path to manual in-game prices |
| `USD_BASE` | Base USD for conversion (default: 100) |
| `DEX_TAKER_FEE` | DEX fee for calculations |
| `INGAME_MARKET_FEE` | In-game market fee |
| `DEFAULT_TZ` | Timezone label for footer |

## Discord bot permissions

- Read Messages / View Channel
- Send Messages
- Embed Links
- Manage Messages (for `/prices_refresh`, `/sm`, `/bulkmarket`)

Enable **Message Content Intent** only if you use prefix commands (this project uses slash commands).

## Run

```bash
# Terminal 1
python feeder.py

# Terminal 2
python bot.py
```

## Runtime files (created automatically)

- `prices.json` — written by feeder
- `ingame_prices.json` — manual prices (created on first bot start if missing)
- `data/prices_card_only.json` — card message state

These are gitignored and must not be committed.
