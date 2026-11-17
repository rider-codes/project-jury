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


SITE_ONLY_NOTE = "no repository was given: this is a review of the live site only"


def site_only_brief(site_url: str, demo_text: str = "") -> Brief:
    """No repo: the brief starts empty and the live site is added to it afterwards.
    Reviewers can cite the site, the demo and the builder's answers, never files."""
    from urllib.parse import urlsplit

    host = urlsplit(site_url).hostname or site_url
    demo = parse_walkthrough(demo_text) if demo_text.strip() else []
    notes = [SITE_ONLY_NOTE + " (there are no files to read or cite, so judge what a visitor sees)"]
    if not demo:
        notes.append("no demo walkthrough was given")
    return Brief(
        project_name=host.removeprefix("www."),
        repo_url=site_url,
        summary=f"A live website at {site_url}. No source code was given.",
        files={},
        tree=[],
        demo=demo,
        notes=notes,
    )
