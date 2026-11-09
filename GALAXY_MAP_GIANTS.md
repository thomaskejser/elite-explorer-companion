# Giants on the galaxy map

Finding giant and supergiant stars by looking at the galaxy map in realistic mode: a key press captures the map, an image-processing algorithm (no machine learning) picks out the stars that look like giants, and the overlay circles them.

- **Status: live test.**
  `SHIFT+S` captures the map, `overlay/src/stars.rs` measures it and the HUD rings each star it calls a giant (`overlay/DESIGN.md`); the rule is tuned on thirteen captures and is now being checked in flight.
- **The detector runs live inside the overlay exe**, in Rust, with no Python, model or network at run time.
  `scripts/galaxy_stars.py` is the bench it is designed on, and uses only steps that port one-to-one: a median background on an 8× subsampled frame, a threshold, connected components, and per-star sums and ray walks.
- Captures land in `log/fss/galaxy/`; `targets.csv` there names the system each capture is centred on and, where it has been found by eye, the target's pixel (`tx`, `ty`).
- The payoff is giants nobody has reported: those are in no feed the model loads, so the map is the only place they show before a commander flies there.

## Target classes

The game has seven giant classes, five of them supergiants.
K goes no higher than giant, and M is the only letter with both a giant and a supergiant.

| class (journal sub-type) | colour on the map | reported bodies |
| --- | --- | --- |
| `B (Blue-White super giant) Star` | blue-white | 14,951 |
| `A (Blue-White super giant) Star` | blue-white | 17,737 |
| `F (White super giant) Star` | white | 8,737 |
| `G (White-Yellow super giant) Star` | white-yellow | 6,425 |
| `M (Red super giant) Star` | red | 3,495 |
| `K (Yellow-Orange giant) Star` | orange | 54,366 |
| `M (Red giant) Star` | red | 232,672 |

- Counts are `body_type_census`: bodies somebody reported, so they lean toward what commanders sought out; the ratios between classes are the usable part, never a galaxy total.
- Every class has the same 1,200 base scan value as an ordinary star (`main.body.cr_value`): the reward is the find, not the credits.
- The overlay's `SUPERGNT` kind (`overlay/src/kinds.rs`) covers the five supergiant classes; giants have no kind yet.

## What the data says about where they are

Per class and mass code, from `main.system_body` joined to `main.body` and `main.system_known`:

| class | mass code | bodies | median solar masses | median \|y\| (ly) | share primary |
| --- | --- | --- | --- | --- | --- |
| red giant | b | 106,153 | 0.27 | 177 | 0.84 |
| red giant | c | 42,104 | 0.27 | 220 | 0.00 |
| red giant | d | 76,109 | 1.01 | 1,151 | 0.71 |
| red giant | e–h | 6,110 | ~1.0 | 1,287–1,506 | 0.00–0.25 |
| K giant | d | 36,784 | 1.71 | 578 | 0.98 |
| K giant | e–h | 1,490 | ~1.8 | 1,316–1,700 | 0.00–0.81 |
| K giant | none (catalogue stars) | 16,092 | 0.63 | 422 | 1.00 |
| supergiants, all five | mostly e and h | 51,345 | | 932–1,263 | 0.86–0.98 |
| every known system | | 205,004,860 | | 238 | |

- **Red giants are two populations.**
  Mass codes b and c hold 148,257 red giants of about a quarter of a solar mass, as close to the plane as ordinary stars.
  They are most likely the M7/M8 IVb red giants that the map draws as regular M stars (see *How the map draws them*), so the detector does not expect to find them.
- **The detectable targets are mass code d and up**: about 82,000 red giants and 38,000 K giants of a solar mass or more, nearly all the primary star of their system.
- **Giants and supergiants sit far from the galactic plane.**
  Their median height is 932–1,700 ly against 238 ly for every known system.
  This is more than their mass code explains: mass-d red giants sit at 1,151 ly, all mass-d systems at 351 ly.
- **Secondary stars probably cannot be seen on the map**, which is believed to draw each system's primary only; no c-mass red giant is a primary.
  The screenshots must confirm this.
- **The 16,092 non-procedural K giants are real catalogue stars** at known positions: calibration points, not discoveries.

## How the map draws them

What players report about realistic mode:

