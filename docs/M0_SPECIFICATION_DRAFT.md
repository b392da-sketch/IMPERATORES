# M0 — "A battle that explains itself" — specification DRAFT v0.2

**Status:** draft v0.2, 22 November 2026, revised after independent review 001 (`reviews/responses/001-m0-specification.md`, answer in `001-m0-specification-answer.md`). Ben's decisions from v0.1 are in section 10. Not yet approved. Every number is a provisional starting value to be tuned, not a historical measurement.

## 1. Purpose

M0 builds the smallest battle that shows the core of IMPERATORES working: commanders and officers who see only part of the field, orders that take time to arrive and can fail, subordinates who act on their own judgement, and outcomes that are not scripted. It ends with a replay you can watch on a 2D map and ask "why?" about.

M0 is a test bench, not a reconstruction. It uses a **fictional engagement** between a Roman-style army and a Carthaginian-style army inspired by the Second Punic War, on a generated or hand-drawn field. It does not recreate any real battle and contains no named historical leaders. Hannibal, Scipio, Alexander and Caesar come after M0's gate, as decision profiles using the same systems.

## 2. What M0 contains

- One land battle on one field, from first deployment to its end.
- Two armies of about 80–100 tactical entities each (section 4).
- Terrain that affects movement, order and sight.
- Command on each side through three software levels (army commander, line or wing commanders, entity officers), with each entity's own historical command succession inside it.
- Belief pictures for every commander and officer, which can be wrong or out of date.
- Orders by messenger and by prearranged signal, each able to fail at every stage.
- Subordinate discretion within, and sometimes beyond, an order's latitude.
- Movement, formation, missile exchange, contact, fatigue, order and resolve, withdrawal, rout, rally, pursuit and surrender.
- A complete decision and event record, a replay viewer and "Why?" (in two steps, section 6.1).

## 3. What M0 leaves out

- Named historical leaders and historically exact armies (after M0).
- Commander mode (M1). Orders from a person will use the same messenger pipeline.
- Campaigns, marching, supply, pre-battle scouting, camps.
- Politics; M0's "whys" are tactical only.
- Naval warfare, sieges, elephants, chariots.
- Mismatch detection and the fast aggregate mode (M0 reports performance so that decision can be made).

## 4. Scale and time

- **Tactical entities are not administrative units.** An entity is a body that moves and fights as one on the field. It may correspond to one historical unit (a maniple), part of one, or several together (a group of turmae acting as a squadron). Each entity records which historical units it represents.
- **Roman side:** the organisation follows Polybius 6.20–26 as a template, not a muster return. A legion of 4,200 infantry and 300 cavalry; 1,200 hastati, 1,200 principes, 600 triarii, the rest velites (21.9; no figure is given for the velites); ten maniples per heavy class (24.1–2); velites divided among the maniples (24.5); cavalry in ten turmae (25.1). Allied infantry usually equal to the Roman, allied cavalry about three times (26.7). How the allied contingent was organised is less documented; the scenario uses maniple-sized blocks for it as a modelling assumption.
- **Velites** belong administratively to their maniples. On the field they act as screening entities, each linked to its parent maniples, so they can skirmish in front and withdraw through the line.
- **Carthaginian side:** contingent entities of comparable size, with types, arms and formation drawn from research question Q001.
- **Default scenario:** half a consular army (one legion and one allied contingent) against a composite force of similar total size, about 80–100 entities per side. The order of battle lives in a scenario file, not in code.
- **Field:** about 4 × 3 km, provisional.
- **Time:** a fixed tick of 2 simulated seconds for movement and contact, provisional. Decisions follow section 5.6. A battle of 2–4 hours is 3,600–7,200 ticks.

## 5. What is represented

### 5.1 Entities

For each entity:

