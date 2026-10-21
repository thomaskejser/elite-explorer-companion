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

Sourced from the community compilation thread *FDev ED-relevant quotes/videos*
(Jorki Rasalas, Frontier Forums, started 2020-08-27, last edited 2025-07-16 — see
Sources). Attribution and dates are as recorded there; where the thread itself flags a
quote as uncorroborated, that is carried through. The thread's own caveat applies:
**these are historical, and the game has changed since many were said.**

| who | when / where | statement | status |
| --- | --- | --- | --- |
| David Braben | 2014-07-08 ~19:00, bar after the BAFTA Games Showcase ("My other car's a Cobra Mk3"), reported by Drew Wagar | Asked "Is Raxxla in the game?" — **"Yes. And we know where it is."** Elsewhere rendered by Wagar as **"It exists, we know where it is and we know why people haven't been able to find it."** | second-hand, but consistently reported by a named licensed author |
| David Braben | Beyond Ch.2 launch livestream (13:43) | "Does Raxxla exist? There's an interesting one. What a silly question, of course.... **You don't know what it is though!**" | on camera |
| Michael Brookes | DJTruthsayer lore interview, 2016-05-14 (01:40:45) | "**It's in the Milky Way**, but I can't tell you where at this stage, it's a journey that everyone has to travel for themselves." On "there will be no clues": "that is true, but **I think you have to make some of it a tiny little bit obvious just so that people know what they are doing**, there is nothing to be revealed at this stage" | on camera |
| Michael Brookes | forum, on *Elite: Legacy* not being a *Dark Wheel* sequel | "We did look at a story involving Raxxla, but felt that was a story that **should be played out in game** rather than as a novel." | forum post |
| Michael Brookes | forum, re Shinrarta Dezhra as the founder's world | "**Raxxla is something different**" | forum post |
| Michael Brookes | **alleged**, closed Q&A at LaveCon 2017 (via Cmdr Ascorbius; Brookes later declined to comment) | "**the system where Raxxla is located has been visited and honked but Raxxla was not detected**" | **uncorroborated rumour** — see F6 in `RAXXLA.md` |
| Arthur Tomlie (grand narrative / Galnet lead) | Grinning_Crow interview, ~2021 (26:00) | Where's Raxxla? "**It's there. Clearly it's there.** I've said this in another stream, I'll say it today, it's been going a long time. **The payoff would have to be great**, and that's all I will say on it." At 1:49:44 he is unaware of the Brookes "honked" rumour and does not know the answer. | on camera |
| Adam Bourke-Waite (senior designer) | Beyond Ch.4 exploration reveal, 2018-10-18 (1:29:58) | Of the then-unshown **Raxxla codex entry**: "there's elements of that that are probably my favourite parts of this" | on camera — confirms a codex entry exists |
| Adam Bourke-Waite / Will Flanagan | forum, on the missing Elite-rank / Founder missions rumoured to be Raxxla- or Dark-Wheel-related | "they should still be available" → later, definitively: **they were removed** | forum posts |
| Michael Brookes | forum, on Mitterand's Hollow | "it's probably orbiting a comet. As for Mitterand's Hollow that was a **manually added body with some incorrect overrides** — we can't blame Stellar Forge for that one!" | forum post — see C7 |
| David Braben | ED development-plan video (6:36) | "**will reserve areas of the galaxy for future expansion** with new things to explore" | on camera |
| David Braben | "ED has a story that embraces all the players" (8:20) | "you'll get invited to join things, **if you get invited to join a secret organisation** that's a thing that can happen to lots of players" | on camera — the Dark Wheel as an *event*, not a place |
| David Braben | EGX 2014 presentation | Ocellus stations are designed so **engines can be fitted and the station driven to another system** (e.g. a mining gold-rush) | on camera — a station-class target need not stay put |
| Drew Wagar | DJTruthsayer interview (17:00) | DB first mentioned Raxxla being in-game at a **pre-launch/launch party**, i.e. very early | second-hand |
| Will Flanagan | EXO stream, 2019-03-21 (31:40) | To commanders hunting Raxxla: "you are looking in the right place, **you're looking in an asteroid**…" | almost certainly a joke; recorded for completeness |

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

### C6 — "You don't know what it is though" + "we know why people haven't been able to find it"  [reframes the target]
Two independent Braben statements agree that the *obstacle* is not distance.
- **My interpretation:** the search may be mis-specified at the object level. "You don't
  know what it is" permits Raxxla to be something other than a star system — a body, a
  station, a megaship, a phenomenon, or an event — and "we know why people haven't
  found it" implies a **known, deliberate reason it evades ordinary discovery**: absent
  from the FSD honk (C8), invisible without a specific action, mobile, or gated behind
  an in-game trigger (C10). With Ocellus stations buildable with engines and driven
  between systems, a **moving** target is not excluded.
