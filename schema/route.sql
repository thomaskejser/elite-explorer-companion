-- route: APP STATE. Solved jump chains this commander means to fly.
-- Lives in elite_mapping_v2_current.duckdb, never in the model.
CREATE TABLE IF NOT EXISTS route (
    route       VARCHAR NOT NULL CHECK (trim(route) <> ''),
    hop         INTEGER NOT NULL CHECK (hop >= 0),
    system      VARCHAR NOT NULL CHECK (trim(system) <> ''),
    x           DOUBLE,
    y           DOUBLE,
    z           DOUBLE,
    -- A hop longer than the range it was solved for is a route that cannot be flown.
    hop_ly      DOUBLE CHECK (hop_ly IS NULL OR hop_ly <= boosted_ly),
    to_go_ly    DOUBLE,
    is_neutron  BOOLEAN NOT NULL,
    boosted_ly  DOUBLE NOT NULL CHECK (boosted_ly > 0),
    jumps       INTEGER NOT NULL CHECK (jumps > 0),
    PRIMARY KEY (route, hop)
);

COMMENT ON TABLE route IS
'APP STATE: a solved chain of jumps, one row per hop, that this commander intends to fly.
Seeded from input/route.parquet by etl/route/load.py.

*** THE OVERLAY DOES NOT FLY THE HOPS STORED HERE. *** It solves its own chain, from
where the ship is standing, at the range the ship actually jumps -- see
common/neutron_route.py, which does it in a second or two. A stored chain was solved for
another position and another ship, so following it would mean flying a route solved for
somebody else. What the overlay takes from this table is the ENDPOINTS: a name and a
position for each end, which is the only place the app-state database knows where
"Shinrarta Dezhra" is. Storing a route is therefore how a destination is registered, and
the hops are the record of one answer rather than a thing to obey.

*** IT IS APP STATE, NOT MODEL. *** The galaxy did not produce this: a route is an
intention, chosen by a commander, over a jump range only that commander''s ship has. Two
ships in the same system get different answers and neither is more correct. Nothing in
etl/ can reproduce a row here, which is the test that decides which database a table
lives in.

*** NAMES AND COORDINATES, NEVER system_id. *** A route survives a re-key of the model
precisely because it holds no model surrogate: the hops are the pasteable names the
galaxy map takes and the positions they sit at, both of which are facts about the game
rather than about our schema.

WHAT ONE ROW MEANS: hop 0 is where the route starts and carries no hop_ly, because
nothing was flown to reach it. Hops 1..jumps are the jumps, in order, each naming the
system you arrive at. So a route of 46 jumps is 47 rows, and jumps = max(hop).

THE ROUTE IS SOLVED FOR A RANGE AND IS ONLY VALID AT THAT RANGE. boosted_ly is on every
row for that reason -- it is not decoration, it is the assumption the chain depends on.
A ship that jumps less far cannot fly these hops at all.

The one route on file was solved Colonia -> Shinrarta Dezhra at 500 ly boosted: 46 jumps
against a straight-line floor of ceil(22,000.98 / 500) = 45, with 45 neutron stars
between the endpoints. The floor is unreachable and that was PROVEN rather than assumed
-- a breadth-first search with the admissible prune "jumps_so_far + ceil(distance_left /
500) > 45" over the 451,382 neutrons within 2,000 ly of the line ran out of live stars at
jump 41 with 2,480 ly still to run. Endpoints are exact game coordinates: Colonia from
main.system_known and the journal''s own FSDJump agreeing, Shinrarta Dezhra from 11
journal records carrying SystemAddress 3932277478106.

*** FUEL IS NOT MODELLED. *** Neutron stars cannot be scooped, so a chain of 45
consecutive supercharges is not by itself flyable -- scoopable stars have to be woven in
by whoever flies it. Nor is the first hop out of a non-neutron start special-cased: it is
assumed boosted like every other, which in game it cannot be.';

COMMENT ON COLUMN route.route IS
'Which route this hop belongs to, and the first half of the natural key. Free text chosen
by whoever solved it ("Colonia -> Shinrarta Dezhra"); it names an intention, so there is
nothing to normalise it against.';

COMMENT ON COLUMN route.hop IS
'Position in the chain and the second half of the natural key. 0 is the origin, 1..jumps
are the jumps in flight order. *** A HOP NUMBER IS NOT A SURROGATE ID *** -- it is the
order itself, so re-solving a route renumbers hops and that is correct rather than the
renumbering merge-never-drop forbids. See the deletion note below.';

COMMENT ON COLUMN route.system IS
'The FULL, PASTEABLE system name of the hop -- what goes into the galaxy map search box
and onto the clipboard. Composed as "<sector> <designation>" with sector_id = 0 standing
alone, which is why hop 45 of the stored route is "PSR J1752-2806" rather than a boxel
name: it is a real catalogued pulsar.';

COMMENT ON COLUMN route.x IS
'Galactic x in ly of this hop, so the overlay can rank hops by distance from the ship
without resolving a single name. Copied from the source the route was solved against --
model.system_neutron for a waypoint, the game''s own journal for an endpoint.';

COMMENT ON COLUMN route.y IS 'Galactic y in ly. See x.';

COMMENT ON COLUMN route.z IS 'Galactic z in ly. See x.';

COMMENT ON COLUMN route.hop_ly IS
'Light-years flown from the previous hop to this one. NULL at hop 0, which was not flown
to. CHECKed against boosted_ly, so a chain the ship could not make cannot be stored.';

COMMENT ON COLUMN route.to_go_ly IS
'Straight-line ly from this hop to the route''s final system. Stored rather than derived
because it is what says how much of the route is left without walking the remaining rows,
and it is a property of the solved chain rather than of the ship.';

COMMENT ON COLUMN route.is_neutron IS
'TRUE for the supercharge waypoints, FALSE for the two ENDPOINTS. The distinction is the
whole reason the chain works: the range assumed in boosted_ly is only available leaving a
neutron star, so a FALSE row is a hop where that assumption does not hold.';

COMMENT ON COLUMN route.boosted_ly IS
'The jump range the route was solved for, repeated on every row. Fly it with less and the
hops do not reach; the chain is not a suggestion that degrades gracefully.';

COMMENT ON COLUMN route.jumps IS
'Total jumps in the route -- max(hop) -- repeated on every row so a single row answers
"how long is this" without an aggregate.';
