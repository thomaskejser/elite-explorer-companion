# Giants on the galaxy map

Finding giant and supergiant stars by looking at the galaxy map in realistic mode: a key press captures the map, an image-processing algorithm (no machine learning) picks out the stars that look like giants, and the overlay circles them.

- **Status: feasibility study.**
  Nothing is built; the test screenshots that decide whether it can work are not yet taken.
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
Four cues separate them, cheapest first:

1. **Colour**: only blue-white, white, white-yellow, orange and red discs are candidates.
2. **Disc width against brightness**: a giant is drawn as a sphere sized by its radius, so it is wide for how bright it is; a near dwarf is small and sharp.
3. **Height off the plane**: a large disc above or below the band of the galactic plane is a strong candidate, as the data above shows.
4. **Parallax**: two captures with the camera nudged between them; a star that barely moves is far away and therefore intrinsically large.
   It is the only cue that can separate a blue-white supergiant from a main-sequence B star.

The hard pairs:

- **Red supergiant against red giant**: red giants outnumber red supergiants 67 to 1, and both are large red spheres; only width or parallax can split them, and only if supergiants are drawn clearly larger.
- **Blue-white supergiant against B main sequence**: B and A supergiants are 64% of all supergiants; parallax is the separating cue.

## The pipeline

Each piece reuses something the overlay already has:

- **Key**: a new action in `win/hotkeys.rs`'s bindings, rebindable on the Settings tab like the others.
- **Capture**: `win::screen::grab_game()`, the game-window grab the FSS predictor uses, taken only while `GuiFocus` is the galaxy map (6).
- **Detection**: star blobs on the dark background (local maxima above the local background), each measured for peak brightness, width and colour, then scored on the cues above.
  It is classical image processing in Rust, well under a second on a 5120×1440 frame.
- **Circles**: a pane like `Pane::Marks`, drawn over the map at the detected positions until the camera moves.
- **Calibration**: known giants and supergiants near the commander, from the model, give the ground truth the thresholds are tuned on.

## The experiment that decides it

1. Pick a spot near known giants and supergiants of the hard pairs: a red supergiant beside red giants, a blue-white supergiant beside B stars, a G supergiant, and a K giant.
2. Take about ten screenshots in realistic mode with the game's screenshot key (F10), at grid spacings of 10 and 100 ly, noting the system each is centred on.
   Take some as pairs with the camera nudged between them.
3. Measure offline, in Python, whether the known giants separate from their neighbours on width, on height off the plane and on parallax.
4. If they separate, build the pipeline; if not, record the measurements in `DEAD_ENDS.md`.

## Open questions

- Does disc size scale with the star's radius, or is it capped?
- How much does bloom widen near bright stars, and does it mimic a giant?
- Does the map draw secondary stars at all?
- Does the M7/M8 IVb exception cover all the b- and c-mass red giants?
- How far off can a giant be and still be told apart, at each grid spacing?
