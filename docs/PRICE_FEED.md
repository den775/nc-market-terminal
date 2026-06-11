# Price Feed

## Overview

`feeder.py` collects Night Crows DEX prices and writes `prices.json`.

## Data sources

### WebSocket (PNIX)

| Gateway | URL | Pairs |
|---------|-----|-------|
| Main | `wss://proddex-crow-agw.azure-api.net/` | MORION-CROW … GEAR-CROW |
| Season | `wss://proddex-crow-season-agw.azure-api.net/` | RAVN-WEMIX |

Subscriptions: `snapshot` and `latestMeasureV2` per market address.

### HTTP references

- **CROW/USD** — GeckoTerminal WEMIX pool
- **WEMIX/USD** — CryptoCompare, OKX, Bybit, KuCoin, Gate.io, CoinGecko (fallback)

## Output format (`prices.json`)

```json
{
  "ts": 1710000000,
  "crow_usd": 0.082,
  "wemix_usd": 1.45,
  "rows": [
    { "pair": "MORION-CROW", "last": 0.34, "usd": 0.0279 }
  ]
}
```

Written atomically via `prices.json.tmp` + rename every ~20 seconds.

## Configuration

- `PRICES_JSON_PATH` in `.env` — output path (default: `prices.json` in project root)
- Market addresses are defined in `feeder.py` (`MANUAL_MARKETS`)

## Running

```bash
python feeder.py
```

Keep running while the Discord bot is active.
