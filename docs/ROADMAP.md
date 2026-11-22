# IMPERATORES roadmap — DRAFT for Ben's approval

**Status:** draft, 22 November 2026; Ben's answers to the open questions recorded the same day (end of document). Each milestone gets its own specification (approved by Ben, reviewed by ChatGPT) and its own behavioural gate before the next begins, as M0 does. The order and contents below are proposals unless marked **decided**. Open questions are collected at the end.

## The whole, in one paragraph

IMPERATORES simulates ancient battles and campaigns in which outcomes emerge from commanders' decisions, imperfect information, delayed orders, subordinate initiative, terrain, armies and institutions, and can be watched on a 2D map and asked "why?". It supports chronologically coherent alternate history and optional anachronistic matchups between leaders of different eras, with their own armies or swapped ones, and flags obvious mismatches with optional balancing. Above the battles sit campaigns (movement, scouting, supply) and the states and societies that raise and lose armies. There are two perspectives on the same world: Historical Figures and Civilizations. Origins settles wars at its own coarse scale and may later hand battles to IMPERATORES. **(All decided, 21–22 November.)**

## Principles that hold throughout (decided)

- One underlying engine for every mode. Chronological and anachronistic play differ only in how scenarios are set up.
- Nothing scripted: no rule names a historical outcome. Leaders differ through source-graded decision tendencies, never special rules.
- Beliefs are not the truth. Every decision uses only what that person has seen or been told.
- Every decision, order and major event can answer "why?". Only political and tactical causes are traced.
- Numbers are provisional, labelled as evidenced or as engineering assumptions, and tested for sensitivity before more research is asked for.
- Research questions name the decision they inform and what ends them.
- Every milestone is reviewed by ChatGPT (history and specification) and Codex (code), and passes a behavioural gate.
- A desktop application, built first as a local page in the browser.

---

## M0 — A battle that explains itself (in build)

A small fictional Roman–Carthaginian engagement; observer mode only. Specification `docs/M0_SPECIFICATION_v1.md`; plan `docs/M0_BUILD_PLAN.md`.

| Step | Contents | Status |
| --- | --- | --- |
| 1 | Foundations: state, keyed random streams, exact replay, records, consistency checks | done, reviewed |
| 2 | Terrain, exact line of sight, routes | done, reviewed |
| 3 | Belief pictures, tracks, information integrity | done, reviewed |
| 4 | Orders, messengers, signals, plans, reports | done, review pending |
| 5 | Decisions: commanders and officers choose for themselves; decision records | next |
| 6 | Combat: equipment, missiles, contact models A and B, order and resolve | |
| 7 | Under pressure: withdrawal, flight, rally, pursuit, line relief, surrender, officer succession | |
| 8 | Viewer, first step: playback and event log | |
| 9 | Controlled scenarios C1–C6 and paired-intervention harness | |
| 10 | Viewer, second step: belief overlays and "Why?" navigation | |
| 11 | Default scenario, diagnostics, sensitivity and performance reports; gate G0 | |

**Gate G0:** the eight acceptance checks in the specification (section 7.1). The **performance decision** is still open, and due by step 11.

---

## M1 — Commander mode and a usable application

**Goal:** you command one side of the M0 battle yourself, under the same constraints as the simulated commanders.

- **Your view is your commander's belief picture**, not the truth: what he can see, what reports have reached him, how old each piece is.
- **Your orders go through the same pipeline:** messengers who ride, can be caught, can fail to find the recipient; signals with their range; latitude; your subordinates' own judgement (from step 5). **(Decided: no omniscient direct control.)**
- **Your commander has a position:** where you put him affects what you see and how long orders take.
- **Pre-battle deployment and plan:** you place units and give conditional instructions before the battle starts.
- **The application:** the browser viewer wrapped as a desktop window; scenario chooser; replays saved and reopened. **(Decided: desktop.)**
- **After a battle:** a debrief comparing what you believed with what was true, through the same "Why?" record.

