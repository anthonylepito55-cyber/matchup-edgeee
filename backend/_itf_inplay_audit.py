"""ARE WE LOGGING ITF PRICES AFTER THE MATCH HAS STARTED? (2026-10-11, user: "itf lines are
moving mid game i mean odds")

If an ITF price is captured in-play it is not a closing line, and every ITF lane number built on
it is contaminated -- an in-play price already knows who is winning, so a "dog" that was logged
a set down is not the dog the market offered before the off.

There IS a guard (tennis_log.log_predictions, the Tarvet case 2026-10-07): never upsert a row
whose status is anything other than "unplayed". But that guard trusts the FEED's status, and ITF
is exactly where the feed is weakest -- qualifying and early-round ITF matches often carry a
nominal or stale start time, courts run early and late, and a match can be underway while the
slate still reports it as unplayed.

So this audits the outcome rather than the intent, three ways:
  A. rows whose logged_at is AFTER their own scheduled start
  B. how far the frozen price sits from the OPENING price, by league -- an in-play capture
     should show a much fatter tail than a pre-match one
  C. whether ITF looks different from tour/challenger on both measures, which is the tell
"""
import numpy as np
import pandas as pd

log = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
for c in ("date", "logged_at", "start_time_utc"):
    if c in log.columns:
        log[c] = pd.to_datetime(log[c], errors="coerce", utc=True)
lg = log["league"].astype(str)
log["grp"] = np.where(lg.str.contains("itf"), "ITF",
                      np.where(lg.str.contains("chall"), "challenger", "tour"))
print("log rows: %d   %s..%s" % (len(log), str(log.date.min())[:10], str(log.date.max())[:10]))
print("by group: %s\n" % dict(log.grp.value_counts()))

print("=" * 100)
print("A. ROWS LOGGED AFTER THEIR OWN SCHEDULED START")
print("=" * 100)
h = log[log.logged_at.notna() & log.start_time_utc.notna()].copy()
h["lag_min"] = (h.logged_at - h.start_time_utc).dt.total_seconds() / 60.0
print("   rows with both timestamps: %d of %d" % (len(h), len(log)))
for g, s in h.groupby("grp"):
    after = s[s.lag_min > 0]
    bad = s[s.lag_min > 10]            # >10 min past the off is not a clock-skew story
    print("   %-11s n=%-5d logged after start: %4d (%4.1f%%)  | >10min after: %3d (%4.1f%%)  "
          "| median lag %+7.1f min"
          % (g, len(s), len(after), 100 * len(after) / max(len(s), 1),
             len(bad), 100 * len(bad) / max(len(s), 1), s.lag_min.median()))
if len(h[h.lag_min > 10]):
    print("\n   worst offenders:")
    for r in h.nlargest(8, "lag_min").itertuples():
        print("      %-10s %-46s start %s  logged +%.0f min  odds %s/%s"
              % (r.grp, ("%s v %s" % (r.player_1, r.player_2))[:46],
                 str(r.start_time_utc)[:16], r.lag_min, r.p1_odds, r.p2_odds))

print("\n" + "=" * 100)
print("B. FROZEN PRICE vs OPENING PRICE -- an in-play capture should have a fat tail")
print("=" * 100)
if "open_p1_odds" in log.columns:
    o = log[log.open_p1_odds.notna() & log.p1_odds.notna()].copy()

    def prob(a):
        a = pd.to_numeric(a, errors="coerce")
        return np.where(a > 0, 100.0 / (a + 100.0), -a / (-a + 100.0))

    o["drift_pp"] = 100.0 * (prob(o.p1_odds) - prob(o.open_p1_odds))
    print("   rows with an opening price: %d" % len(o))
    print("   %-11s %6s %9s %9s %9s %9s" % ("group", "n", "median", "p90 |drift|",
                                            "p99 |drift|", ">25pp"))
    for g, s in o.groupby("grp"):
        ad = s.drift_pp.abs()
        print("   %-11s %6d %8.1fpp %10.1fpp %10.1fpp %8d" %
              (g, len(s), ad.median(), ad.quantile(0.90), ad.quantile(0.99),
               int((ad > 25).sum())))
    print("\n   a pre-match line drifts a few points; a price taken mid-match can sit 30-60pp")
    print("   from the open, so the >25pp column is the contamination count.")
    big = o[o.drift_pp.abs() > 25]
    if len(big):
        print("\n   examples of >25pp drift:")
        for r in big.nlargest(6, "drift_pp", keep="all").head(6).itertuples():
            print("      %-10s %-44s open %s -> frozen %s  (%+.0fpp)"
                  % (r.grp, ("%s v %s" % (r.player_1, r.player_2))[:44],
                     r.open_p1_odds, r.p1_odds, r.drift_pp))
else:
    print("   no open_p1_odds column -- cannot measure drift")

print("\n" + "=" * 100)
print("C. DOES THE ITF LANE RECORD DEPEND ON THE SUSPECT ROWS?")
print("=" * 100)
S = log[(log["settled"] == True) & log.p1_won.notna()          # noqa: E712
        & log.p1_odds.notna() & log.p2_odds.notna()].copy()
S = S[S.grp == "ITF"]
if "surface_bad" in S.columns:
    S = S[~S.surface_bad.fillna(False).astype(bool)]


def dec(a):
    a = float(a)
    return 1 + a / 100.0 if a > 0 else 1 + 100.0 / abs(a)


if len(S):
    S["d1"] = S.p1_odds.map(dec)
    S["d2"] = S.p2_odds.map(dec)
    i1, i2 = 1 / S.d1, 1 / S.d2
    S["mkt"] = i1 / (i1 + i2)
    S["dog1"] = S.mkt < 0.5
    S["lag_min"] = (S.logged_at - S.start_time_utc).dt.total_seconds() / 60.0

    def roi(s, lab):
        if len(s) < 10:
            print("   %-40s n=%d (thin)" % (lab, len(s)))
            return
        w = (s.p1_won.astype(bool) == s.dog1)
        odds = np.where(s.dog1, s.d1, s.d2)
        pnl = np.where(w, odds - 1, -1.0)
        print("   %-40s dog %d-%d  ROI %+6.1f%%  (n=%d)"
              % (lab, int(w.sum()), len(s) - int(w.sum()), 100 * pnl.mean(), len(s)))

    roi(S, "every settled ITF dog")
    roi(S[S.lag_min.isna() | (S.lag_min <= 0)], "   logged BEFORE start (clean)")
    roi(S[S.lag_min > 0], "   logged AFTER start (suspect)")
    roi(S[S.lag_min > 10], "   logged >10 min after start")
else:
    print("   no settled ITF rows")
