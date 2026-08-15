"""Turn logged prediction-vs-outcome rows into a calibration the model can consume.

The app appends one line to app/observations.jsonl for every candidate whose arrival
class the game has revealed, carrying the prediction exactly as it stood plus the
model_version that produced it. This script reads that file, reports how well the
current model is calibrated, and writes app/calibration.json -- which
build_candidates.py multiplies into its LEVEL term on the next rebuild.

That closes the loop: fly, reveal, log, recalibrate, rebuild.

Why a MULTIPLIER and not an absolute rate
-----------------------------------------
The observed hit rate already has the model's index shape and per-boxel residual
baked into it, because those decide which systems you were shown in the first place.
Storing it as an absolute level would double-count them. What is actually being
measured is "how far off is the overall level", i.e. observed / predicted, so that
is what is stored.

The multiplier is shrunk toward 1.0 by sample size:

    mult = (hits + PRIOR) / (expected + PRIOR)

so a mass code with three observations barely moves and one with three hundred moves
most of the way. Without it, a single lucky find in a thin mass code would swing the
whole galaxy's predictions.

  python scripts/analyse_observations.py            # report + write calibration.json
  python scripts/analyse_observations.py --dry-run  # report only
"""
import json, pathlib, argparse, math, collections, datetime, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OBS = ROOT / "app" / "observations.jsonl"
OUT = ROOT / "app" / "calibration.json"
PRIOR = 8.0          # pseudo-observations pulling the multiplier toward 1.0
MIN_N = 20           # below this a mass code is reported but not written


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p, d = k / n, 1 + z*z/n
    c = (p + z*z/(2*n)) / d
    h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def load(path):
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        sys.exit(f"no {path} yet -- run the app so it can log some outcomes first")
    return rows


def report(title, rows, keyfn):
    print(f"\n=== {title} ===")
    print(f"  {'bucket':<16}{'n':>6}{'hits':>6}{'pred':>8}{'obs':>8}"
          f"{'95% CI':>16}{'ratio':>8}")
    g = collections.defaultdict(list)
    for r in rows:
        g[keyfn(r)].append(r)
    for k in sorted(g, key=str):
        v = g[k]
        n = len(v)
        exp = sum(min(1.0, r["p_bh"] + r["p_wr"]) for r in v)
        hits = sum(1 for r in v if r["hit"])
        lo, hi = wilson(hits, n)
        ratio = f"x{hits/exp:.2f}" if exp > 0 else "  -"
        print(f"  {str(k):<16}{n:>6}{hits:>6}{exp/n:>8.1%}{hits/n:>8.1%}"
              f"{f'{lo:.1%}-{hi:.1%}':>16}{ratio:>8}")


ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("--dry-run", action="store_true", help="report only; do not write calibration.json")
ap.add_argument("--model", default=None,
                help="restrict to one model_version (default: the most recent one present)")
ap.add_argument("--force", action="store_true",
                help="compose again even if this model_version has already been scored "
                     "(normally refused -- see the note on double-counting)")
a = ap.parse_args()

rows = load(OBS)
if not rows:
    sys.exit("observations.jsonl is empty")

# --- score against the CURRENT model, not the logged snapshot ----------------------
# An outcome is a fact -- the game either revealed a Wolf-Rayet or it did not -- but the
# prediction beside it in the log is whatever the model said at the time, and it goes
# stale the moment the candidates are rebuilt. Scoring against the frozen value made
# `expected` immovable, so composing after a rebuild kept applying the same correction
# to evidence it had already absorbed. Re-reading p from candidates.parquet keeps
# expected honest, which is what makes M_new = M_old * shrunk a convergent step.
CAND = ROOT / "app" / "candidates.parquet"
META = ROOT / "app" / "candidates_meta.json"
build = None
if META.exists():
    try:
        build = json.loads(META.read_text(encoding="utf-8")).get("model_version")
    except ValueError:
        pass
