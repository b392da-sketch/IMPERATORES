# Review request 002 — M0 build step 1: foundations (for Codex)

**Scope:** everything added in build step 1 (`docs/M0_BUILD_PLAN.md`, step 1; notes in `docs/M0_BUILD_NOTES.md`):
`imperatores/` (params, rng, state, record, scenario, engine, systems/movement, systems/observe), `run.py`, `scenarios/test_march.json`, `tests/test_foundations.py`.

**Questions:**

1. **Replay.** Is the record fully determined by scenario, seed and parameters? Look for anything that could make two identical runs differ (iteration over sets or dicts, time, floating-point order, state not included in the digest).
2. **Keyed random streams.** Does `rng.Random` really guarantee that an intervention on one entity cannot change another entity's random draws? Can you construct a counterexample? Is the spawn-key scheme safe as streams and keys are added later?
3. **Consistency checks.** Do `systems/observe.py` checks catch what they claim (headcount, speed, field bounds, 0..1 ranges)? Is anything checked too late or too weakly?
4. **Parameters.** Are all values labelled with range and basis as `CLAUDE.md` requires? Is the refusal of out-of-range overrides correct?
5. **Tests.** Do the tests in `tests/test_foundations.py` test what their names say? Which important properties are untested?
6. **Foundations for later steps.** Anything in the state or record design that will make steps 3–5 (beliefs, orders, decision records) or the paired-intervention tests in specification 7.1 harder than they need to be.
7. **Python 3.10 compatibility.**

Answer in `reviews/responses/002-step1-foundations-codex.md`, following `AGENTS.md`.
