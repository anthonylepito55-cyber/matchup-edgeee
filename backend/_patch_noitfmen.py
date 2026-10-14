"""DROP ITF MEN FROM THE DOG TAB (2026-10-14, user: "Okay remove all itf men").

Measured on the tab's own basis -- deduped one row per dog, <= +300, gender-gated, $25 flat:

    WTA (tour)        n=134  64-70   +20.98%  +$702.79   t  1.92
    ATP challenger    n=216  98-118  +11.56%  +$624.30   t  1.39
    ATP (tour)        n=72   34-38   +11.43%  +$205.75   t  0.82
    ITF women         n=59   26-33   +14.39%  +$212.25   t  0.86
    ITF MEN           n=27    9-18   -26.15%  -$176.50   t -1.30   <- the only negative league

ITF men is the only league-level negative, and it was dragging the collapsed ITF figure down to
+1.66% while ITF women alone is +14.39%. Its worst slice is +100..+150 (-11.81% on 48 across both
ITF genders), which is also where the volume is.

Honest about the size: 27 bets at t = -1.30 is not statistically established, so this is the
user's call on a consistent lean rather than a proven dead cell. It is consistent with
project_itf_stats_audit -- 91% of ITF players have no stat context at all, so the heads are
working from almost nothing there.

Applied everywhere on the tab: the live/upcoming list, the history view, the daily boxes, the
price bands and the per-cell pick histories. The LANE records underneath are untouched and still
include ITF men, so the by-cell ROI/t figures remain the full-sample numbers -- flipping this
back is one constant.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "frontend", "src", "DogPicksPanel.jsx")
P = os.path.normpath(P)
s = io.open(P, encoding="utf-8").read()
assert "leagueOK" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


rep("const MAX_AM = 300\nconst priceOK = p => p.odds != null && p.odds <= MAX_AM",
    """const MAX_AM = 300
const priceOK = p => p.odds != null && p.odds <= MAX_AM

// LEAGUE GATE (2026-10-14, user "Okay remove all itf men"). ITF men is the only league whose
// dog ROI is negative on this tab's own basis: -26.15% on 27 (9-18, -$176.50, t -1.30) against
// WTA +20.98%, ATP challenger +11.56%, ATP tour +11.43% and ITF women +14.39%. It was also the
// half dragging collapsed ITF down to +1.66% while ITF women alone is +14.39%.
//
// 27 bets is not a settled verdict, so this is a lean the user called rather than a proven dead
// cell -- though it fits the ITF stats audit, where 91% of ITF players have no stat context and
// the heads are working from nearly nothing. The LANE records underneath still include ITF men,
// so the per-cell ROI and t columns stay full-sample and this is one constant to reverse.
const DROP_LEAGUES = new Set(['itf_men'])
const leagueOK = p => !DROP_LEAGUES.has(String(p.league || '').toLowerCase())""")

# the aggregates (daily boxes, price bands, history)
rep("""    for (const p of cel.picks) {
      if (!priceOK(p)) continue
      if (!genderOK(cel.c, genderOf(p))) continue""",
    """    for (const p of cel.picks) {
      if (!priceOK(p) || !leagueOK(p)) continue
      if (!genderOK(cel.c, genderOf(p))) continue""")

# the live/upcoming list
rep("      if (!priceOK(p)) continue          // nothing above +300",
    "      if (!priceOK(p) || !leagueOK(p)) continue   // nothing above +300, no ITF men")

# the per-cell pick histories
rep("                    {cel.picks.filter(priceOK).slice()",
    "                    {cel.picks.filter(p => priceOK(p) && leagueOK(p)).slice()")

# say so in the header
rep("nothing above <b>+300</b> is shown — above that price the archive runs −17% to −18% at any model margin.",
    "nothing above <b>+300</b> is shown — above that price the archive runs −17% to −18% at any model margin. "
    "<b>ITF men is excluded</b>: it is the only league with a negative dog ROI here (−26.2% on 27, against WTA +21.0%, "
    "ATP challenger +11.6%, ATP tour +11.4%, ITF women +14.4%). Per-cell ROI and t below are still full-sample.")

rep("              DAILY — one row per dog, deduped across cells, $25 flat, nothing above +{MAX_AM}",
    "              DAILY — one row per dog, deduped across cells, $25 flat, ≤ +{MAX_AM}, no ITF men")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched DogPicksPanel.jsx -- leagueOK refs %d" % s.count("leagueOK"))
print("RESULT: OK")