fresh, stale = 0, 0
if CAND.exists():
    import duckdb
    _c = duckdb.connect(":memory:")
    _c.execute("SET threads=4")
    cp = {r[0]: (r[1], r[2]) for r in _c.execute(
        f"SELECT name, p_bh, p_wr FROM '{CAND.as_posix()}'").fetchall()}
    _c.close()
    for r in rows:
        hit = cp.get(r.get("name"))
        if hit:
            r["p_bh"], r["p_wr"] = float(hit[0]), float(hit[1])
            fresh += 1
        else:
            stale += 1
    print(f"re-scored {fresh:,} outcome(s) against the current build "
          f"{build or '(unknown)'}; {stale:,} no longer in the pool "
          f"(logged prediction kept)")
else:
    print(f"no {CAND.name} -- scoring against the logged predictions, which may be stale")

versions = collections.Counter(r.get("model_version", "unknown") for r in rows)
print(f"{len(rows):,} logged outcome(s) across {len(versions)} model version(s):")
for v, n in sorted(versions.items()):
    print(f"    {v:<24}{n:>7,}")
target = a.model or max(versions, key=lambda v: (versions[v], v))
cur = [r for r in rows if r.get("model_version") == target]
print(f"\nscoring model_version {target}  ({len(cur):,} rows)")

report("overall", cur, lambda r: "ALL")
report("by mass code", cur, lambda r: r.get("mass_code", "?"))
report("by source", cur, lambda r: r.get("source", "?"))
report("by boxel index band", cur, lambda r: {
    None: "?"}.get(r.get("boxel_index"), None) or (
    "0-9" if r.get("boxel_index", 0) < 10 else
    "10-24" if r["boxel_index"] < 25 else
    "25-49" if r["boxel_index"] < 50 else
    "50-99" if r["boxel_index"] < 100 else
    "100-249" if r["boxel_index"] < 250 else "250+"))

# --- the multiplier the model will consume ---------------------------------------
# ONE multiplier family, keyed (mass_code, source, kind).
#
# This used to be two independent families -- one per mass code, one per source --
# both fitted on the same rows and then MULTIPLIED together in build_candidates.py.
# That corrected every residual twice. Because both also compose across runs, the
# error compounded, and the loop oscillated instead of converging: mean predicted
# probability for h/predicted went 22.2% -> 5.6% -> 26.2% -> 7.6% -> 19.0% -> 27.6%
# -> 15.4% while the observed rate sat still at 10-12.6%, and the product drifted
# down to 0.0274 (h-BH 0.1431 x predicted 0.1917) against an overall calibration of
# x0.88. A cross-keyed family cannot double-count: each cell owns its own residual.
#
# Multipliers still COMPOSE across runs. build_candidates.py always starts from the
# raw EDAstro level and multiplies by whatever is in this file, so the observed
# over/under-shoot is a correction to the multiplier ALREADY IN FORCE:
#
#     M_new = M_old * shrunk(observed / predicted)
#
# Writing the raw ratio instead would throw away every previous round's correction.
prev, legacy, built_against = {}, None, None
if OUT.exists():
    try:
        _p = json.loads(OUT.read_text(encoding="utf-8"))
        prev = _p.get("multiplier", {})
        built_against = _p.get("built_against")
        if _p.get("source_multiplier") is not None and not _p.get("cross_keyed"):
            # migrate the old two-family form: seed each cell at the PRODUCT that was
            # actually in force, so the first cross-keyed rebuild is continuous with
            # what the model was already doing rather than a jump
            legacy = (_p.get("multiplier", {}), _p.get("source_multiplier", {}))
            prev = {}
            for mc, kinds in legacy[0].items():
                for kind, m in kinds.items():
                    for s, sm in legacy[1].items():
                        prev.setdefault(mc, {}).setdefault(s, {})[kind] = m * sm
            print("\nmigrating the old (mass_code) x (source) multipliers to a single"
                  " cross-keyed family, seeded at the product in force:")
            for mc in sorted(prev):
                for s in sorted(prev[mc]):
                    kk = ", ".join(f"{k} x{v:.4f}" for k, v in sorted(prev[mc][s].items()))
                    print(f"    {mc}/{s:<10} {kk}")
        else:
            print(f"\ncomposing with the multipliers already in force: "
                  f"{json.dumps(prev)}")
    except ValueError:
        pass


