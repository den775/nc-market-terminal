from __future__ import annotations
import os, json, time, asyncio, logging
from typing import Optional
from contextlib import suppress

import discord
from discord.ext import commands
from discord import app_commands

from ocr_scan import CANONICAL_KEYS, scan_image
from formatter import (
    build_conversion_block,
    build_ingame_prices_block,
    build_price_block,
    build_prices_embed,
    conversion_rows,
    fmt_ingame_dia,
    fmt_pair_name,
)
from prices_io import (
    load_ingame_rules,
    load_prices_card_state,
    read_prices_json,
    save_ingame_rules,
    save_prices_card_state,
)
from settings import (
    BASE_DIR,
    DATA_DIR,
    PRICES_JSON_PATH,
    PRICES_CARD_STATE,
    INGAME_PRICES_JSON,
    TOKEN,
    DEFAULT_TZ_NAME,
    PRICES_ENABLED,
    PRICES_CHANNEL_ID,
    PRICES_REFRESH_SEC,
    PRICES_TITLE,
    USD_BASE,
    DEX_TAKER_FEE,
    INGAME_MARKET_FEE,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_INGAME_RULES: dict[str, dict[str, float | int | str]] = {
    "MORION-CROW": {"name": "MORION", "diamonds": 9.5, "multiplier": 10},
    "ESSENCE-CROW": {"name": "ESSENCE", "diamonds": 170.0, "multiplier": 1},
    "ALLOY-CROW": {"name": "ALLOY", "diamonds": 179.0, "multiplier": 1},
    "FEATHER-CROW": {"name": "FEATHER", "diamonds": 1.97, "multiplier": 1},
    "TEAR-CROW": {"name": "TEAR", "diamonds": 7.0, "multiplier": 1},
    "PAPYRUS-CROW": {"name": "PAPYRUS", "diamonds": 0.53, "multiplier": 10},
    "PROMOTE-CROW": {"name": "PROMOTE", "diamonds": 14.0, "multiplier": 1},
    "GEAR-CROW": {"name": "GEAR", "diamonds": 0.28, "multiplier": 1},
    "RAVN-WEMIX": {"name": "RAVN", "diamonds": 185.0, "multiplier": 1},
}

INGAME_RULES = load_ingame_rules(INGAME_PRICES_JSON, DEFAULT_INGAME_RULES)

PAIR_ORDER = [
    "MORION-CROW", "ESSENCE-CROW", "ALLOY-CROW", "FEATHER-CROW",
    "TEAR-CROW", "PAPYRUS-CROW", "PROMOTE-CROW", "GEAR-CROW", "RAVN-WEMIX",
]

ITEM_ALIASES = {
    "morion": "MORION-CROW",
    "essence": "ESSENCE-CROW",
    "alloy": "ALLOY-CROW",
    "feather": "FEATHER-CROW",
    "tear": "TEAR-CROW",
    "papyrus": "PAPYRUS-CROW",
    "promote": "PROMOTE-CROW",
    "gear": "GEAR-CROW",
    "ravn": "RAVN-WEMIX",
    "ravium": "RAVN-WEMIX",
}

PAIR_TO_KEY = {v: k.upper() for k, v in ITEM_ALIASES.items()}
PAIR_TO_KEY["RAVN-WEMIX"] = "RAVN"

def _normalize_item_name(raw: str) -> Optional[str]:
    if not raw:
        return None
    key = str(raw).strip().lower().replace(' ', '').replace('_', '').replace('-', '')
    return ITEM_ALIASES.get(key)

def _set_ingame_diamonds(pair: str, diamonds: float) -> dict[str, float | int | str]:
    cfg = INGAME_RULES.setdefault(pair, {})
    if 'name' not in cfg:
        cfg['name'] = fmt_pair_name(pair)
    if 'multiplier' not in cfg:
        cfg['multiplier'] = 1
    cfg['diamonds'] = float(diamonds)
    save_ingame_rules(INGAME_PRICES_JSON, INGAME_RULES)
    return cfg

def _parse_bulk_lines(raw: str) -> tuple[list[tuple[str, float]], list[str]]:
    updated: list[tuple[str, float]] = []
    errors: list[str] = []

    if not raw:
        return updated, errors

    # превращаем всё в один список токенов
    tokens = raw.replace("\n", " ").replace(",", ".").split()

    if len(tokens) % 2 != 0:
        errors.append("Нечётное количество аргументов: у одного ресурса нет цены.")

    limit = len(tokens) - (len(tokens) % 2)

    pair_index = 1
    for i in range(0, limit, 2):

        item = tokens[i]
        price_raw = tokens[i + 1]

        pair = _normalize_item_name(item)
        if not pair:
            errors.append(f"pair {pair_index}: unknown item `{item}`")
            pair_index += 1
            continue

        try:
            diamonds = float(price_raw)
        except:
            errors.append(f"pair {pair_index}: bad price `{price_raw}`")
            pair_index += 1
            continue

        if diamonds >= 10 and diamonds != int(diamonds):
            errors.append(f"pair {pair_index}: prices >=10 dia must be integer")
            pair_index += 1
            continue

        updated.append((pair, diamonds))
        pair_index += 1

    return updated, errors


intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

PRICE_CARD_LOCKS: dict[int, asyncio.Lock] = {}
PRICE_LAST_UPDATE: dict[int, float] = {}
_price_card_msg_id: Optional[int] = None
_price_prev_map: dict[str, float] = {}

def _price_lock_for(ch_id: int) -> asyncio.Lock:
    PRICE_CARD_LOCKS.setdefault(ch_id, asyncio.Lock())
    return PRICE_CARD_LOCKS[ch_id]

async def _get_price_card_message(ch: discord.TextChannel | discord.Thread) -> discord.Message | None:
    """Get existing price card: first by saved message_id, then by history search."""
    if _price_card_msg_id:
        try:
            msg = await ch.fetch_message(_price_card_msg_id)
            if msg and msg.author and bot.user and msg.author.id == bot.user.id and msg.embeds:
                return msg
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
    msgs: list[discord.Message] = []
    async for m in ch.history(limit=50):
        if m.author and bot.user and m.author.id == bot.user.id and m.embeds:
            title = (m.embeds[0].title or "").strip().lower()
            if "prices" in title or "price" in title:
                msgs.append(m)
    if not msgs:
        return None
    return sorted(msgs, key=lambda m: m.created_at)[-1]

async def upsert_prices_card(ch: discord.TextChannel | discord.Thread, embed: discord.Embed, *, force_new: bool = False):
    now_mono = time.monotonic()
    if now_mono - PRICE_LAST_UPDATE.get(ch.id, 0.0) < 5.0 and not force_new:
        return
    PRICE_LAST_UPDATE[ch.id] = now_mono

    async with _price_lock_for(ch.id):
        keep = await _get_price_card_message(ch)
        if keep and not force_new:
            try:
                await keep.edit(embed=embed, view=PricesRefreshView())
                msg = keep
            except Exception:
                try:
                    await keep.delete()
                except Exception:
                    pass
                msg = await ch.send(embed=embed, view=PricesRefreshView())
        else:
            if keep:
                with suppress(Exception):
                    await keep.delete()
            msg = await ch.send(embed=embed, view=PricesRefreshView())
        global _price_card_msg_id
        _price_card_msg_id = msg.id if msg else None
        save_prices_card_state(PRICES_CARD_STATE, _price_card_msg_id, _price_prev_map)
        return msg

async def refresh_prices_card(ch: discord.TextChannel | discord.Thread, *, force_new: bool = False):
    global _price_prev_map
    data = read_prices_json(PRICES_JSON_PATH)
    if not data:
        embed = discord.Embed(
            title=f"📈 {PRICES_TITLE}",
            description=f"Файл цен пока не найден.\nЗапусти price feeder и проверь путь: `{PRICES_JSON_PATH}`",
            color=0xE67E22,
        )
        embed.set_footer(text=f"waiting for prices.json · Auto-refresh: {PRICES_REFRESH_SEC}s")
        await upsert_prices_card(ch, embed, force_new=force_new)
        return

    rows = data.get("rows") or []
    current_map = {
        str(r.get("pair")): float(r.get("last"))
        for r in rows
        if r.get("pair") and isinstance(r.get("last"), (int, float))
    }
    embed = build_prices_embed(data, _price_prev_map, INGAME_RULES, PAIR_ORDER)
    await upsert_prices_card(ch, embed, force_new=force_new)
    _price_prev_map = current_map
    save_prices_card_state(PRICES_CARD_STATE, _price_card_msg_id, _price_prev_map)

async def safe_defer(inter: discord.Interaction, ephemeral: bool):
    try:
        if not inter.response.is_done():
            await inter.response.defer(ephemeral=ephemeral)
            return True
    except Exception:
        pass
    return False

async def safe_send(inter: discord.Interaction, content=None, **kwargs):
    try:
        if inter.response.is_done():
            return await inter.followup.send(content, **kwargs)
        return await inter.response.send_message(content, **kwargs)
    except Exception:
        return None

def officers_only():
    async def predicate(inter: discord.Interaction) -> bool:
        perms = inter.user.guild_permissions
        allowed = perms.manage_messages or perms.administrator
        if not allowed:
            await safe_send(inter, "❌ Недостаточно прав (нужно Manage Messages).", ephemeral=True)
        return allowed
    return app_commands.check(predicate)



class PricesRefreshView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Update prices",
        style=discord.ButtonStyle.green,
        emoji="🔄",
        custom_id="nc_prices_refresh",
    )
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        perms = interaction.user.guild_permissions
        allowed = perms.manage_messages or perms.administrator

        if not allowed:
            return await safe_send(
                interaction,
                "❌ Недостаточно прав для обновления карточки.",
                ephemeral=True,
            )

        ch = bot.get_channel(PRICES_CHANNEL_ID) if PRICES_CHANNEL_ID else interaction.channel
        if not ch:
            return await safe_send(
                interaction,
                "❌ Канал цен не найден. Проверь PRICES_CHANNEL_ID.",
                ephemeral=True,
            )

        await safe_defer(interaction, ephemeral=True)

        try:
            await refresh_prices_card(ch, force_new=False)
            await safe_send(interaction, "✅ Карточка цен обновлена.", ephemeral=True)
        except Exception as e:
            await safe_send(interaction, f"❌ Ошибка обновления: `{e}`", ephemeral=True)


