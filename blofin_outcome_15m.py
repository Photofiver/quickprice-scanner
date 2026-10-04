#!/usr/bin/env python3
import json
from pathlib import Path

from blofin_alert_15m import candles

JOURNAL_DIR = Path("blofin_decision_journal")
TP_PCT = 0.5
SL_PCT = 0.5


def pct(x):
    return round(float(x), 6)


def outcome(direction, entry, bar):
    high = float(bar["h"])
    low = float(bar["l"])
    close = float(bar["c"])
    entry = float(entry)

    if direction == "LONG":
        close_pnl = (close / entry - 1.0) * 100.0
        mfe = (high / entry - 1.0) * 100.0
        mae = (low / entry - 1.0) * 100.0
        tp_hit = high >= entry * (1.0 + TP_PCT / 100.0)
        sl_hit = low <= entry * (1.0 - SL_PCT / 100.0)
    else:
        close_pnl = (entry / close - 1.0) * 100.0
        mfe = (entry / low - 1.0) * 100.0
        mae = (entry / high - 1.0) * 100.0
        tp_hit = low <= entry * (1.0 - TP_PCT / 100.0)
        sl_hit = high >= entry * (1.0 + SL_PCT / 100.0)

    if tp_hit and sl_hit:
        tp_sl_result = "BOTH_HIT_ORDER_UNKNOWN"
    elif tp_hit:
        tp_sl_result = "TP_HIT"
    elif sl_hit:
        tp_sl_result = "SL_HIT"
    else:
        tp_sl_result = "NEITHER_HIT"

    return {
        "horizon": "1x15m_candle",
        "entry_price": entry,
        "next_candle_open": float(bar["o"]),
        "next_candle_high": high,
        "next_candle_low": low,
        "next_candle_close": close,
        "close_pnl_pct_gross": pct(close_pnl),
        "max_favorable_excursion_pct": pct(mfe),
        "max_adverse_excursion_pct": pct(mae),
        "tp_0_5_hit": tp_hit,
        "sl_0_5_hit": sl_hit,
        "tp_sl_0_5_result": tp_sl_result,
        "fees_not_included": True,
    }


def main():
    if not JOURNAL_DIR.exists():
        return

    changed = 0
    for path in sorted(JOURNAL_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        closed_ms = int(data.get("closed_at_ms") or 0)
        if not closed_ms:
            continue

        file_changed = False
        for item in data.get("considered", []):
            if item.get("one_candle_outcome") is not None:
                continue

            analysis = item.get("analysis") or {}
            direction = analysis.get("direction")
            entry = analysis.get("close")
            inst = item.get("instrument")
            if direction not in ("LONG", "SHORT") or not entry or not inst:
                continue

            try:
                bars = candles(inst)
                next_bar = next((b for b in bars if int(b.get("t") or 0) == closed_ms), None)
            except Exception:
                next_bar = None

            if next_bar is None:
                continue

            item["one_candle_outcome"] = outcome(direction, entry, next_bar)
            file_changed = True

        if file_changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed += 1

    print(f"UPDATED_JOURNALS {changed}")


if __name__ == "__main__":
    main()
