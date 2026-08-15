# Rare explorer discoverables: taxonomy and modelling value

## 1. Notable Stellar Phenomena (highest-priority target)

NSP are persistent FSS signal sources found in deep space, at stellar/planetary
Lagrange points, planetary rings and asteroid belts. They frequently contain a
Lagrange cloud and scannable entities; scan results feed Codex discoveries.
They are ideal for a first model because their system/body environment can be
learned from ordinary scan facts.

### NSP content families

| Family | Known named subtypes |
| --- | --- |
| Anomalies | E-, K-, L-, P-, Q- and T-type (numbered variants may exist) |
| Mineral formations | Calcite Plate, Ice Crystal, Lattice Mineral Sphere, Metallic Crystal, Silicate Crystal, Solid Mineral Sphere |
| Molluscs | Bell, Bulb, Bullet, Capsule, Globe, Gourd, Parasol, Reel, Squid, Torus, Umbrella |
| Plants | Aster Tree, Gyre Tree, Peduncle Tree, Stolon Tree, Void Heart |
| Seed pods | Aster, Chalice, Collared, Gyre, Octahedral, Peduncle, Quadripartite, Rhizome, Stolon |
| Associated structures | Lagrange Clouds; physical ring/belt or Lagrange-point placement |

Use two labels: `has_nsp` at system level and `nsp_family/variant` at site
level. A system can contain multiple sites; an NSP may contain several entity
types.  Missing a small entity after locating a site is an observation-quality
issue, not evidence of absence.

## 2. Surface geology and biology

These are a second high-value modelling target because DSS/Journal signal counts
and body physical properties provide useful labels/features.

- **Geological signals:** fumaroles, geysers, gas vents, lava spouts and mud
  pots; legacy Horizons surface feature categories should be kept distinct from
  Odyssey signal semantics.
- **Odyssey exobiology:** microbial and multicellular genera, including
  Bacterium, Stratum, Tussock, Frutexa, Cactoida, Osseus, Recepta, Fonticulua,
  Tubus, Aleoida, Fungoida, Concha, Clypeus, Electricae and more. Model genus,
  species/variant and body occurrence separately. The definitive current
  vocabulary should be imported from observed `ScanOrganic`/Codex events rather
  than hand-maintained alone.
- **Pre-Odyssey biological POIs:** Bark Mounds, Brain Trees, Amphora Plants,
  Anemones, Crystalline Shards/Clusters and Sinuous Tubers. These have different
  generation and discovery history; retain a `content_era` field.

## 3. Stellar and planetary rarities

These are often fully represented by `Scan` and make strong feature/secondary
labels: neutron stars, black holes, white dwarfs, Wolf-Rayet stars, carbon
stars, Herbig Ae/Be stars, proto-stars, unusually massive/ringed worlds,
Earth-like worlds, water worlds, ammonia worlds, terraformable high-metal
content worlds, helium-rich gas giants, and ring types/composition. “Rare” is
not synonymous with a mysterious POI: estimate prevalence from coverage-aware
data.

## 4. Archaeological, alien and narrative POIs

Curated labels matter more than procedural prediction here: Guardian ruins and
structures, Thargoid/Guardian sites, Thargoid Barnacles, abandoned settlements,
generation ships, megaships, listening posts, crashed ships, beacons and
historical sites.  They can be spatially clustered or hand-authored, so train a
separate proximity/region model rather than blend them with Stellar Forge
phenomena.

## 5. Event-specific anomalies

The 3308 “anomalies” were moving, FSS-detectable bright signals associated with
the Thargoid storyline. They are not a stable procedural NSP class. Keep such
time-dependent records in an `events` table with observation time and trajectory
metadata, excluded from static unexplored-system predictions.

## Practical target priority

1. NSP presence and family; 2. exobiology genus/species; 3. rare normal body
classes; 4. legacy biology/geology; 5. curated alien/archaeological POIs; 6.
time-dependent narrative events.
