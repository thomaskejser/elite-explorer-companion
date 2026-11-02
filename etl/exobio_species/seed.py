import ast
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import INPUT, connect
from common.sources import download

if __name__ == "__main__":
    from common.runlog import start
    start()

OUT = INPUT / "exobio_species.parquet"
BIOSCAN = "https://raw.githubusercontent.com/Silarn/EDMC-BioScan/master/src/bio_scan/bio_data"
EXPLODATA = ("https://raw.githubusercontent.com/Silarn/EDMC-ExploData/master/src/"
             "ExploData/explo_data/bio_data/genus.py")
RULESETS = ["aleoida", "anemone", "bacterium", "brain_tree", "cactoida", "clypeus",
            "concha", "electricae", "fonticulua", "frutexa", "fumerola", "fungoida",
            "osseus", "recepta", "shard", "stratum", "tubers", "tubus", "tussock"]
CANONN_SPELLING = {"Bark Mound": "Bark Mounds", "Radicoida Unicus": "Radicoida Unica"}

if OUT.exists():
    sys.exit(f"{OUT} already exists and is AUTHORITATIVE -- refusing to overwrite.\n"
             f"This seeder runs once. To apply the file:  python etl/exobio_species/refresh.py\n"
             f"If a value is wrong, correct the file by hand.")


def literal(path, names):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        target = node.target if isinstance(node, ast.AnnAssign) else (
            node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(target, ast.Name) and target.id in names:
            return ast.literal_eval(node.value)
    sys.exit(f"{path} has no literal {' or '.join(names)} -- the upstream layout changed")


genus = literal(download(EXPLODATA, "bioscan/genus.py"), ["data"])
catalogs = [literal(download(f"{BIOSCAN}/rulesets/{n}.py", f"bioscan/{n}.py",
                                     min_bytes=100), ["catalog"])
            for n in RULESETS]
catalogs.append(literal(download(f"{BIOSCAN}/species.py", "bioscan/species.py"),
                        ["_mound_amphora"]))

found = {}
for catalog in catalogs:
    for genus_key, species in catalog.items():
        g = genus.get(genus_key, {})
        for species_key, s in species.items():
            if species_key in found and not g:
                continue
            name = CANONN_SPELLING.get(s["name"], s["name"])
            found[species_key] = (name, g.get("name") or name, species_key,
                                  genus_key, int(s["value"]), g.get("distance"))
rows = list(found.values())
names = [r[0] for r in rows]
dup = sorted({n for n in names if names.count(n) > 1})
if dup:
    sys.exit(f"species named twice upstream: {dup}")

con = connect()
con.execute("""CREATE OR REPLACE TEMP TABLE seed (species VARCHAR, genus VARCHAR,
               species_key VARCHAR, genus_key VARCHAR, cr_value BIGINT, colony_m INTEGER)""")
con.executemany("INSERT INTO seed VALUES (?,?,?,?,?,?)", rows)

unmatched = con.execute("""
    SELECT c.species, count(*) FROM (
        SELECT split_part(english_name, ' - ', 1) AS species
        FROM staging.canonn_codex_event WHERE hud_category = 'Biology') c
    WHERE NOT EXISTS (SELECT 1 FROM seed s WHERE s.species = c.species)
    GROUP BY 1 ORDER BY 2 DESC""").fetchall()
print(f"seeded {len(rows)} species in {len({r[1] for r in rows})} genera")
print(f"Canonn biology names with no seeded species: {len(unmatched)}")
for name, n in unmatched:
    print(f"  {n:>9,}  {name}")

INPUT.mkdir(exist_ok=True)
con.execute(f"""COPY (SELECT * FROM seed ORDER BY genus, species)
                TO '{OUT.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
same = con.execute(f"""SELECT count(*) FROM (SELECT * FROM seed
                       EXCEPT SELECT * FROM '{OUT.as_posix()}')""").fetchone()[0]
print(f"wrote {OUT} ({len(rows)} rows), round-trips identical: {same == 0}")
con.close()
print("\nNOTE exobio_species was NOT touched. Merge with:"
      "\n  python etl/exobio_species/refresh.py")
print("\nDONE_SEED_EXOBIO_SPECIES")
