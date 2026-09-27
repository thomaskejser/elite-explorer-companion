"""Fewest-jump neutron routing. Primes from the app-state database, solves in memory.

    python -m common.neutron_route --from Colonia --to "Shinrarta Dezhra" --range 500

writes `input/route.parquet`, which `etl/route/load.py` merges into `main.route` and the
overlay offers as a row per direction in its Nearest table.

*** THE JUMP COUNT IS PROVEN, NOT PROPOSED. *** No hop can exceed the boosted range, so
no route can be shorter than `ceil(straight_line / range)` jumps. The solver tries that
floor first and walks up one jump at a time, so the first length that yields a route is
the minimum by construction -- every shorter length was searched to exhaustion and found
empty.

THE SEARCH is breadth-first over unit-cost edges with an admissible prune. Every hop
costs exactly one jump, so breadth-first order IS cheapest-first and no priority queue is
needed; a star is dropped the moment `jumps_so_far + ceil(distance_left / range)` exceeds
the length being tried, which is A*'s test with `h = ceil(d / range)`. That h never
overestimates and is consistent, so nothing that could have won is discarded.

*** AND THE NEIGHBOUR QUESTION IS ASKED BACKWARDS, WHICH IS THE WHOLE PERFORMANCE
STORY. *** A 500 ly sphere in the Colonia corridor holds a mean of 4,217 neutron stars
(median 1,838, max 27,309), so the neighbour graph over 451,382 of them has about a
BILLION undirected edges. Asking each frontier star "who is within range of me" pays for
all of them: 215 s with a KD-tree, 288 s with a hand-built uniform grid whose cells were
the jump range -- the layout was never the problem. But a star is reached at level k+1 if
ANY frontier star is within one jump, which is a nearest-neighbour query with a cutoff:
one lookup per candidate, logarithmic, and it returns the parent for free. The forward
query's output is thousands of neighbours; the reversed query's output is one bit and one
index, which is all the answer ever needed. Same graph, same BFS, same prune, 0.47 s.

*** FUEL IS NOT MODELLED. *** Neutron stars cannot be scooped, so a chain of supercharges
is not by itself flyable -- scoopable stars have to be woven in by whoever flies it. Nor
is the first hop out of a non-neutron start special-cased: it is assumed boosted like
every other, which in game it cannot be.
"""
import argparse
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.current import MODEL_SCHEMA, attach_model, connect, full_name_sql
from common.db import ROOT

SEED = ROOT / "input" / "route.parquet"
# How many jumps above the floor to search, and therefore how wide the corridor must be.
# Each extra jump widens the region a route could occupy, so this is not a free knob:
# 1 is the usual answer, because the floor is almost always missed by exactly one.
DEFAULT_OVER = 1


def corridor_radius(direct, jump_ly, over=DEFAULT_OVER):
    """How far off the straight line a route of `floor + over` jumps could stray. -> ly.

    *** DERIVED, NOT GUESSED, AND THAT IS WHAT MAKES THE ANSWER A PROOF. *** A chain of
    L jumps at range R has total path length at most L*R, so every star it could possibly
    use satisfies `dist(start, s) + dist(s, goal) <= L*R` -- which is the definition of a
    prolate spheroid with the endpoints as foci. Its half-width is sqrt(a^2 - c^2), with
    a = L*R/2 and c = half the straight line. Gather that much and "no route of L jumps
    exists" is a statement about the galaxy rather than about the box we happened to look
    in.

    A fixed corridor cannot say that: 2,000 ly was the first guess for Colonia ->
    Shinrarta Dezhra, and the honest figure at 46 jumps is 3,353. This closes that gap.
    """
    a = (math.ceil(direct / jump_ly) + over) * jump_ly / 2.0
    c = direct / 2.0
    return math.sqrt(max(a * a - c * c, 0.0))