- **Cost to us:** if the target is a body or a station, our system-level anomaly work
  (F2, F4) could never have seen it under any premise.

### C7 — Mitterand's Hollow: hand-placed objects carry override artefacts  [computable]
Brookes confirmed Mitterand's Hollow is "a manually added body with some incorrect
overrides — we can't blame Stellar Forge for that one".
- **My interpretation:** the first developer-confirmed **signature of hand-placement**,
  and it sits at *body* level, not system level. Hand-authored content is written over
  Stellar Forge output and can carry physically inconsistent parameters — which is a
  query we can actually run against `system_body`: bodies whose orbital or physical
  parameters are inconsistent with their parent, their siblings, or with each other.
- **Caveat before anyone gets excited:** overrides are used for *all* hand-authored
  content — every mission target, tourist beacon and named landmark — so this yields a
  population, not a candidate. It is a filter for the hand-placed set, nothing more.

### C8 — "Visited and honked, but not detected"  [premise-critical, uncorroborated]
The most consequential claim in the compilation, and the apparent origin of this
project's own revised premise. Attributed to Michael Brookes at a closed LaveCon 2017
Q&A; Brookes later **declined to comment**, Arthur Tomlie had not heard it, and no
second attendee has corroborated it.
- **My interpretation:** if true it says the opposite of what we assumed. A *honked*
  system is one whose discovery scan fired — which since 2015 is exactly what EDDN and
  EDMC upload. So under this claim Raxxla's system is plausibly **already inside our
  195M**, and the point of the quote is that the honk **does not reveal Raxxla**: the
  object is below or outside what a discovery scan returns.
- **Consequence:** this does not revive F2/F4, which examined *system* naming and
  geometry. It moves the search to **what a honk misses** — bodies the discovery scan
  does not return, and objects that are not bodies at all.
- **Confidence:** low. One uncorroborated second-hand quote plus a declined comment.
  A hypothesis to test, never a fact. See F6 in `RAXXLA.md`.

### C9 — Prester John / Luko Prestigio Giovanni  [textual, unverified]
The compilation notes that Drew Wagar's Salomé-arc character Alessia Verde names her
father as "Luko Prestigio Giovanni", read by the community as **Prester John** — the
figure in the in-game Raxxla codex entry.
- **My interpretation:** a name-level tie between the codex text and the Salomé arc,
  the same arc that produced the Formidine Rift / Zurara trail (C1). Literary, not
  spatial; it cannot be turned into coordinates.

### C10 — Raxxla may be gated behind an event, not a location  [structural]
Braben describes invitations to "join a secret organisation" firing at points in a
commander's progression; Brookes said the Raxxla story "should be played out in game";
Bourke-Waite confirms an unreleased **codex entry**; and the Elite-rank / Founder
missions long rumoured to be Dark-Wheel-related were **removed**.
- **My interpretation:** the strongest structural reading in the compilation. Several of
  these describe *access*, not *place*. If Raxxla is reached by a trigger — a rank, a
  mission, a codex completion — then no amount of coordinate work reaches it, and the
  data's role shrinks to characterising a neighbourhood once a trigger names one.
- **Honest consequence:** this is the most plausible reason our search space is the
  wrong space, and it is not falsifiable from our side.

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
   precise bearing+distance, or a described property) can be translated into candidate
   systems.

## Sources
- [FDev ED-relevant quotes/videos — Frontier Forums](https://forums.frontier.co.uk/threads/fdev-ed-relevant-quotes-videos.553526/)
  — Jorki Rasalas' compilation of developer quotes and videos; source of the Developer
  statements table and C6–C10. The live forum refuses automated fetches; read
  2026-08-26 via the Wayback snapshot of 2025-08-15, which post-dates the thread's last
  edit of 2025-07-16. Several linked Twitch clips are already dead.
- [Raxxla — Elite Dangerous Wiki (Fandom)](https://elite-dangerous.fandom.com/wiki/Raxxla)
- [Drew Wagar's Lore: Raxxla — Canonn](https://canonn.science/lore/drewwagar-raxxla/)
- [The Dark Wheel — Elite Dangerous Wiki](https://elite-dangerous.fandom.com/wiki/The_Dark_Wheel)
- [Kahina Tijani Loren (Salomé) — Elite Dangerous Wiki](https://elite-dangerous.fandom.com/wiki/Kahina_Tijani_Loren)
- [The Children of Raxxla](https://thechildrenofraxxlachronicles.wordpress.com/who-we-are/)
- [The Formidine Rift — Children of Raxxla](https://thechildrenofraxxlachronicles.wordpress.com/2015/05/11/formidine-rift/)
- [The Formidine Rift route — EDSM](https://www.edsm.net/en/galactic-routes/show/id/14/name/The+Formidine+Rift)
- [The Quest To Find Raxxla — Frontier Forums](https://forums.frontier.co.uk/threads/the-quest-to-find-raxxla.168253/)