- **Position, facing and formation:** frontage, depth, spacing.
- **Headcount:** split into fit, wounded or out of action, dead, fled, and captured or surrendered, always summing to the starting strength.
- **Tactical function:** for example heavy infantry, skirmishers, light cavalry or heavy cavalry.
- **Command succession:** the entity's own officers in order. For example, two centurions per maniple, the first commanding the right half, either commanding the whole if the other is absent (Polybius 6.24.7); three decurions per turma, command passing to the second (25.1–2). Losing officers degrades command in steps, not all at once.
- **Equipment (a small, consistent model):** reach class (missile, spear, sword); missile type and stock, kept separate for heavy pila (two per hastatus, Polybius 6.23.8, limited and not replenished during pauses), light javelins and sling stones; protection class; mobility.
- **Fatigue and current task.**
- **Order (cohesion):** how well the formation holds its shape. It is lost by movement over rough ground, passing through other entities, contact, and blows to flank or rear. It is recovered by halting and dressing ranks.
- **Resolve:** willingness to stay and fight. It falls with losses, threats to flank or rear, neighbours breaking, officer loss, and having no way out. It rises with support nearby, fresh troops behind, and success.

Order and resolve interact but are not interchangeable. A formation can keep good order while withdrawing, or fight on in disorder. **Restricted retreat space** does not push in one direction. It can cause crowding and loss of order, prevent a withdrawal, stiffen resistance, lead to surrender, or turn a withdrawal into flight, depending on circumstances.

**Outcomes for an entity under pressure** stay distinct: orderly withdrawal, uncontrolled flight, continued resistance, and surrender.

### 5.2 Contact

The shape of infantry contact is contested (Sabin 2000; Zhmodikov 2000; Slavik 2017/18; Goldsworthy, *The Roman Army at War*, pp. 222–227 on lulls; Devereaux 2025 on micro-recoil versus larger disengagement). **Both M0 contact models allow local fluctuation:** men step back out of reach and press in again, missiles are thrown during short separations, and fatigue builds and partly recovers. The switch concerns one disputed variable only:

- **A. Formation-level pulses:** whole fronts can draw apart to a stand-off distance and come together again in renewed attacks, without an explicit withdrawal order or regrouping event.
- **B. Sustained engagement:** fronts stay engaged, with local fluctuation, until an entity withdraws, is relieved or gives way; any larger separation is an explicit event with a cause.

Both models are **calibrated to the same reference test** (a standard engagement between two identical entities produces similar losses and duration under each), so comparing them tests the structure rather than different loss rates. Neither is treated as the historical truth. Line-relief options follow research question Q003.

### 5.3 Terrain

A coarse height map plus features: rough ground, woods, a stream with fords, gentle slopes. Terrain changes movement speed, loss of order and sight lines. Higher ground sees further. Dust and weather are out of M0.

### 5.4 Perception and belief

Every commander and officer has a **belief picture**: which enemy and friendly entities they think are where, how strong and steady, and how old that information is. It is built only from:

- what they can see from their position (range and line of sight over terrain, poorer accuracy at distance);
- reports that reach them by messenger, which may be late or wrong.

**Decision code receives only the belief picture, never the true state.** This is enforced in the structure of the code and tested (section 7, check 3).

### 5.5 Orders, messengers and signals

- An **order** is an intent: hold; advance to a place; attack a named enemy entity; extend or refuse a flank; support a named friendly entity; relieve the front line; withdraw to a place; pursue or stop pursuing.
- Every order carries a **latitude**: how much discretion the recipient has.
- **Messengers** are riders who leave the sender, travel across the field and can be slowed, cut off or lost.
- **Prearranged signals** (trumpet, standard) carry a small menu of meanings agreed before battle, drawn from research question Q002. A signal has three separate stages: it is emitted, it is received (within range and line of sight or hearing, and by the right entities), and it is complied with.
- **Each stage of an order can fail differently**, and receipt never guarantees execution:

