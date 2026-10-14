"""BROWN FAVOURITE MARKS MUST CLEAR THE PRICE, NOT THE DE-VIGGED MARKET (2026-10-13).

User: "Then why do I have a brown bet signal on bouzkova". Marie Bouzkova -196 vs Maja
Chwalinska +162. She lost, and the card carried a brown 🟤 MC2 FAV 2-8pt mark reading
"2.1pt over".

WHAT WENT WRONG. The band is measured against the DE-VIGGED market, but you pay the real price,
and de-vigging splits the book's margin across both sides. At -196 the break-even on Bouzkova is
66.2% while the de-vigged market reads 63.4%:

    MC2 frozen pre-tilt   62.3%   ->  1.2pt UNDER the market  ->  no mark
    MC2 post-tilt         65.5%   ->  2.1pt OVER the market   ->  BROWN MARK
    break-even at -196    66.2%   ->  the mark was a -1.0% bet by MC2's own number

So today's sample-asymmetry tilt is what created this mark, and the mark was negative EV even
after it. Surveyed across that board: 7 of the 9 brown MC2 favourite marks were NEGATIVE EV at
the offered price (Andreescu -2.4%, Koevermans -1.5%, Teichmann -1.2%, Bouzkova -1.0%,
Passaro -0.8%, Grabher -0.7%, Justo -0.2%).

THE FIX is a COHERENCE requirement, not a backtest claim: a mark cannot recommend backing a
favourite that the head itself prices below break-even. There is no sample size at which that
becomes profitable. (Tested separately as a PREDICTIVE filter it was ambiguous -- MC2's sub-vig
marks ran -20.4% vs -0.3% for the rest, but MC3's ran the other way -- which is a reason to
distrust the heads' favourite side generally, not a reason to keep recommending negative-EV bets.)

Applied in two places that must stay in lockstep:
  * the board (TennisSection.jsx, already patched): all three brown FAV cells require
    mcfav * fav_decimal - 1 >= 0, and fail CLOSED when the price is missing.
  * this file: parallel *_ev study keys that score only the marks which clear the price, so the
    ungated record stays visible as the control and nothing is silently rewritten.

DOG cells are untouched. They are defined by the head sitting UNDER the market, not by a margin
over it, so the de-vig asymmetry does not apply the same way.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tennis_log.py")
s = io.open(P, encoding="utf-8").read()
assert "_favev_key" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


# 1. register the parallel EV-gated keys
rep('''    _m2 = {k: {"v": [], "m": [], "w": [], "p": 0}
           for k in ("mc2_fav_on", "mc2_fav_band", "mc2_fav_deep", "mc2_dog_flip",
                     "mc2_dog3", "mc2_dog_dead", "mc2_dog_long")}''',
    '''    # the *_ev keys (2026-10-13) score only the FAVOURITE marks that clear break-even at the
    # offered price. The ungated keys stay as the control: 7 of 9 brown favourite marks on the
    # board that prompted this were negative EV, so the two records should diverge.
    _m2 = {k: {"v": [], "m": [], "w": [], "p": 0}
           for k in ("mc2_fav_on", "mc2_fav_band", "mc2_fav_deep", "mc2_dog_flip",
                     "mc2_dog3", "mc2_dog_dead", "mc2_dog_long",
                     "mc2_fav_on_ev", "mc2_fav_band_ev", "mc2_fav_deep_ev")}''')

# 2. after the key is chosen, derive the EV-gated twin
rep('''            decm = d1m if takes1 else d2m
            _st3 = bool(rr["settled"]) and not pd.isna(rr["p1_won"])''',
    '''            decm = d1m if takes1 else d2m
            # EV at the offered price, for the favourite cells only. mcfav is MC2's own
            # probability on the favourite and _favodd its decimal price, so mcfav*_favodd - 1
            # is MC2's own EV on the bet the mark recommends. Negative means the mark cannot
            # make money by its own numbers.
            _favev_key = None
            if key in ("mc2_fav_on", "mc2_fav_band", "mc2_fav_deep"):
                if (mcfav * _favodd - 1.0) >= 0.0:
                    _favev_key = key + "_ev"
            _st3 = bool(rr["settled"]) and not pd.isna(rr["p1_won"])''')

# 3. mirror the pick and the P/L into the twin
rep('''            if not _st3:
                _m2[key]["p"] += 1
                continue
            _lg3 = str(rr.get("league") or "")
            _m2[key]["v"].append(pnl3)
            _m2[key]["w" if ("wta" in _lg3 or "itf_women" in _lg3) else "m"].append(pnl3)''',
    '''            if _favev_key:
                _m2picks[_favev_key].append(dict(_m2picks[key][-1]))
            if not _st3:
                _m2[key]["p"] += 1
                if _favev_key:
                    _m2[_favev_key]["p"] += 1
                continue
            _lg3 = str(rr.get("league") or "")
            _wm3 = "w" if ("wta" in _lg3 or "itf_women" in _lg3) else "m"
            for _k3 in (key, _favev_key) if _favev_key else (key,):
                _m2[_k3]["v"].append(pnl3)
                _m2[_k3]["w" if _wm3 == "w" else "m"].append(pnl3)''')

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched tennis_log.py")
for k in ("mc2_fav_on_ev", "mc2_fav_band_ev", "mc2_fav_deep_ev", "_favev_key"):
    print("   %-18s refs %d" % (k, s.count(k)))
import ast
ast.parse(s)
print("syntax OK")
print("RESULT: OK")
