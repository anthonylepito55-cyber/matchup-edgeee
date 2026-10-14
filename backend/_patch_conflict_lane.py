"""BOTH-MARKED CONFLICTS: WHICH SIDE WINS (2026-10-14).

User: "add that lane" -- after Nedic -132 (gold favourite) and Sanchez Quilez +102 (pink s52 dog)
appeared as two marks on ONE match, opposite bets, with nothing recording which side was right.

WHY THE CONFLICT EXISTS AT ALL, and why it can only take one shape: the gold favourite mark is
MC2 four or more points over the market ON THE FAVOURITE, and three of the pink dog marks are MC2
four or six points over ON THE DOG. Those are opposite statements about the same number, so they
can never both fire. A conflict therefore requires a NON-MC2 dog mark -- the s52 seasonal-band dog
or the c75 dog flip -- landing opposite an MC2 gold favourite. That is exactly the Nedic case.

TWO LANES, same rows, opposite sides, so the comparison is paired game by game:
    conflict_gold_fav   back the FAVOURITE (the gold mark)
    conflict_pink_dog   back the DOG       (the pink mark)

THE MARK CONDITIONS, copied from the board rather than approximated:
    GOLD favourite   MC2 >= 4pt over the de-vigged market on the favourite, and
                     women -100..-200, men -100..-150   (the men's deep half is NOT marked)
    PINK dog (non-MC2, the only kind that can conflict):
        s52  the FAVOURITE owns both 52-week seasonal stats and the dog is +100..+200, with
             men +100..+150, women +100..+200
        c75  c75 puts the market dog past 50%, men +100..+150 only

Forward rows only -- recon rows are skipped, like every other lane.

WATCH ONLY. Nothing reads these to gate a pick or paint a card. They exist so that in a few weeks
there is a number instead of an impression.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tennis_log.py")
s = io.open(P, encoding="utf-8").read()
assert "conflict_gold_fav" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


# register the two lanes beside the s52 pair
rep('''            for k in ("s52_fav_band_dog", "s52_dog_band_dog")}''',
    '''            for k in ("s52_fav_band_dog", "s52_dog_band_dog")}
    # 🥇 vs 🧡 CONFLICTS (2026-10-14, user "add that lane"). One match, two marks, opposite
    # sides. Only a NON-MC2 dog mark can conflict with the MC2 gold favourite -- the MC2 dog
    # marks are the same number with the sign flipped, so they can never both fire. Watch only.
    _cfl = {k: {"v": [], "m": [], "w": [], "p": 0, "picks": []}
            for k in ("conflict_gold_fav", "conflict_pink_dog")}''')

# the scoring pass, immediately after the s52 one
rep('''        for k, v in _s52.items():
            # every pick is a DOG by construction, so dog == overall and fav is empty
            study_out[k] = {**agg(v["v"]), "pending": int(v["p"]),
                            "picks": v["picks"],''',
    '''        # ---- 🥇 vs 🧡 CONFLICT PASS (2026-10-14) ----
        # A row qualifies when the GOLD favourite mark and a non-MC2 PINK dog mark both fire on
        # it. Both lanes then record the SAME rows on OPPOSITE sides, so the comparison is paired.
        _c75col = "mc_c75_p1" in log.columns
        for _, rr in _sq.iterrows():
            if "surface_bad" in _sq.columns:
                _sbx = rr.get("surface_bad")
                if _sbx is not None and not pd.isna(_sbx) and bool(_sbx):
                    continue
            _m2 = rr.get("mc2_p1")
            _rc = rr.get("mc2_recon")
            if pd.isna(_m2) or (pd.notna(_rc) and bool(_rc)):
                continue                       # forward rows only
            d1c, d2c = _decimal(rr["p1_odds"]), _decimal(rr["p2_odds"])
            if not d1c or not d2c:
                continue
            i1c, i2c = 1 / d1c, 1 / d2c
            mk1c = i1c / (i1c + i2c)
            dg1 = mk1c < 0.5                   # player_1 is the market dog
            _lgc = str(rr.get("league") or "").lower()
            _isw = ("wta" in _lgc) or ("itf_women" in _lgc)
            dodd = float(rr["p1_odds"] if dg1 else rr["p2_odds"])
            fdec = d2c if dg1 else d1c
            famt = ((fdec - 1) * 100 if fdec >= 2 else -100.0 / max(fdec - 1, 1e-9))

            # --- the GOLD favourite mark ---
            _fp = (1 - float(_m2)) if dg1 else float(_m2)      # MC2 on the favourite
            _ov = _fp - max(mk1c, 1 - mk1c)
            _lo = -200.0 if _isw else -150.0                   # mens deep half is NOT marked
            if not (_ov >= 0.04 and _lo <= famt <= -100.0):
                continue

            # --- a non-MC2 PINK dog mark on the other side ---
            _pink = False
            _ds = (1.0 if dg1 else -1.0) * (float(rr["s52_sgw_p1"]) - float(rr["s52_sgw_p2"]))
            _dr = (1.0 if dg1 else -1.0) * (float(rr["s52_rgw_p1"]) - float(rr["s52_rgw_p2"]))
            if _ds < 0 and _dr < 0 and 100 <= dodd <= (200 if _isw else 150):
                _pink = True                                   # s52 seasonal-band dog
            if not _pink and _c75col and not _isw and 100 <= dodd <= 150:
                _c75 = rr.get("mc_c75_p1")
                if pd.notna(_c75):
                    _c75d = (float(_c75) if dg1 else 1 - float(_c75))
                    if _c75d >= 0.5:
                        _pink = True                           # c75 dog flip, men +100..+150
            if not _pink:
                continue

            _set = bool(rr["settled"]) and not pd.isna(rr["p1_won"])
            for _k, _side1 in (("conflict_gold_fav", not dg1), ("conflict_pink_dog", dg1)):
                _dec = d1c if _side1 else d2c
                _w = (bool(rr["p1_won"]) == _side1) if _set else None
                _cfl[_k]["picks"].append({
                    "date": str(rr.get("date"))[:10], "league": rr.get("league"),
                    "start": str(rr.get("start_time_utc") or ""),
                    "tournament": rr.get("tournament"), "surface": rr.get("surface"),
                    "p1": rr.get("player_1"), "p2": rr.get("player_2"),
                    "pick": rr.get("player_1") if _side1 else rr.get("player_2"),
                    "opp": rr.get("player_2") if _side1 else rr.get("player_1"),
                    "odds": int(rr["p1_odds"] if _side1 else rr["p2_odds"]),
                    "ue_gap": None, "score": rr.get("score"), "settled": _set,
                    "won": _w,
                    "pnl": (None if not _set else round(
                        25.0 * (_dec - 1.0) if _w else -25.0, 2)),
                })
                if not _set:
                    _cfl[_k]["p"] += 1
                    continue
                _p = 25.0 * (_dec - 1.0) if _w else -25.0
                _cfl[_k]["v"].append(_p)
                _cfl[_k]["w" if _isw else "m"].append(_p)
        for k, v in _cfl.items():
            _isfav = k.endswith("_fav")
            study_out[k] = {**agg(v["v"]), "pending": int(v["p"]), "picks": v["picks"],
                            "m": agg(v["m"]), "w": agg(v["w"]),
                            "dog": agg([] if _isfav else v["v"]),
                            "fav": agg(v["v"] if _isfav else []),
                            "m_dog": agg([] if _isfav else v["m"]),
                            "m_fav": agg(v["m"] if _isfav else []),
                            "w_dog": agg([] if _isfav else v["w"]),
                            "w_fav": agg(v["w"] if _isfav else [])}

        for k, v in _s52.items():
            # every pick is a DOG by construction, so dog == overall and fav is empty
            study_out[k] = {**agg(v["v"]), "pending": int(v["p"]),
                            "picks": v["picks"],''')

io.open(P, "w", encoding="utf-8", newline="").write(s)
import ast

ast.parse(s)
print("patched tennis_log.py -- syntax OK")
for k in ("conflict_gold_fav", "conflict_pink_dog"):
    print("   %-20s refs %d" % (k, s.count(k)))
print("RESULT: OK")
