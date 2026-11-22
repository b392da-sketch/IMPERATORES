# Review request 006 — M0 build step 5: decisions (for Codex)

**Scope:** changes since review 005, including the fixes made in answer to it (`reviews/responses/005-step4-orders-answer.md`, `tests/test_review005.py`), and step 5:
- new: `imperatores/decisions.py` and `systems/decide.py`;
- changed: `systems/command.py` (orders from others are decided on, standing orders, report interrupts), `systems/movement.py` (`face` task), `orders.py` (`face` order), `engine.py` (decide phase), `record.py`, `state.py`, `scenario.py` (profiles), `params.py`, `rng.py` (stream `decisions`), `belief.py`;
- tests: `tests/test_decisions.py`.

Notes are in `docs/M0_BUILD_NOTES.md` ("Step 4 revisited after Codex review 005" and "Step 5").

**Questions:**

1. **Information integrity.** Can any decision read the true state, true identities or the audit (`w.audit`), directly or through what `decide._context` hands it? `decisions.py` is meant to be pure and the static scan in `test_decisions` enforces it. Is the scan sound, and is anything that `decide.py` passes in (`OrderView`, `SubView`, the own-state mapping, `understood_handle`, `command.believed_position` and `handle_of` for a commander's own units) a leak? Do the stale-truth and hidden-entity tests prove what they claim?
2. **Decision records.** Is every decision recorded with the inputs it actually used, every option with components that sum to its total, the probabilities, the choice, and links to what followed? Can a decision change the world without a record, or a record claim inputs it did not use?
3. **Scheduling and interrupts.** Are routine intervals and interrupts coherent? Can a decision-maker decide too often, never, twice in a tick in a way that matters, or after death? Does the "near/flank/hot" memory miss or repeat interrupts?
4. **Orders and decisions together.** Obey or decline on receipt; supersession by a decision's own order; standing orders and latitude; a commander's "done" and "committed" memory. Are there loops (an order declined, re-ordered, declined), orders that can never execute, or a decline that leaves state inconsistent?
5. **Paired independence and replay.** Keys on stream `decisions` are (owner, decision number). Can one decision-maker's change shift another's draws? Is all decision state (`deciders`, `standing`, `reported_to`, records) covered by the trace and digest?
6. **Behaviour.** Do the menus and score components move in the directions the notes claim (profiles, latitude, trust in reports, flank threats, commitment)? Any degenerate case: division by zero, an empty menu, NaN, a target handle that no longer exists, a place off the field?
7. **Review 005 fixes.** Are the fixes in the answer sound, and are its tests meaningful?
8. **Tests.** Do the step 5 tests test what they claim? What important behaviour is untested?

Answer in `reviews/responses/006-step5-decisions-codex.md`, following `AGENTS.md`.
