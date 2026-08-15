"""Base-rate analysis on the materialized sys_feat table (no rebuild)."""
import duckdb, pathlib
con = duckdb.connect(str(pathlib.Path(__file__).resolve().parent.parent / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8")

def show(title, sql):
    print(f"\n=== {title} ===", flush=True)
    cols = [d[0] for d in con.execute(sql).description]
    print("  " + "  ".join(f"{c:>14}" for c in cols))
    for row in con.execute(sql).fetchall():
        print("  " + "  ".join(f"{v:>14,}" if isinstance(v,int) else
              (f"{v:>14.4f}" if isinstance(v,float) else f"{str(v):>14}") for v in row), flush=True)

# BH rate by distance-from-core shell, high-mass-code systems only (where BH occur)
show("BH rate among SCANNED e/f/g/h systems, by 2 kly shell from Sgr A*",
    """
    SELECT (floor(r_sgra/2000)*2)::INT AS shell_kly,
           count(*) scanned, sum(has_bh) bh,
           round(100.0*sum(has_bh)/count(*),3) bh_pct
    FROM sys_feat
    WHERE is_scanned AND mass_code IN ('e','f','g','h')
    GROUP BY 1 ORDER BY 1
    """)

# WR rate by shell, mass code h only
show("WR rate among SCANNED mass-code-h systems, by 2 kly shell from Sgr A*",
    """
    SELECT (floor(r_sgra/2000)*2)::INT AS shell_kly,
           count(*) scanned, sum(has_wr) wr,
           round(100.0*sum(has_wr)/count(*),3) wr_pct
    FROM sys_feat
    WHERE is_scanned AND mass_code='h'
    GROUP BY 1 ORDER BY 1
    """)

# The candidate search space: UNSCANNED systems by mass code
show("Candidate (UNSCANNED) systems by mass_code",
    """
    SELECT coalesce(nullif(mass_code,''),'(named)') AS mass_code,
           count(*) unscanned,
           round(100.0*count(*)/sum(count(*)) over (),2) pct
    FROM sys_feat WHERE NOT is_scanned GROUP BY 1 ORDER BY 1
    """)

# Headline: expected undiscovered BH/WR if scanned f/g/h/e rates hold on unscanned
show("Scanned vs unscanned counts in BH-bearing mass codes",
    """
    SELECT coalesce(nullif(mass_code,''),'(named)') AS mass_code,
           count(*) FILTER (WHERE is_scanned)       AS scanned,
           count(*) FILTER (WHERE NOT is_scanned)   AS unscanned,
           round(100.0*count(*) FILTER (WHERE is_scanned)/count(*),2) AS pct_scanned
    FROM sys_feat WHERE mass_code IN ('e','f','g','h')
    GROUP BY 1 ORDER BY 1
    """)
con.close()
print("\nDONE_03B", flush=True)
