# M0 build notes

Decisions, trials, failed attempts and negative results during the M0 build, newest at the bottom.

## Step 1 — foundations (22 November 2026)

- **Plain data, not arrays.** With about 200 entities, the state is a list of plain dataclasses rather than NumPy arrays as in Origins. Simpler to read and to record; the performance report in step 11 will show whether vectorising is needed for the fast mode.
- **Keyed random streams.** Each (stream, entity) pair has its own generator, derived from the run seed with NumPy's `SeedSequence` spawn keys. An intervention on one entity therefore cannot shift any other entity's random draws (specification 6; review 001 finding 4). Test: `tests/test_foundations.py::KeyedRandom`.
- **Digest.** The replay digest is a SHA-256 of the canonical JSON of the record (events and snapshots), so identical runs give identical digests on the same platform. Cross-platform float differences are possible in principle; not tested yet.
- **Movement is a placeholder for step 2.** Terrain is a grid with a rough-ground mask only; height, woods, streams and sight arrive in step 2. Pace and fatigue values are engineering assumptions with ranges in `params.py`.

## Research questions Q001–Q004 answered (22 November 2026)

Answers saved unchanged in `research/questions/`; Claude's notes on use at the end of each question file. Spot-checks against the texts: Polybius 3.114, 5.85 and Livy 30.34.11 agree with the answers. Consequences for the build:

- **Carthaginian side:** seven equipment-and-role types; ethnic names are labels, not statistics; scenario strengths are labelled scenario settings (Q001).
- **Signals:** recall, a prearranged action cue defined in the deployment plan, and cavalry engage; "advance" only as a labelled engineering extension. **Conditional instructions at deployment** added to step 4, following Scipio's briefing of Laelius and Masinissa (Polybius 14.4). Messenger speed, range and loss stay engineering assumptions (Q002).
- **Formations:** three layouts and three relief procedures as switches with no historical default (Q003).
- **Cavalry:** six post-victory options and the listed influences; rout-rally-return to the same battle flagged as experimental (Q004).

The placeholders in steps 4, 6, 7, 9 and 11 can now use these answers.

## Step 1 — after Codex review 002 (22 November 2026)

All eight findings reproduced, agreed and fixed (`reviews/responses/002-step1-foundations-answer.md`). Lasting design consequences:

- **Stable ids everywhere.** Entities carry ids from the scenario file; every reference, random key and record uses them. Later orders, messages and decisions will too.
- **Random keys are validated and unambiguously encoded** (schema 1). Once entities interact, draws that must stay aligned in paired comparisons will be keyed on stable occurrence ids, not on how often an entity has drawn.
- **Checks at load, start of tick, after every phase and end of tick.** A change made and undone within one phase is invisible to these checks, so headcount changes will go through one checked transfer function (step 6).
- **Exact replay is judged by a full-precision state trace** after every tick; viewer snapshots are rounded and separate.
- **Events own their data** (strict-JSON copies at log time).
- Performance after the added checks: one simulated hour of the five-entity test march in about 0.09 s.

## Step 2 — terrain, sight and routes (22 November 2026)

- **Ground:** open, rough, woods, a stream crossable only at fords, and a smooth height map from hills. Format in `imperatores/terrain.py`.
- **Assumption, recorded:** both armies know the ground (pre-battle reconnaissance). Misjudged ground is outside M0. Beliefs about the *enemy* are separate (step 3).
- **Sight** (`sight.py`): range limit, then blocking by ground and wood canopy along the line from eye to target. Higher ground sees further because ridges and woods stop blocking, not through a separate bonus. Inside a wood, sight is short. No haze, dust or weather.
- **Routes** (`pathing.py`): A* over cells minimising travel time for the movement class, then shortened where a straight line is no slower ground. Formed troops therefore go round woods when that is quicker. Slope is ignored in planning but slows movement uphill.
- **A failed first attempt, and its fix.** The first stream drawing marked cells whose centre lay within the stream's half-width, at least half a cell. A diagonal stream thinner than a cell left gaps between diagonal cells, and a straight route slipped through. The sampling checks along routes and steps could also miss a clipped cell corner. Both now use an exact grid traversal (`terrain.cells_on_segment`): the stream marks every cell its line passes through, and routes and movement steps are checked against every cell they touch. A randomised test throws short steps across a thin diagonal stream; none gets through.
- **Movement classes:** formed foot, open-order foot, horse, each with its own pace on rough ground, woods and fords. Only formed troops lose order to ground.
- **Performance:** one route across the test field takes about 80 ms. At about 200 entities that is up to 16 s if every entity replans at once, too slow for the fast mode later and worth watching. Options when it matters: a coarser planning grid, cached routes, or vectorised search.

