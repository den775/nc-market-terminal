# NC Market Terminal

Discord-бот и сборщик цен для мониторинга рынка **Night Crows** на PNIX (WEMIX).

## Превью

![Discord price card](assets/discord-price-card.png)

## Обзор

NC Market Terminal собирает цены DEX через WebSocket, записывает общий `prices.json` и показывает в Discord автообновляемую карточку с оценкой конвертации USD → in-game diamonds.

Два процесса:

- **feeder.py** — сбор цен (WebSocket + HTTP)
- **bot.py** — Discord-бот, slash-команды, карточка цен

## Возможности

- WebSocket PNIX (main + season gateways)
- CROW/USD (GeckoTerminal) и WEMIX/USD (биржи)
- Автообновление одной карточки в Discord (edit, без спама)
- Ручные in-game цены (`ingame_prices.json`)
- Оценка конвертации USD → ресурс → diamonds
- Команды: `/prices_now`, `/prices_refresh`, `/market`, `/sm`, `/bulkmarket`, `/scan_price`
- OCR скриншотов рынка (beta, опционально Tesseract)

## Архитектура

```
feeder.py  →  prices.json  →  bot.py  →  Discord
                  ↑
         ingame_prices.json (ручные цены)
```

| Модуль | Назначение |
|--------|------------|
| `feeder.py` | WebSocket, USD refs, запись `prices.json` |
| `bot.py` | Discord-команды, карточка цен |
| `formatter.py` | Оформление embed |
| `prices_io.py` | Чтение/запись JSON |
| `ocr_scan.py` | OCR скриншотов (beta) |
| `settings.py` | Пути и `.env` |

## Команды

| Команда | Описание |
|---------|----------|
| `/prices_now` | Текущие цены |
| `/prices_refresh` | Обновить карточку (officers) |
| `/market` | Ручные in-game цены |
| `/sm` | Одна цена ресурса в diamonds |
| `/bulkmarket` | Массовое обновление цен |
| `/scan_price` | OCR скриншота (beta) |
| `/prices_template` | Шаблон для `/bulkmarket` |

Подробнее: [docs/COMMANDS.md](docs/COMMANDS.md).

## Сбор цен

Feeder подключается к PNIX WebSocket, подписывается на рынки и периодически обновляет CROW/USD и WEMIX/USD. Записывает `prices.json` атомарно.

Подробнее: [docs/PRICE_FEED.md](docs/PRICE_FEED.md).

## Карточка цен в Discord

При `PRICES_ENABLED=true` и заданном `PRICES_CHANNEL_ID` бот держит **одно** сообщение в канале и редактирует его при обновлении.

## OCR сканирования

Опциональная beta-функция на Tesseract. Нужен системный `tesseract-ocr` с языками `eng` и `rus`.

Подробнее: [docs/OCR.md](docs/OCR.md).

## Конфигурация

Скопируйте `.env.example` в `.env`:

```bash
cp .env.example .env
```

Обязательно:

- `DISCORD_TOKEN` — токен Discord-бота
- `PRICES_CHANNEL_ID` — ID канала для карточки (рекомендуется)

Подробнее: [docs/SETUP.md](docs/SETUP.md).

## Локальная установка

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux

pip install -r requirements.txt
cp .env.example .env
# Заполните .env
```

**Tesseract (опционально, для OCR):**

- Windows: [UB Mannheim tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
- Ubuntu: `sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus`

## Запуск

Терминал 1 — feeder:

```bash
python feeder.py
```

Терминал 2 — бот:

```bash
python bot.py
```

Сначала feeder, чтобы появился `prices.json`.

## Структура проекта

```
nc_market_terminal/
├── bot.py
├── feeder.py
├── formatter.py
├── prices_io.py
├── ocr_scan.py
├── settings.py
├── requirements.txt
├── .env.example
├── docs/
├── data/               # runtime (в .gitignore)
├── prices.json         # runtime (в .gitignore)
└── ingame_prices.json  # runtime (в .gitignore)
```

## Безопасность / секреты

**Не коммитить:**

- `.env`, `token.txt`, токены Discord
- `prices.json`, `ingame_prices.json`, `data/` (runtime, ID каналов/сообщений)

Токен читается только через `os.getenv("DISCORD_TOKEN")` в `settings.py`.

Подробнее: [docs/SECURITY.md](docs/SECURITY.md).

## Troubleshooting

| Проблема | Проверить |
|----------|-----------|
| Бот: нет токена | `DISCORD_TOKEN` в `.env` |
| Карточка не обновляется | `PRICES_ENABLED`, `PRICES_CHANNEL_ID`, feeder запущен |
| Пустые цены | `feeder.py`, путь `PRICES_JSON_PATH` |
| OCR не работает | Tesseract, языки eng+rus |
| Спам сообщений | состояние в `data/`; бот должен edit одно сообщение |

## Лицензия

MIT — см. [LICENSE](LICENSE). Copyright (c) 2026 den775.
