CREATE TABLE IF NOT EXISTS system_known_probe (
    system VARCHAR NOT NULL
);

COMMENT ON TABLE system_known_probe IS
'*** NOT A CENSUS, NOT A SYSTEM LIST, AND NOT system_known. *** A membership probe and
nothing else: the name of every system in the dumps that could still turn out to be a
rare find, so the overlay can answer system_seen.is_known / system_confirmed.is_known
with no model database attached. system_known holds 200,676,922 rows and this holds a
pruned 6,976,174, so a count here counts what survived the pruning and says nothing about
the galaxy. Never quote it as a total of anything.

BUILT BY etl/refresh_current.py, NOT BY THE MODEL: it lives only in the app-state
database and is rebuilt whole on every refresh, so it is a cache of the model and the
merge-never-drop rule does not reach it. Rebuild it whenever the model is re-merged, or
it answers with the previous galaxy.

A row of system_known is KEPT when either its recorded primary star is one of the arrival
classes app/kinds.py can confirm (4,509,144 rows), or it has NO recorded primary star and
its mass code is at or above the floor etl/refresh_current.py states -- or it is
hand-named and so has no mass code. Everything else is dropped because the dumps rule it
out: 70,187,876 systems whose recorded primary is a class nothing here confirms, since an
M dwarf cannot be your black hole, and the unrecorded systems below the mass-code floor,
where the Forge builds none of these objects.

*** ONE-SIDED. A HIT IS PROOF, A MISS IS NOT. *** Absence does not mean the system is
absent from the dumps, so resolve_known() writes TRUE on a hit and leaves NULL on a miss
-- it must never write FALSE from this table. Measured against every row of
system_confirmed: of 1,655 systems that ARE in the dumps it finds 1,250 and misses 405,
and of 702 that are not it returns 0. Every miss is a neutron (384) or a white dwarf
(21), which the Forge builds at mass code d, one below the floor; black holes,
Wolf-Rayets, supergiants, Herbigs and O-types have no rows below the floor at all and are
exact, 0 missed of 423. A miss reads as "nobody has reported this", so the cost is a
neutron offered as a find that somebody already holds -- which is the direction is_known
is already wrong in whenever it is NULL.

The pruning is EMPIRICAL, measured over 74,697,020 recorded primary stars, not a proof
about the Stellar Forge. One counterexample exists -- a single O-type at mass code c in
22,102,247 -- and it is likelier one of the documented duplicate-name defects than a real
one. It also shrinks as the sources improve: every system that gains body data moves out
of the unrecorded rule into either the confirmable set or the discard pile, which is the
safe direction.';

COMMENT ON COLUMN system_known_probe.system IS
'The full pasteable system name, composed from main.system_known and main.sector at
refresh time, and NEVER by naively concatenating sector onto system_in_sector: only
sector_id = 0 means a name stands alone, and sector row 0 is literally named ''crafted'',
so the naive form emits ''crafted Sol''. That mistake has cost this project twice, most
recently 149,726 unpasteable names in a work table nobody was reading closely. The natural key of every app-state table, which
is what makes it the right key here: system_seen.id64 is NULL on almost every row, so a
probe keyed on id64 would need a name-to-address resolution the app has no way to do.

NO PRIMARY KEY AND NO INDEX, DELIBERATELY. Rows are inserted in name order, giving every
row group a min/max zonemap that an equality probe uses to skip almost the whole table:
300 ms on a cold connection and 3 ms on a warm one, against a full scan of the model''s
200.8M system rows -- which it also does not have to open. The cold cost is flat in the number of names probed --
one name and two hundred both measure ~300 ms -- so batching costs nothing extra. An ART
index would add build time and file size to answer the same question no faster.
*** INSERT IN SORTED ORDER OR THE TABLE STOPS BEING FAST *** -- nothing here will tell
you it was not, and the connection this is built on turns preserve_insertion_order off
for the mirror''s sake, which discards an ORDER BY unless it is turned back on.';
