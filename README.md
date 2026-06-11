# Precedent

**A contract triage spike that learns how your legal team thinks.**

Built as a one-day prototype for the AI Pioneer application task: low-stakes commercial contracts, mostly boilerplate, repeating redlines, a queue longer than the day.

Start with **APPROACH.md** for the thinking. This file covers what's in the box and how to run it.

## Quickest look (no setup at all)

**Double-click `START_HERE.html`.** It opens in your browser and walks through the whole thing interactively: both sample reviews, the suggested redlines, and the precedent loop — approve a suggestion and watch the system learn. Nothing to install, nothing leaves your machine.

## One command (live app)

```bash
python app.py
```

Opens the same page served locally, now with a paste-a-contract box wired to the API. Set `ANTHROPIC_API_KEY` in the terminal first for live reviews; without it, the samples still work and the page tells you what's missing.

## The idea in three lines

1. Check every inbound contract clause-by-clause against a **playbook** the legal team owns and edits (a YAML file, not code).
2. Route the result: green = standard, amber = known deviation with a suggested redline attached, red = escalate to a human.
3. Capture every decision the lawyer makes into a **precedent store**, so the next time the same deviation appears the suggestion is the team's own answer, cited. Review converges toward "yep, fine, checked and approved."

## For the curious: the CLI underneath

```bash
pip install -r requirements.txt

# No API key? Replay the bundled reviews:
python demo/review.py demo/contracts/sample_nda_1.txt --demo
python demo/review.py demo/contracts/sample_nda_2.txt --demo

# Live (set ANTHROPIC_API_KEY; works on your own contracts too):
python demo/review.py demo/contracts/sample_nda_2.txt
python demo/review.py path/to/your_nda.txt

# The learning loop — record decisions into the precedent store:
python demo/review.py demo/contracts/sample_nda_1.txt --demo --record

# The eval harness — accuracy and false-green rate against the golden set:
python evals/eval.py
```

The two samples are synthetic and tell the story between them: sample 1 is near-standard paper that fast-lanes with two precedent-backed redlines; sample 2 is hostile counterparty paper that trips seven escalation triggers and routes straight to a human.

## What's in the box

```
START_HERE.html                  Double-click me: interactive walkthrough, zero setup
app.py                           One command: serves the walkthrough wired live
APPROACH.md                      The thinking: design, rollout phases, evals, risks
demo/
  review.py                      The runnable spike (~250 lines, single file)
  playbook/mutual_nda.yaml       The legal team's positions — they own this file
  precedents.jsonl               Seeded decision memory (the learning loop's data)
  contracts/                     Two synthetic sample NDAs
  outputs/                       Pre-generated reviews (JSON + readable markdown)
evals/
  golden_set.jsonl               21 clause-level expected outcomes
  eval.py                        Reports accuracy and false-greens; exits non-zero on any false green
```

## Honest limitations (it's a spike)

- One contract type. Order forms are the obvious second playbook; the structure already supports it.
- Plain text in. Production wants docx/PDF intake from the contracts inbox and tracked-changes output.
- Whole contract in one model call. Fine at NDA length; long documents want chunking and precedent retrieval by similarity rather than "send them all."
- Precedent store is a JSONL file. That's deliberate: at this stage it should be readable, auditable and editable by the legal team in a text editor.
- The bundled outputs in `demo/outputs/` exist so the demo runs without a key, and the eval passing against them validates the *harness*, not the model. The real test is `python evals/eval.py --live`, and the real golden set is your last quarter's contracts, not my two synthetic ones.
- Model default is `claude-sonnet-4-6` via the Anthropic API. The provider is touched in exactly one function (`call_model` in review.py); routing through Bedrock, Vertex or Foundry to sit inside existing cloud governance is a deployment decision, not a rebuild.

## What it is not

Not legal advice, and it signs nothing. Every finding must quote the contract text it rests on (checked programmatically; unverifiable quotes get flagged and a green demoted to amber). A named human remains the accountable approver, with autonomy earned in measured phases — the gates are in APPROACH.md.
