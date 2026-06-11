# Approach note: AI-assisted contract review

**Candidate:** Sam Taylor · AI Pioneer application · June 2026

---

## How I read the brief

The brief says three things that matter:

1. Most contracts are 80% boilerplate.
2. The redlines you do get are ones you've seen before.
3. Every contract still gets read by a person, and the queue is longer than the day.

That's not a "make AI read contracts" problem. It's a triage problem. The expensive thing isn't legal judgement, it's that legal judgement is currently spent equally on documents that don't need it and documents that do. The fix is to spend it unevenly.

So the design goal is not to replace the lawyer's read. It's to make sure the lawyer's read starts from "checked, here's the one thing that needs you" instead of page one.

## The design in one paragraph

Every inbound contract is classified, then checked clause-by-clause against a **playbook**: the legal team's standard positions, acceptable fallbacks, and escalation triggers, written down in a file they own and edit. Each clause comes back green (standard), amber (known deviation, known answer) or red (novel, or trips an escalation trigger). Ambers arrive with a suggested redline. Reds arrive with the exact quoted text and the reason. The lawyer reviews a one-page summary, not a twelve-page contract.

## The part that compounds: precedent memory

The playbook handles the 80%. The interesting bit is the redlines, because the brief says they repeat.

Every decision the lawyer makes (accept, counter with specific language, escalate) is captured into a **precedent store**. The next time the same deviation appears, the suggestion isn't generic; it's "the last four times we saw a 5-year survival period, we accepted it for non-technical counterparties; suggested response attached, ref P-001."

This changes what the system is. It's not a static tool, it's a system that learns how *this* legal team thinks. Over time the amber lane converges on suggestions the lawyer approves without edits, and "review" becomes "confirm." That's the path from assistant to genuine throughput, and it's earned from real decisions rather than assumed.

The capture mechanism costs the lawyer nothing extra: recording the decision *is* the review action.

## Trust is graduated, and gated on numbers

| Phase | What happens | Gate to advance |
|---|---|---|
| 1 — Assist | AI drafts every review; lawyer reads everything | ≥95% reviewer agreement over 50 contracts; false-green rate measured |
| 2 — Fast lane | Green-rated standard contracts become one-click approvals; ambers come precedent-backed | False-green rate <1% on the golden set; Head of Legal signs off per contract class |
| 3 — Selective autonomy | Defined low-risk classes (e.g. our-paper mutual NDAs, unmodified) auto-complete with a 10% sampling audit | Sustained Phase 2 metrics for a quarter; kill switch tested |

The lawyer remains the accountable approver throughout Phases 1–2, and per-class even in Phase 3. No phase advances on vibes; each gate is a number from the eval set.

## Evaluation: did this actually help, by how much, against what

**Safety metric (north star): false-green rate.** A red clause marked green is the failure mode that matters; a green marked amber just costs thirty seconds. The system prompt is explicitly biased toward escalation for exactly this reason, and the eval reports false-greens separately from overall accuracy.

**Build the golden set first.** Take the last quarter's reviewed contracts, label each clause with the outcome the team actually reached, and that's the benchmark. Every playbook change and model change reruns against it before touching the live queue.

**Value metrics:** median turnaround time per contract, % of queue resolved in the fast lane, lawyer minutes per contract, and reviewer agreement rate (how often the AI's draft position survives review unedited). The before-measure is captured during the shadowing days, so the comparison is real.

## What I'd actually do in the two weeks

| Days | Activity |
|---|---|
| 1–2 | Shadow live reviews. Capture decisions verbatim. Measure current turnaround and minutes-per-contract. |
| 3 | Draft the NDA playbook *with* the lawyer, in their words. They own the file from day one. |
| 4–6 | Build the spike (this prototype, roughly). Build the golden set from last quarter's contracts. |
| 7–8 | Run evals, fix the misses, tighten the playbook. Publish the false-green number honestly. |
| 9 | Side-by-side trial on the live queue: lawyer reviews as normal, AI runs in parallel, compare. |
| 10 | Handover: legal team running it themselves, metrics visible, second playbook (order forms) scoped as their next step. |

The two-week artefact is Phase 1 working on one contract type, with the eval harness and the adoption path in place. Not a platform. Platforms come later, if the numbers say so.

## Risks, named

- **Hallucinated readings.** Every finding must quote the exact contract text it's based on. No quote, no finding. This is enforced in the prompt and checkable in the output.
- **False greens.** Covered above; it's the gating metric, and the prompt biases toward escalation when uncertain.
- **Playbook drift / shadow precedents.** A precedent store can encode one lawyer's bad Friday. Quarterly playbook review by the team; precedents carry an approver and are visible, not buried in a model.
- **Confidentiality.** Contracts are sensitive. Run against an API tier with contractual no-training terms, or deploy via Bedrock/Vertex/Foundry inside existing cloud governance. The model call is one function in the code precisely so this is a deployment decision, not a rebuild.
- **Over-trust.** Sampling audits never drop to zero, even in Phase 3. Automation that stops being checked stops being trustworthy.

## What this is not

It's not legal advice and it doesn't sign anything. It's a triage and drafting layer with an audit trail, under a named accountable human. The honest pitch to the legal team is "you'll read less boilerplate and repeat yourself less," not "the AI does law now."

---

*The prototype is a deliberate one-day spike: real enough to run on your contracts this afternoon, rough enough that nobody mistakes it for the finished thing. The fastest way in is to double-click `START_HERE.html` (no setup, runs in your browser); `python app.py` serves the same walkthrough wired live to the API; and the CLI underneath is in `/demo`. The README covers all three.*
