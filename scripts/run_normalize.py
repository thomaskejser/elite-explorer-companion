"""Apply the normalized modelling layer and print a coverage/overlap audit.

Usage:  python scripts/run_normalize.py
Creates norm.* views (cheap, non-destructive) and prints the audit doc 04 asks
for. Views only -- no large materialization, so the .duckdb file barely grows.
"""
import duckdb, pathlib, sys

DB = pathlib.Path(__file__).resolve().parent.parent / "elite_mapping.duckdb"
SQL = pathlib.Path(__file__).resolve().parent / "01_normalize.sql"

con = duckdb.connect(str(DB))
con.execute(SQL.read_text())
print(f"Applied {SQL.name}: norm.* views created.\n")

def q1(sql):
    return con.execute(sql).fetchone()[0]

def section(title):
    print(f"\n=== {title} ===")

section("Normalized layer sanity")
for v in ["norm.system", "norm.body", "norm.codex_observation", "norm.poi"]:
    print(f"  {v:28s} {q1(f'select count(*) from {v}'):>14,} rows")

section("NSP observations (the #1 modelling target)")
r = con.execute("""
    select count(*) filter (where is_nsp) as nsp_obs,
           count(distinct system_id64) filter (where is_nsp) as nsp_systems
    from norm.codex_observation
""").fetchone()
print(f"  NSP observations: {r[0]:,}   distinct systems with an NSP: {r[1]:,}")
print("  NSP family breakdown (distinct systems):")
for fam, c in con.execute("""
    select nsp_family, count(distinct system_id64) c
    from norm.codex_observation where is_nsp group by 1 order by 2 desc
""").fetchall():
    print(f"    {str(fam):20s} {c:>10,}")

section("Source coverage: systems per source (by id64)")
edsm_sys   = q1("select count(distinct system_id64) from norm.system")
edas_sys   = q1("select count(distinct id64) from edastro_star_system where id64 is not null")
print(f"  EDSM systems (full spine)      : {edsm_sys:,}")
print(f"  EDAstro systems (7-day window) : {edas_sys:,}")

section("Overlap audit (doc 04): EDAstro 7-day systems vs EDSM spine")
both = q1("""
    select count(*) from (
      select distinct id64 from edastro_star_system where id64 is not null
    ) e where e.id64 in (select system_id64 from norm.system)
""")
edas_only = edas_sys - both
print(f"  EDAstro  INT  EDSM : {both:,}")
print(f"  EDAstro only   : {edas_only:,}  (systems EDSM's coord dump lacks)")
print(f"  overlap rate   : {100*both/edas_sys:.1f}% of EDAstro systems are in EDSM")

section("UNKNOWN bucket: known systems with NO body facts on hand")
sys_with_body = q1("select count(distinct system_id64) from norm.body")
print(f"  systems with >=1 body fact : {sys_with_body:,}")
print(f"  systems with NO body fact  : {edsm_sys - sys_with_body:,} "
      f"({100*(edsm_sys - sys_with_body)/edsm_sys:.1f}% of the spine)")
print("  -> body-level features are absent for the vast majority of systems;")
print("     these must be treated as UNKNOWN, not negative (needs Spansh backfill).")

section("Live/Legacy")
print("  galaxy_version = 'unknown' across all tables: these dumps do not")
print("  distinguish Live from Legacy. Flagged, not guessed.")

con.close()
print("\nDone.")
