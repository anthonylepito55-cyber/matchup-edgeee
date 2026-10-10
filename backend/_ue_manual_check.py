"""VALIDATE HAND-ENTERED UNFORCED ERRORS (2026-10-10, user: "u can't go through games one by
one and get the avg we need?").

Unforced errors cannot be taken from the sources that have them (Flashscore's terms forbid
scraping and commercial reuse; ATP and the US Open robots-block their stats paths), and the
sources that permit access -- the WTA API, TennisExplorer -- do not carry the field at all. So
the remaining routes are a licensed feed or entering the numbers by hand.

This checks data_cache/mcp/manual_ue.csv before it reaches the model: that the columns parse,
that the names resolve to players the board actually knows, that nothing duplicates a row we
already have from the Match Charting Project, and -- the point of the exercise -- how many more
women's +100..+250 dog matches would gain a full two-sided profile as a result.

Run it after every batch of entries. It writes nothing; it only reports.
"""
import os
import sys

import pandas as pd

import tennis_ue as U

F = os.path.join("data_cache", "mcp", "manual_ue.csv")
REQ = ["match_id", "player", "opp", "Date", "G", "sets", "unforced"]


def main():
    if not os.path.exists(F):
        # data_cache is gitignored, so seed the working file from the tracked template
        tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manual_ue_template.csv")
        if os.path.exists(tpl):
            os.makedirs(os.path.dirname(F), exist_ok=True)
            with open(tpl, encoding="utf-8") as a, open(F, "w", encoding="utf-8") as b:
                b.write(a.read())
            print(f"created {F} from manual_ue_template.csv -- fill in rows and re-run")
        else:
            print(f"no file at {F} and no template to seed it from")
        return
    X = pd.read_csv(F, dtype=str, comment="#")
    X = X[X["player"].notna()] if "player" in X.columns else X
    print(f"{F}: {len(X)} rows")
    missing = [c for c in REQ if c not in X.columns]
    if missing:
        print(f"  ERROR: missing required columns {missing}")
        return
    if X.empty:
        print("  (template is empty -- fill in rows and re-run)")
        return

    bad = []
    for i, r in X.iterrows():
        why = []
        d = pd.to_datetime(str(r["Date"]), format="%Y%m%d", errors="coerce")
        if pd.isna(d):
            why.append("Date must be YYYYMMDD")
        for c in ("sets", "unforced"):
            if pd.isna(pd.to_numeric(r[c], errors="coerce")):
                why.append(f"{c} must be a number")
        if str(r.get("G", "")).upper() not in ("M", "W"):
            why.append("G must be M or W")
        s = pd.to_numeric(r["sets"], errors="coerce")
        if pd.notna(s) and not (1 <= s <= 5):
            why.append("sets out of range")
        u = pd.to_numeric(r["unforced"], errors="coerce")
        if pd.notna(u) and not (0 <= u <= 150):
            why.append("unforced out of range")
        if why:
            bad.append((i + 2, r.get("player"), "; ".join(why)))
    if bad:
        print(f"  {len(bad)} row(s) rejected:")
        for ln, who, why in bad[:15]:
            print(f"    line {ln} ({who}): {why}")
        print("  fix these first -- the loader would drop them silently")
        return
    print("  all rows parse")

    # do the names resolve to someone the board knows?
    try:
        import tennis_model_a as A
        unknown = sorted({p for p in X["player"].unique() if not A.resolve(p)})
        if unknown:
            print(f"  WARNING: {len(unknown)} name(s) the board cannot resolve "
                  f"(they will never match a card): {unknown[:8]}")
        else:
            print("  every name resolves to a known player")
    except Exception as e:  # noqa: BLE001
        print(f"  (name check skipped: {e})")

    # duplicates against what we already hold
    before = U.load(force=True)
    have = set(zip(before.date.dt.strftime("%Y%m%d"), before.key))
    dupes = sum(1 for _, r in X.iterrows()
                if (str(r["Date"]), U.norm(r["player"])) in have)
    print(f"  {dupes} row(s) duplicate a match we already have (harmless -- first copy wins)")

    ue_set = pd.to_numeric(X["unforced"], errors="coerce") / pd.to_numeric(X["sets"], errors="coerce")
    print(f"  UE/set entered: mean {ue_set.mean():.2f}, min {ue_set.min():.2f}, max {ue_set.max():.2f} "
          f"(the charted population averages ~11.2 for women, ~10.9 for men -- "
          f"a mean far off that suggests a column mix-up)")
    print(f"  players covered: {X['player'].nunique()} | "
          f"with 5+ rows (enough for a profile): "
          f"{int((X.groupby('player').size() >= 5).sum())}")

    # what it unlocks
    L = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
    L = L[L.league.astype(str).isin(["wta", "itf_women"])].copy()
    L["d"] = L.date.astype(str).str[:10]

    def dec(am):
        am = float(am)
        return 1 + (am / 100.0 if am > 0 else 100.0 / abs(am))

    tot = both = 0
    for _, r in L.iterrows():
        if pd.isna(r.p1_odds) or pd.isna(r.p2_odds):
            continue
        d1, d2 = dec(r.p1_odds), dec(r.p2_odds)
        if not (2.0 <= max(d1, d2) <= 3.5):
            continue
        tot += 1
        if U.profile(r.player_1, pd.Timestamp(r.d)) and U.profile(r.player_2, pd.Timestamp(r.d)):
            both += 1
    print(f"\n  women's +100..+250 dog matches in the log: {tot}")
    print(f"  with a full two-sided profile NOW: {both} ({100 * both / max(tot, 1):.0f}%)")
    print("  (re-run after each batch to watch this climb)")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
