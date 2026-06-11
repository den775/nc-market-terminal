# Commands

All commands are Discord slash commands.

## Public

### `/prices_now [public]`

Show the current price embed. Default: ephemeral (only you). Set `public=true` to post in channel.

### `/market [public]`

Show manual in-game market prices from `ingame_prices.json`.

### `/prices_template`

Show a text template for `/bulkmarket`.

### `/scan_price image:<attachment>`

OCR scan of a Night Crows market list screenshot (beta).

- Recognizes known resources (RU/EN)
- Shows results with item match type and price confidence
- **Save** button stores only `exact` item + `high` price confidence matches

Requires Tesseract with `eng+rus`.

## Officers only (Manage Messages or Administrator)

### `/prices_refresh [force_new]`

Refresh the price card in `PRICES_CHANNEL_ID`.

- `force_new=false` (default): edit existing card
- `force_new=true`: delete old card and post new

### `/sm item:<name> price:<diamonds>`

Update one resource price in `ingame_prices.json`.

Examples: `morion`, `essence`, `ravn`

### `/bulkmarket text:<lines>`

Bulk update in-game prices. Format per line or space-separated:

```
morion 9.5
essence 170
papyrus 0.53
```

## Price card button

**Update prices** — manual refresh (same as `/prices_refresh`, requires Manage Messages).
