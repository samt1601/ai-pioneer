#!/usr/bin/env python3
"""
Precedent — contract triage that learns how your legal team thinks.

Usage:
    python review.py contracts/sample_nda_2.txt            # live review (needs ANTHROPIC_API_KEY)
    python review.py contracts/sample_nda_2.txt --demo     # replay cached output, no key needed
    python review.py contracts/sample_nda_2.txt --record   # capture decisions into the precedent store

Design notes (deliberate spike-level choices):
  * The model call is isolated in `call_model()`. Swapping provider or routing via
    Bedrock/Vertex/Foundry is a one-function change, not a rebuild.
  * The whole contract goes to the model in one call and the model segments clauses.
    At spike scale this beats brittle regex clause-splitting. At production scale
    you'd chunk long documents and retrieve precedents by similarity.
  * Every finding must quote the exact contract text it relies on. No quote, no finding.
  * The prompt is biased toward escalation: a false green (a problem waved through)
    is the failure mode that matters; a false amber costs thirty seconds.
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
PLAYBOOK_DIR = ROOT / "playbook"
PRECEDENTS_PATH = ROOT / "precedents.jsonl"
OUTPUTS_DIR = ROOT / "outputs"

DEFAULT_MODEL = "claude-sonnet-4-6"

STATUS_ICONS = {"green": "\033[92m● GREEN\033[0m", "amber": "\033[93m● AMBER\033[0m", "red": "\033[91m● RED\033[0m"}

SYSTEM_PROMPT = """You are a contract triage assistant for an in-house legal team. You do not give \
legal advice and you do not make final decisions. You compare an inbound contract against the team's \
playbook and precedent store, clause by clause, and produce a structured review for a lawyer.

Rules, in priority order:
1. NEVER mark a clause green unless it clearly matches the playbook standard or an acceptable \
fallback. If you are uncertain, mark it amber. If it plausibly trips an escalation trigger, mark it \
red. A missed problem is far worse than an unnecessary flag.
2. Every finding MUST include a verbatim quote of the contract text it is based on, in the \
"quote" field. If you cannot quote the text, you may not make the finding.
3. Check for ABSENCE as well as presence: if the playbook expects something (e.g. standard \
carve-outs) and the contract omits it, that is a finding. Use a short quote of the nearest related \
text and state what is missing.
4. Where a precedent matches the deviation, cite its id in "precedent_refs" and base your \
suggested redline on the precedent language. Where no precedent matches, draft a redline from the \
playbook's standard or acceptable position, and leave "precedent_refs" empty.
5. Suggested redlines are proposals for a lawyer to review, in plain contract language, \
ready to paste. For red items, do not draft a redline; state the escalation reason instead.
6. Also flag anything materially unusual that the playbook does not cover, as amber, with \
playbook_ref "uncovered".

