"""Run the eval set: uv run python -m jury.eval [--case weak] [--personas a,b] [--demo-model]

Exits with code 1 if any case fails, so it can gate a prompt or model change.
Full results, with every event, go to evals/results/ (not committed).
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

from jury.eval.run import CASES, load_cases, run_case
from jury.llm import LLM, Budget, LLMError
from jury.personas import load_all


def calls_for(n: int) -> int:
    """Round 1, the debate (2 turns each, 12 at most), verdicts, the summary."""
    return n + min(12, 2 * n) + n + 1


async def run(args) -> int:
    personas = load_all()
    case_set = load_cases()
    cases = [c for c in case_set.cases if not args.case or c.id in args.case]
    if not cases:
        sys.exit(f"no such case. Available: {', '.join(c.id for c in case_set.cases)}")
    default_ids = [p.strip() for p in args.personas.split(",")] if args.personas else case_set.personas
    unknown = [p for c in cases for p in (c.personas or default_ids) if p not in personas]
    if unknown:
        sys.exit(f"unknown persona(s): {', '.join(sorted(set(unknown)))}")

    if args.demo_model:
        from jury.api.demo_llm import DemoLLM
        llm = DemoLLM(delay=0)
        print("DEMO model: this only checks that the eval runs. Its verdicts mean nothing.\n")
    else:
        llm = LLM.from_env()
        # one wrapper for the whole set, so the per-review caps are lifted to cover every case
        llm.budget = Budget(max_calls=llm.budget.max_calls * len(cases), max_tokens=llm.budget.max_tokens * len(cases))
        quota = await llm.quota()
        need = sum(calls_for(len(c.personas or default_ids)) for c in cases)
        print(f"Up to {need} model requests for {len(cases)} case(s)."
              + (f" {quota['remaining']} free requests left today." if quota else "") + "\n")
        if quota and quota["remaining"] is not None and quota["remaining"] < need and not args.force:
            sys.exit("Not enough free requests left today. Run one case with --case, or pass --force.")

    results, log = [], {}
    for case in cases:
        result, events = await run_case(case, default_ids, personas, llm)
        results.append(result)
        log[case.id] = events
        print(f"{'PASS' if result.passed else 'FAIL'}  {case.id}: {case.about}")
        if result.error:
            print(f"      stopped: {result.error}")
        for c in result.checks:
            print(f"      {'ok ' if c.ok else 'NO '} {c.name}  ({c.detail})")
        print(f"      {result.calls} calls, {result.tokens:,} tokens\n")

    passed = sum(r.passed for r in results)
    print(f"{passed} of {len(results)} cases passed.")
    out_dir = CASES.parent / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps({
        "model": getattr(llm, "last_model", None) or type(llm).__name__,
        "results": [r.model_dump() for r in results],
        "events": log,
    }, indent=1), encoding="utf-8")
    print(f"Details: {out}")
    return 0 if passed == len(results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the eval set.")
    parser.add_argument("--case", action="append", help="run only this case (repeatable)")
    parser.add_argument("--personas", help="comma-separated persona ids, instead of the set's default")
    parser.add_argument("--demo-model", action="store_true", help="offline stand-in: checks the plumbing only")
    parser.add_argument("--force", action="store_true", help="run even if the free quota looks too small")
    args = parser.parse_args()
    load_dotenv()
    try:
        sys.exit(asyncio.run(run(args)))
    except LLMError as e:
        sys.exit(f"Model setup problem: {e}")


if __name__ == "__main__":
    main()
