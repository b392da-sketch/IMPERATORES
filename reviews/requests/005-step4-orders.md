# Review request 005 — M0 build step 4: orders, messengers, signals (for Codex)

**Scope:** changes since review 004 (including the fixes made in answer to it, `reviews/responses/004-step3-beliefs-answer.md`): `imperatores/orders.py`, `systems/command.py`, `systems/messengers.py`, `systems/movement.py` (approach), `scenario.py` (plans, inputs), `engine.py`, `record.py`, `state.py`, `params.py`, `rng.py`, `belief.py` (tracks), `terrain.py` (ford rule); `tests/test_orders.py`, `tests/test_beliefs.py`. Notes in `docs/M0_BUILD_NOTES.md` (step 3 revisited, step 4).

**Questions:**

1. **Information integrity.** Can any order, plan condition, signal response or approach movement act on the true state of the enemy rather than the officer's picture? In particular `command.describe_target`, `command.believed_position`, `orders.understand`, `movement._approach_point` and `check_plans`. The order records hold which body the issuer meant and which the recipient took (`intended`, `misread`): is anything able to read these as decision inputs?
2. **Order life.** Does every order end in exactly one of executed or failed, with the stages in a sensible order? Can an order be delivered twice, executed twice, lost without a record, or stuck forever (for example waiting for a messenger that never returns, or pending execution after the entity is destroyed)?
3. **Messengers.** Are the search, return, interception and loss rules coherent? Can a messenger get stuck, deliver from too far away, or deliver after being caught? Is the staff count conserved?
4. **Signals.** Is reception (range, blocking, addressing, misattribution) correct? Are plan bindings and the recall default right?
5. **Paired independence.** Can one order, messenger or signal change the random draws or the outcome of another unrelated one?
6. **Replay.** Is all command state (orders, outbox, messengers, staff, pending, plans, inputs) covered by the trace and digest?
7. **Tracks (from review 004).** Are the new tracking rules coherent: lost tracks, duplicates, recognition merging, attribute matching of reports and unidentified sightings? Can a true identity still leak into a view?
8. **Tests.** Do the step 4 tests test what they claim? What important behaviour is untested?

Answer in `reviews/responses/005-step4-orders-codex.md`, following `AGENTS.md`.