def resolve_system(con, name):
    """-> (x, y, z, where it came from) for `name`, or (None, None, None, why not).

    THE APP-STATE DATABASE HAS NO GENERAL NAME->POSITION TABLE, because `system_known`
    is 197M rows and is not mirrored. So this asks every table that happens to hold a
    position, in order of how much it is to be trusted, and says which one answered --
    a route is only as good as its endpoints, and "which source" is the first question
    to ask when one looks wrong.

    The model is tried last and only if it is free: it has the authoritative answer in
    `main.system_known`, but it is a 60 GiB file that a merge may be halfway through.
    """
    tries = [
        # A route already flown names its own endpoints, and those positions came from
        # the game. Cheapest and most trustworthy source there is.
        ("main.route", "SELECT x, y, z FROM main.route WHERE system = ? LIMIT 1"),
        ("main.system_seen", "SELECT x, y, z FROM main.system_seen "
                             "WHERE system = ? AND x IS NOT NULL"),
        (f"{MODEL_SCHEMA}.system_poi", f"SELECT x, y, z FROM {MODEL_SCHEMA}.system_poi "
                                       f"WHERE system = ?"),
        (f"{MODEL_SCHEMA}.carrier_position",
         f"SELECT x, y, z FROM {MODEL_SCHEMA}.carrier_position WHERE system = ? "
         f"LIMIT 1"),
        (f"{MODEL_SCHEMA}.system_neutron",
         f"""SELECT k.x, k.y, k.z FROM {MODEL_SCHEMA}.system_neutron k
             JOIN {MODEL_SCHEMA}.sector sc ON sc.sector_id = k.sector_id
             WHERE {full_name_sql()} = ?"""),
    ]
    for source, sql in tries:
        try:
            row = con.execute(sql, [name]).fetchone()
        except Exception:
            continue
        if row and row[0] is not None:
            return (*row, source)
    try:
        attached = attach_model(con, "src")
    except Exception:
        # A LOCKED MODEL IS NOT AN ERROR HERE. It is a 60 GiB file with one writer, and
        # `etl/` may well be holding it -- which is exactly when someone plots a route
        # to pass the time. Fall through to the answer below.
        attached = None
    if attached is not None:
        row = con.execute(f"""
            SELECT k.x, k.y, k.z FROM src.main.system_known k
            JOIN src.main.sector sc ON sc.sector_id = k.sector_id
            WHERE {full_name_sql()} = ? AND k.x IS NOT NULL""", [name]).fetchone()
        if row:
            return (*row, "model.system_known")
    return (None, None, None,
            "no table here holds a position for that name, and the model is not "
            "available -- pass --from-xyz/--to-xyz, or fly there once")


