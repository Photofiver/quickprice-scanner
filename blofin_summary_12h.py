#!/usr/bin/env python3
import json
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from blofin_live_trader import (
    D,
    START_CAPITAL,
    TRADE_LOG_DIR,
    iso_time,
    load_state,
    plain,
    send_email,
)

DECISION_LOG_DIR = Path("blofin_decision_journal")


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def main():
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - 12 * 60 * 60 * 1000

    trade_logs = []
    if TRADE_LOG_DIR.exists():
        for path in sorted(TRADE_LOG_DIR.glob("*.json")):
            row = read_json(path)
            if not row:
                continue
            closed_ms = int(row.get("closed_at_ms") or 0)
            if start_ms <= closed_ms <= now_ms:
                trade_logs.append(row)

    trade_logs.sort(key=lambda x: int(x.get("closed_at_ms") or 0))
    wins = sum(1 for x in trade_logs if D(x.get("net_pnl_usdt")) > 0)
    losses = sum(1 for x in trade_logs if D(x.get("net_pnl_usdt")) < 0)
    flat = len(trade_logs) - wins - losses
    net_total = sum((D(x.get("net_pnl_usdt")) for x in trade_logs), Decimal("0"))
    fees_total = sum((D(x.get("fee_usdt")) for x in trade_logs), Decimal("0"))
    funding_total = sum((D(x.get("funding_usdt")) for x in trade_logs), Decimal("0"))

    journals = []
    if DECISION_LOG_DIR.exists():
        for path in sorted(DECISION_LOG_DIR.glob("*.json")):
            row = read_json(path)
            if not row:
                continue
            closed_ms = int(row.get("closed_at_ms") or 0)
            if start_ms <= closed_ms <= now_ms:
                journals.append(row)

    journals.sort(key=lambda x: int(x.get("closed_at_ms") or 0))

    considered_total = 0
    entry_total = 0
    reject_total = 0
    no_signal_total = 0
    for j in journals:
        for x in j.get("considered", []):
            considered_total += 1
            decision = x.get("decision")
            if decision == "WEJŚCIE":
                entry_total += 1
            elif decision == "NIE WCHODZIĆ":
                reject_total += 1
            else:
                no_signal_total += 1

    state = load_state()
    cap_now = D(state.get("capital_usdt", START_CAPITAL))
    active = state.get("active")
    now_uk = datetime.now(ZoneInfo("Europe/London"))
    start_uk = datetime.fromtimestamp(start_ms / 1000, ZoneInfo("Europe/London"))

    lines = [
        "BLOFIN — PODSUMOWANIE 12 GODZIN",
        "",
        f"Okres: {start_uk:%Y-%m-%d %H:%M} -> {now_uk:%Y-%m-%d %H:%M} UK",
        f"Analizy 15m zapisane w pamiętniku: {len(journals)}",
        f"Instrumenty rozważone łącznie: {considered_total}",
        f"Sygnały WEJŚCIE: {entry_total}",
        f"Odrzucone sygnały: {reject_total}",
        f"Bez sygnału kierunkowego: {no_signal_total}",
        "",
        f"Zamknięte transakcje: {len(trade_logs)}",
        f"Wygrane: {wins}",
        f"Stratne: {losses}",
        f"Na zero: {flat}",
        f"Wynik netto łącznie: {plain(net_total)} USDT",
        f"Prowizje łącznie: {plain(fees_total)} USDT",
        f"Funding łącznie: {plain(funding_total)} USDT",
        f"Aktualny kapitał bota: {plain(cap_now)} USDT",
    ]

    if active:
        lines.extend([
            "",
            "AKTYWNA POZYCJA:",
            f"#{active.get('trade_number')} {active.get('direction')} {active.get('inst')}",
            f"Otwarto UK: {iso_time(active.get('opened_at'), ZoneInfo('Europe/London'))}",
            f"Kapitał użyty: {active.get('capital_before')} USDT",
            f"TP: {active.get('tp')}",
            f"SL: {active.get('sl')}",
        ])
    else:
        lines.extend(["", "Aktywna pozycja: brak"])

    if trade_logs:
        lines.extend(["", "ZAMKNIĘTE TRANSAKCJE:"])
        for row in trade_logs:
            lines.append(
                f"#{row.get('trade_number')} {row.get('direction')} {row.get('instrument')} | "
                f"netto {row.get('net_pnl_usdt')} USDT | {row.get('closed_at_uk')}"
            )

    if journals:
        lines.extend(["", "PAMIĘTNIK DECYZJI 15m — WSZYSTKIE ZA I PRZECIW:"])
        for j in journals:
            lines.extend(["", f"=== {j.get('closed_at_uk')} ==="])
            selected = j.get("selected_for_entry")
            if selected:
                lines.append(
                    f"Najlepszy sygnał spełniający warunki: "
                    f"{selected.get('direction')} {selected.get('inst')} | "
                    f"skuteczność {selected.get('hit_rate')}% | cel {selected.get('target_pct')}%"
                )
            else:
                lines.append("Najlepszy sygnał spełniający warunki: brak")

            for x in j.get("considered", []):
                lines.append(
                    f"{x.get('instrument')} | {x.get('decision')} | "
                    f"24h {x.get('change24_pct')}%"
                )
                pros = x.get("pros") or []
                cons = x.get("cons") or []
                lines.append("  ZA: " + ("; ".join(pros) if pros else "brak"))
                lines.append("  PRZECIW: " + ("; ".join(cons) if cons else "brak"))

    body = "\n".join(lines)
    send_email(
        f"BloFin 12h summary | {len(trade_logs)} trades | {plain(net_total)} USDT",
        body,
    )
    print(body)


if __name__ == "__main__":
    main()