## Step 3 — belief pictures (22 November 2026)

- **Commanders** (army and wing) are now in the state: people with their staff at a place on the field, sharing one id space with entities. They do not move until steps 4–5.
- **Belief pictures** (`belief.py`): contacts with what was perceived and when (position with its error, kind, numbers, order and facing when close enough, when seen, first known, and whether seen or reported). They change only through sighting (`observe`) and reports (`merge_report`, used from step 4). Decision code will get a `BeliefView`: an immutable copy with no reference to the world (tested by walking the object).
- **Perception** (`systems/perception.py`), every 10 s: line of sight, then errors in position and numbers growing with distance; kind and facing only within recognition range; horse or foot further out; only "troops" beyond. An entity's officer watches his own sector (1.5 km); commanders watch to the limit of sight.
- **Assumptions recorded:** an observer can tell friend from foe for any body he sees; while a body stays in sight, the observer keeps track of which body it is (no mistaking one body for another); an officer knows his own entity's state exactly. All can be relaxed later.
- **Information-integrity tests (specification 7.1 check 3):** a hidden reserve never enters any enemy belief over 30 minutes; moving, and killing men in, an unseen entity changes no enemy belief (stale-truth test); an unseen contact keeps its last known position and grows old.
- **Pair independence.** Perception noise uses counter-based keyed draws (`rng.keyed_normals`): a pure function of seed, stream, observer, target and cycle, with no stored state. Line of sight samples each pair on its own fixed spacing. Tests confirm that adding entities changes no other pair's sighting, and that batched and single sight checks agree.
- **Performance, a first attempt and two improvements.** Per-observer line of sight cost 230 ms per perception cycle at 200 entities and 6 commanders. Batching all pairs into one chunked call gave 188 ms. Sampling sight lines once per terrain cell instead of twice (now a labelled setting) gave **140 ms**, about 150 s of perception per 3-hour battle on this machine. Further options, not yet taken: share each sight line between its two ends (about 2×); let officers look less often than commanders; precompute horizons. To be decided with the step 11 performance report and the fast mode.

## Step 2 revisited after Codex review 003 (22 November 2026)

All eleven findings reproduced; ten fixed, one resolved by documentation and a check (`reviews/responses/003-step2-terrain-sight-routes-answer.md`). Lasting consequences:

- **Exact geometry.** `cells_on_segment` follows one documented convention (closed squares touching the closed segment), is symmetric, and is tested against an independent oracle. Streams are clipped to the field. Fords open whole cells and must join two banks.
- **Exact line of sight** replaces sampling: per piece of the sight line, the quadratic of ground minus line is maximised exactly. Woods block unless an endpoint stands in that stretch of wood. The step 3 sampling setting is gone.
- **Routes are engine-owned**, costed in open-ground metres with one exact definition shared by search and shortening; shortcuts never cost more; shortening is linear.
- **Movement stays on the planned leg**; stalls are detected, replanned and recorded.
- **A cost to decide on.** Exact sight with coarse bounds costs about 360 ms per perception cycle at 200 entities on hill slopes (about 6.5 minutes per 3-hour battle), against 140 ms for the unsound sampled version. The gate's 200 runs would then take roughly a day on one core, a few hours across several. Next options: share each sight line between its two ends (about 2×); let entity officers look less often than commanders (a model choice, for Ben); reduce officers' attention range (also a model choice).
