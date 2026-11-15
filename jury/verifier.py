"""Claim verifier: plain code, no model. Enforces 'no evidence, no claim'."""

import re

from jury.models import Brief, Claim, ClaimCheck, Verdict, VerifiedVerdict

MIN_QUOTE_CHARS = 4

# Characters models rewrite without changing the meaning: curly quotes, dashes, ellipses,
# and markdown emphasis / code marks. Mapped the same way on both sides.
_SAME = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
    "−": "-", " ": " ", "﻿": None, "`": None, "*": None,
})


def _norm(text: str) -> str:
    text = text.translate(_SAME).replace("…", "...")
    return re.sub(r"\s+", " ", text).strip().lower()


def _quote_in(quote: str, source: str) -> bool:
    """True if the quote appears in the source. A '...' in the quote may skip text,
    but every piece around it must still appear, in order."""
    q = quote.strip(" \"'")
    pieces = [p.strip() for p in q.split("...") if p.strip()]
    if not pieces or any(len(p) < MIN_QUOTE_CHARS for p in pieces):
        return q in source if q else False
    at = 0
    for p in pieces:
        found = source.find(p, at)
        if found < 0:
            return False
        at = found + len(p)
    return True


def _check_tree(claim: Claim, brief: Brief) -> ClaimCheck:
    ev = claim.evidence
    target = _norm(ev.quote).strip("/ \"'")
    mode = ev.ref.strip().lower()
    hit = any(target in p.lower() for p in brief.tree)
    if mode == "present":
        ok, problem = hit, f"no path in the tree matches {ev.quote!r}"
    elif mode == "absent":
        if any(n.startswith("file tree cut") for n in brief.notes):
            return ClaimCheck(claim=claim, ok=False, problem="the tree was cut, so absence cannot be checked")
        ok, problem = not hit, f"the tree does contain {ev.quote!r}"
    else:
        return ClaimCheck(claim=claim, ok=False, problem="tree evidence needs ref 'present' or 'absent'")
    return ClaimCheck(claim=claim, ok=ok, problem=None if ok else problem)


def site_source(brief: Brief, ref: str) -> str | None:
    """Everything a site view shows that can be quoted: its text, headings, buttons, links,
    measured facts and screenshot log. "page-2" (no width) means both widths of page 2.
    A phone view whose text matched desktop falls back to the desktop text."""
    ref = ref.strip().lower().removeprefix("site:").strip()
    views = [v for v in brief.site if v.ref == ref or v.ref.rsplit("-", 1)[0] == ref]
    if not views:
        return None
    parts = []
    for v in views:
        text = v.text
        if not text and v.width == "phone":
            twin = next((d for d in brief.site if d.ref == v.ref.replace("-phone", "-desktop")), None)
            text = twin.text if twin else ""
        parts += [v.title, text, *v.headings, *v.buttons, *v.links, *v.facts, v.log]
    return "\n".join(p for p in parts if p)


def _path(ref: str) -> str:
    """Drop a leading './' only. (lstrip('./') also ate the dot in .github/ and .gitignore.)"""
    ref = ref.strip()
    while ref.startswith("./"):
        ref = ref[2:]
    return ref.lstrip("/")


def check_claim(claim: Claim, brief: Brief, answers: dict[str, str] | None = None) -> ClaimCheck:
    """answers: what the builder told the room, by question id. Without them, `answer` evidence fails."""
    ev = claim.evidence
    quote = _norm(ev.quote)
    if len(quote) < MIN_QUOTE_CHARS:
        return ClaimCheck(claim=claim, ok=False, problem="quote too short")

    if ev.kind == "tree":
        return _check_tree(claim, brief)
    if ev.kind == "answer":
        source = (answers or {}).get(ev.ref.strip().lower().strip("[]"))
        if not source:
            return ClaimCheck(claim=claim, ok=False, problem=f"the builder gave no answer to: {ev.ref}")
    elif ev.kind == "site":
        source = site_source(brief, ev.ref)
        if source is None:
            return ClaimCheck(claim=claim, ok=False, problem=f"site page not captured: {ev.ref}")
    elif ev.kind == "file":
        source = brief.files.get(_path(ev.ref))
        if source is None:
            return ClaimCheck(claim=claim, ok=False, problem=f"file not in brief: {ev.ref}")
    else:
        step = next((s for s in brief.demo if s.ref == ev.ref), None)
        if step is None:
            return ClaimCheck(claim=claim, ok=False, problem=f"demo step not found: {ev.ref}")
        source = step.text

    if not _quote_in(quote, _norm(source)):
        return ClaimCheck(claim=claim, ok=False, problem="quote not found in source")
    return ClaimCheck(claim=claim, ok=True)


def verify_claims(
    claims: list[Claim], brief: Brief, answers: dict[str, str] | None = None
) -> tuple[list[Claim], list[ClaimCheck]]:
    checks = [check_claim(c, brief, answers) for c in claims]
    kept, seen = [], set()
    for c in checks:
        if not c.ok:
            continue
        ev = c.claim.evidence
        key = (ev.kind, _path(ev.ref), _norm(ev.quote))
        if key in seen:  # the same evidence cited twice adds nothing
            continue
        seen.add(key)
        kept.append(c.claim)
    return kept, [c for c in checks if not c.ok]


def verify(persona_id: str, verdict: Verdict, brief: Brief, answers: dict[str, str] | None = None) -> VerifiedVerdict:
    kept, rejected = verify_claims(verdict.reasons, brief, answers)
    return VerifiedVerdict(
        persona_id=persona_id,
        verdict=verdict.model_copy(update={"reasons": kept}),
        rejected=rejected,
    )
