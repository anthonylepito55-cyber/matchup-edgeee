"""TSM — fixture-identity and permitted-parser validation (items 9 and 10).

Runs against the REAL permitted-source captures in sched_html_snapshots/ (no network calls),
plus synthetic mutations for the cases real captures cannot yet show (postponement,
rematches, qualifying ambiguity, provider-id churn across sources).

Writes only a temp alias store and a JSON report. No ledger, no production file, no frozen
artifact, no /api/ access.
"""
import collections
import copy
import datetime as dt
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tsm_identity as I  # noqa: E402
import tsm_sched_html as H  # noqa: E402

PASSES, FAILS = [], []


def check(name, cond):
    (PASSES if cond else FAILS).append(name)
    print(("PASS " if cond else "FAIL ") + name)


SNAPS = sorted(os.listdir(H.SNAP_DIR)) if os.path.isdir(H.SNAP_DIR) else []
if len(SNAPS) < 2:
    print("need >=2 permitted captures in %s; run tsm_study_permitted.py" % H.SNAP_DIR)
    sys.exit(2)

# ---------------------------------------------------------- load every real capture
caps = []
for tag in SNAPS:
    d = os.path.join(H.SNAP_DIR, tag)
    prov = json.load(open(os.path.join(d, "provenance.json"), encoding="utf-8"))
    fx = []
    for tour in ("atp", "wta"):
        p = os.path.join(d, "%s-matches.html" % tour)
        if os.path.exists(p):
            fx += H.parse(open(p, encoding="utf-8").read(), tour)
    caps.append({"tag": tag, "prov": prov, "fx": fx})
print("loaded %d real permitted captures\n" % len(caps))

# ================================================== item 10: parser validation
check("parser: every real capture parses and yields fixtures",
      all(c["fx"] for c in caps))
recon = []
for c in caps:
    for p in c["prov"]:
        got = len([f for f in c["fx"] if f["src_tour"] == p["tour"]])
        recon.append((c["tag"], p["tour"], p.get("declared_total"), got))
check("parser: declared-count reconciliation holds on every page of every capture "
      "(%s)" % "; ".join("%s %s declared=%s parsed=%s" % (tg[9:15], to, dc, pc)
                         for tg, to, dc, pc in recon),
      all(dc is not None and dc == pc for _, _, dc, pc in recon))
check("parser: a page's declared total is actually present (never silently None)",
      all(dc is not None for _, _, dc, _ in recon))
check("parser: identity fields are populated on every parsed fixture across all captures",
      all(f["slug_1"] and f["slug_2"] and f["slug_1"] != f["slug_2"]
          for c in caps for f in c["fx"]))
check("parser: tournament, surface, level, start time and round present on every fixture",
      all(f["tournament_name"] and f["surface"] and f["tournament_level"]
          and f["match_datetime_utc"] and f["round"] for c in caps for f in c["fx"]))
# REGRESSION (2026-10-20): every <img> carries
# onerror="this.src='.../profile_pics/default.jpg'", so an avatar regex that is not
# anchored to src= captures "default" as a player slug. In compact rows, which have no
# /players/ link, that phantom became player 2 on 42 of 154 fixtures and those predictions
# were priced against a player who does not exist.
_pl = [f for c in caps for f in c["fx"]]
check("regression: no fixture in any capture resolves a player to the placeholder avatar "
      "'default' (the onerror fallback must never become an identity)",
      not [f for f in _pl if f["slug_1"] == "default" or f["slug_2"] == "default"])
check("regression: the avatar pattern is anchored to src= so the onerror fallback cannot "
      "be captured",
      'src="[^"]*?/profile_pics/' in open(os.path.join(HERE, "tsm_sched_html.py"),
                                          encoding="utf-8").read())
check("regression: 'default' is also on the unresolvable list as a second line of defence",
      "default" in __import__("tsm_sched").UNRESOLVABLE)
_ERR = "onerror=" + chr(34) + "this.src=" + chr(39) + "/x/profile_pics/default.jpg" \
       + chr(39) + chr(34)
