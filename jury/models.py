"""Typed models shared across the app."""

from enum import Enum
from typing import Literal

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

# Text people read. Blank or near-blank replies (seen from a free model in a real run) are
# rejected, so the model is asked once more and a second failure counts as a failed turn.
Said = Annotated[str, StringConstraints(strip_whitespace=True, min_length=10)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Tier(str, Enum):
    cheap = "cheap"
    mid = "mid"
    strong = "strong"


class RubricItem(BaseModel):
    id: str
    check: str
    fail_when: str


class Persona(BaseModel):
    id: str
    name: str
    tagline: str
    model: Tier
    verdict_question: str
    cares_about: list[str]
    voice: str
    system_prompt: str
    rubric: list[RubricItem] = Field(min_length=1)
    question_triggers: list[str]


class DemoStep(BaseModel):
    ref: str  # e.g. "step-3"
    text: str


class SiteView(BaseModel):
    """One page of the live site at one width, as a first-time visitor sees it."""

    ref: str  # e.g. "page-1-desktop", "page-2-phone"
    url: str
    width: Literal["desktop", "phone"]
    title: str = ""
    headings: list[str] = []
    buttons: list[str] = []
    links: list[str] = []  # link text, then the path it goes to
    facts: list[str] = []  # measured by code, e.g. "the page is wider than the screen"
    text: str = ""  # visible text, capped. Empty for a phone view whose text matches desktop.
    log: str = ""  # what a vision model saw in the screenshot (empty if none was made)


class Brief(BaseModel):
    """The shared project brief every agent reads."""

    project_name: str
    repo_url: str
    summary: str
    files: dict[str, str]  # path -> content (already capped by ingestion)
    tree: list[str] = []  # every path in the repo, so agents know what exists beyond `files`
    demo: list[DemoStep] = []
    site_url: str = ""  # the live site, if one was given
    site: list[SiteView] = []
    notes: list[str] = []  # what ingestion left out or changed (caps hit, secrets redacted)


class Evidence(BaseModel):
    kind: Literal["file", "demo", "tree", "site", "answer"]
    # answer: the id of a question the builder answered (e.g. "q2"); the quote is from their answer.
    # file: a file path. demo: a demo step ref. tree: "present" or "absent".
    # site: a site view ref such as "page-1-desktop" (or "page-1" for either width).
    ref: str
    # file / demo / site: exact text from that file, step, or page's captured text or log. tree: a path or file name to look for.
    quote: str


class Claim(BaseModel):
    text: str
    evidence: Evidence


class VerdictValue(str, Enum):
    useful = "useful"
    unsure = "unsure"
    not_useful = "not useful"


class Verdict(BaseModel):
    """Structured output of one persona. Read by code, never parsed from free text."""

    verdict: VerdictValue
    headline: Short
    reasons: list[Claim]
    what_would_change_my_mind: list[str]
    questions: list[str] = []


class FirstImpression(BaseModel):
    """Round 1 output. The stance is locked once round 1 ends."""

    stance: VerdictValue
    headline: Short
    claims: list[Claim]
    questions: list[str] = []


class MergedQuestion(BaseModel):
    id: str  # q1, q2, ...
    text: str
    asked_by: list[str]  # persona ids


class DebateTurn(BaseModel):
    """One debate turn. Every field except `message` is read by the code router."""

    message: Said  # 3 to 5 sentences, in character
    claims: list[Claim] = []
    stance: VerdictValue
    stance_change_reason: str | None = None
    new_point: bool
    challenges: list[str] = []  # persona ids this turn disputes
    open_question: str | None = None


class ChatReply(BaseModel):
    """One-on-one mode: one persona's reply to the builder."""

    message: Said  # 3 to 5 sentences, in character
    claims: list[Claim] = []
    stance: VerdictValue  # where the persona stands now
    question: str | None = None  # something only the builder can answer


class RouterDecision(BaseModel):
    action: Literal["speak", "ask_user", "end"]
    speaker: str | None = None
    reason: str
    contrarian: bool = False  # the room is unanimous and unchallenged: this speaker argues the other side


class RoomSummary(BaseModel):
    headline: Short
    agreed: list[str] = []
    split: list[str] = []
    top_changes: list[str] = []


class SiteLog(BaseModel):
    """The vision model's reading of one screenshot."""

    on_screen: Said  # what is visible, top to bottom
    what_it_is: str  # what a first-time visitor would think this is, or "not clear"
    main_action: str  # the most prominent next step, or "none visible"
    next_step: str  # what a first-time visitor would most likely do next
    problems: list[str] = []  # visible problems: clipped text, overlap, low contrast, dead ends


class ClaimCheck(BaseModel):
    claim: Claim
    ok: bool
    problem: str | None = None


class VerifiedVerdict(BaseModel):
    persona_id: str
    verdict: Verdict  # reasons hold only claims that passed
    rejected: list[ClaimCheck]


class VerifiedImpression(BaseModel):
    persona_id: str
    impression: FirstImpression  # claims hold only claims that passed
    rejected: list[ClaimCheck]