class Corridor:
    """Every neutron star near one straight line, in the arrays the search wants.

    PRIMED ONCE AND SOLVED MANY TIMES: the geometry that depends on the endpoints --
    distance to the goal, and the jumps that must remain from each star -- is computed
    here, so trying successive route lengths costs only the search.
    """

    def __init__(self, names, pts, start, goal, jump_ly,
                 start_name="(start)", goal_name="(goal)"):
        self.names = names
        # The endpoints are not neutron stars and are not in `names`, but they ARE hops
        # 0 and last, and route.system is NOT NULL -- a chain that cannot say where it
        # begins is not a chain.
        self.start_name, self.goal_name = start_name, goal_name
        self.pts = np.ascontiguousarray(pts, dtype=np.float64)
        self.start = np.asarray(start, dtype=np.float64)
        self.goal = np.asarray(goal, dtype=np.float64)
        self.jump_ly = float(jump_ly)
        self.direct = float(np.linalg.norm(self.goal - self.start))
        self.floor = math.ceil(self.direct / self.jump_ly)
        self.to_goal = np.linalg.norm(self.pts - self.goal, axis=1)
        # The prune, precomputed: jumps that must still be flown from each star, at best.
        self.need = np.ceil(self.to_goal / self.jump_ly).astype(np.int32)
        self.max_limit = self.floor + DEFAULT_OVER
        self.radius = None
        self.first = np.flatnonzero(
            np.linalg.norm(self.pts - self.start, axis=1) <= self.jump_ly)

    @classmethod
    def prime(cls, con, start, goal, jump_ly, radius=None, names=None,
              over=DEFAULT_OVER):
        """Pull the corridor out of the app-state database's neutron mirror.

        NAMES ARE COMPOSED HERE, and that is the point of the table rather than a
        shortcut: a hop is only useful if it can be pasted into the galaxy map. It uses
        the one definition in common.current, so `sector_id = 0` still stands alone.

        Coordinates and names only -- never `system_id`. The model re-keys that column,
        and a route that stored it would rot the next time it did.
        """
        radius = radius or corridor_radius(math.dist(start, goal), jump_ly, over)
        sql = f"""
            WITH line AS (
              SELECT ?::DOUBLE ax, ?::DOUBLE ay, ?::DOUBLE az,
                     ?::DOUBLE dx, ?::DOUBLE dy, ?::DOUBLE dz, ?::DOUBLE len2),
            proj AS (
              SELECT k.x, k.y, k.z, k.sector_id, k.system_in_sector, l.*,
                     ((k.x - l.ax) * l.dx + (k.y - l.ay) * l.dy
                      + (k.z - l.az) * l.dz) / l.len2 AS t
              FROM {MODEL_SCHEMA}.system_neutron k, line l
              WHERE k.x IS NOT NULL)
            SELECT {full_name_sql('proj', 'sc')} AS system,
                   proj.x AS x, proj.y AS y, proj.z AS z
            FROM proj
            JOIN {MODEL_SCHEMA}.sector sc ON sc.sector_id = proj.sector_id
            WHERE proj.t BETWEEN -0.05 AND 1.05
              AND (proj.x - (proj.ax + proj.t * proj.dx)) ** 2
                + (proj.y - (proj.ay + proj.t * proj.dy)) ** 2
                + (proj.z - (proj.az + proj.t * proj.dz)) ** 2 <= ?"""
        d = [goal[i] - start[i] for i in range(3)]
        len2 = sum(v * v for v in d)
        cols = con.execute(sql, [*start, *d, len2, radius * radius]).fetchnumpy()
        pts = np.column_stack([cols["x"], cols["y"], cols["z"]])
        out = cls([str(s) for s in cols["system"]], pts, start, goal, jump_ly,
                  *(names or ()))
        out.radius = radius
        # The longest route this corridor can HONESTLY answer for. Searching past it
        # would be searching a box that no longer holds every candidate route.
        out.max_limit = out.floor + over
        return out

    # -- the search ------------------------------------------------------------------
    def reach(self, limit):
        """Breadth-first to `limit` jumps. -> (index of the last hop, parents) or None.

        The frontier is a KD-tree and the candidates query IT, not the other way round:
        see the module docstring. One tree per level, over the frontier alone, which is
        thousands of points rather than hundreds of thousands.
        """
        from scipy.spatial import cKDTree

        level = np.full(len(self.pts), -1, np.int32)
        parent = np.full(len(self.pts), -1, np.int64)
        frontier = self.first[1 + self.need[self.first] <= limit]
        level[self.first] = 1
        for k in range(2, limit + 1):
            done = frontier[self.to_goal[frontier] <= self.jump_ly]
            if done.size:
                return int(done[np.argmin(self.to_goal[done])]), parent
            if not frontier.size:
                return None
            # Everything still worth reaching: unvisited, and near enough to the goal
            # that the jumps left could still finish it.
            live = np.flatnonzero((level < 0) & (k + self.need <= limit))
            if not live.size:
                return None
            tree = cKDTree(self.pts[frontier])
            dist, near = tree.query(self.pts[live], k=1,
                                    distance_upper_bound=self.jump_ly, workers=-1)
            hit = dist <= self.jump_ly
            fresh = live[hit]
            if not fresh.size:
                return None
            parent[fresh] = frontier[near[hit]]
            level[fresh] = k
            frontier = fresh
        return None

    def solve(self, report=print):
        """The shortest chain there is. -> list of hop dicts, or None.

        Climbs from the floor, so the first length that answers is the minimum and every
        shorter one has been PROVEN empty rather than given up on.
        """
        if self.direct <= self.jump_ly:
            # *** ONE JUMP, NO CHAIN. *** The search only ever builds routes THROUGH a
            # neutron star, so without this a destination already in range comes back as
            # two jumps: out to a cone and back. Nothing to supercharge for.
            if report:
                report("  1 jump: straight there, no chain needed")
            return self.hops([])
        for limit in range(self.floor, self.max_limit + 1):
            found = self.reach(limit)
            if found is None:
                if report:
                    report(f"  {limit} jumps: no route exists through these stars")
                continue
            final, parent = found
            chain = []
            node = final
            while node >= 0:
                chain.append(node)
                node = parent[node]
            chain.reverse()
            if report:
                report(f"  {limit} jumps: FOUND"
                       + ("" if limit == self.floor else
                          f" (the floor of {self.floor} is unreachable)"))
            return self.hops(chain)
        return None

    def hops(self, chain):
        """The solved chain as rows, shaped exactly as input/route.parquet."""
        xyz = [self.start] + [self.pts[i] for i in chain] + [self.goal]
        names = ([self.start_name] + [self.names[i] for i in chain]
                 + [self.goal_name])
        out = []
        for i, p in enumerate(xyz):
            step = None if i == 0 else float(np.linalg.norm(p - xyz[i - 1]))
            out.append({"hop": i, "system": names[i],
                        "x": float(p[0]), "y": float(p[1]), "z": float(p[2]),
                        "hop_ly": None if step is None else round(step, 2),
                        "to_go_ly": round(float(np.linalg.norm(p - self.goal)), 1),
                        "is_neutron": 0 < i < len(xyz) - 1})
        return out


