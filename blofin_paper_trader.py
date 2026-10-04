#!/usr/bin/env python3
import json
import os
from pathlib import Path

from blofin_alert_15m import analyse_candidate, candles, top_usdt_swaps

# HARD SAFETY: THIS PROGRAM IS PAPER-TRADING ONLY.
PAPER_ONLY = True
START_CAPITAL_USDT = 10.0
LEVERAGE = 1.0
SL_PCT = 1.0
ROUND_TRIP_FEE_PCT = 0.12
STATE = Path("blofin_paper_state.json")
OUT = Path("paper.md")

# Even if somebody later adds BloFin API secrets to GitHub, this script refuses to run.
FORBIDDEN_REAL_TRADING_ENV = (
    "BLOFIN_API_KEY",
    "BLOFIN_SECRET_KEY",
    "BLOFIN_PASSPHRASE",
)

def safety_guard():
    if PAPER_ONLY is not True:
        raise RuntimeError("PAPER_ONLY must stay True.")
    present = [k for k in FORBIDDEN_REAL_TRADING_ENV if os.environ.get(k)]
    if present:
        raise RuntimeError(
            "Paper trader refuses private BloFin credentials: " + ", ".join(present)
        )

def load_state():
    if not STATE.exists():
        return {
            "mode": "PAPER_ONLY",
            "starting_capital_usdt": START_CAPITAL_USDT,
            "capital_usdt": START_CAPITAL_USDT,
            "active": None,
            "last_signal_id": None,
            "trades": 0,
            "wins": 0,
            "losses": 0,
        }
    try:
        s = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        s = {}
    s["mode"] = "PAPER_ONLY"
    s.setdefault("starting_capital_usdt", START_CAPITAL_USDT)
    s.setdefault("capital_usdt", START_CAPITAL_USDT)
    s.setdefault("active", None)
    s.setdefault("last_signal_id", None)
    s.setdefault("trades", 0)
    s.setdefault("wins", 0)
    s.setdefault("losses", 0)
    return s

def save_state(s):
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def best_entry():
    candidates = []
    for row in top_usdt_swaps():
        try:
            x = analyse_candidate(row["inst"])
            if x and x["passed"]:
                x["change24"] = row["change24"]
                candidates.append(x)
        except Exception:
            pass
    if not candidates:
        return None
    candidates.sort(
        key=lambda x: (
            float(x["hit_rate"] or 0.0),
            float(x["target_pct"] or 0.0),
            float(x.get("change24") or 0.0),
        ),
        reverse=True,
    )
    return candidates[0]

def close_active_if_hit(s, notes):
    p = s.get("active")
    if not p:
        return False

    bars = candles(p["inst"])
    future = [b for b in bars if int(b["t"]) > int(p["entry_bar_time"])]
    if not future:
        notes.append(
            f"Paper pozycja nadal otwarta: **{p['direction']} {p['inst']}** "
            f"od {p['entry']:.8g}; TP {p['tp']:.8g}; SL {p['sl']:.8g}."
        )
        return True

    result = None
    exit_price = None
    exit_bar = None

    for b in future:
        if p["direction"] == "LONG":
            hit_tp = b["h"] >= p["tp"]
            hit_sl = b["l"] <= p["sl"]
        else:
            hit_tp = b["l"] <= p["tp"]
            hit_sl = b["h"] >= p["sl"]

        # Conservative rule: if TP and SL occur in the same 15m candle, count it as a loss.
        if hit_tp and hit_sl:
            result = "LOSS"
            exit_price = p["sl"]
            exit_bar = b["t"]
            break
        if hit_sl:
            result = "LOSS"
            exit_price = p["sl"]
            exit_bar = b["t"]
            break
        if hit_tp:
            result = "WIN"
            exit_price = p["tp"]
            exit_bar = b["t"]
            break

    if result is None:
        notes.append(
            f"Paper pozycja nadal otwarta: **{p['direction']} {p['inst']}** "
            f"od {p['entry']:.8g}; TP {p['tp']:.8g}; SL {p['sl']:.8g}."
        )
        return True

    entry = float(p["entry"])
    before = float(p["capital_before"])
    if p["direction"] == "LONG":
        gross_pct = (exit_price / entry - 1.0) * 100.0
    else:
        gross_pct = (entry / exit_price - 1.0) * 100.0

    net_pct = gross_pct * LEVERAGE - ROUND_TRIP_FEE_PCT
    pnl = before * net_pct / 100.0
    after = max(0.0, before + pnl)

    s["capital_usdt"] = round(after, 8)
    s["active"] = None
    s["trades"] = int(s.get("trades", 0)) + 1
    if result == "WIN":
        s["wins"] = int(s.get("wins", 0)) + 1
    else:
        s["losses"] = int(s.get("losses", 0)) + 1

    notes.append(
        "## PAPER POZYCJA ZAMKNIĘTA\n\n"
        f"**{result} — {p['direction']} {p['inst']}**\n"
        f"Wejście: **{entry:.8g}**\n"
        f"Wyjście: **{exit_price:.8g}**\n"
        f"Wynik brutto: **{gross_pct:+.3f}%**\n"
        f"Prowizja modelowana: **-{ROUND_TRIP_FEE_PCT:.2f}%**\n"
        f"Wynik netto: **{net_pct:+.3f}% = {pnl:+.4f} USDT**\n"
        f"Kapitał po rolowaniu: **{after:.4f} USDT**"
    )
    return False

