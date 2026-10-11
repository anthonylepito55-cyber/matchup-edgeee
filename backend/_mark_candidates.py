"""Per-gender and per-side records for the lanes the user asked to mark (2026-10-10).

The highlight gate is PER GENDER (HL_BT[lane][g] AND that gender's live ROI > 0 with 3+
settles), so a lane's pooled number cannot authorise a mark. And `tier_avoid` takes Model C's
side whether that is the dog or the favourite -- with 604 settles saying favourite cells return
-9.7%, its side split decides whether the mark should cover the whole bucket or only its dogs.
"""
import tennis_log as TL

st = (TL.get_ab25_record() or {}).get("study") or {}
LANES = ["c75_dog_100plus", "mc_c75_dog", "cc75_dog", "cc75_nod_dog", "pink_cc75_dog",
         "cvg_c", "tier_avoid", "tier1", "tier2", "tier3", "tier_nobet"]


def line(lab, c):
    if not isinstance(c, dict) or not c.get("n"):
        return f"      {lab:12s} --"
    n, w = c["n"], c.get("wins", 0)
    return (f"      {lab:12s} {w}-{n - w:<3d} {100 * w / n:5.1f}%  "
            f"ROI {c.get('roi_pct', 0):+7.1f}%  ${c.get('profit_usd', 0):+8.0f}  (n={n})")


for k in LANES:
    v = st.get(k)
    if not isinstance(v, dict):
        print(f"\n{k}: not in study")
        continue
    print(f"\n{k}  —  pooled {line('', v).strip()}")
    for lab, key in (("men", "m"), ("women", "w"),
                     ("dogs", "dog"), ("favs", "fav"),
                     ("men dog", "m_dog"), ("men fav", "m_fav"),
                     ("women dog", "w_dog"), ("women fav", "w_fav")):
        print(line(lab, v.get(key)))