- Giants and supergiants are "big spheres that are distinctly larger than regular stars"; supergiants are "big blue-white, white and red spheres" ([HerzbubeWiki, EDExploration](https://wiki.herzbube.ch/wiki/EDExploration)).
- The M7 IVb and M8 IVb red giants are the exception and look like regular class M stars (same source).
- Supergiants "tend to be visible from relatively far away" but are "not easy to spot"; panning with the grid at 10 or 100 ly per square works moderately well (same source).
- A supergiant shifts less than its neighbours when the view rotates, because it is farther away than it looks (same source).
- Size alone "doesn't help to distinguish regular B class stars from blue-white supergiants" (same source).
- Betelgeuse "stands out, and appears bigger" on the map ([Steam discussion](https://steamcommunity.com/app/359320/discussions/0/595144308454099345)).
- Realistic mode draws each star's colour and size as they are ([gamepressure guide](https://guides.gamepressure.com/elitedangerous/guide.asp?ID=29597)).
- Map mode's star-class filter has no giant or supergiant filter; they show only under their letter.

## The detector

A screenshot has no depth, so a distant giant and a near bright dwarf can look alike.
**Shape, not colour, separates them**: a giant is drawn as a round saturated disc with a soft halo and faint spikes; an ordinary star, however bright or close, is a point with a strong four-arm cross whose edge falls off sharply.

Every test is a ratio, because the zoom changes every pixel size; the one pixel number, the 6 px floor on `disc`, is the screen's resolution, below which a star has no shape to measure.
`scripts/galaxy_stars.py` measures each star along its four arms and four diagonals, taking the median of the four so a neighbour on one ray cannot swing it:

| measure | what | giant |
|---|---|---|
| `disc` | radius at which the diagonals leave saturation | ≥ 6 px |
| `halo_ratio` | how far the diagonals stay above a quarter of the peak beyond the disc, over `disc` | 0.5 to 0.8 |
| `cross` | arm brightness over diagonal brightness, in a ring just outside the disc sized from `disc` | < 1.6 |
| `white` | the smallest channel at the centre: a giant's core is white-saturated | ≥ 240 |
| `elong` | roundness of the inner core, the saturated pixels at least half the deepest pixel's distance from the plateau's edge: a neighbour joined by a neck drops away, and two equal stars touching split into two cores, each measured as its own star | < 1.5 |

- The bench also prints `rel`, the disc over the frame's 90th-percentile disc; it is not part of the rule, because at the widest zoom the red supergiant is no bigger than its neighbours (`rel` 1.08) while its shape still marks it.
- The background is the 20th percentile over 25 cells of an 8× subsampled frame (200 px), with masked UI cells replaced by the frame's median first; a narrower window sits inside a red supergiant's 60 px disc and erases it, and the bottom bar's black pixels left in drag the background to 0 for 200 px above it.
- Near-black panels (the bottom bar, the hover info panel) are masked on the subsampled frame and grown by two cells, so their borders do not join the stars along them into one blob.
- On the thirteen captures every labelled giant is flagged: the K giant twice, the A supergiant, and the red supergiant at four zooms down to an 8 px disc.
  Every labelled ordinary star is not: a K6 Va dwarf with the largest disc in its frame, and a regular K.
  The halo floor is 0.5 because the live capture of the red supergiant at a 17 px disc measured 0.59, and the halo is whole pixels; ordinary bright stars measure 0.29 to 0.35.
  Frames flag 0 to 7 stars; the unlabelled ones inspected by eye are round blue or purple discs near the Eol Prou IW-W e1 supergiants, and each needs a hover capture to say what it is.

**Blue-violet discs are not separated by shape.**
Grouping every bright, round, single-core star in the captures by the blue share of its halo (`blue`):

| halo colour | `blue` | stars | median `halo_ratio` | median `cross` | pass the shape rule |
|---|---|---|---|---|---|
| orange | below 0.25 | 149 | 0.35 | 3.49 | 11, the giants among them |
| blue-white | 0.25 to 0.66 | 75 | 0.38 | 3.53 | 3 |
| blue-violet | 0.66 and above | 31 | 0.56 | 1.42 | 23 |

- The game draws nearly every bright blue-violet star round and soft, so the shape rule passes plain B stars; the commander hovered two ringed ones and both were main-sequence B.
- The labelled giants all have `blue` 0.16 to 0.18, and the A supergiant 0.59, so `BLUE_SHARE` (0.66) splits blue-violet discs off without touching them; the overlay rings those in a separate colour.
- **What does split them is how much of the disc is white** (`inner_white`): the smallest over the largest channel of the mean colour between 0.4 and 0.8 of `disc` from the centre.
  A plain B star is a hard-edged white dot inside a blue disc, with four thin white spikes from its edge; a B supergiant's white fills the disc and fades through a pinkish rim, with fine rays all round, as the commander saw by eye.
  Seven captures of three B supergiants (Eol Prou EL-Y f1163, EL-Y f809, NC-V e2-3279) measure 0.687 to 0.736; of the 179 other blue discs the shape rule passes, 7 unlabelled ones reach 0.68.
  A fourth, EL-Y f357, captured after the line was set, measures 0.699 to 0.739 at three zooms and gets the confident ring in each.
  Every labelled giant of every colour is white-filled: the K giant 0.87 to 0.90, the red supergiant 0.86 to 0.92, the A supergiant 0.89.
  So `MIN_INNER_WHITE` (0.68) applies to every star, whatever its colour: a star that passes the shape rule and is white-filled gets the confident ring, and one that passes with only a white dot gets the dim ring.
  No hovered dim-ringed star has yet confirmed that the dim ring means a plain star.
- **What a supergiant is not**, from a wide capture the commander checked had none in view: of its 21 rings, the 3 confident ones were two 7 px discs, where the band `inner_white` reads is about three pixels wide and lies inside the saturated core, and one 14 px plain B star that matches a supergiant on every measure.
  The two small ones also had halos wider than any labelled giant's (0.86 and 3.57, one inside a nebula, against at most 0.79).
  So a halo over 0.8 of the disc gets no ring, and a disc under `MIN_WHITE_DISC` (8 px) cannot be called white-filled and gets the dim ring at most.
  All 20 labelled giant captures keep the confident ring; the checked frame keeps one false one, and confident rings across all captures fall from 49 to 33.
- **Known failure: a star overlapping another.** In a second checked frame with no supergiant (521 stars), the one confident ring is a plain blue star with a white cross star about 10 px from its centre, inside the band `inner_white` reads, which lifts it to 0.71.
  Reading the band in eight sectors and taking the median does not help, because the neighbour covers most sectors (0.73), and it lowers the weakest labelled giant to 0.682; it is not used.
  With 20 labelled giant captures and two checked frames, each further threshold would be fitted to the last frame; telling these apart needs more labelled stars, or parallax.
- **The F supergiant** Dryio Flyuae RD-S e4-10396 is a round white disc with fine rays, white-filled at every zoom (0.97 to 1.0).
  Two zoom steps out a small star touches its core at the lower left and the core measures `elong` 1.41, so the limit is 1.5: all 12 labelled giant captures in `targets.csv` get the confident ring, and confident rings in the eleven frames with no supergiant go from 11 to 13.
  Reading only the deepest quarter of the core instead loses six of the twelve, because a small core's shape is noise, and dropping the limit doubles the false rings to 23.
- **The G supergiant** Dryoea Flyuae MD-S e4-96 is a round yellow-white disc with fine rays and gets the confident ring at all three zooms (disc 20, 14, 12 px; `inner_white` 0.98 to 0.99, `elong` at most 1.13, halo blue share 0.21 to 0.25).
- **The M red giant** Dryio Flyuae NP-A b33-27 is drawn like an ordinary star, not like the K giant or the supergiants: a white core with a sharp four-point cross and a spray of fine rays, where those are round glows with no cross.
  Close up it measures `cross` 2.83 against the K6 dwarf's 3.94 and a regular K's 3.08, so it gets no ring at any of three zooms.
  A second red giant, Dryoea Flyuae DL-G b29-0, and a red dwarf beside it at the same zoom (both 24 px discs) measure halo 0.58 against 0.38 and cross 3.30 against 3.55.
  The halo is the only difference: the two red giants 0.83 and 0.58, the three plain stars 0.29, 0.38 and 0.53, a single 0.05 step apart, and a cut at 0.55 rings 149 cross stars in the 43 bench frames, 3.5 a frame.
  So red giants are not ringed: the image does not tell them from plain stars, and the 226,579 known red giants outnumber every supergiant class together (about 48,500).
  The confident ring means a round glow with no cross: the K giant and the M, A, B, F and G supergiants.
- **A plain G star at 8 px** (labelled in play, beside a nebula) gets the confident ring: `cross` 1.55 against the limit of 1.6, two cores from a merged neighbour, halo 0.62, `inner_white` 1.0.
  The labelled giants reach `cross` 1.53, so a limit of 1.55 or a 9 px floor would remove it, the floor at the cost of the red supergiant's 8 px zoom; measuring the cross further out (1.5 to 3 discs) reads 2.21 for it and 1.1 to 4.9 for the giants, so it does not separate them.
  It is kept as a labelled negative for the re-tune rather than fitted now.
- The white spikes of a plain B star are one or two pixels wide; measured as whiteness along the arms against the diagonals just outside the disc, they do not separate the two.
- Neither colour nor size held: `blue` is 0.66 to 0.67 for f1163 but 0.73 to 0.75 for f809, inside the dwarfs' 0.69 to 0.78, and the supergiant is the largest blue disc in only three of its four frames.
- Only the band between the map's two toolbars (`x` 0.287 to 0.716 of the frame) is measured; the rest lies under the HUD panes.

Two cues remain for what shape cannot split:

- **Height off the plane**: a large disc above or below the band of the galactic plane is a strong candidate, as the data above shows.
- **Parallax**: two captures with the camera nudged between them; a star that barely moves is far away and therefore intrinsically large.
  It may be the only cue that separates a blue-white supergiant from a main-sequence B star.

The hard pairs:

- **Red supergiant against red giant**: red giants outnumber red supergiants 67 to 1, and both are large red spheres; only width or parallax can split them, and only if supergiants are drawn clearly larger.
- **Blue-white supergiant against B main sequence**: B and A supergiants are 64% of all supergiants; parallax is the separating cue.

## The pipeline

Each piece reuses something the overlay already has:

- **Key** (built): `SHIFT+S`, the `GalaxyCapture` action in `win/hotkeys.rs`, rebindable on the Settings tab like the others.
- **Capture** (built): `galaxy.rs` grabs the game window with `win::screen::grab_game()` only while `GuiFocus` is the galaxy map (6), with the HUD panes hidden from the capture, into `screenshots\galaxy\` with `captures.csv`.
- **Detection** (built): `stars.rs`, one connected component per star above the background, each measured and flagged as in *The detector*, about 160 ms on a 5120×1440 frame.
  It is `scripts/galaxy_stars.py` ported step for step: on the thirteen captures both measure the same 1,716 stars with no difference in any measure or flag.
- **Circles** (built): `Pane::Giants`, a ring at each detected giant until the next capture or until the map closes.
- **Calibration**: known giants and supergiants near the commander, from the model, give the ground truth the thresholds are tuned on.

## The experiment that decides it

1. Pick a spot near known giants and supergiants of the hard pairs: a red supergiant beside red giants, a blue-white supergiant beside B stars, a G supergiant, and a K giant.
2. Take about ten captures in realistic mode with `SHIFT+S`, at grid spacings of 10 and 100 ly, noting the system each is centred on.
   Take some as pairs with the camera nudged between them.
3. Measure offline, in Python, whether the known giants separate from their neighbours on width, on height off the plane and on parallax.
4. If they separate, build the pipeline; if not, record the measurements in `DEAD_ENDS.md`.

## Black holes

Realistic mode draws a black hole as a disc of pure black, every pixel (0, 0, 0), with a hard edge and no glow: the known black hole Eol Prou IW-W e1-3121 is a 13 px disc.
Nothing else on the map is that black except the game's own panels and the gaps in their text, so `stars::scan` keeps a pure-black patch (every channel at most 16) only when it is round (filling at least 0.6 of its box, since a hard-edged disc of 13 px fills only 0.66 once its single tip pixels widen the box, and at most 1.3 times as long as wide plus one pixel, since a 10 px disc is 4 by 3), at least 6 px in area, outside the UI mask, and on lit map all round: in the ring from 1.6 to 3 radii out, at most 2% of pixels are dark and the median is at least 50.
Across all the captures this finds 119 discs, every one an isolated round black disc like the known one, from 3 to 20 px across; the Colonia region holds 15 known black holes within 110 ly.
The disc shrinks with zoom: IW-W e1-3121 is 180 px in area close up, 39 one zoom step out and 10 two steps out, and from three steps out it is below a pixel and not drawn at all, so a black hole is found only within about two zoom steps of close.
Below 6 px the map holds hundreds of 2 by 2 black specks, which are not kept until a hover shows what they are.
The HUD rings each one in `BLACK_HOLE_RING` and the popup counts them.

## Collecting labels in play

The rule is left as it stands until a few dozen more stars are labelled, then re-tuned once against all of them.

- When a ring looks wrong, or a giant has none: press `P` with the mouse on empty space, then hover that star and press `P` again with the game's info panel open.
  The two captures are taken a few seconds apart from the same camera, so they pair by timestamp, and the panel names the star's class.
- When a whole view holds no supergiant: say so, and every ring in that capture is a labelled negative.
- Each label goes into `log/fss/galaxy/targets.csv` as a row naming the capture, the star and its class, with its pixel where it has been found.
- The re-tune reports every rule against every label, so a threshold is never chosen on the frame that prompted it.

## Open questions

- Does disc size scale with the star's radius, or is it capped?
- How much does bloom widen near bright stars, and does it mimic a giant?
- Does the map draw secondary stars at all?
- Does the M7/M8 IVb exception cover all the b- and c-mass red giants?
- How far off can a giant be and still be told apart, at each grid spacing?
