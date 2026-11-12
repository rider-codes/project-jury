"""Assemble the project brief from the repo and the demo."""

import re

from jury.ingest.demo import parse_walkthrough
from jury.ingest.github import RepoMeta, RepoRef, download_repo
from jury.ingest.select import Caps, select_files
from jury.models import Brief


def _readme_intro(files: dict[str, str]) -> str:
    readme = next((t for p, t in files.items() if "/" not in p and p.lower().startswith("readme")), "")
    for para in re.split(r"\n\s*\n", readme):
        # drop setext headings ("Title" over a line of === or ---) and rule lines
        lines = [l for l in para.strip().splitlines()]
        kept = [l for i, l in enumerate(lines)
                if not _RULE.match(l) and not (i + 1 < len(lines) and _RULE.match(lines[i + 1]))]
        text = " ".join(" ".join(kept).split())
        # skip headings, badges, images and html
        if text and not text.startswith(("#", "[!", "![", "<", "[![")):
            return text[:600]
    return ""


_RULE = re.compile(r"^\s*[=\-*_]{3,}\s*$")


def assemble(
    ref: RepoRef,
    meta: RepoMeta,
    paths: list[str],
    contents: dict[str, bytes],
    demo_text: str = "",
    caps: Caps = Caps(),
) -> Brief:
    sel = select_files(paths, contents, caps)
    intro = _readme_intro(sel.files)
    summary = " ".join(s for s in (meta.description, intro) if s) or "No description or README intro found."
    demo = parse_walkthrough(demo_text) if demo_text.strip() else []
    notes = list(sel.notes)
    if not demo:
        notes.append("no demo walkthrough was given")
    return Brief(
        project_name=ref.repo,
        repo_url=ref.url,
        summary=summary,
        files=sel.files,
        tree=sel.tree,
        demo=demo,
        notes=notes,
    )


def build_brief(url: str, demo_text: str = "", token: str | None = None, caps: Caps = Caps()) -> Brief:
    ref, meta, paths, contents = download_repo(url, token)
    return assemble(ref, meta, paths, contents, demo_text, caps)
