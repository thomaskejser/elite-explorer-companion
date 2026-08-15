"""Does height above the galactic plane refine the BH/WR prediction?

The current app rate lookup (scripts/build_candidates.py) is keyed on
(mass_code x plane_r band) only. The research model (03f/03t) does feed `height`
to the gradient booster, but the DE-BIASING layer -- which is what actually
produces the probabilities we show and the counts in RECOMMENDATIONS.md -- uses
radius alone (03j) or spatial kNN (03l/03v), neither of which treats height
explicitly.

Black holes should favour thick-disk/halo geometry (old population, natal kicks)
while Wolf-Rayets should favour the thin star-forming disk. This measures whether
that is true in-game, and whether adding a height term beats the current key.

Scored with Brier + log-loss on a held-out 20% of WELL-SAMPLED systems (the same
near-complete boxels the de-biasing trusts), so the comparison is out-of-sample and
selection-bias-free. Rates are Laplace-smoothed toward the parent (mass_code, band)
cell so thin cells cannot invent extreme probabilities.
"""
import duckdb, pathlib
import numpy as np

np.random.seed(17)
ROOT = pathlib.Path(__file__).resolve().parent.parent
con = duckdb.connect(str(ROOT / "elite_mapping.duckdb"), read_only=True)
con.execute("SET memory_limit='6GB'")
con.execute("SET threads=8")

KB = r"regexp_replace(name,'[0-9]+(-[0-9]+)?$','')"
TK = r"regexp_extract(name,'([0-9]+(-[0-9]+)?)$',1)"
BX = f"CASE WHEN {TK} LIKE '%-%' THEN {KB}||'#'||split_part({TK},'-',1) ELSE {KB} END"
IX = f"CASE WHEN {TK} LIKE '%-%' THEN CAST(split_part({TK},'-',2) AS BIGINT) ELSE CAST({TK} AS BIGINT) END"

print("loading well-sampled (near-complete) f/g/h systems...", flush=True)
con.execute(f"""
CREATE OR REPLACE TEMP TABLE bx AS
SELECT {BX} AS boxel, max({IX})+1 pop, count(*) FILTER (WHERE is_scanned) scanned
FROM sys_feat WHERE mass_code IN ('f','g','h') AND {TK} <> '' GROUP BY 1
""")
df = con.execute(f"""
SELECT s.mass_code, s.has_bh, s.has_wr, s.height, s.plane_r, s.r_sgra
FROM sys_feat s JOIN bx b ON b.boxel = {BX}
WHERE s.is_scanned AND s.mass_code IN ('f','g','h') AND {TK} <> ''
  AND b.scanned >= 10 AND b.scanned >= 0.8 * b.pop
""").df()
con.close()
print(f"  well-sampled systems: {len(df):,}")

BAND = 2500.0
HEDGES = [0, 300, 1000, np.inf]          # thin disk / mid / thick+halo
df["prb"] = np.floor(df.plane_r.values / BAND).astype(int)
df["rsb"] = np.floor(df.r_sgra.values / BAND).astype(int)     # 3D distance to Sgr A*
df["hb"] = np.digitize(df.height.values, HEDGES[1:-1])
df["mc"] = df.mass_code.values

# r_sgra^2 = plane_r^2 + height^2, so 3D distance already folds in the height term.
# Crucially the two effects pull in OPPOSITE directions for black holes (rate falls
# with disk radius, rises with height), so collapsing them into one number can cancel
# signal rather than capture it. Hence: test r_sgra properly rather than assume.
d = np.abs(df.r_sgra.values - df.plane_r.values)
print(f"  |r_sgra - plane_r|: median={np.median(d):.0f} ly  p95={np.percentile(d,95):.0f} ly  "
      f"max={d.max():.0f} ly")

te = np.random.rand(len(df)) < 0.20
train, test = df[~te], df[te]
print(f"  train={len(train):,}  test={len(test):,}")


def fit(tr, target, keys, prior_keys=None, k=25.0):
    """Smoothed rate per key-tuple, shrunk toward the parent cell (or global mean)."""
    glob = tr[target].mean()
    parent = tr.groupby(prior_keys)[target].agg(["sum", "count"]) if prior_keys else None
    g = tr.groupby(keys)[target].agg(["sum", "count"])
    rate = {}
    for idx, row in g.iterrows():
        if prior_keys:
            pidx = idx[:len(prior_keys)] if isinstance(idx, tuple) else idx
            pr = parent.loc[pidx] if pidx in parent.index else None
            mu = (pr["sum"] / pr["count"]) if pr is not None and pr["count"] else glob
        else:
            mu = glob
        rate[idx] = (row["sum"] + k * mu) / (row["count"] + k)
    return rate, glob


