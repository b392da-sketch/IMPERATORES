# M0 build notes

Decisions, trials, failed attempts and negative results during the M0 build, newest at the bottom.

## Step 1 — foundations (22 November 2026)

- **Plain data, not arrays.** With about 200 entities, the state is a list of plain dataclasses rather than NumPy arrays as in Origins. Simpler to read and to record; the performance report in step 11 will show whether vectorising is needed for the fast mode.
- **Keyed random streams.** Each (stream, entity) pair has its own generator, derived from the run seed with NumPy's `SeedSequence` spawn keys. An intervention on one entity therefore cannot shift any other entity's random draws (specification 6; review 001 finding 4). Test: `tests/test_foundations.py::KeyedRandom`.
- **Digest.** The replay digest is a SHA-256 of the canonical JSON of the record (events and snapshots), so identical runs give identical digests on the same platform. Cross-platform float differences are possible in principle; not tested yet.
- **Movement is a placeholder for step 2.** Terrain is a grid with a rough-ground mask only; height, woods, streams and sight arrive in step 2. Pace and fatigue values are engineering assumptions with ranges in `params.py`.