**Gate (proposed):** a human-commanded battle replays exactly; the simulated side behaves as it does in observer mode; your information is never better than your commander's.

---

## M2 — The first historical leaders and armies

**Goal:** the four leaders already authorised, each with historically grounded armies and decision tendencies. **(Decided: Alexander, Hannibal, Scipio Africanus, Julius Caesar first; own standard armies first.)**

- **Dated army snapshots:** "standard army" means a specific army at a date (for example Hannibal 216 BCE, Hannibal 202 BCE), with sizes as ranges and ancient reported figures labelled as such. One default per leader.
- **Period-specific military systems:** mid-Republican manipular legion and allies; Hannibal's composite army (Q001's seven types); late Republican cohort legion (Caesar); Macedonian phalanx, hypaspists and Companion cavalry (Alexander); and their enemies as needed (Gallic, Persian). New unit types as each army needs them: the pike phalanx first.
- **Leader decision profiles:** tendencies (risk, use of reserves, initiative, deception, reading the enemy) taken from the dossiers with source grades, uncertainties and missing counterexamples kept visible. Where a profile is extrapolated beyond the leader's evidenced situations, the game says so.
- **Historically grounded scenarios** that start from real conditions, with outcomes free to diverge. These are *not* reconstructions that must reproduce history.
- **Order: Hannibal and Scipio first** (the armies M0 already approximates), then Alexander and Caesar.

**Research needed:** army snapshots for each leader and date; profile evidence; the pike phalanx and Companion cavalry in action; how far each leader's tendencies are evidenced.

**Gate (proposed):** each leader behaves distinguishably *for reasons traceable to his tendencies*, across many runs and varied situations; swapping the profiles between two leaders swaps the differences; no special-case rules.

---

## M3 — Matchups, swaps and the fast mode

**Goal:** the anachronistic and comparative features. **(Decided in outline: own armies first; army swaps as an option; mismatch flags offering equal resources, neutral terrain, or swapping the weaker army while keeping the leader.)**

- **Fast aggregate battle mode:** a quicker, coarser model of the same battle, calibrated against the detailed one, used for mismatch detection and later for campaigns. It is checked against the detailed model, never trusted on its own.
- **Mismatch detection:** many fast runs of a proposed matchup. If the results are heavily one-sided, the game says so and why: leader, army or ground (shown by swapping each).
- **Balancing options**, defined explicitly:
  - equal numbers;
  - equal cost (with a stated cost model);
  - forces adjusted until the odds are roughly even (a scenario setting, never forcing the battle itself);
  - neutral terrain: mirror-symmetric, randomised or chosen, with its bias stated.
- **Leader–army familiarity:** a leader commanding an unfamiliar army has to learn its drill, signals and officers. Unfamiliarity has real effects.
- **Learning an unfamiliar enemy:** a leader facing an army he has never met has no expectations about it, and forms them during the battle.
- **Chronologically coherent alternate history** and **anachronistic matchups** both run on the same engine.

**Gate (proposed):** mismatch flags agree with the detailed model; profiles and armies can be swapped independently; familiarity and learning produce traceable effects.

---

## M4 — Campaigns

**Goal:** battles arise from operations rather than being set up. **(Decided in outline: operational, logistical and command scales are part of the vision.)**

- **An operational map:** regions, roads, rivers, passes, settlements.
- **Armies on the march:** columns, marching rates, camps, baggage.
- **Scouting and intelligence** at campaign scale, through the same belief machinery.
- **Supply:** grain, fodder, water, foraging, magazines, seasons (research workstream 04).
- **Deciding whether to give battle:** offering, refusing or forcing battle; choosing ground.
- **Command at a distance:** letters and dispatches between commanders and home.
- **Handing over to the tactical layer:** a battle on the campaign map opens as a detailed (or fast) battle, and its outcome flows back: losses, morale, position, reputation.
- **Strategic leader profiles** (Fabius, for example, is defined by refusing battle).

