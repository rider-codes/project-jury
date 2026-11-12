"""Claim verifier: plain code, no model. Enforces 'no evidence, no claim'."""

import re

from jury.models import Brief, Claim, ClaimCheck, Verdict, VerifiedVerdict

MIN_QUOTE_CHARS = 4


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("﻿", "")).strip().lower()


def _path(ref: str) -> str:
    """Drop a leading './' only. (lstrip('./') also ate the dot in .github/ and .gitignore.)"""
    ref = ref.strip()
    while ref.startswith("./"):
        ref = ref[2:]
    return ref.lstrip("/")


def check_claim(claim: Claim, brief: Brief) -> ClaimCheck:
    ev = claim.evidence
    quote = _norm(ev.quote)
    if len(quote) < MIN_QUOTE_CHARS:
        return ClaimCheck(claim=claim, ok=False, problem="quote too short")

    if ev.kind == "file":
        source = brief.files.get(_path(ev.ref))
        if source is None:
            return ClaimCheck(claim=claim, ok=False, problem=f"file not in brief: {ev.ref}")
    else:
        step = next((s for s in brief.demo if s.ref == ev.ref), None)
        if step is None:
            return ClaimCheck(claim=claim, ok=False, problem=f"demo step not found: {ev.ref}")
        source = step.text

    if quote not in _norm(source):
        return ClaimCheck(claim=claim, ok=False, problem="quote not found in source")
    return ClaimCheck(claim=claim, ok=True)


def verify_claims(claims: list[Claim], brief: Brief) -> tuple[list[Claim], list[ClaimCheck]]:
    checks = [check_claim(c, brief) for c in claims]
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


def verify(persona_id: str, verdict: Verdict, brief: Brief) -> VerifiedVerdict:
    kept, rejected = verify_claims(verdict.reasons, brief)
    return VerifiedVerdict(
        persona_id=persona_id,
        verdict=verdict.model_copy(update={"reasons": kept}),
        rejected=rejected,
    )
