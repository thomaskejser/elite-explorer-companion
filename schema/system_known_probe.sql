CREATE TABLE IF NOT EXISTS system_known_probe (
    system VARCHAR NOT NULL
);

COMMENT ON TABLE system_known_probe IS
'*** NOT A CENSUS, NOT A SYSTEM LIST, AND NOT system_known. *** A membership probe and nothing else: the name of every SCANNED system -- one with body data in the model''s system_body -- that could hold a rare arrival star, so the overlay can answer system_seen.is_known / system_confirmed.is_known with no model database attached. A count here counts what survived the pruning and says nothing about the galaxy.

BUILT BY etl/refresh_current.py, NOT BY THE MODEL: it lives only in the app-state database and is rebuilt whole on every refresh, so it is a cache of the model and the merge-never-drop rule does not reach it.

A row of system_known is KEPT when it has at least one system_body row, AND either its recorded primary star is one of the arrival classes overlay/src/kinds.rs can confirm, or it has no recorded primary star and its mass code is at or above the floor etl/refresh_current.py states, or it is hand-named. *** A SYSTEM WITH NO BODY DATA IS NEVER HERE, EVEN WITH A RARE PRIMARY: *** a route plot reports a system''s arrival-star class without anyone scanning it, so its rare star is still undiscovered (sources.md).

*** ONE-SIDED. A HIT IS PROOF, A MISS IS NOT. *** A miss can be a scanned system the pruning dropped (a neutron or white dwarf below the mass-code floor), so resolve_known() writes TRUE on a hit and never FALSE from this table.';

COMMENT ON COLUMN system_known_probe.system IS
'The full pasteable system name, composed from main.system_known and main.sector at
refresh time, and NEVER by naively concatenating sector onto system_in_sector: only
sector_id = 0 means a name stands alone, and sector row 0 is literally named ''crafted'',
so the naive form emits ''crafted Sol''. That mistake has cost this project twice, most
recently 149,726 unpasteable names in a work table nobody was reading closely. The natural key of every app-state table, which
is what makes it the right key here: system_seen.system_id is NULL on almost every row, so a
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
