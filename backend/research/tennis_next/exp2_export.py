"""EXP2 display export — builds a compact read-only JSON snapshot of the paper experiment
for the site's NEXT tab. Reads the ledger; writes ONLY tennis_next_public.json (here and,
at deploy time, copied to backend/data_cache/). Changes nothing official.
"""
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import exp2_paper as P  # noqa: E402

OUT = os.path.join(HERE, "tennis_next_public.json")


def build():
    led = P.Ledger(os.path.join(HERE, "exp2_ledger"))
    preds = sorted(led.of_type("prediction"), key=lambda e: e["start_ts"])
    latest = P._latest_settlements(led)
    rep = P.report(led)
    rows = []
    for e in preds:
        st = latest.get(e["fixture_id"])
        if st is None:
            status = "pending"
        elif st["winner"] == "void":
            status = "void"
        else:
            status = "p%d_won" % st["winner"]
        B = e["strategies"]["B"]
        rows.append({
            "players": e["players"], "league": e["league"],
            "tournament": (e.get("tournament") or "").strip("/").split("/")[0][:28],
            "start_utc": dt.datetime.fromtimestamp(e["start_ts"], dt.timezone.utc)
            .strftime("%m-%d %H:%M"),
            "pE": round(e["pE"], 4), "mkt": round(e["market_input"]["p1"], 4),
            "shadow": round(e.get("pE_sym_shadow", e["pE"]), 4),
            "selA": e["strategies"]["A"]["bet"],
            "selB": ({"venue": B["venue"], "side": B["side"],
                      "implied": round(B["implied_p"], 4), "ev": round(B["ev"], 4)}
                     if B.get("bet") else None),
            "selC": e["strategies"]["C"]["bet"],
            "ctrlB": e["controls"]["B"].get("bet", False),
            "status": status,
        })

    def strat(tag, s):
        d = rep[tag][s]
        return {"selections": d["selections"], "settled": d["selections_settled"],
                "hit": round(d["hit"], 4) if d["hit"] is not None else None,
                "roi": round(d["roi"], 4) if d["roi"] is not None else None,
                "avg_odds": round(d["avg_odds"], 3) if d["avg_odds"] else None,
                "bankroll": round(d["bankroll_final"], 3) if d["bankroll_final"] is not None
                else None,
                "max_dd": round(d["max_drawdown"], 3) if d["max_drawdown"] is not None
                else None,
                "no_bet_days": d["no_bet_days"], "capped": d["capped"]}

    # MODEL ACCURACY on the settled cohort (2026-10-20, user "how has cohort been" /
    # "am i able to see those models?"). Winner accuracy, log loss and Brier for Model E,
    # Model A and the market price, on exactly the same settled fixtures.
    import math as _math
    acc_rows = []
    for e in preds:
        st = latest.get(e["fixture_id"])
        if st is None or st.get("winner") not in (1, 2):
            continue
        mi = e.get("market_input") or {}
        acc_rows.append({"pE": e.get("pE"), "pA": e.get("pA"), "mkt": mi.get("p1"),
                         "y": 1 if st["winner"] == 1 else 0})

    def _m(key):
        r = [x for x in acc_rows if x.get(key) is not None]
        if not r:
            return None
        c = sum(1 for x in r if (x[key] >= 0.5) == (x["y"] == 1))
        ll = -sum(_math.log(max(min(x[key] if x["y"] == 1 else 1 - x[key],
                                    1 - 1e-9), 1e-9)) for x in r) / len(r)
        br = sum((x[key] - x["y"]) ** 2 for x in r) / len(r)
        return {"n": len(r), "correct": c, "acc": round(c / len(r), 4),
                "logloss": round(ll, 4), "brier": round(br, 4)}

    _dis = [x for x in acc_rows if x.get("pE") is not None and x.get("mkt") is not None
            and (x["pE"] >= 0.5) != (x["mkt"] >= 0.5)]
    models = {
        "settled_scored": len(acc_rows),
        "E": _m("pE"), "A": _m("pA"), "market": _m("mkt"),
        "agree_with_market": sum(
            1 for x in acc_rows if x.get("pE") is not None and x.get("mkt") is not None
            and (x["pE"] >= 0.5) == (x["mkt"] >= 0.5)),
        "disagreements": len(_dis),
        "E_right_on_disagreements": sum(1 for x in _dis
                                        if (x["pE"] >= 0.5) == (x["y"] == 1)),
        "PRELIMINARY": "tiny sample; where E and the market never disagree they score "
                       "identically on winners by construction, so only calibration "
                       "separates them and that needs far more settled matches",
    }

    fz = led.of_type("protocol_freeze")[0]
    out = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "protocol_sha8": fz["protocol_sha256"][:8],
        "artifact_sha8": fz["artifact_models_sha256"][:8],
        "ledger_events": len(led.events),
        "predictions": len(preds), "settled": rep["settled"],
        "pending": len(preds) - rep["settled"],
        "days": rep["days"],
        "models": models,
        "strategies": {s: strat("strategies", s) for s in ("A", "B", "C")},
        "controls": {s: strat("controls", s) for s in ("A", "B", "C")},
        "rows": rows,
    }
    led.close()
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print("wrote", OUT, "| preds", len(preds), "| settled", rep["settled"])


if __name__ == "__main__":
    build()
