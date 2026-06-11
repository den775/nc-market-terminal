"""
File I/O for NC Market Terminal.
Reading/writing prices.json, ingame_prices.json, prices card state.
"""
import json
import logging
import os
from contextlib import suppress
from typing import Any, Optional

logger = logging.getLogger(__name__)


def read_prices_json(path: str) -> Optional[dict[str, Any]]:
    """Read prices.json. Returns None on error."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_ingame_rules(
    path: str,
    default_rules: dict[str, dict[str, float | int | str]],
) -> dict[str, dict[str, float | int | str]]:
    """Load ingame_prices.json, merge with default. Creates file with default if missing."""
    data = {k: dict(v) for k, v in default_rules.items()}
    try:
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return data
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for pair, cfg in raw.items():
                if not isinstance(cfg, dict):
                    continue
                base = data.setdefault(pair, {})
                if "name" in cfg:
                    base["name"] = str(cfg["name"])
                if "diamonds" in cfg:
                    with suppress(Exception):
                        base["diamonds"] = float(cfg["diamonds"])
                if "multiplier" in cfg:
                    with suppress(Exception):
                        base["multiplier"] = int(cfg["multiplier"])
    except Exception:
        logger.exception("Failed to load ingame prices config")
    return data


def save_ingame_rules(path: str, rules: dict[str, dict[str, float | int | str]]) -> None:
    """Save ingame_prices.json."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Failed to save ingame prices config")


def load_prices_card_state(path: str) -> tuple[Optional[int], dict[str, float]]:
    """Load prices card state. Returns (message_id, prev_map)."""
    message_id: Optional[int] = None
    prev_map: dict[str, float] = {}
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                message_id = int(data.get("message_id") or 0) or None
                prev_raw = data.get("prev_map") or {}
                if isinstance(prev_raw, dict):
                    prev_map = {
                        str(k): float(v)
                        for k, v in prev_raw.items()
                        if isinstance(v, (int, float))
                    }
    except Exception:
        logger.exception("Failed to load prices card state")
    return (message_id, prev_map)


def save_prices_card_state(
    path: str,
    message_id: Optional[int],
    prev_map: dict[str, float],
) -> None:
    """Save prices card state."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"message_id": message_id, "prev_map": prev_map},
                f,
                ensure_ascii=False,
            )
    except Exception:
        logger.exception("Failed to save prices card state")
