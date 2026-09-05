-- system_unfound: real stars we believe are in the game but cannot find by name.
-- No foreign key: the whole point of a row here is that it resolves to no system_id.
CREATE TABLE IF NOT EXISTS system_unfound (
    -- The catalogue name. Natural key and primary key, same as system_catalog.
    system      VARCHAR NOT NULL PRIMARY KEY,
    type        VARCHAR NOT NULL,
    -- WHERE THE ASTRONOMY PUTS IT, in game coordinates. Not a game position: no game
    -- system has been matched to this star, which is why the row exists.
    x           DOUBLE,
    y           DOUBLE,
    z           DOUBLE,
    dist_ly     DOUBLE,
    plx_snr     DOUBLE,
    vmag        DOUBLE,
    sp_type     VARCHAR,
    -- How far the position can be trusted, and what to do about it. See the comments.
    band        VARCHAR NOT NULL,
    -- WHICH SECTOR THE STAR SHOULD BE IN, so the overlay can offer it while you are
    -- there. Derived from the position, not from a name -- see the column comment.
    sector_id   INTEGER,
    sector      VARCHAR,
    -- The nearest HAND-NAMED game system, which is the only practical way to fly here:
    -- the galaxy map takes a name, not a coordinate.
    nearest     VARCHAR,
    nearest_ly  DOUBLE
);

-- --------------------------------------------------------------------------
-- COMMENTS, beside the DDL per ETL.md.
-- --------------------------------------------------------------------------

COMMENT ON TABLE system_unfound IS
'HUNTING LIST: real catalogued stars with a trustworthy astrometric position that no
system in the game can be matched to, by name or by any cross-identification we hold.
Built by etl/system_unfound/build.py from system_catalog + staging.catalog_parallax.

*** THESE ARE NOT PREDICTIONS AND THEY ARE DELIBERATELY NOT IN system_predicted. ***
That table is about Stellar Forge systems: its grain is a procedurally generated system,
`mass_code` is NOT NULL because the Forge letter gates every probability in it, and its
builder DELETES any row its pool no longer produces -- so rows inserted here by hand
would vanish on the next --build. A Hipparcos star has no mass code, no boxel and no
id64; forcing one in would mean inventing a Forge identity for a real star, which is
exactly the kind of fabricated key this project has been bitten by before.

The question a row asks is also different. system_predicted asks "what is IN this
system"; this asks "is this system THERE AT ALL". The answer is a visit, not a scan.

*** THE ANSWER IS GENUINELY UNKNOWN, AND THAT IS THE POINT. *** Every row is one of:
  1. a star the game HAS, under a name no catalogue assigns and position could not match
     (~15,800 game systems carry names Frontier invented outright);
  2. a star nobody has visited, so no dump carries it and no name can match;
  3. a star Frontier did not ship.
Only 1 and 2 can be settled by flying there, and 2 is the interesting one.

HOW TO USE IT. The galaxy map takes a NAME, not a coordinate, so fly to `nearest` and
look around from there -- `nearest_ly` says how far the remaining hop is. Under ~5 ly
that is one jump and a visual check.';

COMMENT ON COLUMN system_unfound.system IS
'PRIMARY KEY: the catalogue name, in the game''s spelling, exactly as system_catalog
holds it. Paste it into the galaxy map FIRST -- if it resolves, this row is stale and the
star was found under its own name after all, which is worth knowing.';

COMMENT ON COLUMN system_unfound.band IS
'WHICH KIND OF CANDIDATE THIS IS, because the two are worth very different effort:

  "near"  -- inside 300 ly with a parallax good enough that the position is trustworthy
             to about a light year. A hand-named game system sitting at that spot would
             have been matched already, so there is genuinely nothing there under a name
             we can reach. THE STRONGEST CANDIDATES: if the star is in the game at all it
             is unvisited, or named something no catalogue lists.
  "mid"   -- 300 to 1,000 ly. The parallax still clears the quality bar, but at this
             range a 10% distance error is 30-100 ly against a mean system spacing of
             about 4 ly, so a positional match CANNOT be made either way. Absence from
             the matched list is a limit of the method here, not evidence about the game.
             Treat these as unverified rather than as finds.

Nothing beyond 1,000 ly is listed: the position would be a guess dressed as a target.';

COMMENT ON COLUMN system_unfound.x IS
'GAME-FRAME x, computed from the catalogue''s parallax and galactic coordinates, NOT read
from any dump. The frame is the galactic one rotated: x = -Y_gal, y = Z_gal, z = X_gal,
fitted against the 71,098 Hipparcos stars that DO resolve by name and reproducing them to
well under a light year nearby. Accurate to roughly dist_ly / plx_snr.';

COMMENT ON COLUMN system_unfound.y IS 'GAME-FRAME y. See the x comment for the frame.';
COMMENT ON COLUMN system_unfound.z IS 'GAME-FRAME z. See the x comment for the frame.';

COMMENT ON COLUMN system_unfound.type IS
'The catalogue this name comes from: HIP, GJ or HR. Restricted to the three that publish
a parallax, because a candidate without a position is not a place you can go -- 92% of
system_catalog has no usable coordinate at all and is silently excluded here.';

COMMENT ON COLUMN system_unfound.dist_ly IS
'Distance from Sol implied by the parallax, in light years. The uncertainty is roughly
dist_ly / plx_snr, which is what makes the 300 ly boundary in `band` matter.';

COMMENT ON COLUMN system_unfound.plx_snr IS
'plx / e_plx. At least 3 for every row here and at least 10 for the "near" band -- the
error on the distance is 1/snr, so snr 10 is a 10% position and snr 3 is a 33% one.';

COMMENT ON COLUMN system_unfound.vmag IS
'Visual magnitude. Useful for expectation-setting: a V=11 red dwarf will not be visible
in the galaxy map from a distance, while a V=5 star should be obvious.';

COMMENT ON COLUMN system_unfound.sp_type IS
'Spectral type as the catalogue publishes it. An M dwarf here is unremarkable; an O, B or
supergiant type would be worth checking carefully, because a star that bright being
absent from every dump is a strong claim.';

COMMENT ON COLUMN system_unfound.nearest IS
'The nearest HAND-NAMED game system -- the practical way in, since the galaxy map takes a
name and not a coordinate. Plot to it, then look for an unnamed system at the offset
given by nearest_ly.';

COMMENT ON COLUMN system_unfound.nearest_ly IS
'Distance from this star''s computed position to `nearest`, in light years. NULL when no
hand-named system is within 20 ly, which for a "near" row makes it a harder trip and a
more interesting one.';

COMMENT ON COLUMN system_unfound.sector_id IS
'The sector this star''s POSITION falls in, so the overlay can offer it while you are
flying that sector. Assigned by nearest sector centroid from `sector`, NOT parsed from a
name -- these stars have no procedural name to parse, which is the whole reason they are
here.

*** AN APPROXIMATION, AND THE ERROR IS THE SAME ONE THE ROW CARRIES ANYWAY. *** Sector
cells are 1,280 ly across and their recorded centres are bounding-ball centres rather
than cell centres, so a star near a boundary can land in the neighbour. For a `near` row
the position is good to a few light years and the assignment is reliable; for a `mid` row
the position error is 100-333 ly and the sector is a hint, not a fact. Read it with
`band`, never alone.';

COMMENT ON COLUMN system_unfound.sector IS
'The sector name, carried beside sector_id so a query does not need the join. Same
approximation as sector_id.';
