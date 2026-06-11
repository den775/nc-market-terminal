"""
Formatting and calculation helpers for NC Market Terminal.
Pure functions for prices display, conversion blocks, embeds.
"""
import datetime as dt
import time
from typing import Any, Optional

import discord
import pytz

from settings import (
    DEFAULT_TZ_NAME,
    DEX_TAKER_FEE,
    INGAME_MARKET_FEE,
    PRICES_REFRESH_SEC,
    PRICES_TITLE,
    USD_BASE,
)

RESOURCE_EMOJI = {
    "MORION": "<:mori:1479350148218884096>",
    "ESSENCE": "<:essence:1479449812284866764>",
    "ALLOY": "<:alloy:1479450181656248410>",
    "FEATHER": "<:feather:1479450459977678990>",
    "TEAR": "<:tear:1479450598024679485>",
    "PAPYRUS": "<:papyrus:1479450709064814622>",
    "PROMOTE": "<:promote:1479450798827241482>",
    "GEAR": "<:gear:1479450884554625055>",
    "RAVN": "<:ravn:1479450951042465984>",
}

RANK_MARKER_TOP = "🟩"
RANK_MARKER_MID = "🟨"
RANK_MARKER_LOW = "🟥"

WANTED_CROW = [
    "MORION-CROW", "ESSENCE-CROW", "ALLOY-CROW", "FEATHER-CROW",
    "TEAR-CROW", "PAPYRUS-CROW", "PROMOTE-CROW", "GEAR-CROW",
]
WANTED_SEASON = ["RAVN-WEMIX"]


def _tz_from_name(name: str) -> dt.tzinfo:
    try:
        return pytz.timezone(name)
    except Exception:
        if name.lower() == "europe/kyiv":
            return pytz.timezone("Europe/Kiev")
        return pytz.timezone("Etc/GMT-3")


def safe_float(v: Any) -> Optional[float]:
    try:
        if isinstance(v, (int, float)):
            return float(v)
    except Exception:
        pass
    return None


def fmt_pair_name(pair: str) -> str:
    return pair.replace("-CROW", "").replace("-WEMIX", "")


def fmt_ingame_dia(dia: float) -> str:
    if dia >= 10:
        return f"{int(round(dia))}"
    return f"{dia:.2f}".rstrip("0").rstrip(".")


def price_arrow(curr: object, prev: object) -> str:
    if not isinstance(curr, (int, float)) or not isinstance(prev, (int, float)):
        return "•"
    if curr > prev:
        return "↗"
    if curr < prev:
        return "↘"
    return "→"


def emoji_for_name(name: str) -> str:
    return RESOURCE_EMOJI.get(str(name).upper(), "•")


