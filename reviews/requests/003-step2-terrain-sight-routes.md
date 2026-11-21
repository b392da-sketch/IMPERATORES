# Review request 003 — M0 build step 2: terrain, sight and routes (for Codex)

**Scope:** changes since review 002: `imperatores/terrain.py`, `sight.py`, `pathing.py`, `systems/movement.py`, `state.py`, `scenario.py`, `record.py`, `params.py`; `scenarios/test_field.json`; `tests/test_terrain.py`. Notes in `docs/M0_BUILD_NOTES.md` (step 2).

**Questions:**

1. **Stream barrier.** Can any entity cross the stream away from a ford: by route, by a single movement step, at the field edge, at a ford's edge, or where stream segments join? Try to construct a counterexample. Check `cells_on_segment` for exactness (corners, axis-aligned lines, zero-length segments, points on the field boundary).
2. **Routes.** Is the A* correct and its heuristic admissible for the cost used? Does the shortening step ever produce a route that is slower, crosses ground the original avoided, or cuts through impassable cells? Can a unit get stuck following a valid route (for example formed troops wheeling near the stream)?
3. **Line of sight.** Are there cases where sight is clearly wrong: over hills, into or out of woods, at wood edges, symmetry between observer and target? Is the in-wood rule coherent?
4. **Determinism and replay** with the new systems, including routes stored in tasks.
5. **Values.** Are the new parameters labelled with ranges and basis, and is anything tunable still hard-coded (for example the 5 m look-ahead for slope)?
6. **Tests.** Do the step 2 tests test what they claim? What important behaviour is untested?
7. **Performance.** Route planning costs about 80 ms per route on the test field. Is anything pathological in the planner or the shortening (quadratic behaviour on long routes)?

Answer in `reviews/responses/003-step2-terrain-sight-routes-codex.md`, following `AGENTS.md`.
