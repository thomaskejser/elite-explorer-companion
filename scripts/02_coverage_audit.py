"""Post-Spansh coverage audit: quantify how far the body-coverage gap closed.

Applies scripts/01_normalize.sql (now Spansh-backed norm.body) then reports
source coverage, the collapsed UNKNOWN bucket, and body-level readiness of the
NSP positive-label set.
"""
import duckdb, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
con = duckdb.connect(str(ROOT / "elite_mapping.duckdb"))
con.execute("SET memory_limit='6GB'")
con.execute((ROOT / "scripts" / "01_normalize.sql").read_text())

def q1(sql): return con.execute(sql).fetchone()[0]
def sec(t): print(f"\n=== {t} ===")

sec("Body corpus: before vs after Spansh")
edsm_bodies  = q1("select count(*) from edsm_celestial_body")
spansh_bodies= q1("select count(*) from spansh_body")
print(f"  EDSM 7-day bodies (old spine) : {edsm_bodies:,}")
print(f"  Spansh full-galaxy bodies     : {spansh_bodies:,}   ({spansh_bodies/edsm_bodies:.0f}x more)")

sec("System spine coverage (distinct id64)")
edsm_sys   = q1("select count(distinct system_id64) from norm.system")
spansh_sys = q1("select count(distinct system_id64) from spansh_system")
union_sys  = q1("""select count(*) from (
                     select system_id64 from norm.system
                     union
                     select system_id64 from spansh_system)""")
print(f"  EDSM systems           : {edsm_sys:,}")
print(f"  Spansh systems         : {spansh_sys:,}")
print(f"  Union (distinct id64)  : {union_sys:,}")

sec("UNKNOWN bucket: systems with body facts, before vs after")
sys_with_body = q1("select count(distinct system_id64) from spansh_body")
print(f"  systems with >=1 body fact now : {sys_with_body:,}")
print(f"  of the {union_sys:,}-system union, no body fact: "
      f"{union_sys - sys_with_body:,} ({100*(union_sys-sys_with_body)/union_sys:.1f}%)")
print(f"  BEFORE Spansh this was 99.7% unknown; now {100*sys_with_body/union_sys:.1f}% have body facts.")

sec("Direct discovery labels now available (from DSS signals)")
geo = q1("select count(*) from spansh_body where coalesce(signal_geology,0) > 0")
bio = q1("select count(*) from spansh_body where coalesce(signal_biology,0) > 0")
gen = q1("select count(*) from spansh_body where genuses is not null")
print(f"  bodies with geology signals : {geo:,}")
print(f"  bodies with biology signals : {bio:,}")
print(f"  bodies with recorded genuses: {gen:,}")

sec("NSP positive set: body-level readiness")
r = con.execute("""
    with nsp as (select distinct system_id64 from norm.codex_observation
                 where is_nsp and system_id64 is not null)
    select count(*) tot,
           count(*) filter (where exists (select 1 from spansh_system s where s.system_id64 = nsp.system_id64)) in_spansh,
           count(*) filter (where exists (select 1 from spansh_body b where b.system_id64 = nsp.system_id64)) with_bodies
    from nsp
""").fetchone()
print(f"  NSP systems: {r[0]:,}   in Spansh: {r[1]:,} ({100*r[1]/r[0]:.1f}%)   "
      f"with body facts: {r[2]:,} ({100*r[2]/r[0]:.1f}%)")

con.close()
print("\nDone.")