Respond with ONLY a JSON object, no markdown fences, matching this schema:
{
  "contract_type": str,
  "counterparty": str,
  "summary": str,                  // 2-3 sentences, plain language, lead with the verdict
  "overall": "green"|"amber"|"red",// red if any clause is red; amber if any amber; else green
  "clauses": [
    {
      "heading": str,              // clause heading or number as it appears in the contract
      "playbook_ref": str,         // id from the playbook, or "uncovered"
      "status": "green"|"amber"|"red",
      "quote": str,                // verbatim contract text the finding rests on
      "finding": str,              // one or two sentences: what and why
      "suggested_redline": str|null,
      "precedent_refs": [str]
    }
  ],
  "escalations": [str]             // one line per red, naming the trigger tripped
}"""


def load_playbook() -> dict:
    # Spike: one playbook. Production: classify the contract first, then load by type.
    path = PLAYBOOK_DIR / "mutual_nda.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def load_precedents(contract_type: str) -> list[dict]:
    if not PRECEDENTS_PATH.exists():
        return []
    precedents = []
    with open(PRECEDENTS_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                p = json.loads(line)
                if p.get("contract_type") == contract_type:
                    precedents.append(p)
    return precedents


def build_user_prompt(contract_text: str, playbook: dict, precedents: list[dict]) -> str:
    return (
        "<playbook>\n" + yaml.safe_dump(playbook, sort_keys=False) + "</playbook>\n\n"
        "<precedents>\n" + "\n".join(json.dumps(p) for p in precedents) + "\n</precedents>\n\n"
        "<contract>\n" + contract_text + "\n</contract>\n\n"
        "Review the contract against the playbook and precedents. JSON only."
    )


def call_model(system: str, user: str, model: str) -> str:
    """The only place the provider is touched. Swap this function to change provider."""
    from anthropic import Anthropic

    client = Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def parse_review(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("{"):]
    return json.loads(raw)


def verify_quotes(review: dict, contract_text: str) -> None:
    """Hallucination check: every quote must actually appear in the contract."""
    flat = " ".join(contract_text.split())
    for clause in review.get("clauses", []):
        quote = " ".join(clause.get("quote", "").split())
        if quote and quote not in flat:
            clause["finding"] += "  [WARNING: quote not found verbatim in contract — verify manually]"
            if clause["status"] == "green":
                clause["status"] = "amber"  # an unverifiable green is not a green


def render(review: dict) -> str:
    lines = []
    lines.append(f"\n{'=' * 72}")
    lines.append(f"  {review.get('contract_type', 'contract').upper()}  ·  {review.get('counterparty', 'unknown counterparty')}")
    lines.append(f"  Overall: {STATUS_ICONS[review['overall']]}")
    lines.append("=" * 72)
    lines.append(f"\n{review['summary']}\n")
    for c in review["clauses"]:
        lines.append(f"{STATUS_ICONS[c['status']]}  {c['heading']}  [{c['playbook_ref']}]")
        lines.append(f"    \u201c{c['quote'][:160]}{'\u2026' if len(c['quote']) > 160 else ''}\u201d")
        lines.append(f"    {c['finding']}")
        if c.get("suggested_redline"):
            lines.append(f"    \u21b3 Suggested redline: {c['suggested_redline']}")
        if c.get("precedent_refs"):
            lines.append(f"    \u21b3 Precedents: {', '.join(c['precedent_refs'])}")
        lines.append("")
    if review.get("escalations"):
        lines.append("ESCALATIONS (route to senior counsel):")
        for e in review["escalations"]:
            lines.append(f"  \u2718 {e}")
    return "\n".join(lines)


def to_markdown(review: dict, source: str) -> str:
    badge = {"green": "🟢", "amber": "🟠", "red": "🔴"}
    md = [f"# Review: {source}", "", f"**Overall: {badge[review['overall']]} {review['overall'].upper()}**", "", review["summary"], "", "| Clause | Ref | Status | Finding |", "|---|---|---|---|"]
    for c in review["clauses"]:
        md.append(f"| {c['heading']} | `{c['playbook_ref']}` | {badge[c['status']]} | {c['finding']} |")
    ambers = [c for c in review["clauses"] if c["status"] == "amber" and c.get("suggested_redline")]
    if ambers:
        md += ["", "## Suggested redlines", ""]
        for c in ambers:
            refs = f" *(precedents: {', '.join(c['precedent_refs'])})*" if c.get("precedent_refs") else ""
            md += [f"**{c['heading']}**{refs}", f"> {c['suggested_redline']}", ""]
    if review.get("escalations"):
        md += ["## Escalations", ""] + [f"- {e}" for e in review["escalations"]]
    return "\n".join(md) + "\n"


def record_decisions(review: dict) -> None:
    """The learning loop. Recording the decision IS the review action."""
    flagged = [c for c in review["clauses"] if c["status"] in ("amber", "red")]
    if not flagged:
        print("Nothing flagged; nothing to record.")
        return
    print(f"\n--- Decision capture: {len(flagged)} flagged clause(s) ---")
    initials = input("Your initials (for the audit trail): ").strip() or "??"
    next_id = sum(1 for _ in open(PRECEDENTS_PATH)) + 1 if PRECEDENTS_PATH.exists() else 1
    for c in flagged:
        print(f"\n{c['heading']} [{c['status'].upper()}] — {c['finding']}")
        if c.get("suggested_redline"):
            print(f"  Suggested: {c['suggested_redline']}")
        choice = input("  [a]ccept suggestion / [o]verride with your language / [e]scalate / [s]kip: ").strip().lower()
        if choice == "s" or choice == "":
            continue
        decision = {"a": "accepted_suggestion", "o": "countered", "e": "escalated"}.get(choice, "skipped")
        language = c.get("suggested_redline") if choice == "a" else (input("  Your language: ").strip() if choice == "o" else None)
        entry = {
            "id": f"P-{next_id:03d}",
            "date": datetime.date.today().isoformat(),
            "contract_type": review.get("contract_type", "mutual_nda"),
            "playbook_ref": c["playbook_ref"],
            "counterparty_position": c["quote"][:200],
            "decision": decision,
            "language": language,
            "notes": "",
            "approved_by": initials,
        }
        with open(PRECEDENTS_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"  Recorded as {entry['id']}. Next review of this deviation starts from your answer.")
        next_id += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Precedent — contract triage spike")
    parser.add_argument("contract", help="Path to a plain-text contract")
    parser.add_argument("--demo", action="store_true", help="Replay the cached review (no API key needed)")
    parser.add_argument("--record", action="store_true", help="Capture decisions into the precedent store")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model id (default: {DEFAULT_MODEL})")
    args = parser.parse_args()

    contract_path = Path(args.contract)
    contract_text = contract_path.read_text()
    cached = OUTPUTS_DIR / f"{contract_path.stem}.review.json"

    if args.demo:
        if not cached.exists():
            sys.exit(f"No cached review at {cached}. Run live first, or use a bundled sample.")
        review = json.loads(cached.read_text())
        print("(demo mode: replaying cached review — run without --demo for a live one)")
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("ANTHROPIC_API_KEY not set. Use --demo to replay the bundled output instead.")
        playbook = load_playbook()
        precedents = load_precedents(playbook["contract_type"])
        raw = call_model(SYSTEM_PROMPT, build_user_prompt(contract_text, playbook, precedents), args.model)
        review = parse_review(raw)
        verify_quotes(review, contract_text)
        OUTPUTS_DIR.mkdir(exist_ok=True)
        cached.write_text(json.dumps(review, indent=2))
        (OUTPUTS_DIR / f"{contract_path.stem}.review.md").write_text(to_markdown(review, contract_path.name))

    print(render(review))
    print(f"\nFull report: {OUTPUTS_DIR / (contract_path.stem + '.review.md')}")

    if args.record:
        record_decisions(review)


if __name__ == "__main__":
    main()
