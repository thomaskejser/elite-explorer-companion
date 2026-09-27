CREATE TABLE IF NOT EXISTS system_catalog (
    system      VARCHAR NOT NULL PRIMARY KEY,
    type        VARCHAR NOT NULL,
    designation VARCHAR NOT NULL,
    system_id   BIGINT,
    missing_coordinate BOOLEAN
);

COMMENT ON TABLE system_catalog IS
'REAL-WORLD star catalogues, and whether Frontier shipped each entry as a playable
system. Loaded by etl/system_catalog/load.py from input/system_catalog.parquet, which
etl/system_catalog/seed.py seeds once from VizieR/CDS and the NASA Exoplanet Archive.

*** THIS TABLE IS NOT ABOUT THE GAME. IT IS ABOUT ASTRONOMY. *** Every other table here
starts from what Elite Dangerous contains and describes it. This one starts from what
the sky contains and asks how much of it made it in. So a row with system_id IS NULL is
not a gap in our data -- it is the ANSWER: a real star that Frontier did not ship.

*** THERE ARE TWO COVERAGE RATES AND THEY ANSWER DIFFERENT QUESTIONS. *** Frontier ships
each real star under ONE designation, and it is often not the one you looked up, so
"is this name in the game" and "is this star in the game" are not the same question:

    -- IS THE STAR IN THE GAME AT ALL? Counts an alias resolution, so it is the
    -- statement about the SKY. HIP 90.5%, HR 87.8%, SAO 36.1%, HD 25.7%, ALL 11.2%.
    SELECT type, count(*) AS in_catalogue, count(system_id) AS in_game,
           count(system_id) * 1.0 / count(*) AS coverage
    FROM system_catalog GROUP BY type ORDER BY in_game DESC;

    -- DID FRONTIER USE THIS CATALOGUE''S SPELLING? The statement about NAMING.
    -- HIP 60.1%, HD 7.7%, ALL 2.3%.
    SELECT c.type, count(*) FILTER (WHERE k.system_in_sector = c.system) AS own_name
    FROM system_catalog c LEFT JOIN system_known k USING (system_id) GROUP BY 1;

Hipparcos is 71,098 of 118,218 under its own name but 106,970 present somehow -- the
35,872 difference is stars the game named HD, TYC, SAO, a Durchmusterung, or something
that is not a catalogue designation at all (Sirius, Alpha Centauri, 61 Cygni). Both
numbers are printed by etl/system_catalog/load.py on every run, side by side, because
quoting one where the other belongs is the mistake this table exists to prevent.

*** 534,981 RESOLVED ROWS POINT AT 113,618 DISTINCT GAME SYSTEMS. *** One star carries
several designations, so many-names-to-one-system is the normal case and not a defect:
21 catalogue names is the widest, and it is a triple star whose three components each
carry an HD, an HR, a SAO, a TYC and a Durchmusterung number.

THE BRIGHT STARS ARE REACHED THROUGH THEIR GAME NAME, NOT THROUGH A CATALOGUE. Below
V=6 Frontier uses proper, Bayer and Flamsteed names -- Sirius, Alpha Centauri, 61 Cygni --
which are not catalogue designations and can never appear in this table. They resolve
anyway because system_catalog_alias carries edges that end at a GAME name: HR 2491,
HD 48915 and HIP 32349 all point at Sirius. Without those edges HR is 52% present
rather than 87.8%, and the ceiling is the 109,458 systems that name-matching alone
reaches.

*** THE COVERAGE RATE ONLY MEANS SOMETHING FOR CATALOGUES FRONTIER INGESTED WHOLESALE.
*** Four all-sky surveys appear in the game in trace amounts -- 2MASS (8,205 systems),
USNO-A2.0 (188), GSC (53), NOMAD1 (43) -- and they are DELIBERATELY ABSENT from this
table. Loading them would mean 3.83 BILLION rows (measured: ~50 GB of table, ~146 GB
more for the index, ~23 GB of parquet, ~219 GB all in) to compute a coverage rate of
0.000004%, which is not a rate but a rounding error. It would also mean going to IRSA,
USNO/NOFS and MAST by hand, because CDS does not distribute those four in bulk at all --
their FTP directories hold a ReadMe, a 1,000-row sample and a coverage map, and no data.
Resolve those few thousand names against SIMBAD one at a time instead. See DEAD_ENDS.md.

Cluster-member designations are absent for a different reason. In-game names like
"NGC 2539 ZUG 25", "IC 4756 ALC 85" and "Melotte 111 AV 186" are cluster PLUS member id,
so they do not join to NGC 2000.0''s 13,226-object list -- that lists the clusters, not
the stars in them. ~6,000 in-game systems are of this shape and need per-cluster
membership catalogues or SIMBAD, not a catalogue of clusters.';

COMMENT ON COLUMN system_catalog.system IS
'PRIMARY KEY. The full, PASTEABLE system name, exactly as the galaxy map''s search box
expects it: "HIP 1000", "BD+56 1773", "TYC 149-1079-1".

Composed by the builder as the catalogue''s prefix plus `designation`, using the prefix
the GAME actually renders rather than the one the catalogue prefers -- they differ, and
the game wins because this column has to be copyable. The worked example is Gliese: CDS
writes "Gl 695", the game writes "Gliese 695", and 293 of the 303 in-game Gliese systems
use the long form. Names here are therefore in game spelling even for the 3.7M rows that
have no game system at all.

Unique across ALL types, not just within one: "HIP 1000" is one name, and if two
catalogues ever collided on a string they would be describing the same star anyway.';

