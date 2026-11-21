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
