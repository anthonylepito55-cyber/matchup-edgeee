"""MOVE THE TAKE RULE TO -6, UNGATE MC3/MC5, ADD THE MC2 6pt DOG CELL (2026-10-14).

User: "Do both and add All mc2 6 pt to dog tab", accepting both suggestions:
  1. let MC3 and MC5 accrue from the WHOLE forward log instead of yesterday's cutoff
  2. move the MC2 dog rule from -4 to -6

MEASURED, forward only (recon excluded), which is what motivated both:
  the threshold ladder on MC2's dog side
      0-2pt under  n=42   -32.17%        4-6pt   n=45    -4.20%   <- still losing
      2-3pt        n=8    -43.12%        6-8pt   n=48   +14.13%
      3-4pt        n=27    -1.89%        8pt+    n=207   +6.93%
  so the edge begins at 6pt, not 4. The -4 rule is +7.68% on 304 ($584); dropping the
  4-6pt slice gives +8.28% on 255. A small gain, but -4 was never where the turn was.

  forward sample under the -4 rule, by head
      MC2  n=304  +7.68%   (men +0.83% / women +16.50%)
      MC3  n=46   +1.65%   (1,326 of its 1,400 rows are recon)
      MC5  n=4   -32.00%   (552 of 565 recon)
  MC3 and MC5 are starved because TAKE_LIVE_FROM is 2026-10-13T16:00Z. Nothing about a
  frozen non-recon row from last week makes it unfit for these lanes -- the stamp was
  added because the RULE was written on 10-13, which is a reason to keep the stamped
  lanes as the clean in-sample-free record, not a reason to have no other record at all.

WHAT CHANGES
  * the take rule's dog threshold: -0.04 -> MC_TAKE_DOG = -0.06. The -4 version keeps
    running as *_take_dog4 so the move is measurable rather than asserted.
  * new *_take_dog_all / *_take_fav_all lanes with NO date stamp, forward rows only, so
    MC3 and MC5 have a sample now. The stamped lanes are untouched.
  * new mc2_dog6_all: MC2 six or more points over the market on the dog, ANY price,
    forward only -- the cell the user asked to put on the Dog picks tab.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tennis_log.py")
s = io.open(P, encoding="utf-8").read()
assert "MC_TAKE_DOG" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:95])
    s = s.replace(old, new)


# ------------------------------------------------------------------ the threshold constant
rep('TAKE_LIVE_FROM = "2026-10-13T16:00:00Z"',
    '''TAKE_LIVE_FROM = "2026-10-13T16:00:00Z"
# THE DOG THRESHOLD (2026-10-14, user "move the MC2 dog rule to -6"). The forward ladder put
# the turn at 6pt, not 4: 3-4pt -1.89% on 27, 4-6pt -4.20% on 45, 6-8pt +14.13% on 48, 8pt+
# +6.93% on 207. The -4 rule returned +7.68% on 304; cutting the 4-6pt slice gives +8.28% on
# 255. MC_TAKE_DOG4 keeps the old threshold alive as *_take_dog4 so the change is measured
# instead of assumed.
MC_TAKE_DOG = -0.06
MC_TAKE_DOG4 = -0.04''')

# ------------------------------------------------------------------------ register the lanes
rep('''              "mc2_take_fav", "mc2_take_dog", "mc3_take_fav", "mc3_take_dog",
              "both_take_fav", "both_take_dog",''',
    '''              "mc2_take_fav", "mc2_take_dog", "mc3_take_fav", "mc3_take_dog",
              "both_take_fav", "both_take_dog",
              # the OLD -4 threshold, kept so moving to -6 is measurable (2026-10-14)
              "mc2_take_dog4", "mc3_take_dog4", "mc5_take_dog4",
              # the same rules with NO date stamp, forward rows only. TAKE_LIVE_FROM exists
              # because the rule was written on 10-13, which keeps the stamped lanes free of
              # in-sample replay -- but it also left MC3 at n=46 and MC5 at n=4, so these
              # count every genuinely frozen row instead.
              "mc2_take_dog_all", "mc3_take_dog_all", "mc5_take_dog_all",
              "mc2_take_fav_all", "mc3_take_fav_all", "mc5_take_fav_all",
              # MC2 6pt+ over on the dog at ANY price -- the Dog picks tab cell
              # (2026-10-14, user "add All mc2 6 pt to dog tab")
              "mc2_dog6_all",''')

# ------------------------------------------------------------------------------- the rule
rep('''                if _ov >= 0:
                    bet("%s_take_fav" % _tag, not dog1)
                    _tk[_tag] = "fav"
                elif _ov <= -0.04 or _flip:
                    bet("%s_take_dog" % _tag, dog1)
                    _tk[_tag] = "dog"
                else:
                    _tk[_tag] = None                       # the dead zone between the rules''',
    '''                if _ov >= 0:
                    bet("%s_take_fav" % _tag, not dog1)
                    _tk[_tag] = "fav"
                elif _ov <= MC_TAKE_DOG or _flip:
                    bet("%s_take_dog" % _tag, dog1)
                    _tk[_tag] = "dog"
                else:
                    _tk[_tag] = None                       # the dead zone between the rules
                # the old -4 threshold, scored alongside so the move to -6 is measurable
                if _ov <= MC_TAKE_DOG4 or _flip:
                    bet("%s_take_dog4" % _tag, dog1)''')

# ------------------------------- the unstamped versions, outside the TAKE_LIVE_FROM gate
rep('''            if _tk.get("mc2") and _tk.get("mc2") == _tk.get("mc3"):''',
    '''            # THE SAME RULES WITH NO DATE STAMP (2026-10-14). Forward rows only -- a recon
            # backfill still cannot enter a money lane -- but every frozen row counts, which is
            # the only way MC3 and MC5 have a readable sample before next month.
            for _tag9, _pv9, _rc0 in (("mc2", r.get("mc2_p1"), r.get("mc2_recon")),
                                      ("mc3", r.get("mc3_p1"), r.get("mc3_recon")),
                                      ("mc5", r.get("mc5_p1"), r.get("mc5_recon"))):
                if pd.isna(_pv9) or (pd.notna(_rc0) and bool(_rc0)):
                    continue
                _pv9 = float(_pv9)
                _fp9 = _pv9 if not dog1 else 1 - _pv9
                _ov9 = _fp9 - max(mk1, 1 - mk1)
                if _ov9 >= 0:
                    bet("%s_take_fav_all" % _tag9, not dog1)
                elif _ov9 <= MC_TAKE_DOG or _fp9 < 0.5:
                    bet("%s_take_dog_all" % _tag9, dog1)
                # MC2 6pt+ over on the DOG at any price -> the Dog picks tab cell. Same
                # threshold as the new take rule but without the flip clause, so it is the
                # plain "MC2 is 6 points better than the price on this dog" statement.
                if _tag9 == "mc2" and _ov9 <= -0.06:
                    bet("mc2_dog6_all", dog1)
            if _tk.get("mc2") and _tk.get("mc2") == _tk.get("mc3"):''')

# ----------------------------------------------------------- record picks for the new cell
rep('''               "dma_dog", "mc2_dog_band", "cgray_dog_late", "ovl_dog", "fight_mc4_dog"}''',
    '''               "dma_dog", "mc2_dog_band", "cgray_dog_late", "ovl_dog", "fight_mc4_dog",
               # 2026-10-14: MC2 6pt+ on the dog, any price, and the unstamped take-dog lanes
               "mc2_dog6_all", "mc2_take_dog_all", "mc3_take_dog_all", "mc5_take_dog_all"}''')

io.open(P, "w", encoding="utf-8", newline="").write(s)
import ast

ast.parse(s)
print("patched tennis_log.py -- syntax OK")
for k in ("MC_TAKE_DOG", "mc2_dog6_all", "take_dog_all", "take_dog4"):
    print("   %-16s refs %d" % (k, s.count(k)))
print("RESULT: OK")
