-- system_wrong: APP STATE. Systems the commander has established do not exist.
-- Lives in elite_mapping_v2_current.duckdb, never in the model.
CREATE TABLE IF NOT EXISTS system_wrong (
    system      VARCHAR NOT NULL PRIMARY KEY,
    -- Which list it was offered from, so a correction can be traced to what produced it.
    source      VARCHAR,
    sector      VARCHAR,
    -- Cross-database join key only, unenforced, NULL is normal (ETL.md section 0).
    id64        BIGINT,
    marked_utc  VARCHAR NOT NULL,
    note        VARCHAR
);

COMMENT ON TABLE system_wrong IS
'APP STATE: systems this commander has personally established DO NOT EXIST -- the route
would not plot, or the arrival found nothing. Written by the overlay on SHIFT+BACKSPACE
and by nothing else.

*** THIS IS THE ONLY KIND OF NEGATIVE EVIDENCE THE PROJECT CAN COLLECT, AND IT CANNOT BE
DERIVED. *** Every other table here is built from what somebody reported seeing. Nobody
reports an absence, so a system that does not exist is indistinguishable from one nobody
has visited -- except to the commander who just tried to plot to it and was refused. That
makes these rows irreplaceable in the way flight logs are irreplaceable: re-running the
pipeline cannot reproduce a single one.

*** IT LIVES IN THE APP DATABASE BECAUSE THE APP MAY NEVER WRITE THE MODEL. *** The
model is derived and fully rebuildable, so a row written there would be erased by the
next merge with no warning (ETL.md section 0). The overlay therefore FILTERS against this
table rather than deleting from system_predicted or system_unfound -- the prediction
stays, and this says the commander has settled it.

WHY A SYSTEM MIGHT NOT EXIST, and all three are worth recording the same way:
  * a boxel prediction (system_predicted, is_catalog = FALSE) enumerated an index gap the
    Forge never filled -- the layer is a lower bound and was always expected to contain
    misses;
  * a system_unfound star whose game system genuinely is not there, which is the answer
    that list exists to get;
  * a catalogued system whose name the galaxy map will not take, which usually means a
    spelling difference rather than an absence -- worth a note before trusting it.

`note` is free text for that last case. A row with no note is a plain "did not plot".';

COMMENT ON COLUMN system_wrong.system IS
'PRIMARY KEY: the system name exactly as the overlay offered it, which is the string that
was pasted into the galaxy map and refused. Kept verbatim rather than normalised -- if
the name was wrong, THAT is the finding, and rewriting it would erase the evidence.';

COMMENT ON COLUMN system_wrong.source IS
'Which list offered it: "predicted" (system_predicted) or "unfound" (system_unfound).
Provenance for the correction, and the thing to GROUP BY when asking which layer is
producing misses -- a boxel layer with a high wrong-rate is a measurement about the
enumeration, not just about one system.';

COMMENT ON COLUMN system_wrong.sector IS
'The sector the row was offered under, carried so a miss can be located without a join
back to a model table the app may not have attached.';

COMMENT ON COLUMN system_wrong.id64 IS
'The game id64 when the offering row had one -- boxel predictions do not. JOIN KEY ONLY,
unenforced and usually NULL, exactly like every other id64 in this database: there are no
cross-database foreign keys in DuckDB and the app cannot depend on the model being
attached at the moment it writes.';

COMMENT ON COLUMN system_wrong.marked_utc IS
'When the commander marked it, ISO-8601 UTC to the second. A miss is a fact about the
galaxy AT A VERSION of the game: Frontier has added systems before, so an old row is
weaker evidence than a new one and this is what says which it is.';

COMMENT ON COLUMN system_wrong.note IS
'Free text, normally NULL. For the case worth distinguishing: a name the galaxy map would
not accept, which is a SPELLING problem rather than a missing system.';
