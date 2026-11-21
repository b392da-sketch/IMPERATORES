# Review 001 — IMPERATORES M0 Specification

**Reviewer:** ChatGPT — Independent historical and simulation review  
**Date:** 22 November 2026  
**Reviewed:** `docs/M0_SPECIFICATION_DRAFT.md`, branch `m0-spec-draft`  
**Recommendation:** Approve direction; request revisions before specification approval.

## Numbered findings

### 1. [HIGH] The proposed force size and unit count are inconsistent

Section 4 proposes 25–40 units per army, with the Roman side representing approximately one legion plus allied forces.

Polybius 6.21–25 describes a legion organised into thirty heavy infantry maniples (ten each of hastati, principes and triarii), with velites distributed among the maniples and cavalry organised into ten turmae.

Representing all heavy infantry maniples and cavalry turmae individually already requires approximately forty entities before adding separate skirmisher formations or allied contingents.

**Recommendation:** Retain maniple-scale representation where useful, but distinguish simulated tactical entities from historical administrative units. Either increase the entity budget or explicitly represent a reduced detachment rather than a complete legion and allied army. Do not silently compress an entire Polybian army into an inaccurate order of battle.

### 2. [HIGH] Contact Model B needs a more historically defensible definition

Section 5.2 correctly treats infantry contact as contested. However, the distinction between pulsed contact and sustained combat risks becoming misleading.

Sabin's intermittent-contact model is an important scholarly hypothesis. But sustained engagement does not necessarily mean continuous sword blows or bodily contact until one side collapses.

Devereaux's 2025 examination usefully distinguishes small withdrawals outside weapon reach from larger disengagements between formations. This is an interpretation, not settled consensus, but it demonstrates why a simple binary may be insufficient.

**Recommendation:** Both models should permit local fluctuations in striking distance.

The disputed variable should primarily be whether whole formations can undergo substantial disengagements and renewed attacks without an explicit withdrawal or regrouping event.

Do not make sustained contact a physically implausible strawman merely to provide an alternative to Sabin's model.

### 3. [HIGH] Gate checks 3–7 could reward scripted behaviour

The proposed thresholds require particular frequencies of victories, flank exposures, stale orders and response types.

These are useful diagnostic observations, but poor universal acceptance criteria.

An effectively scripted system could satisfy all of them by injecting random events or deliberately balancing results.

Conversely, a credible model might fail because the chosen scenario strongly favours one side or rarely creates a particular opportunity.

**Recommendation:** Replace fixed frequency gates with controlled scenario tests and causal interventions.

For example, construct a situation where a flank becomes vulnerable because of actual movement and terrain, then verify that officers can recognise and respond to it.

Keep frequencies as descriptive statistics. Do not require the simulation to manufacture particular frequencies.

### 4. [HIGH] The anti-scripting tests need stronger counterfactual controls

Gate 8 compares the default simulation with perfect sight and instantaneous orders.

This is valuable but insufficient.

The outcome distribution could change substantially while the model still contains scripted decisions. Conversely, a model with genuine command effects might produce similar victory frequencies despite substantially different battlefield developments.

**Recommendation:** Introduce paired-seed intervention tests:

- Change a commander's information while keeping the actual battlefield identical.
- Delay or prevent one specific order.
- Remove or reposition a reserve.
- Change an officer's assigned discretion while holding other circumstances constant.
- Reverse equivalent forces and terrain to test unintended side advantages.

Record changes in decisions, movement, timing and outcomes—not simply victory frequencies.

A particularly important test is that commanders must not respond to information they could not possess.

### 5. [HIGH] The explanatory system must distinguish recorded reasons from proven causes

The proposed "Why?" system is one of M0's most valuable features.

However, a decision log showing that a commander chose withdrawal because resolve was low is not necessarily a sufficient causal explanation.

A convincing explanation should distinguish:

- Information available to the decision-maker.
- The options considered.
- The factors influencing their relative desirability.
- The action actually selected.
- The physical consequences of that action.

The explanation must never consult hidden information to justify an earlier decision.

**Recommendation:** Store the decision's input snapshot, evaluated alternatives, selection factors, order history and resulting events. Make explanations reconstructible from that record rather than generating plausible-sounding retrospective narratives.

### 6. [MEDIUM] The division between order and resolve is appropriate

Section 5.1 makes a defensible modelling distinction between structural formation integrity and willingness to continue fighting.