| Stage | Possible failure |
| --- | --- |
| Decided | Decision based on a wrong or stale picture |
| Sent | No messenger available; sent to the wrong recipient |
| In transit | Delayed by route or terrain; intercepted; messenger lost |
| Delivered | Out of date: the target has moved or the situation has changed |
| Understood | Misread, because the recipient's picture differs from the sender's |
| Executed | Not executable: the entity is engaged, disordered, blocked or too tired; or the recipient chooses not to, within or beyond their latitude |

Each order's life is recorded stage by stage with times.

### 5.6 Decisions

- **Routine reassessment** every few tens of seconds for officers and longer for higher commanders. These are provisional, randomised scheduling assumptions, not historical reaction times.
- **Interrupts:** unexpected contact, an order arriving, an officer lost, a nearby rout, or a threat to flank or rear can prompt immediate reconsideration. Whether the officer notices the event and acts on it remains up to the model (perception and tendencies).
- At each decision the commander or officer takes their belief picture and current orders, lists the options open to their rank, scores each against goals, believed risks and **tendencies**, chooses with some randomness, and stores the full decision record (section 6).
- **Tendencies** are a small set of weights: how much risk they accept, how strongly they prefer keeping a reserve, how far they will act beyond orders, how quickly they commit to an opening, how much they trust reports against their own eyes. In M0 they are **generic test profiles** (for example "cautious", "bold", "by the book"), not historical people.

### 5.7 End of battle

The battle ends when one army has no formed entities able to resist in the field, when both sides have disengaged, or at nightfall. The record then gives:

- **Battlefield conditions at the end:** each entity's state, who holds which ground, losses, captured and fled.
- **A tactical verdict, given separately**, which may be inconclusive (for example "both armies withdrew in order; the Roman side held the stream").

## 6. The record and "Why?"

- **Reproducibility:** every run is reproducible from its scenario file and seed. Random draws are keyed by system and by entity, so a change to one entity or order does not reshuffle the randomness of everything else. This makes the paired intervention tests in section 7 possible.
- **Decision records:** each decision stores its input snapshot (the belief picture and current orders as they were), the options considered with the components of their scores, the option chosen, and links to the orders and events that followed.
- **Order records** store each stage with times and any failure. The event record stores contacts, missile exchanges, withdrawals, routs, rallies, surrenders and officer losses, with links to their causes.
- **"Why?" is read from these records only.** It never consults hidden information or reconstructs a reason after the fact. It shows what the decision-maker knew, what they weighed and what followed. Where a question needs more than the record ("would the wing have broken without that late order?"), it is answered by a paired intervention run, not by narrative.
- **Only tactical causes are traced.** Soldiers are counts.

### 6.1 Viewer, in two steps

1. **Playback and event log:** a local browser page with the 2D field, entities as blocks with facing and state, messengers moving, a timeline you can scrub, and an inspectable, filterable event and decision log.
2. **Navigation:** belief overlays for a chosen commander ("what does he think is happening?"), and clicking any entity, order or event to follow its "Why?" chain.

The desktop window wrapper comes after the browser version works.

## 7. Gate G0

### 7.1 Acceptance checks

1. **Determinism.** The same scenario and seed reproduce identical state changes and records.
2. **State consistency.** Headcounts are conserved through every transition; entities move within physical speed limits and do not overlap except where passing through each other is allowed.
3. **Information integrity.**
   - Structural: decision code can access only belief pictures.
   - Hidden-entity test: an enemy entity no one can see or has been told about never appears in any decision record.
   - Stale-truth test: changing the true position of an unseen entity leaves every decision unchanged until someone sees it or is told.
4. **Order integrity.** Every order's stages are recorded separately, and controlled scenarios produce each failure mode in the table in 5.5.
5. **Causal responsiveness (paired-seed interventions).** Each produces a traceable difference in decisions, movement or timing where one is expected, recorded and reported (not only in outcomes):
   - change one commander's information while the battlefield stays identical;
   - delay or block one specific order;
   - remove or move a reserve;
   - change one officer's latitude;
   - **mirror test:** swap sides with equivalent forces and mirrored terrain; no side advantage beyond random variation.