def write_seed(hops, route, jump_ly, out=SEED, con=None):
    """Write the solved chain to input/route.parquet. -> the path.

    VERIFIED BEFORE IT IS WRITTEN. A hop beyond the range, a chain that does not start
    and end where it was asked to, or a system appearing twice all mean the search is
    wrong, and a route nobody can fly is worse than no route.
    """
    import duckdb

    jumps = len(hops) - 1
    assert all(h["hop_ly"] <= jump_ly for h in hops[1:]), "a hop is out of range"
    assert all(h["system"] for h in hops), "a hop has no name"
    assert len({h["system"] for h in hops}) == len(hops), "a system repeats"
    con = con or duckdb.connect()
    con.execute("CREATE OR REPLACE TEMP TABLE seed (route VARCHAR, hop INTEGER, "
                "system VARCHAR, x DOUBLE, y DOUBLE, z DOUBLE, hop_ly DOUBLE, "
                "to_go_ly DOUBLE, is_neutron BOOLEAN, boosted_ly DOUBLE, "
                "jumps INTEGER)")
    con.executemany("INSERT INTO seed VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [(route, h["hop"], h["system"], h["x"], h["y"], h["z"],
                      h["hop_ly"], h["to_go_ly"], h["is_neutron"], jump_ly, jumps)
                     for h in hops])
    out.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY seed TO '{pathlib.Path(out).as_posix()}' (FORMAT parquet)")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="origin", required=True, help="system to start from")
    ap.add_argument("--to", dest="dest", required=True, help="system to reach")
    ap.add_argument("--range", type=float, default=500.0,
                    help="boosted jump range in ly (default 500)")
    ap.add_argument("--corridor", type=float,
                    help="ly off the line to gather stars; derived from the range "
                         "and --over unless given, which is what makes it a proof")
    ap.add_argument("--over", type=int, default=DEFAULT_OVER,
                    help=f"jumps above the floor to search (default {DEFAULT_OVER})")
    ap.add_argument("--from-xyz", dest="origin_xyz", nargs=3, type=float,
                    metavar=("X", "Y", "Z"),
                    help="coordinates for --from, when nothing here knows them")
    ap.add_argument("--to-xyz", dest="dest_xyz", nargs=3, type=float,
                    metavar=("X", "Y", "Z"), help="coordinates for --to")
    ap.add_argument("--name", help="route name; defaults to 'A -> B'")
    ap.add_argument("--out", type=pathlib.Path, default=SEED)
    ap.add_argument("--dry-run", action="store_true",
                    help="solve and print, write nothing")
    args = ap.parse_args()

    con = connect(read_only=True)
    try:
        ends = {}
        for role, name, given in (("from", args.origin, args.origin_xyz),
                                  ("to", args.dest, args.dest_xyz)):
            if given:
                x, y, z, source = (*given, "the command line")
            else:
                x, y, z, source = resolve_system(con, name)
            if x is None:
                raise SystemExit(f"cannot locate {name!r}: {source}")
            print(f"{role:<5}{name:<26}{x:>12,.2f}{y:>12,.2f}{z:>12,.2f}   {source}")
            ends[role] = (x, y, z)

        import time
        t0 = time.perf_counter()
        corridor = Corridor.prime(con, ends["from"], ends["to"], args.range,
                                  args.corridor, (args.origin, args.dest),
                                  args.over)
        primed = time.perf_counter() - t0
        print(f"\n{len(corridor.names):,} neutron star(s) within "
              f"{corridor.radius:,.0f} ly of the line, primed in {primed:.1f}s")
        print(f"straight line {corridor.direct:,.1f} ly at {args.range:,.0f} ly "
              f"boosted -> no route can be shorter than {corridor.floor} jumps\n")

        t0 = time.perf_counter()
        hops = corridor.solve()
        secs = time.perf_counter() - t0
        if hops is None:
            raise SystemExit(f"no route of {corridor.max_limit} jumps or fewer -- "
                             f"raise --over, which widens the corridor with it, or "
                             f"--range")
        flown = sum(h["hop_ly"] for h in hops[1:])
        print(f"\nsolved in {secs:.2f}s: {len(hops) - 1} jumps, {flown:,.1f} ly flown "
              f"against {corridor.direct:,.1f} straight, longest hop "
              f"{max(h['hop_ly'] for h in hops[1:]):,.1f} ly")
        for h in hops:
            print(f"  {h['hop']:>3}  {h['system']:<28}"
                  f"{'   start' if h['hop_ly'] is None else format(h['hop_ly'], '8.1f')}"
                  f"   to go {h['to_go_ly']:>9,.0f}")
    finally:
        con.close()

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return
    route = args.name or f"{args.origin} -> {args.dest}"
    out = write_seed(hops, route, args.range, args.out)
    print(f"\nwrote {out}\n  merge it with:  python etl/route/load.py")


if __name__ == "__main__":
    main()