class ScanSaveView(discord.ui.View):
    """View with Save button for OCR scan results. Saves only exact matches, whitelist items."""

    def __init__(self, results: list[dict], *, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.results = results  # [{canonical_key, price, matched_text, match_type, raw_line}, ...]

    @discord.ui.button(label="Сохранить", style=discord.ButtonStyle.green, emoji="💾", custom_id="scan_save")
    async def save_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        perms = interaction.user.guild_permissions
        if not (perms.manage_messages or perms.administrator):
            return await safe_send(interaction, "❌ Недостаточно прав (нужно Manage Messages).", ephemeral=True)
        if not self.results:
            return await safe_send(interaction, "❌ Нечего сохранять.", ephemeral=True)
        to_save = [
            r for r in self.results
            if r.get("match_type") == "exact"
            and r.get("canonical_key") in CANONICAL_KEYS
            and r.get("price_confidence", "low") == "high"
        ]
        if not to_save:
            return await safe_send(
                interaction,
                "❌ Нет записей для сохранения (нужны exact item + high price confidence). Используйте /sm вручную.",
                ephemeral=True,
            )
        changed: list[str] = []
        for r in to_save:
            canonical = r.get("canonical_key")
            price = r.get("price")
            if canonical is None or price is None:
                continue
            pair = ITEM_ALIASES.get(canonical)
            if not pair:
                continue
            cfg = _set_ingame_diamonds(pair, price)
            changed.append(f"{cfg.get('name', fmt_pair_name(pair))}: {fmt_ingame_dia(price)}")
        ch = bot.get_channel(PRICES_CHANNEL_ID) if PRICES_CHANNEL_ID else interaction.channel
        if ch and changed:
            await refresh_prices_card(ch, force_new=False)
        await safe_send(interaction, "✅ Сохранено:\n" + "\n".join(changed[:15]), ephemeral=True)
        self.stop()


@bot.tree.command(name="prices_now", description="Показать текущие цены Night Crows")
async def prices_now(interaction: discord.Interaction, public: bool = False):
    await safe_defer(interaction, ephemeral=not public)
    data = read_prices_json(PRICES_JSON_PATH)
    if not data:
        return await safe_send(interaction, "Файл цен пока не найден. Сначала запусти price feeder.", ephemeral=not public)
    embed = build_prices_embed(data, _price_prev_map, INGAME_RULES, PAIR_ORDER)
    await safe_send(interaction, embed=embed, ephemeral=not public)

@bot.tree.command(name="prices_refresh", description="Обновить карточку цен Night Crows")
@officers_only()
async def prices_refresh(interaction: discord.Interaction, force_new: bool = False):
    ch = bot.get_channel(PRICES_CHANNEL_ID) if PRICES_CHANNEL_ID else interaction.channel
    if not ch:
        return await safe_send(interaction, "Канал цен не найден. Проверь PRICES_CHANNEL_ID.", ephemeral=True)
    await refresh_prices_card(ch, force_new=force_new)
    await safe_send(interaction, "Карточка цен обновлена.", ephemeral=True)

@bot.tree.command(name="market", description="Показать текущие ручные цены рынка")
async def market(interaction: discord.Interaction, public: bool = False):
    await safe_defer(interaction, ephemeral=not public)
    embed = discord.Embed(title="💎 In-game market prices", color=0x3498DB)
    embed.add_field(name="Current prices", value=build_ingame_prices_block(INGAME_RULES, PAIR_ORDER), inline=False)
    embed.set_footer(text="Use /sm <item> <price> or /bulkmarket to edit")
    await safe_send(interaction, embed=embed, ephemeral=not public)

@bot.tree.command(name="sm", description="Быстро обновить цену одного ресурса в diamonds")
@officers_only()
@app_commands.describe(item="morion / essence / alloy / ...", price="Цена в diamonds")
async def sm(interaction: discord.Interaction, item: str, price: float):
    pair = _normalize_item_name(item)
    if not pair:
        valid = ", ".join(sorted(set(ITEM_ALIASES.keys())))
        return await safe_send(interaction, f"Неизвестный ресурс: `{item}`\nДоступно: `{valid}`", ephemeral=True)
    if price >= 10 and price != int(price):
        return await safe_send(interaction, "❌ Для цен от 10 dia вводи только целое число.", ephemeral=True)
    cfg = _set_ingame_diamonds(pair, price)
    ch = bot.get_channel(PRICES_CHANNEL_ID) if PRICES_CHANNEL_ID else interaction.channel
    if ch:
        await refresh_prices_card(ch, force_new=False)
    name = str(cfg.get('name', fmt_pair_name(pair)))
    mult = int(cfg.get('multiplier', 1))
    await safe_send(interaction, f"✅ {name} updated -> `{fmt_ingame_dia(float(price))}` diamonds", ephemeral=True)

@bot.tree.command(name="bulkmarket", description="Массово обновить цены рынка: каждый ресурс с новой строки")
@officers_only()
@app_commands.describe(text="Например: morion 9.67\nessence 170\npapyrus 0.53")
async def bulkmarket(interaction: discord.Interaction, text: str):
    updates, errors = _parse_bulk_lines(text)
    if not updates and errors:
        return await safe_send(interaction, "❌ Ошибки:\n" + "\n".join(errors[:15]), ephemeral=True)

    changed: list[str] = []
    for pair, diamonds in updates:
        cfg = _set_ingame_diamonds(pair, diamonds)
        changed.append(f"{cfg.get('name', fmt_pair_name(pair))}: {fmt_ingame_dia(diamonds)}")

    ch = bot.get_channel(PRICES_CHANNEL_ID) if PRICES_CHANNEL_ID else interaction.channel
    if ch and changed:
        await refresh_prices_card(ch, force_new=False)

    msg = []
    if changed:
        msg.append("✅ Updated:\n" + "\n".join(changed[:20]))
    if errors:
        msg.append("⚠️ Skipped:\n" + "\n".join(errors[:10]))
    await safe_send(interaction, "\n\n".join(msg) if msg else "Нечего обновлять.", ephemeral=True)

@bot.tree.command(name="scan_price", description="Сканировать скриншот рынка Night Crows (OCR)")
@app_commands.describe(image="Скриншот списка рынка (PNG/JPG)")
async def scan_price(interaction: discord.Interaction, image: discord.Attachment):
    await safe_defer(interaction, ephemeral=False)
    if not image.content_type or not image.content_type.startswith("image/"):
        return await safe_send(interaction, "❌ Прикрепите изображение (PNG, JPG).", ephemeral=True)
    try:
        data = await image.read()
    except Exception as e:
        return await safe_send(interaction, f"❌ Не удалось загрузить файл: {e}", ephemeral=True)
    results = scan_image(data)
    if not results:
        return await safe_send(
            interaction,
            "Ничего не распознано. Проверьте: скрин списка рынка NC, читаемый текст, RU/EN.",
            ephemeral=True,
        )
    lines = []
    for r in results:
        canonical = r.get("canonical_key", "")
        price = r.get("price", 0)
        pair = ITEM_ALIASES.get(canonical)
        name = fmt_pair_name(pair) if pair else canonical
        mt = r.get("match_type", "exact")
        pc = r.get("price_confidence", "low")
        badge = "✓" if (mt == "exact" and pc == "high") else "~"
        lines.append(f"{badge} **{name}** → `{fmt_ingame_dia(price)}` ({mt}/{pc})")
    debug_block = "\n".join(
        f"`{r.get('matched_text', '')}` | {(r.get('raw_line') or '')[:70]}" for r in results[:8]
    )
    embed = discord.Embed(
        title="📷 Результаты сканирования",
        description="\n".join(lines) + "\n\n**Отладка:**\n" + (debug_block or "-") + "\n\n✓ = exact+high (сохранится) | ~ = остальное",
        color=0x9B59B6,
    )
    embed.set_footer(text="Сохраняются только exact item + high price confidence.")
    await safe_send(interaction, embed=embed, view=ScanSaveView(results), ephemeral=False)


@bot.tree.command(name="prices_template", description="Шаблон для /bulkmarket")
async def prices_template(interaction: discord.Interaction):
    lines = []
    for pair in PAIR_ORDER:
        cfg = INGAME_RULES.get(pair, {})
        alias = PAIR_TO_KEY.get(pair, fmt_pair_name(pair))
        dia = float(cfg.get('diamonds', 0.0))
        lines.append(f"{alias.lower()} {dia:g}")
    text = "```\n" + "\n".join(lines) + "\n```"
    await safe_send(interaction, f"Шаблон для `/bulkmarket`:\n{text}", ephemeral=True)

@bot.event
async def on_ready():
    global _price_card_msg_id, _price_prev_map
    logging.info(f"✅ Logged in as {bot.user} | TZ={DEFAULT_TZ_NAME}")
    _price_card_msg_id, _price_prev_map = load_prices_card_state(PRICES_CARD_STATE)
    bot.add_view(PricesRefreshView())

    try:
        await bot.tree.sync()
        logging.info("Slash-команды синхронизированы")
    except Exception:
        logging.exception("Slash sync error")

    async def _tick_prices_card():
        while True:
            try:
                channel = bot.get_channel(PRICES_CHANNEL_ID) if PRICES_CHANNEL_ID else None
                if channel and PRICES_ENABLED:
                    await refresh_prices_card(channel, force_new=False)
            except Exception:
                logging.exception("prices card periodic update failed")
            await asyncio.sleep(PRICES_REFRESH_SEC)

    if PRICES_ENABLED and PRICES_CHANNEL_ID and not hasattr(bot, "_prices_task"):
        bot._prices_task = asyncio.create_task(_tick_prices_card())

    try:
        price_channel = bot.get_channel(PRICES_CHANNEL_ID) if PRICES_CHANNEL_ID else None
        if price_channel and PRICES_ENABLED:
            await refresh_prices_card(price_channel, force_new=True)
    except Exception:
        logging.exception("prices card initial update failed")

async def main():
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN отсутствует в .env")
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
