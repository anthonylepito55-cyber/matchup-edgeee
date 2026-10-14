"""EXTEND MODEL P PAST +250 AND -250 (2026-10-13, user: "and model p can go over -250 and over
+250 now").

Both asks are the SAME widening, because a dog longer than +250 is a favourite shorter than -250
on the other side of the same match. So the dog universe goes 2.0 -> 6.0 decimal (+100..+500) and
the favourite gate goes 2.0 -> 1.2 decimal (-100..-500).

RETRAINED, NOT JUST UNGATED. P is an offset model fitted only on +100..+250 dogs; lifting the
runtime filter alone would apply its coefficients to prices it has never seen. The universe was
widened at TRAINING time and the walk-forward re-run (_model_p_wide_build.py), and widening did
NOT damage the original band -- men +100..+200 went +14.5% -> +14.8%, women +200..+250 +27.2% ->
+33.7% -- so one artifact serves both and no second model is needed.

MEASURED OUT OF SAMPLE (walk-forward, two-level, 2024-26):

  FAVOURITES below -250, P fav EV >= 3%   <-- the well-motivated half
      men    n=1,481  hit 83.9%  +10.0%   (2024 +13.0 / 2025  +7.2 / 2026 +11.0)
      women  n=1,512  hit 87.0%  +13.7%   (2024 +15.3 / 2025 +13.3 / 2026 +13.0)
      -400 and shorter on its own: men +10.9%, women +13.6%, every year positive
      Blind backing of favourites below -250 is already +3.6%/+4.4%, which matches the
      independently measured favourite-longshot bias (-400 and shorter UNDERpriced by +2.1pt).

  DOGS above +250, P EV >= 5%             <-- backtests well but shows decay
      men    n=1,130  +13.3%  but 2026 only +2.9% (and +250..+400 alone is -6.9% in 2026)
      women  n=  953  +32.3%  leaning on a +78.2% 2024
      This region is measured OVERpriced by 1.7-2.2pt, so dogs there should be HARDER, not
      easier. The +400+ cells are ~180 bets of mostly losers plus a few big winners.

SO: WATCH-ONLY, NO BOARD MARKS. Both extensions are registered as their own lanes and nothing is
promoted. That is not timidity, it is this project's record: every archive FAVOURITE cell that
backtested well has died forward (604 live favourite settles -9.7% against 377 dog settles
+16.1%, six fav cells failed in a row), and this is a backtest showing favourites paying +10-14%.
Board colour changes need a live lane record plus explicit sign-off.
"""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def patch(name, pairs):
    p = os.path.join(HERE, name)
    s = io.open(p, encoding="utf-8").read()
    for old, new in pairs:
        assert s.count(old) == 1, "%s: found %d of %r" % (name, s.count(old), old[:70])
        s = s.replace(old, new)
    io.open(p, "w", encoding="utf-8", newline="").write(s)
    print("patched %s" % name)


# ------------------------------------------------------------------- tennis_model_p.py: bands
patch("tennis_model_p.py", [
    ('BAND = {"M": 3.0, "W": 3.5}',
     '''# WIDENED 2026-10-13 (user: "model p can go over -250 and over +250 now") from
# {"M": 3.0, "W": 3.5} to +500 both genders, with the model RETRAINED on the wider
# universe rather than the filter merely lifted. See _patch_p_wide.py for the numbers;
# the new regions are watch-only lanes (p_dog_250up / p_fav_250up), not board marks.
BAND = {"M": 6.0, "W": 6.0}
# the favourite gate's shortest acceptable price. 1.2 decimal = -500, the paired side of
# a +500 dog. Was 1.5 (-200).
FAV_DEC_MIN = 1.2'''),
    ("    fav_bet = bool(fev is not None and 1.5 <= fod <= 2.0 and fev >= EV_FAV)",
     "    fav_bet = bool(fev is not None and FAV_DEC_MIN <= fod <= 2.0 and fev >= EV_FAV)"),
    ('    if od is None or not (2.0 <= od <= BAND[G]):',
     '    if od is None or not (2.0 <= od <= BAND[G]):'),
])
# the replay path carries its own copy of the favourite gate
patch("tennis_model_p.py", [
    ('"fav_bet": bool(fev is not None and 1.5 <= fo <= 2.0 and fev >= EV_FAV), "recon": recon,',
     '"fav_bet": bool(fev is not None and FAV_DEC_MIN <= fo <= 2.0 and fev >= EV_FAV),\n'
     '            "recon": recon,'),
])

