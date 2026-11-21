# M0 build plan

Steps in order. Each step ends with its tests passing and a Codex review (`reviews/`) before the next step builds on it. Ben is told when each step is done; gate G0 runs only after all steps are built and reviewed.

| Step | Contents | Specification |
| --- | --- | --- |
| 1 | **Foundations:** plain-data state; tactical entities with headcount, succession and equipment fields; provisional values with ranges and labels; random streams keyed by system and entity; scenario files; engine phase order; simple movement and fatigue over terrain; event record, snapshots and digest; conservation and speed checks; command-line runner | 4, 5.1 (fields), 6 (record), 7.1 checks 1–2 |
| 2 | **Terrain and sight:** height map, rough ground, woods, stream and fords; line of sight; movement and order effects | 5.3 |
| 3 | **Belief pictures:** what each commander and officer sees and is told; decision code given beliefs only; hidden-entity and stale-truth tests | 5.4, 7.1 check 3 |
| 4 | **Orders, messengers, signals:** order life stages and failure modes; riders on the field; signal emission, reception and compliance | 5.5, 7.1 check 4 |
| 5 | **Decisions:** routine reassessment and interrupts; option menus by rank; tendencies; full decision records | 5.6, 6 |
| 6 | **Combat:** equipment model; missile exchange; contact models A and B with the shared calibration test; order and resolve | 5.1, 5.2 |
| 7 | **Under pressure:** withdrawal, flight, rally, pursuit and recall, line relief, surrender, officer succession | 5.1, 5.7 |
| 8 | **Viewer, first step:** browser playback and inspectable event and decision log | 6.1 |
| 9 | **Controlled scenarios C1–C6 and the intervention harness** (paired-seed runs, mirror test) | 7.1 checks 4–6, 7.2 |
| 10 | **Viewer, second step:** belief overlays and "Why?" navigation | 6.1, 7.1 check 7 |
| 11 | **Default scenario** (with Q001–Q004 answers), diagnostics, sensitivity and performance reports; then gate G0 | 4, 7.3 |

Research questions Q001–Q004 (answered 22 November 2026) feed steps 4, 6, 7, 9 and 11; see `research/questions/` and the build notes.
