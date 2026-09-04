"""BUILD system_neutron: the systems whose PRIMARY star is a neutron star.

    python etl/build_system_neutron.py

SOURCE: system_known, and NOTHING ELSE. The membership test is
primary_star_body_id = the body row for 'Neutron Star', which system_known already
carries, so this builder touches no staging table and needs no feed downloaded first.

*** PRIMARY STAR IS THE ARRIVAL STAR *** -- you drop out of witchspace at the primary --
so one column answers the whole question, and every row here is a jet cone boost you can
take without supercruising anywhere.

*** WHY NOT EDAstro's NEUTRON CATALOGUE, WHICH IS RIGHT THERE. ***
staging.edastro_neutron_star has an is_arrival_star flag that looks like exactly what
this needs. It is not: measured over all 4,143,570 rows it is EXACTLY the test
`body_name = system_name`, with no exceptions in either direction. An unnamed primary
takes the system's own name and passes; a primary designated 'A' fails, though it is the
same star in the same place. Believing it would have thrown away 1,727,383 good systems.
Where the two sources both have an opinion they agree on all but 2 rows of 1,698,816.

WHY MATERIALISE. The overlay asks "what are the three nearest" on every jump, and a
3.4M-row scan is a different proposition from a 197.6M-row one.

Merge; never drop. All the work is SQL; Python only drives it.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import (apply_comment_file, comment_file, connect,
                       count_then_update, report_merge)

TABLE = "system_neutron"
# Every column, in system_known order. ONE list: the SELECT, the UPDATE and the INSERT
# all walk it, so this table's layout cannot drift from the one it mirrors.
COLUMNS = ["system_id", "sector_id", "system_in_sector", "cube_id", "mass_code", "sub_cube_id",
           "boxel_index", "region_id", "primary_star_body_id", "body_count",
           "x", "y", "z", "id_poi", "id64"]
KEY = "system_id"

con = connect()
con.execute(comment_file(TABLE).read_text(encoding="utf-8"))
before = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
print(f"{TABLE}: {before:,} row(s) before; source system_known")

# Looked up, not hardcoded. body_id 40 is 'Neutron Star' today and there is no reason
# for a surrogate key to be a literal in a query.
neutron = con.execute(
    "SELECT body_id FROM body WHERE type = 'star' AND body = 'Neutron Star'").fetchone()
if not neutron:
    raise SystemExit("body has no 'Neutron Star' row -- run etl/build_body.py first")
neutron_id = neutron[0]
print(f"  'Neutron Star' is body_id {neutron_id}")

cols = ", ".join(f'"{c}"' for c in COLUMNS)
con.execute(f"""
CREATE OR REPLACE TEMP TABLE src AS
SELECT {cols} FROM system_known WHERE primary_star_body_id = ?""", [neutron_id])

n_src, n_known, n_primary = con.execute(f"""
    SELECT (SELECT count(*) FROM src),
           (SELECT count(*) FROM system_known),
           (SELECT count(primary_star_body_id) FROM system_known)""").fetchone()
print(f"  {n_src:,} system(s) with a neutron primary")
print(f"  A FLOOR, NOT A CENSUS: system_known records a primary for only "
      f"{n_primary:,} of {n_known:,} rows ({n_primary / n_known:.1%}), so a system "
      f"absent here may just be one nobody has reported a primary for")

# UPDATE before INSERT, or the rows just inserted get scanned again. IS DISTINCT FROM so
# a value becoming NULL still counts as a change.
CHANGED = " OR ".join(f't."{c}" IS DISTINCT FROM s."{c}"' for c in COLUMNS if c != KEY)
SETS = ", ".join(f'"{c}" = s."{c}"' for c in COLUMNS if c != KEY)
updated = count_then_update(
    con,
    f"SELECT count(*) FROM {TABLE} t JOIN src s USING ({KEY}) WHERE {CHANGED}",
    f"""UPDATE {TABLE} AS t SET {SETS}
        FROM src AS s WHERE s.{KEY} = t.{KEY} AND ({CHANGED})""")

con.execute(f"""
    INSERT INTO {TABLE} ({cols})
    SELECT {cols} FROM src s
    WHERE NOT EXISTS (SELECT 1 FROM {TABLE} t WHERE t.{KEY} = s.{KEY})""")

after = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
# Systems system_known no longer calls a neutron primary. NEVER deleted: a star does not
# stop being a neutron, and a changed primary is far more likely to be a data correction
# upstream than a fact about the galaxy.
orphans = [r[0] for r in con.execute(f"""
    SELECT {KEY} FROM {TABLE} t
    WHERE NOT EXISTS (SELECT 1 FROM src s WHERE s.{KEY} = t.{KEY}) LIMIT 5""").fetchall()]
report_merge(TABLE, before, after, after - before, updated, orphans)

apply_comment_file(con, comment_file(TABLE))

# ---- the shape of what we just built ----------------------------------------------
# The project's notes say g and h neutrons are never the arrival star. Print it every
# run so that stays a checked fact rather than a remembered one.
print(f"\n  {'mass code':<14}{'systems':>12}")
for r in con.execute(f"""
    SELECT coalesce(mass_code, '(hand-named)'), count(*) FROM {TABLE}
    GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {r[0]:<14}{r[1]:>12,}")

missing = con.execute(f"SELECT count(*) FROM {TABLE} WHERE x IS NULL").fetchone()[0]
print(f"\n  without coordinates: {missing:,} -- cannot be ranked by distance")

print("\nDONE_BUILD_SYSTEM_NEUTRON")