# ----------------------------------------------------------------------- tennis_log.py: lanes
OLD_FAV = '''                if _pf9 is not None and pd.notna(_pf9) and float(_pf9) >= 0.03 and 1.5 <= _fd9 <= 2.0:
                    bet("p_fav", not _ps9)'''
NEW_FAV = '''                if _pf9 is not None and pd.notna(_pf9) and float(_pf9) >= 0.03 and 1.5 <= _fd9 <= 2.0:
                    bet("p_fav", not _ps9)
                # P BAND EXTENSION (2026-10-13, user "model p can go over -250 and over
                # +250 now"). P was retrained on dogs out to +500 / favourites in to -500
                # (_model_p_wide_build.py). The two new regions are scored as SEPARATE
                # lanes because they are different bets and the evidence for them is not
                # the same strength:
                #   favourites below -250, P fav EV >= 3%  -- walk-forward men +10.0%
                #     (n=1,481) and women +13.7% (n=1,512), every year positive both
                #     genders, and the region is independently measured UNDERpriced by
                #     +2.1pt. The better-motivated half.
                #   dogs above +250, P EV >= 5%  -- walk-forward men +13.3% and women
                #     +32.3%, BUT men's 2026 is only +2.9% (+250..+400 alone -6.9%), the
                #     women's figure leans on a +78% 2024, and the region is measured
                #     OVERpriced by 1.7-2.2pt, so a good number here is suspect.
                # Watch-only. No board mark until the live lanes say something, per the
                # colour-promotion rule and the six archive favourite cells that have
                # already failed forward.
                if _pf9 is not None and pd.notna(_pf9) and float(_pf9) >= 0.03 and _fd9 < 1.5:
                    bet("p_fav_250up", not _ps9)
                    if _fd9 < 1.25:
                        bet("p_fav_400up", not _ps9)
                if float(_pe9) >= 0.05 and (d1 if _ps9 else d2) > 3.5:
                    bet("p_dog_250up", _ps9)
                    if (d1 if _ps9 else d2) > 5.0:
                        bet("p_dog_400up", _ps9)'''
patch("tennis_log.py", [
    (OLD_FAV, NEW_FAV),
    ('"p_dog_w250", "p_dog_flip", "p_close",',
     '"p_dog_w250", "p_dog_flip", "p_dog_250up", "p_dog_400up",\n'
     '              "p_fav_250up", "p_fav_400up", "p_close",'),
    ('ASYM_LIVE_FROM = "2026-10-13T22:00:00Z"',
     'ASYM_LIVE_FROM = "2026-10-13T22:00:00Z"\n'
     '# Model P band extension went live with the same deploy. The four p_*_250up/400up lanes\n'
     '# did not exist before it, so they carry no pre-stamp history to replay.\n'
     'P_WIDE_LIVE_FROM = "2026-10-13T22:00:00Z"'),
])

# ------------------------------------------------------------------------------------- verify
import re                                                            # noqa: E402

s = io.open(os.path.join(HERE, "tennis_model_p.py"), encoding="utf-8").read()
assert 'BAND = {"M": 6.0, "W": 6.0}' in s and "FAV_DEC_MIN = 1.2" in s
assert "1.5 <= fod" not in s and "1.5 <= fo <= 2.0" not in s, "a favourite gate was missed"
print("   tennis_model_p.py  bands widened, %d FAV_DEC_MIN refs" % len(re.findall(r"FAV_DEC_MIN", s)))
s = io.open(os.path.join(HERE, "tennis_log.py"), encoding="utf-8").read()
for lane in ("p_dog_250up", "p_dog_400up", "p_fav_250up", "p_fav_400up"):
    assert s.count('"%s"' % lane) >= 2, "%s not both registered and bet" % lane
    print("   lane %-14s registered + wired" % lane)
print("RESULT: OK")
