# Review request 004 — M0 build step 3: belief pictures (for Codex)

**Scope:** changes since review 003 (including the fixes made in answer to it, `reviews/responses/003-step2-terrain-sight-routes-answer.md`): `imperatores/belief.py`, `systems/perception.py`, `sight.py` (batched `visible_pairs`), `rng.py` (`keyed_uniforms`, `keyed_normals`), `terrain.py` (vectorised queries), `state.py` (commanders), `scenario.py`, `record.py`, `engine.py`, `params.py`; `scenarios/test_beliefs.json`; `tests/test_beliefs.py`. Notes in `docs/M0_BUILD_NOTES.md` (step 3).

**Questions:**

1. **Information integrity, the central question.** Is there any path by which true state reaches a belief other than through a sighting within line of sight, or a report? Try to construct one (for example through `own`, through contact fields copied from the entity, through ids, or through the order of contacts). Is `BeliefView` really immutable and free of references to the world?
2. **Pair independence.** Can adding, removing or moving one entity change another pair's sighting, its errors, or its visibility? Check `visible_pairs` chunking and sorting, and the keyed draws.
3. **Exact sight with coarse bounds.** `sight.py` now uses exact line of sight with two coarse bounds (certainly visible, certainly blocked). Can either bound ever give a different answer from the exact check?
4. **Keyed draws.** Is the SplitMix64 construction in `rng.keyed_uniforms` sound for this use (distinct keys giving independent-looking streams, no collisions from the key combination, correct conversion to [0, 1), Box–Muller edge cases)?
5. **Line of sight after batching.** Does `visible_pairs` give the same answer as a direct per-pair check in every case (wood edges, zero distance, observer or target exactly on a cell boundary, chunk boundaries)?
6. **Replay.** Is everything that can affect later behaviour (beliefs, commanders) covered by the trace and digest?
7. **Assumptions.** Are the three recorded assumptions in `belief.py` (friend or foe always known; bodies tracked while seen; officers know their own entity) implemented as stated, and is anything else assumed without being recorded?
8. **Tests.** Do the step 3 tests test what they claim? What is untested?
9. **Performance.** Perception costs about 360 ms per cycle at 200 entities on hill slopes, after exact line of sight replaced sampling (review 003). Anything wasteful, or any approach likely to give a large gain without breaking pair independence?

Answer in `reviews/responses/004-step3-beliefs-codex.md`, following `AGENTS.md`.