def open_new_if_possible(s, notes):
    if s.get("active"):
        return
    sig = best_entry()
    if not sig:
        notes.append(
            f"Paper kapitał: **{float(s['capital_usdt']):.4f} USDT** — "
            "brak nowego sygnału **WEJŚCIE**."
        )
        return

    signal_id = f"{sig['inst']}:{sig['bar_time']}:{sig['direction']}"
    if s.get("last_signal_id") == signal_id:
        notes.append("Brak nowej paper transakcji — ten sygnał był już wykorzystany.")
        return

    entry = float(sig["close"])
    target = float(sig["target_price"])
    if sig["direction"] == "LONG":
        sl = entry * (1.0 - SL_PCT / 100.0)
    else:
        sl = entry * (1.0 + SL_PCT / 100.0)

    capital = float(s["capital_usdt"])
    s["active"] = {
        "inst": sig["inst"],
        "direction": sig["direction"],
        "entry": entry,
        "tp": target,
        "sl": sl,
        "entry_bar_time": int(sig["bar_time"]),
        "capital_before": capital,
        "paper_notional_usdt": capital * LEVERAGE,
        "hit_rate": sig["hit_rate"],
        "target_pct": sig["target_pct"],
    }
    s["last_signal_id"] = signal_id

    notes.append(
        "## PAPER WEJŚCIE\n\n"
        f"**{sig['direction']} {sig['inst']}**\n"
        f"Kapitał użyty: **{capital:.4f} USDT** przy **1×**\n"
        f"Wejście: **{entry:.8g}**\n"
        f"TP: **{target:.8g}** (+{float(sig['target_pct']):.2f}%)\n"
        f"SL: **{sl:.8g}** (-{SL_PCT:.2f}%)\n"
        f"Historyczna skuteczność sygnału: **{float(sig['hit_rate']):.1f}%**\n"
        "Po zamknięciu cała wygrana albo strata netto zmieni kapitał następnej paper transakcji."
    )

def main():
    safety_guard()
    s = load_state()
    notes = ["# PAPER TRADING — BRAK PRAWDZIWYCH ZLECEŃ"]

    still_open = close_active_if_hit(s, notes)
    if not still_open:
        open_new_if_possible(s, notes)

    notes.append(
        f"Stan: **{float(s['capital_usdt']):.4f} USDT**, "
        f"zamknięte transakcje: **{int(s['trades'])}**, "
        f"W/L: **{int(s['wins'])}/{int(s['losses'])}**."
    )

    save_state(s)
    OUT.write_text("\n\n".join(notes) + "\n", encoding="utf-8")
    print(OUT.read_text(encoding="utf-8"))

if __name__ == "__main__":
    main()
