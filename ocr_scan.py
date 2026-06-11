"""
OCR scan for Night Crows market screenshots.
Recognizes known item names + prices. Returns rich result for debugging.
"""
import re
from difflib import get_close_matches
from io import BytesIO
from typing import Literal, Optional

import pytesseract
from PIL import Image, ImageEnhance, ImageOps

# Canonical keys (whitelist) - only these are saved
CANONICAL_KEYS = frozenset({
    "morion", "essence", "alloy", "feather", "tear",
    "papyrus", "promote", "gear", "ravn",
})

# Alias -> canonical (RU + EN + common OCR variants)
_ALIAS_RAW = [
    ("morion", "morion"), ("морион", "morion"), ("moriоn", "morion"), ("mori0n", "morion"),
    ("essence", "essence"), ("essence of curses", "essence"), ("ядро проклятия", "essence"),
    ("ядро проклтья", "essence"), ("essence of curces", "essence"),
    ("alloy", "alloy"), ("ancient master's alloy", "alloy"), ("сплав древнего мастера", "alloy"),
    ("сплав древнего матера", "alloy"), ("ancient masters alloy", "alloy"),
    ("feather", "feather"), ("piece of the sky", "feather"), ("фрагмент поднебесья", "feather"),
    ("фрагмент поднебесъя", "feather"), ("piece of sky", "feather"),
    ("tear", "tear"), ("frozen tear", "tear"), ("заледеневшая слеза", "tear"),
    ("заледеневша слеза", "tear"), ("frozentear", "tear"),
    ("papyrus", "papyrus"), ("ancient papyrus", "papyrus"), ("древний папирус", "papyrus"),
    ("древнй папирус", "papyrus"), ("ancient papirs", "papyrus"),
    ("promote", "promote"), ("higher seal of advancement", "promote"),
    ("высш. жетон продвижения", "promote"), ("высш жетон продвижения", "promote"),
    ("higher seal advancement", "promote"), ("higher seal of advancemment", "promote"),
    ("seal of advancement", "promote"), ("жетон продвижения", "promote"),
    ("gear", "gear"), ("meticulous aircraft component", "gear"),
    ("микроточные летные детали", "gear"), ("микроточные летные детал", "gear"),
    ("ravn", "ravn"), ("ravium", "ravn"),
]


def _normalize_for_match(s: str) -> str:
    if not s:
        return ""
    s = str(s).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


_ALIAS_TO_CANONICAL: dict[str, str] = {}
for alias, canonical in _ALIAS_RAW:
    key = _normalize_for_match(alias)
    if key and canonical in CANONICAL_KEYS:
        _ALIAS_TO_CANONICAL[key] = canonical
for c in CANONICAL_KEYS:
    _ALIAS_TO_CANONICAL[c] = c

_ALIAS_KEYS_LIST = list(_ALIAS_TO_CANONICAL.keys())
FUZZY_CUTOFF = 0.72
FUZZY_MAX = 3


def _preprocess_image(img: Image.Image) -> Image.Image:
    """Grayscale, contrast, resize, threshold."""
    if img.mode != "L":
        img = img.convert("L")
    w, h = img.size
    if w < 500:
        scale = 1000 / w
        new_w, new_h = int(w * scale), int(h * scale)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)
    try:
        img = ImageOps.autocontrast(img, cutoff=2)
    except Exception:
        pass
    img = img.point(lambda p: 255 if p > 150 else 0, mode="1")
    return img.convert("L")


def _match_to_canonical(text: str) -> tuple[Optional[str], Literal["exact", "fuzzy"] | None]:
    """Returns (canonical, match_type) or (None, None)."""
    if not text or len(text) < 2:
        return (None, None)
    n = _normalize_for_match(text)
    if not n:
        return (None, None)
    exact = _ALIAS_TO_CANONICAL.get(n)
    if exact:
        return (exact, "exact")
    matches = get_close_matches(n, _ALIAS_KEYS_LIST, n=FUZZY_MAX, cutoff=FUZZY_CUTOFF)
    if matches:
        return (_ALIAS_TO_CANONICAL.get(matches[0]), "fuzzy")
    return (None, None)