It reflects our research better than treating morale as a single variable determining all movement and resistance.

However, these states should interact without becoming interchangeable.

A formation can retain reasonable order while withdrawing. Soldiers may continue fighting despite severe structural disorder. Units surrounded without an escape route may surrender, panic, resist desperately or become physically unable to withdraw.

**Recommendation:** Retain the distinction, but avoid deterministic rules such as "no retreat space always increases rout probability." Ensure that orderly withdrawal, uncontrolled flight, resistance and surrender remain distinct possible outcomes.

### 7. [MEDIUM] Polybius should inform Roman organisation without imposing a universal hierarchy

Polybius 6.24 describes two centurions and two optiones assigned to each maniple, with arrangements intended partly to prevent the unit from becoming leaderless.

Velites were distributed among the maniples administratively rather than simply constituting another identical category of heavy infantry unit.

Cavalry also had a different officer structure.

The Carthaginian army, meanwhile, contained contingents with different organisations and command relationships.

**Recommendation:** Represent the entity's tactical function and available command succession separately from any universal assumption that every unit possesses one officer and one standard.

The three-level hierarchy is acceptable as a software abstraction, but should not be presented as a reconstruction of identical Roman and Carthaginian command structures.

### 8. [MEDIUM] Basic equipment and tactical roles must influence combat from M0

The specification mentions missiles, infantry and cavalry, but the interactions between equipment, distance and formation behaviour remain insufficiently explicit.

Even a small Second Punic War-style engagement requires meaningful distinctions between missile troops, formed heavy infantry and cavalry.

Otherwise, the simulation may reproduce generic combat blocks rather than recognisable ancient battlefield behaviour.

**Recommendation:** Include a minimal representation of weapon reach, ammunition, protection, mobility and effective engagement conditions.

In particular, heavy infantry should not possess inexhaustible javelins during repeated contact-model pauses. The distinction between heavy infantry pila and the ammunition carried by light troops matters.

Do not attempt elaborate individual weapons modelling at M0. A small, consistent equipment model is sufficient.

### 9. [MEDIUM] The decision schedule should permit urgent event-driven responses

Section 4 specifies periodic reconsideration intervals of 10–120 seconds.

These are acceptable provisional scheduling assumptions, but they should not become rigid historical reaction times.

An officer who suddenly observes a cavalry attack against his flank should not necessarily remain inactive merely because his next decision tick has not arrived.

**Recommendation:** Separate routine reassessment from event-triggered responses.

Unexpected contact, receipt of orders, officer casualties, a nearby rout and an immediate flank threat should be capable of prompting reconsideration. Whether the officer recognises and acts on the event remains subject to the model.

This preserves imperfect command without introducing artificial passivity.

### 10. [MEDIUM] Order transmission needs explicit failure modes

The messenger system is promising, as is the distinction between an order being sent, delivered, understood and executed.

However, these stages should produce different possible failures.

For example, an order might arrive correctly but be impractical because the original target has moved. It could be misunderstood because the recipient's information differs from the sender's. It might be understood but not executable because a unit is engaged.

Caesar's account of the failed recall at Gergovia (BG 7.47–52) is particularly useful evidence for distinguishing signal emission, reception and compliance.

**Recommendation:** Ensure that order receipt never guarantees immediate execution, and that the effect of an order depends on the recipient's circumstances.

### 11. [MEDIUM] Gate 9 assumes a particular relationship between encirclement and collapse

The gate requires units without retreat space to break more frequently.

This may occur under some conditions, but it is not universally defensible.

Restricted escape routes can contribute to panic, crowding, destruction or surrender. They may also prevent an attempted withdrawal or encourage continued resistance.

**Recommendation:** Test whether the system can produce several plausible consequences of restricted retreat space rather than requiring one universal behavioural direction.

This is an especially important distinction for future reconstructions of Cannae and Zama.

### 12. [MEDIUM] Sensitivity testing should isolate the assumptions under investigation

Gate 11 proposes comparing contact models and varying parameters by ±50%.

The principle is excellent. The implementation requires greater care.

A percentage change may be inappropriate for bounded probabilities, geometrical constraints or parameters near zero.

Likewise, if the two contact models also use substantially different casualty rates, the comparison may reveal only that one model inflicts more casualties.

**Recommendation:** Use explicitly bounded parameter ranges, paired initial conditions and controlled comparisons. Separate structural assumptions from parameter changes wherever feasible.

