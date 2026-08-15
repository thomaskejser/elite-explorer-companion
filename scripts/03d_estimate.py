"""Estimate theorised (Stellar-Forge-implied but not-in-DB) systems per mass code.

Each procedural name encodes a dense 0..K-1 index within its boxel, so
max(index)+1 is a lower bound on that boxel's true population. Summed over
boxels, (boxel_pop - have) lower-bounds the missing systems we could enumerate.
"""
import duckdb, pathlib
con = duckdb.connect(str(pathlib.Path(__file__).resolve().parent.parent / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8")

q = r"""
with p as (
  select mass_code,
         regexp_replace(name, '[0-9]+(-[0-9]+)?$', '') as boxel_key,
         regexp_extract(name, '([0-9]+(-[0-9]+)?)$', 1) as idx_raw
  from sys_feat
  where mass_code in ('e','f','g','h')
),
i as (
  select mass_code, boxel_key,
    case when idx_raw like '%-%'
         then cast(split_part(idx_raw,'-',1) as bigint)*1000 + cast(split_part(idx_raw,'-',2) as bigint)
         else cast(idx_raw as bigint) end as idx
  from p
  where idx_raw <> ''
),
b as (
  select mass_code, boxel_key, max(idx)+1 as boxel_pop, count(*) as have
  from i group by 1,2
)
select mass_code,
       count(*)                                   as boxels,
       sum(have)                                  as systems_in_db,
       sum(boxel_pop)                             as theorised_total_lb,
       sum(boxel_pop - have)                      as missing_lb,
       round(100.0*sum(have)/sum(boxel_pop),1)    as pct_explored,
       round(100.0*count(*) filter (where have=boxel_pop)/count(*),1) as pct_boxels_full
from b group by 1 order by 1
"""
rows = con.execute(q).fetchall()
hdr = ["mc","boxels","in_db","theorised_LB","missing_LB","%expl","%boxfull"]
print("  ".join(f"{h:>14}" for h in hdr))
tot_db = tot_theo = tot_miss = 0
for r in rows:
    tot_db += r[2]; tot_theo += r[3]; tot_miss += r[4]
    print("  ".join(f"{v:>14,}" if isinstance(v,int) else f"{v:>14}" for v in r))
print("  ".join(f"{v:>14}" for v in ["TOTAL","", f"{tot_db:,}", f"{tot_theo:,}", f"{tot_miss:,}","",""]))
con.close()
