import json
import os
import ssl
import threading
import time
from functools import partial

import requests
import websocket

from settings import PRICES_JSON_PATH

# ========= CONFIG =========
# Two gateways:
# - /nightcrows        -> proddex-crow-agw
# - /nightcrows-season -> proddex-crow-season-agw
PNIX_WS_MAIN = "wss://proddex-crow-agw.azure-api.net/"
PNIX_WS_SEASON = "wss://proddex-crow-season-agw.azure-api.net/"

ORIGIN = "https://pnix.exchange"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# CROW/USD (GeckoTerminal pool)
CROW_POOL = "0x42cf1af7fa9c2b50855a47806706d623de73316b"
GECKO_POOL_API = f"https://api.geckoterminal.com/api/v2/networks/wemix/pools/{CROW_POOL}"

# === ВАЖНО: сюда вставляй market addresses из DevTools WS Messages ===
MANUAL_MARKETS = {
    "MORION-CROW": "0x19690c8ecd26a82853d5a9059480be15dc7884a4",
    "ESSENCE-CROW": "0xfaedb457e82eacf55c9cd7816d783ef39e16a202",
    "ALLOY-CROW": "0x5a93cd0300add26619e2a9e2209d655f238c12b9",
    "FEATHER-CROW": "0x7d82933a4e9ed20dd11008d6a0beaa5c4b0b2687",
    "TEAR-CROW": "0x8697bed5499737c10ab5adb4bc7952fe457b50e0",
    "PAPYRUS-CROW": "0x9d5949c408ca8a41b5ef322bd078e1b7e16ce628",
    "PROMOTE-CROW": "0x0c82e7e5a95a0d599bff88d0b7f7b0ec2b2c2002",
    "GEAR-CROW": "0x2ae7e7cbbcbe04fa274d4f743c15eb1fff2b789c",
    "RAVN-WEMIX": "0xebefdba23e9c06708ba590fbc59abd91e8c10009",
}

SYMBOLS = [
    "MORION-CROW",
    "ESSENCE-CROW",
    "ALLOY-CROW",
    "FEATHER-CROW",
    "TEAR-CROW",
    "PAPYRUS-CROW",
    "PROMOTE-CROW",
    "GEAR-CROW",
    "RAVN-WEMIX",
]

# Which gateway each symbol lives on
SYMBOL_GATEWAY = {sym: "main" for sym in SYMBOLS}
SYMBOL_GATEWAY["RAVN-WEMIX"] = "season"  # this one uses /nightcrows-season

# ====== RUNTIME STATE ======
STATE = {
    "crow_usd": None,
    "wemix_usd": None,
    "last": {},  # symbol -> latestPrice
    "ws": {
        "main": {"subs": {}, "pending": {}},    # sub_id -> (symbol, channel), req_id -> (symbol, channel)
        "season": {"subs": {}, "pending": {}},
    }
}
LOCK = threading.Lock()

# Cache refs to avoid rate limits and avoid blocking startup
PRICE_CACHE = {
    "crow_usd": {"value": None, "ts": 0.0},
    "wemix_usd": {"value": None, "ts": 0.0},
}
REFRESH_CROW_SEC = 60
REFRESH_WEMIX_SEC = 60


# ========= HTTP REFS (NON-BLOCKING STARTUP) =========
def get_crow_usd():
    now = time.time()
    with LOCK:
        cached = PRICE_CACHE["crow_usd"]["value"]
        ts = PRICE_CACHE["crow_usd"]["ts"]
    if cached is not None and (now - ts) < REFRESH_CROW_SEC:
        return cached

    try:
        r = requests.get(
            GECKO_POOL_API,
            timeout=8,
            headers={"User-Agent": UA, "Accept": "application/json"},
        )
        if r.status_code != 200:
            print("GeckoTerminal CROW/USD failed:", r.status_code, r.text[:120])
            return cached
        data = r.json()
        attrs = data.get("data", {}).get("attributes", {})
        price = attrs.get("base_token_price_usd") or attrs.get("price_in_usd")
        val = float(price) if price is not None else None
        if val is not None:
            with LOCK:
                PRICE_CACHE["crow_usd"]["value"] = val
                PRICE_CACHE["crow_usd"]["ts"] = now
        return val if val is not None else cached
    except Exception as e:
        print("GeckoTerminal CROW/USD exception:", e)
        return cached

def write_prices_json():
    with LOCK:
        crow = STATE.get("crow_usd")
        wemix = STATE.get("wemix_usd")
        last = dict(STATE.get("last", {}))

    rows = []
    for sym in SYMBOLS:
        p = last.get(sym)
        if p is None:
            continue

        usd = estimate_usd(sym, float(p), crow, wemix)

        rows.append({
            "pair": sym,
            "last": float(p),
            "usd": float(usd) if usd is not None else None,
        })

    payload = {
        "ts": int(time.time()),
        "crow_usd": float(crow) if crow is not None else None,
        "wemix_usd": float(wemix) if wemix is not None else None,
        "rows": rows,
    }

    tmp = PRICES_JSON_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PRICES_JSON_PATH)