def old_mult(mc, src, kind):
    return float(prev.get(mc, {}).get(src, {}).get(kind, 1.0))


print("\n=== calibration multipliers, keyed (mass code, source, kind) ===")
print("  Each cell is corrected once and only once. 'in force' is what produced the")
print("  predictions being scored, so 'new' = in force x shrunk.")
print(f"  {'mc':<4}{'source':<11}{'kind':>5}{'n':>6}{'expected':>10}{'observed':>10}"
      f"{'raw':>8}{'shrunk':>9}{'in force':>10}{'new':>9}")
level = {}
by_cell = collections.defaultdict(list)
for r in cur:
    by_cell[(r.get("mass_code", "?"), r.get("source", "?"))].append(r)
for (mc, src) in sorted(by_cell):
    v = by_cell[(mc, src)]
    n = len(v)
    for kind, pkey in (("bh", "p_bh"), ("wr", "p_wr")):
        exp = sum(r[pkey] for r in v)
        hits = sum(1 for r in v if r.get("kind") == kind.upper())
        if exp <= 0 and hits == 0:
            continue
        raw = hits / exp if exp > 0 else float("inf")
        shrunk = (hits + PRIOR) / (exp + PRIOR)
        old = old_mult(mc, src, kind)
        new = old * shrunk
        flag = "" if n >= MIN_N else f"  (n<{MIN_N})"
        print(f"  {mc:<4}{src:<11}{kind:>5}{n:>6}{exp:>10.1f}{hits:>10}"
              f"{(f'x{raw:.2f}' if exp > 0 else '  -'):>8}{f'x{shrunk:.2f}':>9}"
              f"{f'x{old:.4f}':>10}{f'x{new:.4f}':>9}{flag}")
        if n >= MIN_N:
            level.setdefault(mc, {}).setdefault(src, {})[kind] = round(new, 6)

if a.dry_run:
    print("\n--dry-run: calibration.json not written")
    raise SystemExit

# --- compose once per BUILD ---------------------------------------------------------
# M_new = M_old * shrunk is a valid step only when `expected` reflects the multiplier
# currently in force. Since expected is now re-read from candidates.parquet, that means
# once per build: run it twice against the same parquet and it applies the same
# correction to evidence it has already absorbed. Five such runs drove h/predicted/wr
# from x0.098 to x3.03 and h/predicted/bh to x0.00004. Rebuild (or fly) between runs.
if not a.force and build is not None and built_against == build:
    print(f"\nREFUSING to write: {OUT.name} was already composed against build {build}.")
    print("  `expected` has not moved since, so composing again would double-count the")
    print("  same evidence. Rebuild the candidates (or fly further and rebuild) first.")
    print("  --dry-run shows the report; --force overrides.")
    raise SystemExit(1)

payload = {
    "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "scored_model_version": target,
    "built_against": build,
    "observations": len(cur),
    "prior_pseudo_observations": PRIOR,
    "min_n_to_apply": MIN_N,
    "cross_keyed": True,
    "note": "multiplier[mass_code][source][kind], applied ONCE to build_candidates.py's "
            "EDAstro-derived LEVEL term. Superseded the separate mass_code and source "
            "families, which double-corrected the same residual and made the loop "
            "oscillate.",
    "multiplier": level,
}
OUT.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
print(f"\nwrote {OUT}")
for mc in sorted(level):
    for s in sorted(level[mc]):
        kk = ", ".join(f"{k} x{v:.4f}" for k, v in sorted(level[mc][s].items()))
        print(f"  {mc}/{s:<10} {kk}")
print("\nre-run scripts/build_candidates.py to apply, then restart the overlay.")
