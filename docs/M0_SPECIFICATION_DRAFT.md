# M0 — "A battle that explains itself" — specification DRAFT

**Status:** draft, 22 November 2026. Ben has answered the decisions in section 10; the draft is under independent review (request 001) and is not yet approved. Every number is a provisional starting value to be tuned, not a historical measurement.

## 1. Purpose

M0 builds the smallest battle that shows the core of IMPERATORES working: commanders and officers who see only part of the field, orders that take time to arrive, subordinates who act on their own judgement, and outcomes that are not scripted. It ends with a replay you can watch on a 2D map and ask "why?" about.

M0 is a test bench, not a reconstruction. It uses a **fictional engagement** between a Roman-style army and a Carthaginian-style army inspired by the Second Punic War, on a generated or hand-drawn field. It does not recreate Cannae, Zama or any real battle, and it contains no named historical leaders. Hannibal, Scipio, Alexander and Caesar come after M0's gate, as decision profiles that use the same systems.

## 2. What M0 contains

- One land battle on one field, from first deployment to a decision or nightfall.
- Two armies of about 25–40 units each (section 3).
- Terrain that affects movement, cohesion and sight.
- A three-level command chain on each side: army commander, a few line or wing commanders, unit officers.
- What each commander and officer believes about the battle, which can be wrong or out of date.
- Orders carried by messengers who ride across the field, plus a small set of prearranged signals.
- Subordinate discretion: officers act within, and sometimes beyond, what they were told.
- Movement, formation, contact, fatigue, cohesion, withdrawal, rout, rally and pursuit.
- A complete record of the battle, and a 2D replay viewer with a "Why?" panel.

## 3. What M0 leaves out

- Named historical leaders and historically exact armies (after M0).
- Commander mode, in which Ben gives the orders. M0 is observer mode only, but orders from a person will go through exactly the same messenger pipeline, so commander mode needs no second system. **DECIDE 1.**
- Campaigns, marching, supply, scouting before battle, camps.
- Politics. The "whys" tracked in M0 are tactical only; political whys arrive with campaigns.
- Naval warfare, sieges, elephants, chariots.
- Mismatch detection and the fast aggregate battle mode (but M0 measures performance so that decision can be made; see check 12).

## 4. Scale and time

- **Unit:** the smallest body with its own officer and standard. Roman side: maniples (nominally 120 hastati or principes, 60 triarii), groups of velites, and cavalry turmae of 30, following Polybius 6.19–26 as an organisational template only. Carthaginian side: contingent blocks of comparable size (heavy infantry, other infantry, slingers, light and heavy cavalry). Each unit tracks its own headcount. **DECIDE 2** (unit scale).
- **Default scenario size:** roughly one legion plus an allied contingent on the Roman side, against a composite force of similar total size. Exact orders of battle live in a scenario file, not in code.
- **Field:** about 4 × 3 km, provisional.
- **Time:** a fixed tick of 2 simulated seconds for movement and contact (provisional). Officers reconsider their situation every 10–30 s, line commanders every 30–60 s, the army commander every 60–120 s, all provisional and randomised so decisions do not happen in lockstep.
- A battle of 2–4 simulated hours is therefore 3,600–7,200 ticks.

## 5. What is represented

### 5.1 Units

For each unit: position, facing, formation (frontage, depth, spacing), headcount split into **fit, wounded/out of action, dead, fled, captured** (always summing to the starting strength), fatigue, missiles left, current task, the officer present or lost, and two separate states:

- **Order (cohesion):** how well the formation holds its shape. Lost by movement over rough ground, passing through other units, contact, and being struck in flank or rear. Recovered by halting and dressing ranks.
- **Resolve:** willingness to stay and fight. Lowered by losses, threats to flank or rear, neighbours breaking, losing the officer, having nowhere to retreat; raised by support nearby, fresh units behind, and success.

Two variables are a deliberate simplification. The research rejects a single "morale" number; splitting physical order from willingness to stay is the minimum that lets a unit **withdraw without routing**, or **advance while losing its formation**, both documented cases (Phases XXVIII–XXIX). Their effects are provisional.

### 5.2 Contact