def get_wemix_usd():
    now = time.time()
    with LOCK:
        cached = PRICE_CACHE["wemix_usd"]["value"]
        ts = PRICE_CACHE["wemix_usd"]["ts"]
        cg_cd = PRICE_CACHE.get("wemix_cg_cooldown_until", 0.0)

    # do not refresh too often
    if cached is not None and (now - ts) < REFRESH_WEMIX_SEC:
        return cached

    def cache_and_return(val: float | None):
        if val is not None:
            with LOCK:
                PRICE_CACHE["wemix_usd"]["value"] = val
                PRICE_CACHE["wemix_usd"]["ts"] = now
            return val
        return cached

    def _get_json(url, params=None, headers=None, timeout=6):
        h = {"User-Agent": UA, "Accept": "application/json"}
        if headers:
            h.update(headers)
        r = requests.get(url, params=params, headers=h, timeout=timeout)
        ct = (r.headers.get("content-type") or "").lower()
        data = None
        if "application/json" in ct:
            try:
                data = r.json()
            except Exception:
                data = None
        return r, data

    # Prefer stable, non-rate-limited sources first.

    # 1) CryptoCompare
    try:
        r, data = _get_json(
            "https://min-api.cryptocompare.com/data/price",
            params={"fsym": "WEMIX", "tsyms": "USD"},
        )
        if r.status_code == 200 and isinstance(data, dict):
            price = data.get("USD")
            val = float(price) if price is not None else None
            if val is not None:
                return cache_and_return(val)
        # no spam logging for normal fails
    except Exception:
        pass

    # 2) OKX spot ticker
    try:
        r, data = _get_json(
            "https://www.okx.com/api/v5/market/ticker",
            params={"instId": "WEMIX-USDT"},
        )
        if r.status_code == 200 and isinstance(data, dict):
            arr = data.get("data") or []
            last = (arr[0] or {}).get("last") if arr else None
            val = float(last) if last is not None else None
            if val is not None:
                return cache_and_return(val)
    except Exception:
        pass

    # 3) Bybit spot ticker
    try:
        r, data = _get_json(
            "https://api.bybit.com/v5/market/tickers",
            params={"category": "spot", "symbol": "WEMIXUSDT"},
        )
        if r.status_code == 200 and isinstance(data, dict):
            lst = ((data.get("result") or {}).get("list")) or []
            last = (lst[0] or {}).get("lastPrice") if lst else None
            val = float(last) if last is not None else None
            if val is not None:
                return cache_and_return(val)
    except Exception:
        pass

    # 4) KuCoin level1
    try:
        r, data = _get_json(
            "https://api.kucoin.com/api/v1/market/orderbook/level1",
            params={"symbol": "WEMIX-USDT"},
        )
        if r.status_code == 200 and isinstance(data, dict):
            last = ((data.get("data") or {}) ).get("price")
            val = float(last) if last is not None else None
            if val is not None:
                return cache_and_return(val)
    except Exception:
        pass

    # 5) Gate.io tickers
    try:
        r = requests.get(
            "https://api.gateio.ws/api/v4/spot/tickers",
            params={"currency_pair": "WEMIX_USDT"},
            headers={"User-Agent": UA, "Accept": "application/json"},
            timeout=6,
        )
        if r.status_code == 200:
            data = r.json()
            last = None
            if isinstance(data, list) and data:
                last = (data[0] or {}).get("last")
            elif isinstance(data, dict):
                last = data.get("last")
            val = float(last) if last is not None else None
            if val is not None:
                return cache_and_return(val)
    except Exception:
        pass

    # 6) CoinGecko LAST (often 429). If we hit 429, cool down for 10 minutes.
    if now < cg_cd:
        return cached

    try:
        r, data = _get_json(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "wemix", "vs_currencies": "usd"},
        )
        if r.status_code == 200 and isinstance(data, dict):
            price = (data.get("wemix") or {}).get("usd")
            val = float(price) if price is not None else None
            if val is not None:
                return cache_and_return(val)
        elif r.status_code == 429:
            with LOCK:
                PRICE_CACHE["wemix_cg_cooldown_until"] = now + 600
            print("CoinGecko WEMIX/USD rate limited (429). Cooldown 10 min.")
    except Exception:
        pass

    return cached



# ========= OUTPUT =========
def estimate_usd(sym: str, last_price: float, crow_usd, wemix_usd):
    if sym.endswith("-CROW"):
        return last_price * crow_usd if crow_usd is not None else None
    if sym.endswith("-WEMIX"):
        return last_price * wemix_usd if wemix_usd is not None else None
    return None


def print_table():
    with LOCK:
        crow = STATE.get("crow_usd")
        wemix = STATE.get("wemix_usd")
        last = dict(STATE.get("last", {}))

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print("\nNight Crows prices (PNIX WS dual gateways + USD refs)")
    print(ts)
    print(f"\nCROW USD : {crow}")
    print(f"WEMIX USD: {wemix}\n")

    print(f"{'PAIR':16} {'LAST':>12} {'USD(est)':>12}")
    print("-" * 44)

    for sym in SYMBOLS:
        p = last.get(sym)
        if p is None:
            continue
        usd = estimate_usd(sym, float(p), crow, wemix)
        last_s = f"{float(p):.6f}"
        usd_s = f"{usd:.6f}" if usd is not None else "None"
        print(f"{sym:16} {last_s:>12} {usd_s:>12}")

    print("\nОбновление ~ каждые 20 сек. Ctrl+C чтобы выйти.")

