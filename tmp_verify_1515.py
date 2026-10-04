#!/usr/bin/env python3
import math
from datetime import datetime
from zoneinfo import ZoneInfo
import blofin_alert_15m as s

def fprice(x):
    return s.fmt_price(x) if x is not None else "-"

top=s.top_usdt_swaps()
print("VERIFY_TIME", datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d %H:%M:%S UK"))
print("TOP10", ", ".join(f"{r['inst']} {r['change24']:.2f}%" for r in top))
print()

for row in top:
    inst=row["inst"]
    try:
        b=s.candles(inst)
        k,d=s.stochastic_8_3(b)
        a=s.atr(b)
        i=len(b)-1
        close=b[i]["c"]
        direction=s.current_direction(k[i],d[i])
        change8=(close/b[i-7]["c"]-1.0)*100.0
        support,resistance=s.nearest_levels(b,a,i)
        print(f"{inst} close={fprice(close)} K={k[i]:.2f} D={d[i]:.2f} change8={change8:.3f}%")
        if direction==0:
            print("  REJECT: brak czystego kierunku Stochastic(8,3)")
            continue
        dname="LONG" if direction==1 else "SHORT"
        print("  DIR:",dname)
        if direction==1 and change8<=0:
            print("  REJECT: LONG niezgodny z kierunkiem 8 świec")
            continue
        if direction==-1 and change8>=0:
            print("  REJECT: SHORT niezgodny z kierunkiem 8 świec")
            continue
        print(f"  support={fprice(support['price']) if support else '-'} resistance={fprice(resistance['price']) if resistance else '-'}")
        if direction==1:
            if not resistance:
                print("  REJECT: brak oporu powyżej ceny")
                continue
            target_price=resistance["price"]
            target_pct=(target_price-close)/close*100.0
        else:
            if not support:
                print("  REJECT: brak wsparcia poniżej ceny")
                continue
            target_price=support["price"]
            target_pct=(close-target_price)/close*100.0
        print(f"  target={fprice(target_price)} target_pct={target_pct:.3f}%")
        if target_pct < s.MIN_TARGET_PCT:
            print(f"  REJECT: cel < {s.MIN_TARGET_PCT:.1f}%")
            continue
        bt=s.backtest_current_setup(b,k,d,direction,target_pct)
        hr=bt["hit_rate"]
        print(f"  backtest decided={bt['decided']} wins={bt['wins']} losses={bt['losses']} unresolved={bt['unresolved']} hit_rate={hr:.3f}%")
        if bt["decided"] < s.MIN_DECIDED:
            print(f"  REJECT: mniej niż {s.MIN_DECIDED} rozstrzygniętych przypadków")
        elif hr is None or hr < s.MIN_HIT_RATE:
            print(f"  REJECT: hit rate < {s.MIN_HIT_RATE:.0f}%")
        else:
            print("  PASS")
    except Exception as e:
        print(inst,"ERROR",repr(e))
    print()
