"""Neutron-boosted routing. Minimum JUMPS, not minimum distance.

A jet cone boost multiplies your range (see ship.NEUTRON_BOOST), and the boost is taken
at the arrival star, so a route that lands on neutron after neutron flies at six times
the range of one that does not. That makes this a shortest-path problem on a graph whose
nodes are neutron systems:

    START  -> neutron        if within START_LEGS unboosted jumps (no cone yet)
    neutron -> neutron       if within the BOOSTED range
    neutron -> DESTINATION   if within the BOOSTED range
    START  -> DESTINATION    if within START_LEGS unboosted jumps (no cone needed)

*** THE FIRST LEG IS ALLOWED TO BE SEVERAL PLAIN JUMPS, AND HAS TO BE. *** You start
wherever you happen to be, which is usually not next to a cone: measured from one real
position in deep space, the nearest neutron was 115.9 ly away against a 75.3 ly range,
so a router that demanded a cone within ONE jump would answer "no route" almost
everywhere. It costs nothing to allow: every hop this returns is pasted into the galaxy
map, and Elite's own plotter finds the ordinary systems in between. That is also why no
check is made that those systems exist -- ordinary systems outnumber neutrons roughly
58 to 1, and if the galaxy map cannot plot it, it says so long before you undock.

*** BREADTH-FIRST, AND THAT IS AN EXACT ANSWER, NOT AN APPROXIMATION. *** Every edge
costs exactly one jump, so BFS returns a provably minimum-hop route -- there is nothing
for A* to improve on and no heuristic to get wrong. It is levelled and vectorised: one
`query_ball_point` call per LEVEL over the whole frontier at once, not one per node.
A 5,000 ly route is about twelve levels.

*** WHAT THIS DOES NOT MODEL: FUEL. *** A supercharged jump burns the drive's maximum
fuel, and *** YOU CANNOT SCOOP AT A NEUTRON STAR ***. A long chain of boosted jumps will
run the tank dry, and this router will happily hand you one. It answers "what is the
shortest chain of cones", which is not the same question as "can I get there". Watch the
fuel gauge and detour to a scoopable star when it gets low -- the route survives it,
because arriving anywhere on the chain picks it up again.

Not modelled either: whether the intermediate systems are DISCOVERED. Irrelevant -- a
cone boosts you whether or not anyone has logged it.
"""
import itertools

import numpy as np
from scipy.spatial import cKDTree

# Stop rather than grind. A frontier this wide means the corridor was drawn far too
# generously, and 2 million expanded nodes in a Tk callback is a hung overlay.
MAX_VISITED = 2_000_000

# *** THE FURTHEST THIS WILL PLOT, IN LIGHT YEARS. *** Not a performance guard so much
# as a statement about what the answer is worth. The corridor query and the search both
# scale with the straight-line distance, and past roughly this far the honest advice is
# a fleet carrier or the neutron highway rather than a chain of cones held in a HUD --
# a 48,578 ly plot to Sol selected 2.95M of the 3.4M neutrons and took 4.5 seconds to
# fetch before the search even started. The caller refuses beyond this and says so.
MAX_ROUTE_LY = 10_000.0

# How many ordinary jumps the FIRST leg may span before a cone is reached. Three is
# enough to cover the gap above with room to spare, and small enough that the answer is
# still a neutron route rather than a suggestion to fly manually for a while.
START_LEGS = 3


def plan(xyz, start, dest, plain_range, boosted_range, start_legs=START_LEGS):
    """-> list of indices into `xyz`, the neutrons to jump through, or None.

    An EMPTY list is a real answer and means "no cone needed, the destination is within
    plain jumping distance". `None` means no route exists inside the node set you passed --
    which is a statement about the corridor you queried, not about the galaxy.
    """
    start = np.asarray(start, dtype=float)
    dest = np.asarray(dest, dtype=float)
    reach = plain_range * start_legs
    if np.linalg.norm(dest - start) <= reach:
        return []
    if len(xyz) == 0:
        return None

    tree = cKDTree(xyz)
    # -1 = unvisited. Anything else is the index of the node we arrived FROM, with -2
    # standing for "arrived from START", which is how the path is reconstructed.
    parent = np.full(len(xyz), -1, dtype=np.int64)

    frontier = np.fromiter(tree.query_ball_point(start, reach), dtype=np.int64)
    if not len(frontier):
        return None
    parent[frontier] = -2
    visited = len(frontier)

    while len(frontier):
        # Done? Any node in this level that can see the destination ends the search,
        # and because levels are explored in order this is a minimum-hop finish.
        reach = np.linalg.norm(xyz[frontier] - dest, axis=1) <= boosted_range
        if reach.any():
            # The one closest to the destination, purely to break the tie sensibly --
            # every candidate here ends the route in the same number of jumps.
            last = frontier[reach][np.argmin(
                np.linalg.norm(xyz[frontier[reach]] - dest, axis=1))]
            path = []
            while last != -2:
                path.append(int(last))
                last = parent[last]
            return path[::-1]
        if visited > MAX_VISITED:
            return None

        # One vectorised radius query for the WHOLE level. `query_ball_point` on an
        # array returns one list per point; chained into a flat array of targets, with
        # `repeat` giving the matching source for each so parents survive the flatten.
        lists = tree.query_ball_point(xyz[frontier], boosted_range)
        counts = np.fromiter((len(l) for l in lists), dtype=np.int64, count=len(lists))
        if not counts.sum():
            return None
        flat = np.fromiter(itertools.chain.from_iterable(lists), dtype=np.int64,
                           count=int(counts.sum()))
        src = np.repeat(frontier, counts)
        fresh = parent[flat] == -1
        if not fresh.any():
            return None
        flat, src = flat[fresh], src[fresh]
        # A node reached twice in one level: keep the FIRST source and drop the rest,
        # or `parent` would be written twice and the second write would win arbitrarily.
        flat, first = np.unique(flat, return_index=True)
        parent[flat] = src[first]
        frontier = flat
        visited += len(flat)
    return None
