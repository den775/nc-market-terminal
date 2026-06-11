# OCR Market Scan (Beta)

## Status

Beta / helper feature. Not the primary workflow — use `/sm` and `/bulkmarket` for reliable manual price entry.

## Requirements

```bash
pip install pytesseract Pillow
```

System Tesseract:

- **Windows**: [UB Mannheim tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
- **Ubuntu**: `sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus`

## Usage

```
/scan_price image:<screenshot>
```

Upload a screenshot of the Night Crows market list (PNG/JPG).

## Behavior

1. Image preprocessing (grayscale, contrast, threshold)
2. OCR with `eng+rus`
3. Match known items via alias map (RU + EN)
4. Extract price from right side of line
5. Show results; **Save** only for `exact` item + `high` price confidence

## Limitations

- Works best on clear list screenshots
- Fuzzy matches and low-confidence prices are not auto-saved
- Decimal comma handling is heuristic (`2,19` vs `219`)
- Only whitelist items from `CANONICAL_KEYS` in `ocr_scan.py`

## Module

Logic in `ocr_scan.py` — independent of Discord (takes image bytes).