def predict(rate, glob, d, keys, fallback=None, fb_keys=None):
    out = np.empty(len(d))
    tup = list(zip(*[d[k].values for k in keys]))
    fbt = list(zip(*[d[k].values for k in fb_keys])) if fb_keys else None
    for i, t in enumerate(tup):
        t = t if len(keys) > 1 else t[0]
        if t in rate:
            out[i] = rate[t]
        elif fallback is not None:
            ft = fbt[i]
            ft = ft if len(fb_keys) > 1 else ft[0]
            out[i] = fallback.get(ft, glob)
        else:
            out[i] = glob
    return out


def score(name, p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    brier = np.mean((p - y) ** 2)
    ll = -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
    print(f"    {name:34s} Brier={brier:.5f}  logloss={ll:.5f}")
    return brier, ll


for target, label, codes in [("has_bh", "BLACK HOLE", ("f", "g", "h")),
                             ("has_wr", "WOLF-RAYET", ("h",))]:
    tr = train[train.mc.isin(codes)]
    ts = test[test.mc.isin(codes)]
    y = ts[target].values.astype(float)
    print(f"\n=== {label}  (train={len(tr):,} test={len(ts):,}) ===")

    r0, g0 = fit(tr, target, ["mc"])
    p0 = predict(r0, g0, ts, ["mc"])
    b0, l0 = score("mass_code only", p0, y)

    r1, g1 = fit(tr, target, ["mc", "prb"])
    p1 = predict(r1, g1, ts, ["mc", "prb"])
    b1, l1 = score("mass_code x plane_r  (CURRENT APP)", p1, y)

    rs, gs = fit(tr, target, ["mc", "rsb"])
    ps = predict(rs, gs, ts, ["mc", "rsb"])
    bs, ls = score("mass_code x r_sgra (3D to Sgr A*)", ps, y)

    rsh, gsh = fit(tr, target, ["mc", "rsb", "hb"], prior_keys=["mc", "rsb"])
    psh = predict(rsh, gsh, ts, ["mc", "rsb", "hb"], fallback=rs, fb_keys=["mc", "rsb"])
    bsh, lsh = score("mass_code x r_sgra x HEIGHT", psh, y)

    r2, g2 = fit(tr, target, ["mc", "prb", "hb"], prior_keys=["mc", "prb"])
    p2 = predict(r2, g2, ts, ["mc", "prb", "hb"], fallback=r1, fb_keys=["mc", "prb"])
    b2, l2 = score("mass_code x plane_r x HEIGHT", p2, y)

    # both radii together: does 3D distance add anything on top of (plane_r, height)?
    r3, g3 = fit(tr, target, ["mc", "prb", "hb", "rsb"], prior_keys=["mc", "prb", "hb"])
    p3 = predict(r3, g3, ts, ["mc", "prb", "hb", "rsb"], fallback=r2, fb_keys=["mc", "prb", "hb"])
    b3, l3 = score("mass_code x plane_r x HEIGHT x r_sgra", p3, y)

    cands = {"plane_r": b1, "r_sgra": bs, "r_sgra+height": bsh,
             "plane_r+height": b2, "all three": b3}
    best = min(cands, key=cands.get)
    print(f"    -> BEST: {best} (Brier {cands[best]:.5f})")
    print(f"       r_sgra vs plane_r alone:      {100*(b1-bs)/b1:+.1f}% Brier")
    print(f"       plane_r+height vs plane_r:    {100*(b1-b2)/b1:+.1f}% Brier")
    print(f"       all three vs plane_r+height:  {100*(b2-b3)/b2:+.1f}% Brier")

    print(f"\n    rate table (train), {label}:")
    print(f"      {'mc':>3}{'plane_r kly':>13}{'thin<300':>10}{'300-1k':>9}{'1k+':>9}{'n':>9}")
    for mc in codes:
        for prb in sorted({p for m, p, _h in r2 if m == mc}):
            cells = [r2.get((mc, prb, h)) for h in (0, 1, 2)]
            n = int(((tr.mc == mc) & (tr.prb == prb)).sum())
            if n < 500:
                continue
            f = lambda v: f"{v:9.1%}" if v is not None else f"{'-':>9}"
            print(f"      {mc:>3}{prb*2.5:>10.1f}-{(prb+1)*2.5:<2.1f}"
                  f"{f(cells[0])}{f(cells[1])}{f(cells[2])}{n:>9,}")
print("\nDONE_03W")