def _parse_price(s: str) -> Optional[float]:
    """Parse price, support decimal comma. 9,33 -> 9.33. Prefer decimal pattern."""
    if not s:
        return None
    s = str(s).strip()
    s_nodot = s.replace(",", ".").replace(" ", "")
    decimal_match = re.search(r"\d+[.,]\d+", s)
    if decimal_match:
        part = decimal_match.group(0).replace(",", ".")
        try:
            v = float(part)
            if 0.001 <= v <= 999999:
                return v
        except ValueError:
            pass
    matches = re.findall(r"\d+\.?\d*", s_nodot)
    for m in reversed(matches):
        try:
            v = float(m)
            if 0.001 <= v <= 999999:
                return v
        except ValueError:
            pass
    return None


def _build_merged_numbers_from_line(words_sorted_by_x: list[tuple[int, int, str]]) -> list[tuple[int, float]]:
    """
    Build numbers from words, merging adjacent digit words. Returns [(right_edge, price), ...].
    "9" "2" adjacent -> 92; "2" "," "19" -> 2.19.
    """
    candidates: list[tuple[int, float]] = []
    i = 0
    while i < len(words_sorted_by_x):
        x, r, t = words_sorted_by_x[i]
        p = _parse_price(t)
        merged_r = r
        merged = t
        j = i + 1
        while j < len(words_sorted_by_x):
            nx, nr, nt = words_sorted_by_x[j]
            if nx - merged_r > 30:
                break
            if re.match(r"^[\d,\.]+$", nt) or nt in ",.":
                merged += nt
                merged_r = nr
                p = _parse_price(merged.replace(",", "."))
            else:
                break
            j += 1
        if p is not None:
            candidates.append((merged_r, p))
        i = j if j > i + 1 else i + 1
    return candidates


def _price_confidence(price: float, raw_line: str, from_right_zone: bool) -> Literal["high", "low"]:
    """Heuristic: single digit or suspicious values = low."""
    if price < 0.01 or price > 9999:
        return "low"
    if price < 10 and price == int(price) and int(price) < 10:
        decimal_in_line = bool(re.search(r"\d+[,.]\d+", raw_line))
        if decimal_in_line:
            return "low"
        if not from_right_zone:
            return "low"
    if 1 <= price <= 9 and price == int(price):
        if re.search(r"\d{2,}", raw_line):
            return "low"
    return "high"


def _extract_price_prefer_right(
    words_with_pos: list[tuple[int, int, str]],
    raw_line: str = "",
) -> tuple[Optional[float], Literal["high", "low"]]:
    """
    Prefer numbers from right zone. Merge adjacent digit words. Returns (price, confidence).
    """
    sorted_w = sorted(words_with_pos, key=lambda w: w[0])
    candidates = _build_merged_numbers_from_line(sorted_w)
    if not candidates:
        return (None, "low")
    candidates.sort(key=lambda x: x[0], reverse=True)
    price = candidates[0][1]
    from_right = len(words_with_pos) > 1
    conf = _price_confidence(price, raw_line, from_right)
    return (price, conf)


