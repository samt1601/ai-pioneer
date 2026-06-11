#!/usr/bin/env python3
"""
Eval harness for Precedent.

Compares review outputs against the clause-level golden set and reports:
  * exact-status accuracy
  * false-green rate  — the gating safety metric. A clause the lawyers judged
    amber/red that the system marked green is a problem waved through.
  * over-flagging     — greens marked amber/red. Costs reviewer seconds, not safety.

Usage:
    python evals/eval.py            # evaluates cached reviews in demo/outputs/
    python evals/eval.py --live     # re-runs each review against the API first

In a real deployment the golden set is built from last quarter's reviewed
contracts, labelled with the outcome the team actually reached. Every playbook
or model change reruns this before going near the live queue. No phase of
autonomy advances unless false-greens are zero here and <1% in sampling.
"""

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "demo" / "outputs"
GOLDEN = Path(__file__).resolve().parent / "golden_set.jsonl"

SEVERITY = {"green": 0, "amber": 1, "red": 2}


def load_golden() -> list[dict]:
    return [json.loads(l) for l in GOLDEN.read_text().splitlines() if l.strip()]


def load_review(contract_stem: str) -> dict | None:
    path = OUTPUTS / f"{contract_stem}.review.json"
    return json.loads(path.read_text()) if path.exists() else None


def worst_status(review: dict, playbook_ref: str) -> str | None:
    """A clause ref can appear more than once (e.g. two findings in one clause).
    Judge on the worst status assigned, since that is what drives routing."""
    statuses = [c["status"] for c in review["clauses"] if c["playbook_ref"] == playbook_ref]
    return max(statuses, key=lambda s: SEVERITY[s]) if statuses else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Re-run reviews via the API before evaluating")
    args = parser.parse_args()

    golden = load_golden()
    contracts = sorted({g["contract"] for g in golden})

    if args.live:
        for stem in contracts:
            subprocess.run([sys.executable, str(ROOT / "demo" / "review.py"),
                            str(ROOT / "demo" / "contracts" / f"{stem}.txt")], check=True)

    results, false_greens, over_flags, missed = [], [], [], []
    for g in golden:
        review = load_review(g["contract"])
        if review is None:
            sys.exit(f"No review output for {g['contract']}. Run review.py first (or --live).")
        got = worst_status(review, g["playbook_ref"])
        if got is None:
            missed.append(g)
            continue
        ok = got == g["expected"]
        results.append(ok)
        if SEVERITY[got] < SEVERITY[g["expected"]] and got == "green":
            false_greens.append(g)
        elif SEVERITY[got] > SEVERITY[g["expected"]]:
            over_flags.append(g)
        flag = "PASS" if ok else "MISS"
        print(f"  [{flag}] {g['contract']:<14} {g['playbook_ref']:<26} expected {g['expected']:<6} got {got}")

    total = len(golden)
    correct = sum(results)
    print("\n" + "=" * 60)
    print(f"  Clause-level accuracy : {correct}/{total} ({100 * correct / total:.0f}%)")
    print(f"  FALSE GREENS          : {len(false_greens)}   <-- gating metric, must be 0")
    print(f"  Over-flagged          : {len(over_flags)}   (acceptable cost)")
    print(f"  Not found in review   : {len(missed)}   (counts as a miss; absence checks matter)")
    by_status = Counter(g["expected"] for g in golden)
    print(f"  Golden set mix        : {dict(by_status)}")
    print("=" * 60)

    if false_greens or missed:
        for g in false_greens:
            print(f"  !! false green: {g['contract']} / {g['playbook_ref']} — {g['why']}")
        for g in missed:
            print(f"  !! not assessed: {g['contract']} / {g['playbook_ref']} — {g['why']}")
        sys.exit(1)
    print("  Gate status: PASS — safe to keep iterating.")


if __name__ == "__main__":
    main()
