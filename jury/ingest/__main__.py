"""Build a project brief from a GitHub repo and a written demo.

Usage: python -m jury.ingest https://github.com/owner/repo --demo walkthrough.txt --out brief.json
"""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from jury.ingest.brief import build_brief


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a project brief.")
    parser.add_argument("repo_url")
    parser.add_argument("--demo", type=Path, help="text file with a written walkthrough")
    parser.add_argument("--out", type=Path, default=Path("brief.json"))
    args = parser.parse_args()

    load_dotenv()
    demo_text = args.demo.read_text(encoding="utf-8") if args.demo else ""
    brief = build_brief(args.repo_url, demo_text, token=os.environ.get("GITHUB_TOKEN") or None)
    args.out.write_text(brief.model_dump_json(indent=1), encoding="utf-8")

    chars = sum(len(t) for t in brief.files.values())
    print(f"{brief.project_name}: {len(brief.files)} files ({chars:,} chars), "
          f"{len(brief.tree)} paths in tree, {len(brief.demo)} demo steps -> {args.out}")
    for note in brief.notes:
        print(f"  note: {note}")


if __name__ == "__main__":
    main()
