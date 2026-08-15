"""Measure P(black hole / Wolf-Rayet in system | ARRIVAL STAR CLASS).

Elite reveals the arrival star's class the moment you plot a route (NavRoute.json,
FSDTarget, StartJump) -- before you travel, and without any scan. That turns out to
be very nearly deterministic: 99.07% of black-hole systems have the black hole AS the
primary, and 94.14% of Wolf-Rayet systems have the Wolf-Rayet as the primary. So the
arrival class alone settles most candidates.

Two subtleties this script exists to handle correctly:

1. GRANULARITY. `Scan` events distinguish giants ('F_WhiteSuperGiant'), but the
   PRE-ARRIVAL events -- FSDTarget / StartJump / NavRoute -- do not: a B supergiant
   reports as plain 'B'. Since B supergiants carry a ~5.9% Wolf-Rayet rate while
   ordinary B stars carry ~0.7%, the rates must be POOLED to the vocabulary the app
   actually observes, or we would wrongly rule out supergiants.

2. MASS CODE. Rates are computed per mass code where the sample supports it, with a
   pooled fallback, since the app can be run with mass code e included.

Output: app/class_rates.json  -- {mass_code|"*": {class: {n, p_bh, p_wr}}}

Usage:  python scripts/build_class_rates.py
"""
import duckdb, pathlib, json, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "app"
OUT = APP / "class_rates.json"
APP.mkdir(exist_ok=True)

# spansh sub_type -> the class string the journal shows BEFORE arrival
JCLASS = """CASE
 WHEN sub_type LIKE '%Black Hole%' THEN 'H'
 WHEN sub_type='Neutron Star' THEN 'N'
 WHEN sub_type LIKE 'Wolf-Rayet%' THEN 'W*'
 WHEN sub_type='Herbig Ae/Be Star' THEN 'AeBe'
 WHEN sub_type='T Tauri Star' THEN 'TTS'
 WHEN sub_type LIKE 'White Dwarf%' THEN 'D*'
 WHEN sub_type LIKE 'M %' THEN 'M' WHEN sub_type LIKE 'K %' THEN 'K'
 WHEN sub_type LIKE 'G %' THEN 'G' WHEN sub_type LIKE 'F %' THEN 'F'
 WHEN sub_type LIKE 'A %' THEN 'A' WHEN sub_type LIKE 'B %' THEN 'B'
 WHEN sub_type LIKE 'O %' THEN 'O' WHEN sub_type LIKE 'L %' THEN 'L'
 WHEN sub_type LIKE 'T %' THEN 'T' WHEN sub_type LIKE 'Y %' THEN 'Y'
 ELSE 'other' END"""

con = duckdb.connect(str(ROOT / "elite_mapping.duckdb"), read_only=True)
con.execute("SET memory_limit='6GB'")
con.execute("SET threads=8")

print("identifying primary stars...", flush=True)
con.execute(f"""
CREATE OR REPLACE TEMP TABLE prim AS
SELECT system_id64, any_value({JCLASS}) AS jclass
FROM spansh_body WHERE type='Star' AND main_star GROUP BY system_id64
""")

print("measuring rates per mass code...", flush=True)
rows = con.execute("""
SELECT s.mass_code, p.jclass, count(*) n, avg(s.has_bh) p_bh, avg(s.has_wr) p_wr
FROM sys_feat s JOIN prim p USING(system_id64)
WHERE s.is_scanned AND s.mass_code IN ('e','f','g','h')
GROUP BY 1,2
""").fetchall()
pooled = con.execute("""
SELECT p.jclass, count(*) n, avg(s.has_bh) p_bh, avg(s.has_wr) p_wr
FROM sys_feat s JOIN prim p USING(system_id64)
WHERE s.is_scanned AND s.mass_code IN ('e','f','g','h')
GROUP BY 1
""").fetchall()
con.close()

MIN_N = 100
out = {"*": {r[0]: {"n": int(r[1]), "p_bh": float(r[2]), "p_wr": float(r[3])}
             for r in pooled if r[1] >= MIN_N}}
for mc, jc, n, pb, pw in rows:
    if n >= MIN_N:
        out.setdefault(mc, {})[jc] = {"n": int(n), "p_bh": float(pb), "p_wr": float(pw)}

out["_meta"] = {
    "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "min_n": MIN_N,
    "note": ("Rates are keyed on the PRE-ARRIVAL journal class (FSDTarget/StartJump/"
             "NavRoute), where giants are NOT distinguished from dwarfs, so giant and "
             "supergiant sub-types are pooled into the base letter."),
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=1, sort_keys=True)

print(f"\nwrote {OUT}")
print(f"\n  pooled e/f/g/h  {'class':>6}{'n':>10}{'P(BH)':>10}{'P(WR)':>10}{'P(either)':>11}")
for jc, d in sorted(out["*"].items(), key=lambda kv: -(kv[1]["p_bh"] + kv[1]["p_wr"])):
    print(f"                  {jc:>6}{d['n']:>10,}{d['p_bh']:>10.4%}{d['p_wr']:>10.4%}"
          f"{min(1.0, d['p_bh']+d['p_wr']):>11.4%}")
print("\nDONE_BUILD_CLASS_RATES")