# ========= WS =========
def jsend(ws, obj):
    ws.send(json.dumps(obj, separators=(",", ":")))


def ping_loop(ws, gw_name: str):
    while True:
        try:
            jsend(ws, {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "dex_ping",
                "params": [{"id": 1, "unixtimestamp": int(time.time() * 1000)}],
            })
        except Exception:
            return
        time.sleep(2)


def printer_loop():
    while True:
        try:
            crow = get_crow_usd()
            wemix = get_wemix_usd()

            with LOCK:
                if crow is not None:
                    STATE["crow_usd"] = crow
                if wemix is not None:
                    STATE["wemix_usd"] = wemix

            print_table()
            write_prices_json()

        except Exception as e:
            print("printer_loop error:", e)

        time.sleep(20)


def subscribe_gateway(ws, gw_name: str):
    req_id = 100
    did = 0

    for sym in SYMBOLS:
        if SYMBOL_GATEWAY.get(sym) != gw_name:
            continue

        addr = MANUAL_MARKETS.get(sym)
        if not addr:
            continue

        req_id += 1
        with LOCK:
            STATE["ws"][gw_name]["pending"][req_id] = (sym, "snapshot")
        jsend(ws, {"jsonrpc": "2.0", "id": req_id, "method": "dex_subscribe",
                   "params": ["snapshot", addr, None]})

        req_id += 1
        with LOCK:
            STATE["ws"][gw_name]["pending"][req_id] = (sym, "latestMeasureV2")
        jsend(ws, {"jsonrpc": "2.0", "id": req_id, "method": "dex_subscribe",
                   "params": ["latestMeasureV2", addr, None]})

        did += 1
        time.sleep(0.05)

    if did == 0:
        print(f"[{gw_name}] No manual markets set yet for this gateway.")
    else:
        print(f"[{gw_name}] Subscribed to {did} markets.")


def on_open(ws, gw_name: str):
    print(f"CONNECTED [{gw_name}]")
    # НИКАКИХ HTTP вызовов здесь - чтобы старт был мгновенный и без "тишины"
    threading.Thread(target=ping_loop, args=(ws, gw_name), daemon=True).start()
    subscribe_gateway(ws, gw_name)


def on_message(ws, message, gw_name: str):
    try:
        msg = json.loads(message)
    except Exception:
        return

    # dex_subscribe response -> subscription id
    if (
        isinstance(msg, dict)
        and msg.get("jsonrpc") == "2.0"
        and "id" in msg
        and "result" in msg
        and isinstance(msg["result"], str)
    ):
        req_id = msg["id"]
        sub_id = msg["result"]
        with LOCK:
            info = STATE["ws"][gw_name]["pending"].pop(req_id, None)
            if info:
                STATE["ws"][gw_name]["subs"][sub_id] = info
        return

    # streaming updates
    if isinstance(msg, dict) and msg.get("method") == "dex_subscription":
        params = msg.get("params") or {}
        sub_id = params.get("subscription")
        result = params.get("result") or {}

        ob = result.get("orderbook") or {}
        latest = ob.get("latestPrice")

        with LOCK:
            sym_ch = STATE["ws"][gw_name]["subs"].get(sub_id)

        if not sym_ch:
            return

        sym = sym_ch[0]

        if latest is None:
            return

        with LOCK:
            STATE["last"][sym] = float(latest)


def on_error(ws, err, gw_name: str):
    print(f"WS ERROR [{gw_name}]:", err)


def on_close(ws, code, reason, gw_name: str):
    print(f"CLOSED [{gw_name}]:", code, reason)


def run_gateway_forever(ws_url: str, gw_name: str):
    headers = [
        f"Origin: {ORIGIN}",
        f"User-Agent: {UA}",
    ]

    while True:
        try:
            ws = websocket.WebSocketApp(
                ws_url,
                header=headers,
                on_open=partial(on_open, gw_name=gw_name),
                on_message=partial(on_message, gw_name=gw_name),
                on_error=partial(on_error, gw_name=gw_name),
                on_close=partial(on_close, gw_name=gw_name),
            )
            ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=0, ping_timeout=None)
        except Exception as e:
            print(f"MAIN LOOP ERROR [{gw_name}]:", e)

        print(f"Reconnecting [{gw_name}] in 3 sec...\n")
        time.sleep(3)


def run_forever():
    # Принтер запускаем сразу (без ожидания сетевых запросов)
    threading.Thread(target=printer_loop, daemon=True).start()

    t1 = threading.Thread(target=run_gateway_forever, args=(PNIX_WS_MAIN, "main"), daemon=True)
    t2 = threading.Thread(target=run_gateway_forever, args=(PNIX_WS_SEASON, "season"), daemon=True)
    t1.start()
    t2.start()

    while True:
        time.sleep(3600)


if __name__ == "__main__":
    run_forever()
