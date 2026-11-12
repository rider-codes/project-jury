"""Milestone 1 CLI: one persona gives a verified verdict on a brief.

Usage: python -m jury.cli --persona senior_engineer --brief examples/sample_brief.json
"""

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from jury.agent import final_verdict
from jury.llm import LLM
from jury.models import Brief
from jury.personas import load_persona


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one persona on a project brief.")
    parser.add_argument("--persona", required=True, help="persona id, e.g. senior_engineer")
    parser.add_argument("--brief", required=True, type=Path)
    args = parser.parse_args()

    load_dotenv()
    llm = LLM.from_env()
    persona = load_persona(args.persona)
    brief = Brief.model_validate(json.loads(args.brief.read_text(encoding="utf-8")))

    result = asyncio.run(final_verdict(llm, persona, brief))
    v = result.verdict
    print(f"\n{persona.name}: {persona.verdict_question}")
    print(f"Verdict: {v.verdict.value}  |  {v.headline}\n")
    for c in v.reasons:
        print(f"- {c.text}\n    [{c.evidence.kind}: {c.evidence.ref}] \"{c.evidence.quote}\"")
    if result.rejected:
        print(f"\nDropped {len(result.rejected)} unverified claim(s):")
        for r in result.rejected:
            print(f"- {r.claim.text}  ({r.problem})")
    if v.what_would_change_my_mind:
        print("\nWhat would change my mind:")
        for w in v.what_would_change_my_mind:
            print(f"- {w}")
    if v.questions:
        print("\nQuestions for you:")
        for q in v.questions:
            print(f"- {q}")
    print(f"\nBudget used: {llm.budget.calls} call(s), {llm.budget.tokens} tokens")


if __name__ == "__main__":
    main()
