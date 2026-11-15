"""Score one finished review against what the eval case expects. Plain code, no model."""

from pydantic import BaseModel


class Notice(BaseModel):
    """Something the panel must point at, with evidence that passed the verifier."""

    name: str
    any: list[str]  # one of these appears in the claim's text, ref or quote
    kind: str | None = None  # narrow to one evidence kind
    ref: str | None = None  # narrow to one ref, e.g. "absent" for tree evidence


class Expect(BaseModel):
    min_useful: int | None = None
    max_useful: int | None = None
    min_not_useful: int | None = None
    max_not_useful: int | None = None
    must_notice: list[Notice] = []
    max_dropped_share: float | None = None


class Check(BaseModel):
    name: str
    ok: bool
    detail: str


def all_claims(events: list[dict]) -> tuple[list[dict], int]:
    """Every claim that passed the verifier, and how many were dropped."""
    kept: list[dict] = []
    dropped = 0
    for e in events:
        if e["type"] in ("impression", "debate_turn"):
            kept += e.get("claims") or []
        elif e["type"] == "verdict":
            kept += e.get("reasons") or []
        else:
            continue
        dropped += len(e.get("rejected") or [])
    return kept, dropped


def matches(claim: dict, n: Notice) -> bool:
    ev = claim["evidence"]
    if n.kind and ev["kind"] != n.kind:
        return False
    if n.ref and ev["ref"].strip().lower() != n.ref.lower():
        return False
    hay = f"{claim['text']} {ev['ref']} {ev['quote']}".lower()
    return any(word.lower() in hay for word in n.any)


def score(events: list[dict], expect: Expect, persona_ids: list[str]) -> list[Check]:
    verdicts = {e["persona_id"]: e["verdict"] for e in events if e["type"] == "verdict"}
    useful = sum(1 for v in verdicts.values() if v == "useful")
    not_useful = sum(1 for v in verdicts.values() if v == "not useful")
    tally = f"{useful} useful, {len(verdicts) - useful - not_useful} unsure, {not_useful} not useful"
    missing = [p for p in persona_ids if p not in verdicts]
    checks = [Check(name="every reviewer gave a verdict", ok=not missing,
                    detail="all in" if not missing else f"missing: {', '.join(missing)}")]

    bounds = [("min_useful", useful, "at least {} useful"), ("max_useful", useful, "at most {} useful"),
              ("min_not_useful", not_useful, "at least {} not useful"),
              ("max_not_useful", not_useful, "at most {} not useful")]
    for field, got, label in bounds:
        want = getattr(expect, field)
        if want is None:
            continue
        ok = got >= want if field.startswith("min") else got <= want
        checks.append(Check(name=label.format(want), ok=ok, detail=tally))

    kept, dropped = all_claims(events)
    for n in expect.must_notice:
        hit = next((c for c in kept if matches(c, n)), None)
        checks.append(Check(name=n.name, ok=hit is not None,
                            detail=f"\"{hit['text'][:90]}\"" if hit else "no verified claim points at it"))

    if expect.max_dropped_share is not None:
        total = len(kept) + dropped
        share = dropped / total if total else 0.0
        checks.append(Check(name=f"at most {expect.max_dropped_share:.0%} of claims dropped by the verifier",
                            ok=share <= expect.max_dropped_share, detail=f"{dropped} of {total} dropped ({share:.0%})"))
    return checks