6. **Formation behaviour.** In controlled scenarios, each of these can arise from the same systems without separate scripts: orderly withdrawal, disorder and recovery, line relief, pursuit and its recall, rout, rally, surrender and continued resistance.
7. **Reproducible explanation.** Every decision, order and major entity state change has a complete record chain (automated check). Ben reads ten randomly chosen "Why?" chains and judges them sensible and true to the record.
8. **Plausibility review.** Ben (and ChatGPT, if he wishes) watches a sample of replays and judges whether anything is absurd.

### 7.2 Controlled scenarios

Small set-piece situations used by checks 4–6:

- **C1:** a flank becomes vulnerable through movement and terrain (enemy horse passing behind a wood). Can officers recognise and respond? Sometimes they will not, and the record should show why.
- **C2:** an order reaches an entity already engaged.
- **C3:** a messenger's route is blocked or the messenger is lost.
- **C4:** line relief under pressure.
- **C5:** an entity with a stream at its back; several consequences possible.
- **C6:** victorious cavalry with the options to pursue, stop or turn on infantry (informed by Q004).

### 7.3 Diagnostic reports (described, not required)

On 200 runs of the default scenario:

- the distribution of outcomes and end conditions;
- how often flanks were exposed and who saw it first;
- stale orders;
- the variety of responses.

If every run ends the same way, that is flagged to Ben as a warning, not hidden.

Also reported:

- **Contact model comparison:** A against B, both calibrated as in 5.2.
- **Sensitivity:** each provisional value varied across an explicit plausible range (not a blanket percentage), with paired initial conditions, and structural switches tested separately from parameter changes.
- **Performance:** time per full battle on Ben's machine.

Results describe the model's behaviour; they are not historical validation. Failed checks and negative results are recorded in `docs/`.

## 8. Provisional values and their basis

All values live in one `params` file, each with an explicit plausible range and one of two labels: **evidenced** (with source and grade) or **engineering assumption**. Examples:

| Value | Starting value | Label |
| --- | --- | --- |
| Roman unit sizes and organisation | as in section 4 | evidenced: Polybius 6.20–26, as a template |
| Pila per hastatus | 2 | evidenced: Polybius 6.23.8 |
| Infantry pace in formation | to be set, with range | engineering assumption |
| Messenger riding speed across the field | to be set, with range | engineering assumption; the documented desert-post records measure postal routes, not battlefield riders |
| Sight range for recognising entities | to be set, with range | engineering assumption |
| Missile ranges and effect | to be set, with range | engineering assumption, bounded by what sources and modern experiments support |
| Contact model | A or B | competing scholarly reconstructions |
| Effects on order and resolve | to be set, with range | engineering assumptions shaped by the research's qualitative findings |

## 9. Stack and layout

- Python 3.10 or newer with NumPy only for the simulation; a local browser viewer first, wrapped in a desktop window later.
- Patterns are copied from Origins, not imported: plain-data state with systems in a fixed phase order, separate random streams, exact replay, cause records, one file of tunable values, behavioural gates.
- Layout: `imperatores/` (state, systems, engine, record, explain, params), `scenarios/`, `viewer/`, `tests/`, `gates/`, `docs/`, `reviews/`, `research/`.

## 10. Decisions

Answered by Ben, 22 November 2026, on v0.1:

1. Observer mode only in M0; commander mode in M1 on the same order pipeline. **Yes.**
2. Maniple-scale tactical entities. **As proposed.** *v0.2 corrects the count:* one legion plus allies needs about 80–100 entities per side, not 25–40 (review finding 1). **Ben to confirm.**
3. A local browser viewer first, then a desktop window. **As proposed.**
4. Gate thresholds as starting proposals. **Yes**, but v0.2 replaces the frequency thresholds with acceptance checks plus diagnostics, following review finding 3. **Ben to confirm.**
5. Independent review before approval. **Yes; done** (review 001). Codex joins later as a second reviewer.

**Open for Ben:** approve v0.2, or ask for changes.