Report uncertain effects as uncertain; do not convert simulation output into historical validation.

### 13. [LOW] The initial viewer can be simplified without sacrificing research value

A full interactive replay with timeline scrubbing, belief overlays, messenger movement and comprehensive causal exploration is desirable.

Nevertheless, the visual interface should not delay validation of the underlying simulation.

**Recommendation:** Implement basic battlefield playback and an inspectable event log first. Add sophisticated causal navigation once the event and explanation records are reliable.

This is a sequencing recommendation, not a suggestion to abandon the "Why?" system.

### 14. [LOW] Preserve a distinction between battle termination and victory

The conditions in section 5.7 are acceptable for a first test, but reaching nightfall does not inherently establish a victor.

Two armies may withdraw in good order, disengage after partial success, or preserve their fighting capacity while losing control of important ground.

**Recommendation:** Report battlefield conditions at termination separately from any tactical verdict. Support inconclusive outcomes without compelling a winner.

## Section 10 — Recommendations for Ben

| Decision | Recommendation | Reason |
| --- | --- | --- |
| 1. Observer-only M0 | **Yes** | Establish one functioning command simulation before introducing player orders. |
| 2. Maniple-scale units | **Yes, with revisions** | The scale preserves relevant Roman formation interactions, but the unit budget and historical order of battle must be reconciled. |
| 3. Browser-based viewer | **Yes** | A local browser viewer is a sensible, inspectable first implementation. Desktop packaging can follow. |
| 4. Gate thresholds | **Revise before approval** | Retain deterministic and causal gates, but treat arbitrary event frequencies as diagnostics rather than mandatory results. |
| 5. Independent ChatGPT review | **Yes** | Review this draft before final approval and continue reviewing subsequent substantive milestones. |

## Recommended minimum gate revisions

For M0, I would prioritise the following acceptance properties:

1. **Determinism:** identical scenario and seed reproduce identical state changes and event records.
2. **State consistency:** headcounts remain conserved through every transition; movement and unit geometry obey basic constraints.
3. **Information integrity:** officers never access hidden state when making decisions.
4. **Order integrity:** decisions, transmission, receipt, interpretation and execution are distinguishable.
5. **Causal responsiveness:** changing information, terrain, order availability or subordinate discretion can produce explainable differences in behaviour.
6. **Formation behaviour:** the simulation can produce organised withdrawal, disorder, recovery, pursuit and rout without separate scripted outcomes.
7. **Reproducible review:** significant actions can be traced to the information and mechanisms that produced them.

Frequency statistics, battle outcomes, model comparisons and performance should accompany these as diagnostic reports.

## Evidence and access notes

**Directly checked primary organisational text:** Polybius, *Histories* 6.21, 6.24–25, accessible in English translation. The original Greek was not independently collated for this review.

**Checked modern discussion:** Bret Devereaux, "Intermission: Battle Pulses" (18 December 2025), complete online essay read. It is a historian's interpretive essay, not a peer-reviewed quantitative validation of a combat model.

**Partially checked modern scholarship:** Philip Sabin, "The Face of Roman Battle," *Journal of Roman Studies* 90 (2000), 1–17. Publisher bibliographic material checked; the existing IMPERATORES source audit was consulted, but the entire original article was not independently reread during this review.

**Existing project evidence consulted:** IMPERATORES Notion workstreams 02 and 08, including the Roman Infantry Combat evidence-to-mechanism specification. These records preserve further research on Goldsworthy, Zhmodikov, Slavik and related disputes. The underlying works were not all independently reread for this review.

**Ancient comparative case:** Caesar, *Bellum Gallicum* 7.47–52, previously reviewed in the IMPERATORES research concerning Gergovia. Not freshly collated against a critical Latin edition.

## Final recommendation

**Request revisions rather than reject M0.**

The architecture's central direction is sound. Its attempt to produce explainable, emergent behaviour under incomplete information is closely aligned with the project's historical aims.

The two most important corrections are:

1. Reconcile the selected tactical entity scale with the historical force organisation being represented.
2. Replace outcome-frequency acceptance thresholds with more rigorous tests of causal emergence and information integrity.

Once these issues are addressed, the specification should provide a suitable foundation for the first executable IMPERATORES milestone.

**This review does not constitute Ben's approval of the specification or its final design decisions.**