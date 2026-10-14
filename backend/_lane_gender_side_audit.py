"""EVERY NON-MC LANE ON THE BOARD, BY GENDER x SIDE (2026-10-14).

User: "now check the c50 c75 stuff and the fade forms gender specific / the other stuff on our board".

The C family, the fade-form cells and the rest of the board's signals are LANES, not probability
columns, so unlike MC2/MC3/MC5 they cannot be re-run as a primary through arbitrary thresholds.
What they do carry is their own forward record, already split four ways by bet(): m_dog / w_dog /
m_fav / w_fav. That split is the answer to the question asked.

These records are FORWARD in the sense that matters -- they are scored off frozen pre-match rows
in the live log -- and they reach much further back than MC2 does, because the C and gray columns
have been logged for months while MC2 only has seven days.

CAVEAT THAT APPLIES TO ALL OF THEM, and it is the reason nothing here is a recommendation: a lane
registered today REPLAYS the whole frozen log, so for any lane whose RULE was written recently the
early part of its record is in-sample for that rule ([[feedback_new_lane_replay_is_not_forward]]).
The n column is the guard: cells under the floor are printed but flagged.

Run on EC2: ./venv/bin/python _lane_gender_side_audit.py [--min N]
"""
import json
import math
import sys
import urllib.request

MIN_N = int(sys.argv[sys.argv.index("--min") + 1]) if "--min" in sys.argv else 15

# the board's non-MC families, grouped the way the user thinks about them
GROUPS = [
    ("C75 / C50 FAMILY", [
        ("mc_c75_dog", "c75 DOG FLIP -- c75 puts the market dog past 50%"),
        ("c75_dog_100plus", "c75 dog priced +100 or longer"),
        ("cc75_dog", "c50 AND c75 both back the dog"),
        ("cc75_nod_dog", "c50 AND c75 back the dog, Model D does NOT"),
        ("cgray_dog_late", "C and the gray line on the dog, later rounds"),
    ]),
    ("FADE FORM", [
        ("pf_c75_dis_dog", "c75 dog where the pure-form overlay points at the OPPONENT"),
    ]),
    ("THE REST OF THE BOARD", [
        ("split64_fade_dog", "the 10 heads split 6-4; back the 4-minority when it is the dog"),
        ("tier_avoid_dog", "the dog side of cards the board labels AVOID"),
        ("cr1_stardog", "conflict-resolver tier-1 star dog"),
        ("dma_dog", "Model D market-aware picks the dog"),
        ("ovl_dog", "the overlay dog cell"),
        ("fight_mc4_dog", "MC4 disagrees with the market on the dog"),
        ("returner_dog_w", "women, dog wins the return-pressure gap"),
        ("allround_dog_w", "women, dog better on serve AND return pressure"),
        ("pink_fadeb_dog_m", "men, pink fade-B dog watch cell"),
        ("pink_mc2_dog", "the pink MC2 dog watch cell"),
        ("s52_fav_band_dog", "seasonal favourite-band dog"),
        ("x_dog", "Model X on the dog"),
        ("p_dog", "Model P on the dog"),
        ("p_dog_flip", "Model P above 50% on the dog (the crown gate)"),
    ]),
]

req = urllib.request.Request("http://127.0.0.1/api/tennis/track-record",
                             headers={"X-Dashboard-Password": "freezeray23"})
st = (json.load(urllib.request.urlopen(req, timeout=180)).get("ab25") or {}).get("study") or {}


def tstat(d):
    n, w, roi = d.get("n"), d.get("wins"), d.get("roi_pct")
    if not n or w is None or roi is None or n < 2 or w <= 0:
        return None
    r = roi / 100.0
    g = (r * n + (n - w)) / w
    v = (w * g * g + (n - w)) / n - r * r
    return (r / (math.sqrt(v) / math.sqrt(n))) if v > 0 else None


def cell(d):
    if not d or not d.get("n"):
        return "      --      "
    t = tstat(d)
    return "%+6.1f%%/%-4d%s" % (d.get("roi_pct", 0), d["n"],
                                (" t%5.2f" % t) if t is not None else "      ")


BAR = "=" * 118
print(BAR)
print("NON-MC LANES BY GENDER x SIDE -- forward records from the lanes themselves")
print("floor for a readable cell: n >= %d.  '--' = no settles." % MIN_N)
print(BAR)
hdr = "%-22s %-21s %-21s %-21s %-21s" % ("lane", "MEN dog", "WOMEN dog", "MEN fav", "WOMEN fav")
winners = []
for gname, lanes in GROUPS:
    print("\n" + "-" * 118)
    print(gname)
    print("-" * 118)
    print(hdr)
    for key, desc in lanes:
        c = st.get(key)
        if not c:
            print("%-22s  (not in the study payload)" % key)
            continue
        md, wd = c.get("m_dog") or {}, c.get("w_dog") or {}
        mf, wf = c.get("m_fav") or {}, c.get("w_fav") or {}
        print("%-22s %-21s %-21s %-21s %-21s"
              % (key, cell(md), cell(wd), cell(mf), cell(wf)))
        for d, lab, side in ((md, "men dog", "dog"), (wd, "women dog", "dog"),
                             (mf, "men fav", "fav"), (wf, "women fav", "fav")):
            if d.get("n", 0) >= MIN_N and (d.get("roi_pct") or 0) > 0:
                winners.append((d["roi_pct"], d["n"], tstat(d), key, lab, side, desc))

print("\n" + BAR)
print("FORWARD-POSITIVE CELLS AT n >= %d, best first" % MIN_N)
print(BAR)
winners.sort(reverse=True)
if not winners:
    print("   none")
for roi, n, t, key, lab, side, desc in winners:
    print("   %-22s %-10s %+7.2f%% on %-4d %s"
          % (key, lab, roi, n, ("t %5.2f" % t) if t is not None else ""))
print("\n   (dog cells would fall under PINK, favourite cells under GOLD)")
print(BAR)
