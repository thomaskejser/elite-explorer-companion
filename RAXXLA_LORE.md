# Raxxla lore reference

Compiled lore, clues, and developer statements for the Raxxla hunt, with an
**interpretation** of each hint and whether our data/tools can act on it. For
easy retrieval; kept separate from the investigation log (`RAXXLA.md`).

Compiled 2026-07-13 from public community sources (see bottom). Canon status noted
per item — *The Dark Wheel* (1984 novella) is **not** ED canon; *Elite: Reclamation*
(Drew Wagar, licensed) carries the in-fiction clues.

## What Raxxla is said to be
- A legendary, definite **place holding a mysterious secret**; sought for centuries.
- *Dark Wheel* novella: a "ghost world / planet" holding an **alien construct that is
  a gateway to other Universes**. Described near the "wreckplace at Tionisla" as, when
  approached from the Sun, "a shimmering silver disc, a double spiral of tiny bright
  points, slowly turning like a galaxy in miniature with an intense blur of light at
  its centre."
- The **Dark Wheel**: secretive fraternity dedicated to finding Raxxla.
- Earliest recorded mention: 2296, journal of Art Tornqvist, **Tau Ceti**.

## Developer statements
- **David Braben:** "It's out there and we (FD) know where it is."
- **Michael Brookes:** it is in the **Milky Way**; "There will be no clues"; "It's a
  journey that everyone has to travel for themselves."
- **Drew Wagar:** told by FD staff that Raxxla **is present in the game**.

## The clues (with interpretation)

### C1 — The Reorte→Riedquat line  [strongest computable clue; likely SPENT]
"Take a line from Reorte to Riedquat and carry on to the edge of the arm." (First
clue, seeded in *Reclamation*.) Points toward the **Formidine Rift** (between the
Perseus and New Outer arms).
- **Verified with our tool:** Reorte (75.8, 48.8, 75.2), Riedquat (68.8, 48.8, 69.8).
  Direction Reorte→Riedquat = unit **(−0.787, 0, −0.616)** — heads to the −x/−z rim;
  extended 10–40 kly beyond Riedquat it reaches galactocentric radius ~33–59 kly,
  i.e. the outer-rim Formidine Rift zone. Matches the lore.
- **My interpretation:** this thread is almost certainly **spent** — following it
  historically resolved to the **Formidine Rift** and the **Zurara** ghost ship
  (Syreadiae JX-F c0), which is *not* Raxxla. Value now: (a) it validates the
  "draw a line through significant original-Elite systems" *method*; (b) the RR-line
  corridor at the rim is enumerable in our predicted space if we want to sweep it.

### C2 — Merope 5C / Unknown Probes  [concrete, but a known anchor]
Unknown Artefacts and Unknown Probes point to **Merope 5C**. Merope is one of only
two "fixed" (hand-placed, real-coordinate) systems.
- **Data:** Merope is present at (−78.6, −149.6, −340.5), Pleiades.
- **My interpretation:** a confirmed Thargoid/Pleiades focal point, tying the
  Salomé arc (Formidine Rift ↔ Hawking's Gap ↔ Conflux ↔ "recent events in the
  Pleiades") together. It's a known location to *inspect*, not an undiscovered target.
  More likely a signpost in the trail than Raxxla itself.

### C3 — "Silver disc / double spiral, turning like a galaxy in miniature"  [thematic]
The novella's visual of the gateway.
- **My interpretation (strongest thematic hint):** "a spiral that turns like a galaxy
  with an intense blur of light at its centre" + "gateway to other Universes" reads
  as an **accretion disc around a (rotating) black hole** — the classic sci-fi
  wormhole/gateway. This *thematically* points to Raxxla being **at or beside a black
  hole**, which connects to our black-hole work. Caveat: it's a hand-placed unique
  site, not a procedurally-predictable one, and the novella is non-canon — so treat as
  flavour/theme, not coordinates.

### C4 — Gateway / Oresrian / stargate  [speculative]
Alien construct = portal; some link it to Guardian/Thargoid ("Oresrian") tech.
- **My interpretation:** reinforces C3 (a portal, possibly at an exotic object).
  Not independently locatable from data.

### C5 — Community theories  [low confidence, unconfirmed]
Witch Head Nebula, Barnard's Loop, Horsehead Nebula, Cassiopeia (Alpha Cas / Schedar).
- **My interpretation:** guesses without decisive evidence; useful only as regions to
  rule in/out if a stronger clue narrows things.

## Handy reference: real coordinates of key lore systems
| system | x, y, z | note |
| --- | --- | --- |
| Sol | 0, 0, 0 | origin |
| Tau Ceti | −0.4, −11.4, −3.5 | earliest Raxxla mention (2296) |
| Reorte | 75.8, 48.8, 75.2 | RR-line endpoint 1 (original Elite) |
| Riedquat | 68.8, 48.8, 69.8 | RR-line endpoint 2 (original Elite) |
| Tionisla | 82.3, 48.8, 68.2 | novella "wreckplace"; near Reorte/Riedquat |
| Merope | −78.6, −149.6, −340.5 | fixed system; Unknown Probes → Merope 5C |
| Sagittarius A* | 25, −21, 25900 | galactic centre |

## Overall assessment — what actually helps us
1. **Best computable artifact:** C1 (RR line) — but it resolved to the Formidine
   Rift/Zurara, not Raxxla, so it is likely spent. Its corridor is still sweepable in
   our predicted space if desired.
2. **Best thematic hint:** C3 — Raxxla plausibly sits **at/near a (rotating) black
   hole** (gateway imagery). This is direction, not coordinates: it says *what kind*
   of place, not *where*. It cannot be turned into a statistical prediction (n=0,
   hand-placed) but could prioritise inspecting notable/black-hole systems.
3. **Known anchors to inspect, not predict:** Merope (C2), Tau Ceti, the
   Reorte/Riedquat/Tionisla cluster.
4. **Honest bottom line:** no public clue has ever *located* Raxxla. Everything here
   is direction or theme. Under our "visited pre-automation → predicted system"
   premise, the only way the data helps is if a **new, specific** clue (a name, a
   precise bearing+distance, or a described property) lets the pgnames tool translate
   it into candidate systems.

## Sources
- [Raxxla — Elite Dangerous Wiki (Fandom)](https://elite-dangerous.fandom.com/wiki/Raxxla)
- [Drew Wagar's Lore: Raxxla — Canonn](https://canonn.science/lore/drewwagar-raxxla/)
- [The Dark Wheel — Elite Dangerous Wiki](https://elite-dangerous.fandom.com/wiki/The_Dark_Wheel)
- [Kahina Tijani Loren (Salomé) — Elite Dangerous Wiki](https://elite-dangerous.fandom.com/wiki/Kahina_Tijani_Loren)
- [The Children of Raxxla](https://thechildrenofraxxlachronicles.wordpress.com/who-we-are/)
- [The Formidine Rift — Children of Raxxla](https://thechildrenofraxxlachronicles.wordpress.com/2015/05/11/formidine-rift/)
- [The Formidine Rift route — EDSM](https://www.edsm.net/en/galactic-routes/show/id/14/name/The+Formidine+Rift)
- [The Quest To Find Raxxla — Frontier Forums](https://forums.frontier.co.uk/threads/the-quest-to-find-raxxla.168253/)
