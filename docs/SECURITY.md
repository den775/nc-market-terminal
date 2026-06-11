# Security

This project is intended for **public** GitHub. Follow these rules before commit and push.

## Never commit

| File / pattern | Reason |
|----------------|--------|
| `.env`, `*.env` (except `.env.example`) | Discord token, channel IDs |
| `token.txt` | Raw bot token |
| `secrets/`, `credentials.json` | Credentials |
| `prices.json`, `ingame_prices.json` | Runtime data |
| `data/` | Message IDs, channel state, price history |
| `logs/`, `*.db`, `*.sqlite` | Runtime / private data |
| `.venv/`, `__pycache__/` | Local environment |

## Token handling

- `DISCORD_TOKEN` is read via `os.getenv("DISCORD_TOKEN")` in `settings.py`
- No hardcoded tokens in Python source
- If a token was ever committed, **rotate it** in Discord Developer Portal immediately

## Before push checklist

```bash
git ls-files | findstr /i ".env token secrets prices.json data"
```

Should return nothing sensitive.

```bash
git grep -i "MTQ" 
```

Should not find Discord token literals in tracked files.

## Runtime data privacy

`data/prices_card_only.json` contains Discord `message_id` — treat as private runtime state.

`PRICES_CHANNEL_ID` in `.env` identifies your server channel — keep in `.env` only.

## Reporting

If you find a committed secret in a public repo, rotate credentials and force-remove from history before continuing.