COMMENT ON COLUMN system_catalog.type IS
'WHICH CATALOGUE the row came from: HIP, HD, HR, GJ, LHS, NLTT, LP, SAO, TYC, BD, CD,
CPD, KOI. Both the provenance tag and the thing you GROUP BY to get a coverage rate, so
it is the reason the table is worth having rather than a bookkeeping column.

Stable strings, not free text. They match the prefix the game uses, which means
`type || '' '' || designation = system` for every type except the ones whose designation
carries its own sign (BD, CD, CPD: "BD" + "+56 1773") -- do not rely on that identity,
use `system`.';

COMMENT ON COLUMN system_catalog.designation IS
'The identifier WITHIN its catalogue, with the prefix stripped: "1000" for HIP 1000,
"+56 1773" for BD+56 1773, "149-1079-1" for TYC 149-1079-1.

Kept alongside the composed `system` because it is what you join to any other
astronomical source, all of which store the number and the catalogue separately. Stored
as VARCHAR and not an integer: Tycho-2 is three numbers, the Durchmusterungs carry a
signed zone, and Gliese has entries like "154.2".';

COMMENT ON COLUMN system_catalog.system_id IS
'REFERENCES system_known.system_id -- THE GAME SYSTEM THAT IS THIS STAR, whatever the game
chose to call it, or NULL.

*** NULL IS A FINDING, NOT A MISSING VALUE. *** It means the star is real and catalogued
and Frontier did not put it in the game. That is what this table is FOR, so never
"repair" a NULL, and never filter them out by default -- doing so throws away the answer
and leaves you measuring only what you already had.

RESOLVED IN TWO PHASES by etl/system_catalog/load.py, and the phase matters to what the
value MEANS:

  1. BY NAME -- exact match of this row''s `system` against system_known rows with
     sector_id = 0. Correct and cheap: a real-catalogue name is always hand-named, so it
     can only live under the ''crafted'' sentinel, which turns a 197.6M-row scan into a
     149,749-row one. (Sentinel rule from ETL.md: for sector_id = 0 the full name IS
     system_in_sector, with no sector prefix.) 109,458 rows. A name held by more than
     one hand-named game system resolves to NULL here rather than to a pick among them;
     transform.system_catalog_name counts those.
  2. BY IDENTITY -- walked across system_catalog_alias to a name that resolved in
     phase 1 or to a hand-named game system, iterated to a fixpoint. 401,961 rows. *** THIS IS WHY A NON-NULL system_id
     DOES NOT MEAN THE GAME USES THIS NAME. *** HIP 1000 and HD 812 are one star, shipped
     as HIP 1000, so both rows now carry that system_id -- which is the point: you can
     ask "is this star in the game" of any catalogue name and get the right answer.

To recover "did Frontier use THIS name", compare against the system''s own name; there is
no flag column because the join already answers it exactly:

    ... FROM system_catalog c JOIN system_known k USING (system_id)
        WHERE k.system_in_sector = c.system      -- shipped under its own name

*** BOTH PHASES ARE RECOMPUTED ON EVERY LOAD. *** Every system_id is first set to its
phase-1 name match (or NULL), which resets every alias-resolved value, and phase 2 then
re-derives from today''s edges -- so a corrected or retracted cross-ID takes its resolution
with it, and a system_id that system_known changes is followed on the next load. A
single bad cross-ID field can chain over a hundred unrelated names onto one system, so no
resolution may outlive the edge that justifies it.

A remaining NULL means: not shipped under this name, and not shipped under any other
name this table can reach. The reachable set is capped at the game systems a name match
or an alias edge arrives at -- so a star the game ships under a name that no catalogue and
no edge reaches is absent from this column while present in the game. Cross-identify via
SIMBAD before claiming a specific bright star is missing.';

COMMENT ON COLUMN system_catalog.missing_coordinate IS
'TRUE when NO USABLE DISTANCE for this star can be found in any source this project
holds, and so it cannot be placed in 3D. Usable means a parallax greater than zero whose
signal-to-noise (plx / e_plx) is at least 3; anything else -- absent, negative, or lost
in its own error bars -- is not a position.

*** THIS IS THE STRONGEST SINGLE EXPLANATION OF WHY A STAR IS NOT IN THE GAME, AND IT WAS
MEASURED. *** Over Hipparcos: a star with no parallax at all is absent from the game 98.1%
of the time, one with a negative or zero parallax 66.2%. Across the whole absent set 27.3%
have no usable parallax against 1.3% of the stars that were shipped -- a 21x enrichment,
against which faintness (secondary) and multiplicity (barely) do not compare. Stellar
Forge needs somewhere to put a star; where the astronomy could not say, Frontier did not
guess.

RESOLVED THROUGH THE ALIAS GRAPH, not from this row alone. A Tycho-2 entry carries no
parallax of its own, but if it is the same star as a Hipparcos entry that does, then the
star has a distance and this column says so. Parallaxes come from Hipparcos (I/239),
CNS3 (V/70A) and the Bright Star Catalogue (V/50), which are the catalogues here that
publish one at all.

*** READ IT AS "WE COULD NOT FIND A COORDINATE", NOT "THE MEASUREMENT FAILED". *** For the
deep surveys -- Tycho-2, the Durchmusterungs, SAO -- TRUE overwhelmingly means no
astrometric source we hold covers that star, which is a statement about our sources as
much as about the star. For Hipparcos, HR and Gliese, where a parallax is published for
essentially every entry, TRUE genuinely means the measurement did not yield a distance.
Separate the two by asking whether the row has a parallax source at all:

    SELECT type, count(*) FILTER (WHERE missing_coordinate) AS no_coordinate
    FROM system_catalog GROUP BY 1;

NULL means not yet computed -- the loader leaves it alone when the parallax staging table
is absent, rather than asserting FALSE it cannot support.';
