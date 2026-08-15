"""Per-sector expected finds over the RELIABLE pool: real in-db-unscanned systems.

After the 03s correction, "theorised" (enumerated internal gaps in dense boxels) is
a thin, heavily core-biased layer -- only ~208k systems galaxy-wide, and near zero
in the fringe.  The dependable candidate pool is instead the ~2.26M systems that
are REAL catalogued records (exact coordinates, present in the dumps) which simply
have not been detail-scanned.

This computes, per boxel, the same locally de-biased rate 03l/03n validated, and
applies it to `unscanned = in_db - scanned` for seven targets (BH, WR, and the five
rare-star types).  Aggregated to sector -> table `sector_unscanned`.

Unlike the theorised layer this needs no density/gap assumption: every candidate is
a real system with real coordinates, so counts are trustworthy wherever the local
rate estimate is (rate uncertainty remains -- rank sectors, don't trust decimals).
"""
import duckdb, pathlib, numpy as np
from scipy.spatial import cKDTree
np.random.seed(13)
ROOT = pathlib.Path(__file__).resolve().parent.parent
con = duckdb.connect(str(ROOT / "elite_mapping.duckdb"))
con.execute("SET memory_limit='6GB'"); con.execute("SET threads=8")
con.execute("SET preserve_insertion_order=false")
KB = r"regexp_replace(name,'[0-9]+(-[0-9]+)?$','')"
TK = r"regexp_extract(name,'([0-9]+(-[0-9]+)?)$',1)"
BX = f"CASE WHEN {TK} LIKE '%-%' THEN {KB}||'#'||split_part({TK},'-',1) ELSE {KB} END"

print("1/4 aggregating BH/WR counts per boxel...", flush=True)
con.execute(f"""
CREATE OR REPLACE TEMP TABLE bhwr AS
SELECT {BX} AS boxel,
       sum(has_bh) FILTER (WHERE is_scanned) AS n_bh,
       sum(has_wr) FILTER (WHERE is_scanned) AS n_wr
FROM sys_feat WHERE mass_code IN ('e','f','g','h') AND {TK} <> ''
GROUP BY 1
""")

print("2/4 loading boxels...", flush=True)
bx = con.execute("""
SELECT s.boxel, s.mass_code, s.sector, s.x, s.y, s.z, s.plane_r, s.dist_sol,
       s.pop, s.in_db, s.scanned, s.missing AS theorised,
       coalesce(b.n_bh,0) AS n_bh, coalesce(b.n_wr,0) AS n_wr,
       s.n_neutron, s.n_wd, s.n_herbig, s.n_otype, s.n_supergiant
FROM star_boxels s LEFT JOIN bhwr b USING(boxel)
""").df()
bx["unscanned"] = (bx.in_db - bx.scanned).clip(lower=0)
bx["well"] = (bx.scanned >= 10) & (bx.scanned >= 0.8 * bx["pop"])
print(f"    boxels={len(bx):,}  in_db={int(bx.in_db.sum()):,}  "
      f"unscanned={int(bx.unscanned.sum()):,}  theorised={int(bx.theorised.sum()):,}")

TARGETS = [("n_bh", "Black hole"), ("n_wr", "Wolf-Rayet"), ("n_neutron", "Neutron star"),
           ("n_wd", "White dwarf"), ("n_herbig", "Herbig Ae/Be"),
           ("n_otype", "O-type star"), ("n_supergiant", "Supergiant")]
MCS = ["e", "f", "g", "h"]
# Wolf-Rayets occur only in mass code h (R1) -- do not smear a rate onto e/f/g.
GATE = {"n_wr": {"h"}}


def local_rate(cand, num_col, anchors, k=12, k0=10.0):
    """kNN pooled rate within mass code, shrunk toward that mass code's
    well-sampled mean (empirical Bayes) -- identical to the 03n estimator."""
    out = np.zeros(len(cand))
    gate = GATE.get(num_col)
    for mc in MCS:
        if gate and mc not in gate:
            continue
        cm = cand.mass_code.values == mc
        anc = anchors[anchors.mass_code.values == mc]
        if cm.sum() == 0 or len(anc) == 0:
            continue
        den_all = anc["scanned"].sum()
        mu = anc[num_col].sum() / den_all if den_all > 0 else 0.0
        if len(anc) >= 30:
            tree = cKDTree(anc[["x", "y", "z"]].values)
            d, idx = tree.query(cand[cm][["x", "y", "z"]].values, k=min(k, len(anc)))
            if idx.ndim == 1:
                idx = idx[:, None]
            num = anc[num_col].values[idx].sum(1)
            den = anc["scanned"].values[idx].sum(1)
            out[np.where(cm)] = (num + k0 * mu) / (den + k0)
        else:
            out[np.where(cm)] = mu
    return out


print("3/4 de-biasing each target over the unscanned pool...", flush=True)
well = bx[bx.well]
print(f"    well-sampled anchor boxels: {len(well):,}")
for num_col, label in TARGETS:
    rate = local_rate(bx, num_col, well)
    bx["exp_" + num_col] = bx["unscanned"] * rate
    bx["theo_" + num_col] = bx["theorised"] * rate
    print(f"    {label:14s} galaxy-wide expected over unscanned: "
          f"{bx['exp_' + num_col].sum():>12,.0f}   (over theorised: {bx['theo_' + num_col].sum():>8,.0f})")

print("4/4 aggregating to sector -> sector_unscanned ...", flush=True)
agg = {"dist_sol": ("dist_sol", "mean"), "plane_r": ("plane_r", "mean"),
       "x": ("x", "mean"), "y": ("y", "mean"), "z": ("z", "mean"),
       "in_db": ("in_db", "sum"), "scanned": ("scanned", "sum"),
       "unscanned": ("unscanned", "sum"), "theorised": ("theorised", "sum")}
for num_col, _ in TARGETS:
    agg["found_" + num_col] = (num_col, "sum")
    agg["exp_" + num_col] = ("exp_" + num_col, "sum")
    agg["theo_exp_" + num_col] = ("theo_" + num_col, "sum")
g = bx.groupby("sector").agg(**agg).reset_index()
con.register("g_df", g)
con.execute("CREATE OR REPLACE TABLE sector_unscanned AS SELECT * FROM g_df")
con.unregister("g_df")
print(f"    sector_unscanned rows: {len(g):,}")

for num_col, label in TARGETS:
    ecol, fcol = "exp_" + num_col, "found_" + num_col
    near = g[(g[ecol] >= 2) & (g.unscanned >= 50)].sort_values("dist_sol").head(8)
    print(f"\n########## {label.upper()} -- nearest sectors with a real unscanned pool "
          f"(exp>=2, unscanned>=50) ##########")
    print(f"    {'sector':20}{'dist_Sol':>9}{'plane_r':>8}{'unscan':>8}{'found':>7}{'exp':>8}")
    for _, r in near.iterrows():
        print(f"    {str(r['sector'])[:18]:18s}{int(r.dist_sol):>9,}{int(r.plane_r):>8,}"
              f"{int(r.unscanned):>8,}{int(r[fcol]):>7,}{r[ecol]:>8.1f}")
con.close()
print("\nDONE_03V", flush=True)