def _extract_from_data(data: dict) -> list[dict]:
    """
    Extract from pytesseract image_to_data result.
    Uses word positions: prefer price from right zone.
    Returns list of {canonical_key, price, matched_text, match_type, raw_line}.
    """
    texts = data.get("text", [])
    lefts = data.get("left", [])
    tops = data.get("top", [])
    widths = data.get("width", [])
    n = len(texts)
    if n == 0:
        return []

    def right(i: int) -> int:
        return lefts[i] + widths[i] if i < len(widths) else lefts[i]

    lines: dict[int, list[tuple[int, int, str]]] = {}
    line_y_tolerance = 10

    for i in range(n):
        t = (texts[i] or "").strip()
        if not t:
            continue
        x, y, w = lefts[i] if i < len(lefts) else 0, tops[i] if i < len(tops) else 0, widths[i] if i < len(widths) else 0
        r = x + w
        line_key = (y // line_y_tolerance) * line_y_tolerance
        lines.setdefault(line_key, []).append((x, r, t))

    seen: dict[str, dict] = {}
    line_keys = sorted(lines.keys())

    for lk in line_keys:
        words = lines[lk]
        words_sorted_by_x = sorted(words, key=lambda w: w[0])
        raw_line = " ".join(w[2] for w in words_sorted_by_x)
        line_width = max(w[1] for w in words) - min(w[0] for w in words) if words else 0
        right_threshold = min(w[0] for w in words) + line_width * 0.5 if line_width else 0

        for j, (x, r, t) in enumerate(words_sorted_by_x):
            canonical, match_type = _match_to_canonical(t)
            if not canonical:
                for nwords in (2, 3, 4):
                    chunk_words = words_sorted_by_x[j : j + nwords]
                    if len(chunk_words) != nwords:
                        continue
                    chunk = " ".join(w[2] for w in chunk_words)
                    canonical, match_type = _match_to_canonical(chunk)
                    if canonical:
                        t = chunk
                        break
            if canonical and canonical in CANONICAL_KEYS:
                right_zone = [w for w in words if w[1] >= right_threshold]
                price, conf = _extract_price_prefer_right(right_zone, raw_line)
                if price is None:
                    price, conf = _extract_price_prefer_right(words, raw_line)
                if price is not None:
                    seen[canonical] = {
                        "canonical_key": canonical,
                        "price": price,
                        "matched_text": t,
                        "match_type": match_type or "exact",
                        "price_confidence": conf,
                        "raw_line": raw_line[:120],
                    }
                break

    return list(seen.values())


def _extract_fallback_from_text(raw_text: str) -> list[dict]:
    """Fallback when image_to_data fails: use plain text, prefer last number (right)."""
    seen: dict[str, dict] = {}
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]

    for i, line in enumerate(lines):
        words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9,.\-]+", line)
        for j, w in enumerate(words):
            canonical, match_type = _match_to_canonical(w)
            if not canonical:
                for n in (2, 3, 4):
                    if j + n <= len(words):
                        chunk = " ".join(words[j : j + n])
                        canonical, match_type = _match_to_canonical(chunk)
                        if canonical:
                            w = chunk
                            break
            if canonical and canonical in CANONICAL_KEYS:
                price = _parse_price(line)
                if price is None and i + 1 < len(lines):
                    price = _parse_price(lines[i + 1])
                if price is not None:
                    conf = _price_confidence(price, line, from_right_zone=False)
                    seen[canonical] = {
                        "canonical_key": canonical,
                        "price": price,
                        "matched_text": w,
                        "match_type": match_type or "exact",
                        "price_confidence": conf,
                        "raw_line": line[:120],
                    }
                break

    return list(seen.values())


def scan_image(image_bytes: bytes) -> list[dict]:
    """
    OCR scan of Night Crows market screenshot.
    Returns list of {
        canonical_key, price, matched_text, match_type ("exact"|"fuzzy"), raw_line
    } for whitelist items only.
    """
    try:
        img = Image.open(BytesIO(image_bytes))
    except Exception:
        return []

    img = _preprocess_image(img)

    try:
        data = pytesseract.image_to_data(img, lang="eng+rus", config="--psm 6", output_type=pytesseract.Output.DICT)
        results = _extract_from_data(data)
        if results:
            return results
        text = pytesseract.image_to_string(img, lang="eng+rus", config="--psm 6")
        return _extract_fallback_from_text(text or "")
    except Exception:
        try:
            text = pytesseract.image_to_string(img, lang="eng+rus", config="--psm 6")
            return _extract_fallback_from_text(text or "")
        except Exception:
            return []