The research leaves the shape of infantry contact open (Sabin's intermittent stand-off and pulses; Zhmodikov's and Slavik's emphasis on missiles; Goldsworthy's lulls; Devereaux's micro-recoil versus large disengagement). M0 therefore implements **two contact models behind one switch**:

- **A. Pulsed contact:** lines close to a short stand-off distance; local surges into hand-to-hand fighting come and go with fatigue, resolve and officers' presence; missiles are thrown during the stand-off.
- **B. Sustained contact:** lines stay in close combat until one gives way; fatigue builds steadily; relief comes from rear ranks or a following line.

Neither is treated as the historical truth. Check 11 measures whether choosing one or the other changes outcomes, which tells us whether further research into it is worth the time. Ranges, rates of loss and so on are provisional values in `params`.

### 5.3 Terrain

A coarse height map plus features: rough ground, woods, a stream with fords, gentle slopes. Terrain changes movement speed, loss of order, and sight lines. Hills give a better view. Dust and weather are out of M0.

### 5.4 Perception and belief

Every commander and officer has a **belief picture**: which enemy and friendly units they think are where, how strong and how steady, and how old that information is. It is built from:

- what they can see from their own position (range and line of sight over the terrain, with poorer accuracy at distance);
- reports carried by messengers from other officers, which arrive late and may already be out of date.

Beliefs are never copied from the true state. Wrong beliefs are recorded so that the replay can show, for example, "the commander still thought the left was holding".

### 5.5 Orders and messengers

- An **order** is an intent, not a movement path: hold, advance to a place, attack a named enemy unit, extend or refuse a flank, support a named friendly unit, relieve the front line, withdraw to a place, pursue or stop pursuing.
- Every order carries a **latitude**: how much discretion the recipient has (from "exactly this" to "use your judgement").
- Orders and reports go by **messenger**: a rider who leaves the sender, travels across the field at a provisional speed, and can be slowed, cut off or lost. An order's life is recorded in stages: decided, sent, delivered, understood, acted upon (Phase XII distinction).
- **Prearranged signals** (trumpet, standard) reach units within a limited range and carry only a few meanings agreed before battle, such as "advance", "halt", "the reserve goes in". The research shows commanders planning contingencies before battle (Gaugamela, Alesia, Cannae); signals let that happen.

### 5.6 Decisions

At each decision moment a commander or officer:

1. looks at their belief picture and their current orders;
2. lists the options open to them (from a fixed menu per rank);
3. scores each option against their goals, the risks they believe exist, and their **tendencies**;
4. chooses, with some randomness, and records why.

**Tendencies** are a small set of weights, not a "generalship" score: for example, how much risk they accept, how strongly they prefer keeping a reserve, how far they will act beyond their orders, how quickly they commit to an opening, how much they trust reports versus their own eyes. In M0 these are **generic profiles** (for example "cautious", "bold", "by the book") used to test that the system can produce different behaviour. Historical profiles come later and must be source-graded.

An officer who acts beyond their latitude records it as such ("acted without orders because the flank was open and the line commander was out of reach").

### 5.7 End of battle

The battle ends when one army no longer has formed units able to resist in the field, when both sides have disengaged, or at nightfall. Pursuit, capture and rallying continue until then. The result is described in words (for example "Carthaginian victory; Roman left routed, centre withdrew in order"), not reduced to a score.

## 6. The record, replay and "Why?"

- Every run is reproducible from its scenario file and seed. Separate random streams per system.
- The run records unit states every few seconds and every significant event: decisions, orders and their stages, reports, contacts, withdrawals, routs, rallies, officer losses.
- **Why?** answers tactical questions about any decision or major state change, through a chain of recorded causes. For example: *Unit L7 routed* ← flank struck by Numidian horse (event) ← L6 to its left had withdrawn 90 s earlier (event) ← L6's officer ordered the withdrawal because his resolve and order were low after missile fire (decision, with beliefs) ← the relief order from the line commander arrived 4 minutes after it was sent (order stages) ← the messenger rode around a wood (route).
- Only tactical causes are traced. Individual soldiers' deaths are counts, not stories.

### 6.1 Viewer

A local 2D battlefield view: units drawn as blocks with facing, state shown by colour and outline, messengers as moving dots, sight and belief overlays for a chosen commander ("what does he think is happening?"), a timeline you can scrub, play speed, and clicking any unit, order or event opens its "Why?" chain. **DECIDE 3** (window versus browser).

## 7. Gate G0 — behavioural checks

M0 is complete when these pass on **200 runs** of the default scenario (different seeds) plus the knock-out and sensitivity runs. Thresholds are proposals.

1. **Exact replay.** The same scenario and seed reproduce the identical record.
2. **Nobody appears or vanishes.** In every tick of every run, each unit's fit + wounded + dead + fled + captured equals its starting strength.
3. **No scripted winner.** Neither side wins more than 85% of the default runs, and battles end in at least three different ways (for example a rout of one wing, an orderly withdrawal, nightfall with neither side broken).
4. **Flank exposure emerges.** In at least 30% of runs, a formed enemy unit reaches the flank or rear of a line without any rule that puts it there.
5. **Someone else sees it first.** In at least a quarter of those cases, a subordinate's belief picture records the exposure before the army commander's does.
6. **Orders can arrive too late.** In at least 20% of runs, at least one order arrives after the situation it answered has changed in a way that makes it wrong (recorded as stale).
7. **Different responses.** Across runs with an exposed flank, at least three different responses occur (for example extending the line, committing a reserve, withdrawing the wing, accepting the risk), and none accounts for more than 70%.
8. **Command matters (knock-out).** With instant orders and perfect sight for everyone, the distribution of outcomes changes significantly against the default (for example in who wins, or how often a flank is exposed). If it doesn't, the command system is decoration.
9. **Rout is not a cliff.** Some units withdraw in order without routing; routs are clustered in space and time (neighbours break together); units with no room behind them break more often than units with room.
10. **Every answer has a why.** Every decision, order, rout, withdrawal and rally has a complete cause chain (automated check), and Ben reads ten randomly chosen "Why?" chains and judges them sensible.
11. **Sensitivity report.** Runs with contact model A against B, and with key provisional values at ±50%, reporting which change outcomes materially and which don't. This report decides where research goes next; it is not a pass/fail check.
12. **Performance report.** Time to run one full battle at full detail on Ben's machine. This decides how the later fast mode for mismatch detection is built; it is not a pass/fail check.

Failed checks and negative results are recorded in `docs/`, not hidden.

## 8. Provisional values and their basis

Kept in one `params` file, each with a note of its basis. Examples (all provisional):

| Value | Starting value | Basis |
| --- | --- | --- |
| Roman unit sizes | maniples 120/120/60; turmae 30 | Polybius 6.19–26, as an organisational template, not a muster return |
| Infantry walking pace in formation | to be set | engineering assumption; sensitivity-tested |
| Messenger riding speed across the field | to be set | engineering assumption; the documented desert-post records measure postal routes, not battlefield riders |
| Sight range for recognising units | to be set | engineering assumption |
| Contact model | A or B | competing scholarly reconstructions (Phase XV–XVIII) |
| Effects on order and resolve | to be set | engineering assumptions shaped by the research's qualitative findings |

Where the sources cannot give a range, the value is labelled an **engineering assumption** and tested for sensitivity, never presented as a historical measurement.

## 9. Stack and layout

- Python 3.10 or newer and NumPy only for the simulation, like Origins. **DECIDE 3** covers the viewer.
- Patterns taken from Origins (copied, not imported, so neither project can break the other): plain-data state with systems run in a fixed order, separate random streams, exact replay, cause chains, one file of tunable values, behavioural gates.
- Proposed layout: `imperatores/` (state, systems, engine, record, explain, params), `scenarios/`, `viewer/`, `tests/`, `gates/`, `docs/`, `reviews/`.

## 10. Decisions for Ben — answered 22 November 2026

1. **Observer mode only in M0**, with commander mode in M1 using the same order pipeline. **Ben: yes.**
2. **Unit scale:** maniple-sized units, about 25–40 per side (rather than larger blocks of about 10–15 per side, which would be faster but lose the intervals and lines that make Roman tactics distinctive). **Ben: as proposed.**
3. **Viewer:** a local page in the browser first, then wrapped in its own desktop window. **Ben: as proposed.**
4. **Gate thresholds** in section 7 accepted as starting proposals. **Ben: yes.**
5. **Review:** the draft goes to independent review (request 001) before Ben approves it. **Ben: yes; sent.** Codex will also join as an independent reviewer at a later point, as in Origins.

The specification stays a draft until the review has been answered and Ben approves it.
