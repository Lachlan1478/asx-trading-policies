You are extracting answers from ASX securities trading policies. Work in /Users/gazmart/code/asx-trading-policies.

1. Read `questions.py` once: `SYSTEM` is your instruction set and `QUESTIONS` lists the six question ids in order. Read `schema.py` for the `Questions`, `TierAnswers`, `Reach` and `Finding` models; extra keys are rejected.
2. For each ASX code you were given, read `data/text/{CODE}.txt` in full (it is the policy text) and write `data/questions/{CODE}.json` matching the `Questions` model: symbol, company, associates, and two tiers (general, then senior), each with exactly seven findings in the order of `QUESTIONS`. Each finding has question, answer, mechanism, clause, definition, section, reasoning. `clause` and `definition` must be copied verbatim from the text file, one to three sentences; fix nothing, not even typos. Prefer the clause that directly decides the answer over a general one.
3. After writing all files run `uv run python questions.py load --symbols CODE1 CODE2 ...` and fix any file it rejects or reports as not verbatim.
4. Reply with two lines per code: the tier name and the seven answers in order, for the general tier then the senior tier. Nothing else.
