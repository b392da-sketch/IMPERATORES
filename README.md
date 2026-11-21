# IMPERATORES

A historically grounded simulation of ancient battles and campaigns, in which outcomes emerge from commanders' decisions, imperfect information, delayed orders, subordinate initiative, terrain and the armies themselves, rather than being scripted. Battles can be watched on a 2D map and asked "why?".

It supports chronologically coherent alternate history and an optional anachronistic mode that pits leaders from different eras against each other.

**Where it stands (22 November 2026):** build steps 1–2 of 11 (foundations; terrain, sight and routes) are done. The first milestone, M0 "a battle that explains itself", has an approved specification (`docs/M0_SPECIFICATION_v1.md`) and is in build (`docs/M0_BUILD_PLAN.md`).

Historical research is kept in Notion (IMPERATORES Research Hub). Working rules for Claude sessions are in `CLAUDE.md`; independent reviews in `reviews/`.

IMPERATORES is a separate project from Origins. Origins settles wars at its own coarse scale; IMPERATORES is the detailed battle and campaign layer.

## Run it

Python 3.10 or newer with NumPy (`pip install -r requirements.txt`).

```
python -m unittest discover -s tests -v
python run.py scenarios/test_march.json --seed 1 --seconds 3600 --out records/test.json
```

There is no battle or viewer yet. `scenarios/test_field.json` moves a few test entities over a hill, a wood, rough ground and a stream with one ford, and records it.