**Gate (proposed):** campaigns where supply, scouting and timing decide whether and where battles happen, with causes traceable.

---

## M5 — States, politics and societies

**Goal:** the political and social causes of war, and its consequences. **(Decided: political "whys" are tracked.)**

- **Institutions of command:** who appoints, recalls or overrules a commander; what he may order, recruit, punish or requisition (research workstream 05, Phases X–XIII).
- **Recruitment and manpower** as political and economic relationships: levies, allies, mercenaries, land and pay (Phases XXXI–XXXIII).
- **Finance and arrears;** loyalty and mutiny.
- **Legitimacy:** victories and defeats change a commander's standing and factional balance at home.
- **Two perspectives on the same world:** Historical Figures (play or watch a person, whose world is what he knows and controls) and Civilizations (play or watch a state over generations). **(Decided: both exist; how they differ in practice is open.)**

**Gate (proposed):** political events (a recall, a mutiny, a levy refused) arise from modelled causes and change military outcomes, traceably.

---

## M6 — The wider ancient world

**Goal:** the rest of the seventeen-leader roster and their worlds. **(Decided: the roster of 17 is for research; which are playable at release is open.)**

- **Leaders:** Pompey, Hamilcar Barca, Scipio Aemilianus, Fabius Maximus, Philip II, Cyrus the Great, Pyrrhus, Trajan, Aurelian, Sulla, Marius and Thutmose III. Themistocles waits for war at sea (M7). **(Decided.)**
- **Military systems still to come:**
  - Classical Greek hoplites;
  - Achaemenid Persian armies;
  - war elephants (Pyrrhus, Hannibal);
  - chariots and New Kingdom Egyptian warfare (Thutmose III, Megiddo);
  - horse archers (Parthians);
  - the imperial Roman army (Trajan, Aurelian).
- **Each system's research** is commissioned when its leader is scheduled, never earlier.

**Gate (proposed):** each new system is distinct for reasons in its equipment, organisation and doctrine, not through ethnic statistics, and holds up in anachronistic matchups.

---

## M7 — War at sea and sieges

- **Naval warfare:** triremes and quinqueremes, ramming and boarding, fleets and coastal operations (the naval stages of the Punic Wars). **Themistocles and Salamis come here (decided).**
- **Sieges:** works, assaults, blockades, relief armies (Alesia, Dyrrachium).

---

## M8 — Historical cases as tests

**Goal:** check the whole against history without scripting it.

- **Battles and campaigns** start from source-critical reconstructions of their conditions: Megiddo, Salamis, Gaugamela, Cannae, Zama, Ilipa, Cynoscephalae, Pharsalus and others (research workstream 06).
- **The test:** across many runs, are the historical outcomes *among* the plausible ones, for recognisable reasons? Are the alternatives plausible too? It is out-of-sample: never tuned to one famous victory.
- **Some of these can begin earlier,** as checks within M2–M6, once their systems exist.

---

## M9 — Origins integration

- **Origins hands a battle to IMPERATORES** and receives the result. **(Decided: a good idea to return to later.)**
- **An interface agreed with the Origins project** when both are ready; nothing before.

---

## Running alongside every milestone

- **Research:** questions raised in `research/questions/` when a step needs them; Notion remains the archive.
- **Review:** ChatGPT on specifications and history; Codex on code, every step.
- **Performance:** measured at every gate; the fast mode (M3) serves campaigns and matchups.
- **Validation:** sensitivity reports decide where research goes next.

## Ben's answers (22 November 2026)

1. **Order of M3 to M5:** as proposed: matchups, then campaigns, then politics. **Decided.**
2. **Historical Figures and Civilizations:** to be settled when that stage comes. **Deferred.**
3. **Naval warfare:** stays in M7; Themistocles is postponed to it. **Decided.**
4. **First playable roster:** Alexander, Scipio Africanus, Hannibal and Caesar. **Decided.**
5. **The performance choice** from M0: **open.**
6. **Where "release" falls:** later. **Deferred.**
