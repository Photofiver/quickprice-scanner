#!/usr/bin/env python3
from blofin_alert_15m import top_usdt_swaps, analyse_candidate
from blofin_live_trader import send_email

def rank(x):
    return (
        float(x.get("hit_rate") or 0),
        float(x.get("target_pct") or 0),
        float(x.get("change24") or 0),
    )

def main():
    rows = top_usdt_swaps()
    analysed = []
    for row in rows:
        try:
            x = analyse_candidate(row["inst"])
            if x:
                x["change24"] = row["change24"]
                analysed.append(x)
        except Exception as exc:
            analysed.append({"inst": row["inst"], "error": str(exc), "passed": False, "reasons":[str(exc)]})

    passed = sorted([x for x in analysed if x.get("passed")], key=rank, reverse=True)
    best = passed[0] if passed else None

    lines = ["BLOFIN — TEST OSTATNIEJ ZAMKNIĘTEJ ŚWIECY 15m", ""]
    if best:
        lines += [
            f"DECYZJA: WEJŚCIE",
            f"Instrument: {best['inst']}",
            f"Kierunek: {best['direction']}",
            f"Skuteczność historyczna: {best.get('hit_rate'):.1f}%",
            f"Cel S/R: {best.get('target_pct'):.2f}%",
            f"Zmiana 8 świec: {best.get('change8_pct', best.get('change8')):.3f}%",
            f"Stochastic K/D: {best.get('stoch_k_8', best.get('k')):.2f}/{best.get('stoch_d_3', best.get('d')):.2f}",
        ]
    else:
        lines += ["DECYZJA: NIE WCHODZIĆ", "Powód: brak sygnału spełniającego wszystkie warunki."]

    lines += ["", "SZCZEGÓŁY TOP10:"]
    for x in analysed:
        if "error" in x:
            lines.append(f"{x['inst']}: BŁĄD — {x['error']}")
            continue
        status = "WEJŚCIE" if x.get("passed") else "ODRZUCONY"
        reasons = "; ".join(x.get("reasons") or []) or "spełnia warunki"
        lines.append(
            f"{x['inst']} {x.get('direction')} | {status} | "
            f"hit {x.get('hit_rate')} | target {x.get('target_pct')} | {reasons}"
        )

    body = "\n".join(lines)
    subject = f"BloFin 15m test | {'WEJŚCIE ' + best['direction'] + ' ' + best['inst'] if best else 'NIE WCHODZIĆ'}"
    send_email(subject, body)
    print(body)

if __name__ == "__main__":
    main()
