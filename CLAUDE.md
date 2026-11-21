# IMPERATORES — working rules for Claude sessions

Ben owns the design. Read the current milestone specification in `docs/` before changing anything. Ben approves specifications and milestone gates; propose design changes, don't make them silently.

## Division of labour
- **Ben:** priorities, design decisions, gate approval.
- **Claude:** technical architect and implementer. Evaluates research proposals and may accept, refine, reject or defer them.
- **ChatGPT:** historical research (kept in Notion, IMPERATORES Research Hub) and independent review of specifications, build steps and gate reports. Ben relays requests and answers through `reviews/`. Claude reproduces each finding before acting on it and answers in writing.
- **Codex:** joins later as a second independent reviewer (rules will go in `AGENTS.md`).
- **Research questions** for ChatGPT go in `research/questions/` (format in `research/README.md`), raised when a build step needs them.

## Rules
- **Behavioural gates decide progress, not test counts.** No new layer until the current gate passes. Record failed attempts and negative results in `docs/`.
- **Nothing scripted.** No rule may name a historical outcome or force a result. Historical leaders differ through source-graded decision tendencies, never through special-case rules or hidden bonuses.
- **Beliefs are not the truth.** Commanders and officers act only on what they have seen or been told. Never read the true state inside a decision.
- **Nobody appears or vanishes.** Each unit's fit + wounded + dead + fled + captured equals its starting strength at every tick.
- **Tactical and political causes are recorded.** Every decision, order and major unit state change must be explainable through the "Why?" chain. Individual soldiers are counts, not stories.
- **Data plus systems.** State is plain data; systems declare what they read and write; the phase order lives in the engine.
- **Separate random streams** per system. Never draw from another system's stream. Append new streams at the end; never insert.
- **Exact replay.** The same scenario and seed reproduce the identical record. Keep the replay test passing.
- **Python 3.10+ and NumPy only** for the simulation.
- **Numbers are provisional.** Every value in `params` is a tunable starting value with a recorded basis. Label each one either as a historically evidenced range (with source) or as an engineering assumption. Say so wherever results are reported. Test sensitivity before asking for more research on a value.
- **Research must name the decision it informs.** When asking for historical research, state which design choice the answer could change and what would end the inquiry.
- **Origins is a separate project.** Patterns may be copied from `b392da-sketch/origins`; never import from it, change it or push to it.
- Code lives in this repository, not in Notion.
