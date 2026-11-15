"""Build a project brief from a GitHub repo and a written demo.

Usage: python -m jury.ingest https://github.com/owner/repo --demo walkthrough.txt --out brief.json
       [--site https://app.example.com [--shots shots/] [--no-vision]]

--site captures the live site with a headless browser; its screenshots are described by the
vision model (JURY_MODEL_VISION, else the mid tier), one call each, unless --no-vision.
"""

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from jury.ingest.brief import build_brief


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a project brief.")
    parser.add_argument("repo_url")
    parser.add_argument("--demo", type=Path, help="text file with a written walkthrough")
    parser.add_argument("--out", type=Path, default=Path("brief.json"))
    parser.add_argument("--site", default="", help="the project's live site to capture")
    parser.add_argument("--shots", type=Path, help="also save the site screenshots in this folder")
    parser.add_argument("--no-vision", action="store_true", help="capture the site without describing screenshots")
    args = parser.parse_args()

    load_dotenv()
    demo_text = args.demo.read_text(encoding="utf-8") if args.demo else ""
    brief = build_brief(args.repo_url, demo_text, token=os.environ.get("GITHUB_TOKEN") or None)
    if args.site:
        brief = asyncio.run(_add_site(brief, args))
    args.out.write_text(brief.model_dump_json(indent=1), encoding="utf-8")

    chars = sum(len(t) for t in brief.files.values())
    print(f"{brief.project_name}: {len(brief.files)} files ({chars:,} chars), "
          f"{len(brief.tree)} paths in tree, {len(brief.demo)} demo steps, "
          f"{len(brief.site)} site views ({sum(1 for v in brief.site if v.log)} described) -> {args.out}")
    for note in brief.notes:
        print(f"  note: {note}")


async def _add_site(brief, args):
    from jury.ingest.site import capture_site
    from jury.ingest.site_log import add_site
    from jury.llm import LLM

    def capture(url, max_pages):
        cap = capture_site(url, max_pages)
        if args.shots:
            args.shots.mkdir(parents=True, exist_ok=True)
            for s in cap.shots:
                (args.shots / f"{s.view.ref}.jpg").write_bytes(s.image)
        return cap

    llm = None if args.no_vision else LLM.from_env()
    brief = await add_site(llm, brief, args.site, max_calls=0 if args.no_vision else None, capture=capture)
    if llm:
        print(f"model calls for the site: {llm.budget.calls} ({llm.budget.tokens:,} tokens)")
    return brief


if __name__ == "__main__":
    main()