_syn = H.parse(
    '<section class="matches-date-group" data-date="2026-10-20">'
    '<div class="tournament-group" data-level="ATP" data-surface="Hard">'
    '<span class="tournament-title">T</span>'
    '<span class="tournament-meta">Round of 32 &middot; 1 matches</span>'
    '<a class="compact-row" data-match-id="1" data-level="ATP" data-surface="Hard">'
    '<span class="compact-time" data-utc="2026-10-20T14:00:00Z">14:00</span>'
    '<img src="/x/profile_pics/AlphaOne.jpg" ' + _ERR + '>'
    '<span class="compact-name">Alpha One</span>'
    '<img src="/x/profile_pics/BetaTwo.jpg" ' + _ERR + '>'
    '<span class="compact-name">Beta Two</span></a>', "atp")
check("regression: a synthetic compact row with two onerror fallbacks resolves BOTH real "
      "players, not 'default'",
      len(_syn) == 1 and _syn[0]["slug_1"] == "alphaone"
      and _syn[0]["slug_2"] == "betatwo")

check("parser: round translation is confident on every fixture in every capture",
      all(f["round_confident"] for c in caps for f in c["fx"]))
check("parser: per-player category is absent from this source on EVERY fixture, so the "
      "limitation is uniform and not sporadic",
      all(f["player1_category"] is None and f["player2_category"] is None
          for c in caps for f in c["fx"]))

# missing-category consequence: slams would be excluded
import tsm_prospective as P  # noqa: E402
slam = dict(caps[0]["fx"][0])
slam.update({"tournament_level": "Grand Slams", "tournament_name": "US Open",
             "round": "R32", "round_confident": True})
check("parser/format: a slam fixture from this source resolves to UNKNOWN because no "
      "per-player category is available (conservative, per A1.5)",
      P.assign_format(slam)[0] == "UNKNOWN")
check("parser/format: non-slam fixtures from this source are unaffected and price bo3",
      all(P.assign_format(f)[0] == "bo3" for f in caps[0]["fx"][:40]))

# qualifying-round ambiguity
qa = dict(caps[0]["fx"][0])
qa.update({"round": None, "round_confident": False, "round_feed": "Qualification"})
check("parser/format: an unconfident qualifying round is never given a confident round "
      "class, so it cannot share an identity with a main-draw fixture",
      I.round_class(qa).startswith("UNCONFIRMED:")
      and I.round_class(caps[0]["fx"][0]) == caps[0]["fx"][0]["round"])
mr = H.map_round("Qualification · 4 matches")
check("parser: 'Qualification' without a round number is flagged unconfident rather than "
      "guessed", mr[0] is None and mr[2] is False)
check("parser: numbered qualifying maps to the archive vocabulary",
      H.map_round("Q2 · 8 matches")[:3] == ("Q2", "qual", True))
check("parser: main-draw rounds map to the archive vocabulary",
      H.map_round("Round of 32 · 2 matches")[0] == "R32"
      and H.map_round("Round of 16 · 4 matches")[0] == "R16"
      and H.map_round("Quarterfinals · 4 matches")[0] == "QF")

# timestamp changes across real captures
ts = collections.defaultdict(dict)
for c in caps:
    for f in c["fx"]:
        k, bad = I.content_key(f)
        if not bad:
            ts[k][c["tag"]] = f["match_datetime_utc"]
moved = {k: v for k, v in ts.items() if len(set(v.values())) > 1}
shared = [k for k, v in ts.items() if len(v) == len(caps)]
check("parser: fixtures are consistently identified across all %d real captures (%d keys "
      "seen in every capture)" % (len(caps), len(shared)), len(shared) > 100)
print("   timestamp changes observed across real captures: %d of %d keys"
      % (len(moved), len(ts)))
for k, v in list(moved.items())[:5]:
    print("      %s -> %s" % (I.key_digest(k), v))

# ================================================== item 9: identity behaviour
TMP = tempfile.mkdtemp(prefix="tsm_ident_")
store = os.path.join(TMP, "aliases.jsonl")
ident = I.Identity(store)
events = []
for c in caps:
    obs = c["prov"][0].get("fetched_utc")
    for f in c["fx"]:
        events.append(ident.observe(f, c["tag"], obs))