def rank_marker(index: int, total: int) -> str:
    if total <= 1:
        return RANK_MARKER_TOP
    if index < max(1, total // 3):
        return RANK_MARKER_TOP
    if index < max(2, (total * 2) // 3):
        return RANK_MARKER_MID
    return RANK_MARKER_LOW


def price_age_text(ts: int | float | None) -> str:
    if not ts:
        return "no timestamp"
    age = int(time.time() - int(ts))
    if age < 60:
        return f"{age}s ago"
    if age < 3600:
        return f"{age // 60}m ago"
    return f"{age // 3600}h ago"


def fmt_time_local(ts: int | float | None, tz_name: str = DEFAULT_TZ_NAME) -> str:
    if not ts:
        return "unknown"
    try:
        tz = _tz_from_name(tz_name)
        dtobj = dt.datetime.fromtimestamp(int(ts), tz=tz)
        zone = getattr(tz, "zone", tz_name)
        label = "MSK" if zone == "Europe/Moscow" else (tz.tzname(dtobj) or zone)
        return dtobj.strftime("%H:%M") + f" {label}"
    except Exception:
        return "unknown"


def build_price_block(
    pairs: list[str],
    by_pair: dict,
    prev_map: dict[str, float],
    quote_label: str,
) -> str:
    lines: list[str] = [f"{'PAIR':<10} {quote_label:>7}   {'USD':>8}", "-" * 32]
    for pair in pairs:
        r = by_pair.get(pair)
        if not r:
            continue
        last = r.get("last")
        usd = r.get("usd")
        last_s = f"{float(last):.4f}" if isinstance(last, (int, float)) else "None"
        usd_s = f"${float(usd):.4f}" if isinstance(usd, (int, float)) else "None"
        short = fmt_pair_name(pair)
        arrow = price_arrow(last, prev_map.get(pair))
        lines.append(f"{arrow} {short:<8} {last_s:>7}   {usd_s:>8}")
    if len(lines) == 2:
        lines.append("No data yet.")
    return "```\n" + "\n".join(lines) + "\n```"


def conversion_rows(
    data: dict,
    ingame_rules: dict[str, dict[str, float | int | str]],
    usd_base: float = USD_BASE,
    dex_fee: float = DEX_TAKER_FEE,
    market_fee: float = INGAME_MARKET_FEE,
) -> list[dict[str, float | str | int]]:
    rows = data.get("rows") or []
    by_pair = {str(r.get("pair")): r for r in rows if r.get("pair")}
    crow_usd = safe_float(data.get("crow_usd"))
    wemix_usd = safe_float(data.get("wemix_usd"))
    result: list[dict[str, float | str | int]] = []
    if not crow_usd or crow_usd <= 0:
        return result

    crow_amount = usd_base / crow_usd
    for pair, cfg in ingame_rules.items():
        if pair == "RAVN-WEMIX":
            continue
        short = str(cfg.get("name", fmt_pair_name(pair)))
        ingame_price = float(cfg.get("diamonds", 0.0))
        multiplier = int(cfg.get("multiplier", 1))
        row = by_pair.get(pair)
        last = safe_float(row.get("last")) if row else None
        if not last or last <= 0:
            continue
        token_amount = crow_amount / (last * (1.0 + dex_fee))
        ingame_amount = token_amount * multiplier
        diamonds = ingame_amount * ingame_price * (1.0 - market_fee)
        result.append({"name": short, "diamonds": diamonds, "pair": pair, "multiplier": multiplier})

    ravn_row = by_pair.get("RAVN-WEMIX")
    ravn_last = safe_float(ravn_row.get("last")) if ravn_row else None
    if ravn_last and ravn_last > 0 and wemix_usd and wemix_usd > 0:
        wemix_amount = usd_base / wemix_usd
        ravn_amount = wemix_amount / (ravn_last * (1.0 + dex_fee))
        ravn_cfg = ingame_rules.get("RAVN-WEMIX", {})
        ravn_name = str(ravn_cfg.get("name", "RAVN"))
        ravn_ingame = float(ravn_cfg.get("diamonds", 185.0))
        ravn_mult = int(ravn_cfg.get("multiplier", 1))
        ravn_diamonds = ravn_amount * ravn_mult * ravn_ingame * (1.0 - market_fee)
        result.append({"name": ravn_name, "diamonds": ravn_diamonds, "pair": "RAVN-WEMIX", "multiplier": ravn_mult})

    result.sort(key=lambda x: float(x["diamonds"]), reverse=True)
    return result


def build_conversion_block(
    data: dict,
    ingame_rules: dict[str, dict[str, float | int | str]],
    usd_base: float = USD_BASE,
    dex_fee: float = DEX_TAKER_FEE,
    market_fee: float = INGAME_MARKET_FEE,
) -> str:
    crow_usd = safe_float(data.get("crow_usd"))
    wemix_usd = safe_float(data.get("wemix_usd"))
    if not crow_usd or crow_usd <= 0:
        return "```\nNo conversion data yet.\n```"

    rows = conversion_rows(data, ingame_rules, usd_base, dex_fee, market_fee)
    if not rows:
        return "```\nNo conversion data yet.\n```"

    crow_amount = usd_base / crow_usd
    header = [
        f"Base: ${usd_base:.0f}",
        f"CROW: {crow_amount:.2f}",
        f"DEX {dex_fee * 100:.0f}%",
        f"Mkt {market_fee * 100:.0f}%",
    ]
    if wemix_usd and wemix_usd > 0:
        header.append(f"WEMIX: {usd_base / wemix_usd:.2f}")

    body: list[str] = [f"{'PAIR':<10} {'DIA':>8}", "-" * 20]
    for row in rows:
        name = str(row.get("name", ""))
        diamonds = float(row.get("diamonds", 0))
        body.append(f"{name:<10} {diamonds:>8.0f}")
    return "```\n" + " | ".join(header) + "\n\n" + "\n".join(body) + "\n```"


def build_ingame_prices_block(
    ingame_rules: dict[str, dict[str, float | int | str]],
    pair_order: list[str],
) -> str:
    lines: list[str] = [f"{'PAIR':<10} {'DIA':>8}", "-" * 20]
    for pair in pair_order:
        cfg = ingame_rules.get(pair)
        if not cfg:
            continue
        name = str(cfg.get("name", fmt_pair_name(pair)))
        dia = float(cfg.get("diamonds", 0.0))
        lines.append(f"{name:<10} {fmt_ingame_dia(dia):>8}")
    return "```\n" + "\n".join(lines) + "\n```"


def build_prices_embed(
    data: dict,
    prev_map: dict[str, float],
    ingame_rules: dict[str, dict[str, float | int | str]],
    pair_order: list[str],
    *,
    prices_title: str = PRICES_TITLE,
    prices_refresh_sec: int = PRICES_REFRESH_SEC,
    usd_base: float = USD_BASE,
    default_tz_name: str = DEFAULT_TZ_NAME,
) -> discord.Embed:
    ts = int(data.get("ts") or 0)
    crow = data.get("crow_usd")
    wemix = data.get("wemix_usd")
    rows = data.get("rows") or []

    stale = bool(ts and (time.time() - ts) > (prices_refresh_sec * 3))
    color = 0x2ECC71 if not stale else 0xF1C40F
    title = f"📈 {prices_title}" if not stale else f"🟡 {prices_title} (stale)"
    embed = discord.Embed(title=title, color=color)

    crow_s = f"{float(crow):.6f}" if isinstance(crow, (int, float)) else "None"
    wemix_s = f"{float(wemix):.4f}" if isinstance(wemix, (int, float)) else "None"
    conv_rows = conversion_rows(data, ingame_rules)
    best_val = int(conv_rows[0]["diamonds"]) if conv_rows else 0
    best_dia_s = f"~{best_val:,} dia" if conv_rows else "—"

    embed.add_field(name="CROW/USD", value=f"`{crow_s}`", inline=True)
    embed.add_field(name="WEMIX/USD", value=f"`{wemix_s}`", inline=True)
    embed.add_field(name="Best $100", value=best_dia_s, inline=True)
    embed.add_field(name="Auto-refresh", value=f"`{prices_refresh_sec}s`", inline=True)

    if conv_rows:
        medals = ["🥇", "🥈", "🥉"]
        top3_lines = []
        for i, row in enumerate(conv_rows[:3]):
            n = str(row.get("name", ""))
            d = float(row.get("diamonds", 0))
            m = medals[i] if i < len(medals) else "•"
            top3_lines.append(f"{m} {n} {int(d):,} dia")
        embed.add_field(name="Top 3", value="\n".join(top3_lines), inline=False)

    by_pair = {str(r.get("pair")): r for r in rows if r.get("pair")}
    embed.add_field(name="CROW market", value=build_price_block(WANTED_CROW, by_pair, prev_map, "CROW"), inline=False)
    embed.add_field(name="Season market", value=build_price_block(WANTED_SEASON, by_pair, prev_map, "WEMIX"), inline=False)
    embed.add_field(name="In-game prices (manual)", value=build_ingame_prices_block(ingame_rules, pair_order), inline=False)
    embed.add_field(
        name=f"${usd_base:.0f} -> in-game diamonds",
        value=build_conversion_block(data, ingame_rules),
        inline=False,
    )

    main_url = "https://pnix.exchange/nightcrows/trade/"
    season_url = "https://pnix.exchange/nightcrows-season/"
    embed.add_field(
        name="Markets",
        value=f"[Main]({main_url}) · [Season]({season_url}) · _/sm /bulkmarket_",
        inline=False,
    )

    if ts:
        embed.set_footer(
            text=f"Updated {fmt_time_local(ts, default_tz_name)} · {price_age_text(ts)} · Auto-refresh: {prices_refresh_sec}s"
        )
    else:
        embed.set_footer(text=f"waiting for prices.json · Auto-refresh: {prices_refresh_sec}s")
    return embed