s = ident.summary()
print("\nidentity summary over real captures:", json.dumps(s))
check("identity: all real fixtures resolve to a content key (no unresolvable identities)",
      not [e for e in events if e["event"] == "unresolvable"])
check("identity: repeated captures of the same card do NOT mint new identities "
      "(%d identities from %d observations across %d captures)"
      % (s["identities"], len(events), len(caps)),
      s["identities"] < len(events) and s["identities"] >= 100)
check("identity: the content key is stable across captures (second and third captures "
      "produce no 'new' events for fixtures already seen)",
      sum(1 for e in events if e["event"] == "new") == s["identities"])

base = copy.deepcopy(caps[0]["fx"][0])
k0, _ = I.content_key(base)

# provider-id churn
churn = copy.deepcopy(base)
churn["source_match_id"] = str(int(base["source_match_id"]) + 187)
i2 = I.Identity(os.path.join(TMP, "a2.jsonl"))
i2.observe(base, "c1", "t1")
ev = i2.observe(churn, "c2", "t2")
check("identity: the SAME fixture arriving under a different provider id keeps ONE "
      "identity and the churn is recorded (the measured +187 offset case)",
      ev["event"] == "provider_id_churn" and i2.summary()["identities"] == 1
      and len(i2.by_key[k0]["provider_ids"]) == 2)
check("identity: both provider ids resolve back to the same identity (alias retention)",
      i2.resolve_provider_id(base["source_match_id"]) == k0
      and i2.resolve_provider_id(churn["source_match_id"]) == k0)

# postponement: the date moves
post = copy.deepcopy(base)
st = dt.datetime.fromisoformat(base["match_datetime_utc"].replace("Z", "+00:00"))
post["match_datetime_utc"] = (st + dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
post["match_date_iso"] = post["match_datetime_utc"][:10]
i3 = I.Identity(os.path.join(TMP, "a3.jsonl"))
i3.observe(base, "c1", "t1")
ev = i3.observe(post, "c2", "t2")
check("identity: a POSTPONEMENT to the next day keeps ONE identity (date is not part of "
      "the key) and is flagged for review, not silently merged away",
      ev["event"] == "postponement" and ev.get("review_required") is True
      and i3.summary()["identities"] == 1)
check("identity: a (date, slug-pair) key would WRONGLY have minted a second identity here",
      ("%s|%s" % (base["match_date_iso"], "|".join(sorted((base["slug_1"],
                                                           base["slug_2"])))))
      != ("%s|%s" % (post["match_date_iso"], "|".join(sorted((post["slug_1"],
                                                              post["slug_2"]))))))

# same-day reschedule, small and large
for mins, want, rev in ((45, "reschedule", False), (8 * 60, "reschedule", True)):
    r = copy.deepcopy(base)
    nt = st + dt.timedelta(minutes=mins)
    r["match_datetime_utc"] = nt.strftime("%Y-%m-%dT%H:%M:%SZ")
    r["match_date_iso"] = r["match_datetime_utc"][:10]
    ii = I.Identity(os.path.join(TMP, "a_%d.jsonl" % mins))
    ii.observe(base, "c1", "t1")
    e = ii.observe(r, "c2", "t2")
    same_day = r["match_date_iso"] == base["match_date_iso"]
    check("identity: a %d-minute same-day move is a reschedule%s"
          % (mins, " flagged for review" if rev else " (no review needed)"),
          (e["event"] == want if same_day else e["event"] == "postponement")
          and bool(e.get("review_required")) == rev and ii.summary()["identities"] == 1)

# rematch: same players, different tournament
rem = copy.deepcopy(base)
rem["tournament_name"] = "Some Other Event"
k1, _ = I.content_key(rem)
check("identity: a REMATCH at a different tournament is a DIFFERENT identity", k0 != k1)
rem2 = copy.deepcopy(base)
rem2["round"] = "R16"
check("identity: the same pair in a different round (round-robin / team event) is a "
      "different identity", I.content_key(rem2)[0] != k0)
rem3 = copy.deepcopy(base)
rem3["match_date_iso"] = "2025-" + base["match_date_iso"][5:]
rem3["match_datetime_utc"] = "2025-" + base["match_datetime_utc"][5:]
check("identity: the same pair at the same event in a different SEASON is a different "
      "identity", I.content_key(rem3)[0] != k0)

# shared-venue mislabel must not merge distinct events
mv = copy.deepcopy(base)
mv.update({"tournament_name": "M25 Santa Margherita Di Pula 11", "tournament_level":
           "Futures"})
mw = copy.deepcopy(mv)
mw["tournament_name"] = "W35 Santa Margherita Di Pula 11"
check("identity: shared-venue men's and women's events at the same site stay distinct",
      I.content_key(mv)[0] != I.content_key(mw)[0])

# ambiguity: same key, starts far apart
amb = copy.deepcopy(base)
amb["match_datetime_utc"] = (st + dt.timedelta(days=9)).strftime("%Y-%m-%dT%H:%M:%SZ")
amb["match_date_iso"] = amb["match_datetime_utc"][:10]
i4 = I.Identity(os.path.join(TMP, "a4.jsonl"))
i4.observe(base, "c1", "t1")
e = i4.observe(amb, "c2", "t2")
check("identity: two fixtures sharing a key but scheduled >3 days apart are flagged "
      "AMBIGUOUS rather than treated as one routine reschedule",
      e["event"] == "ambiguous_same_key_far_apart")

# unresolvable inputs
for fld, reason in (("slug_1", "missing_slug"), ("tournament_name", "missing_tournament")):
    bad = copy.deepcopy(base)
    bad[fld] = None
    check("identity: a fixture with no %s is unresolvable (%s), never given a key"
          % (fld, reason), I.content_key(bad) == (None, reason))
same = copy.deepcopy(base)
same["slug_2"] = same["slug_1"]
check("identity: identical players are unresolvable",
      I.content_key(same) == (None, "identical_players"))
nod = copy.deepcopy(base)
nod["match_date_iso"] = None
nod["match_datetime_utc"] = None
check("identity: an undatable fixture is unresolvable (no season could be assigned)",
      I.content_key(nod) == (None, "undatable"))

# persistence round-trip
p = ident.flush()
re2 = I.Identity(p)
check("identity: the alias store round-trips (identities and provider aliases survive)",
      re2.summary()["identities"] == s["identities"]
      and re2.summary()["provider_ids_seen"] == s["provider_ids_seen"])

# the historical /api/ captures prove the churn is real, not hypothetical
api_dir = os.path.join(HERE, "sched_snapshots")
if os.path.isdir(api_dir):
    tags = sorted(os.listdir(api_dir))
    api = json.load(open(os.path.join(api_dir, tags[-1], "raw_atp.json"),
                         encoding="utf-8"))
    from tsm import slug as _s
    apair = {frozenset((_s(m["player1_slug"]), _s(m["player2_slug"]))): str(m["id"])
             for m in api}
    hpair = {frozenset((f["slug_1"], f["slug_2"])): f["source_match_id"]
             for f in caps[-1]["fx"] if f["src_tour"] == "atp"}
    both = set(apair) & set(hpair)
    diff = sum(1 for k in both if apair[k] != hpair[k])
    check("identity: provider-id instability is confirmed on real data -- %d of %d matchups "
          "shared between the archived /api/ capture and the permitted HTML capture carry "
          "DIFFERENT provider ids" % (diff, len(both)),
          len(both) > 20 and diff == len(both))

rep = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
       "real_captures": [c["tag"] for c in caps],
       "declared_count_reconciliation": [{"capture": a, "tour": b, "declared": c_,
                                          "parsed": d_} for a, b, c_, d_ in recon],
       "identity_summary": s,
       "timestamp_changes_across_captures": len(moved),
       "keys_seen_in_every_capture": len(shared),
       "passed": len(PASSES), "failed": len(FAILS)}
json.dump(rep, open(os.path.join(HERE, "TSM_IDENTITY_REPORT.json"), "w",
                    encoding="utf-8"), indent=1)
print("\n%d passed, %d failed" % (len(PASSES), len(FAILS)))
if FAILS:
    print("FAILED:")
    for f in FAILS:
        print("  -", f)
import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAILS else 0)
