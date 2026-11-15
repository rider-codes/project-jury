"""Turn site screenshots into a citable log: one vision-model call per screenshot.

Calls count against the review's budget and the daily free quota like any other call, so
only the most useful views get one: the home page at both widths first, then other pages
at desktop width, then their phone views.
"""

import asyncio
import base64
import os
from pathlib import Path

from jury.ingest.site import VIEWPORTS, SiteCapture, Shot, capture_site
from jury.llm import BudgetExceeded
from jury.models import SiteLog, SiteView, Tier

PROMPT = Path(__file__).resolve().parent.parent.parent / "prompts" / "site_log.md"
DEFAULT_VISION_CALLS = 4


def log_order(shots: list[Shot]) -> list[Shot]:
    """Home desktop, home phone, then other desktop views, then other phone views."""
    def key(s: Shot) -> tuple[int, int]:
        page = int(s.view.ref.split("-")[1])
        if page == 1:
            return (0, 0 if s.view.width == "desktop" else 1)
        return (1 if s.view.width == "desktop" else 2, page)
    return sorted(shots, key=key)


def format_log(log: SiteLog) -> str:
    lines = [f"On screen: {log.on_screen}", f"What it seems to be: {log.what_it_is}",
             f"Main action: {log.main_action}", f"Likely next step: {log.next_step}"]
    if log.problems:
        lines.append("Problems seen: " + "; ".join(log.problems))
    return "\n".join(lines)


def vision_messages(shot: Shot) -> list[dict]:
    v = shot.view
    w, h, _ = VIEWPORTS[v.width]
    text = v.text or "(same text as the desktop view of this page)"
    prompt = PROMPT.read_text(encoding="utf-8").format(url=v.url, width=v.width, size=f"{w}x{h}", text=text)
    image = "data:image/jpeg;base64," + base64.b64encode(shot.image).decode()
    return [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": image}},
    ]}]


async def describe_site(llm, capture: SiteCapture, max_calls: int = DEFAULT_VISION_CALLS) -> tuple[list[SiteView], list[str]]:
    """Returns every captured view (in capture order) and notes. A failed or skipped
    vision call leaves that view's log empty: its text is still citable."""
    notes: list[str] = []
    logged = 0
    for shot in log_order(capture.shots)[:max_calls]:
        try:
            data = await llm.complete_json(Tier.mid, vision_messages(shot), vision=True)
            shot.view.log = format_log(SiteLog.model_validate(data))
            logged += 1
        except BudgetExceeded:
            notes.append("the review budget ran out before every site screenshot was described")
            break
        except Exception as e:  # a bad reply costs one log, not the review
            notes.append(f"no screenshot log for {shot.view.ref}: {type(e).__name__}")
    skipped = len(capture.shots) - logged
    if skipped > 0 and len(capture.shots) > max_calls:
        notes.append(f"{len(capture.shots) - max_calls} site views have text only, no screenshot log "
                     f"(at most {max_calls} screenshots are described per review)")
    return [s.view for s in capture.shots], notes


def vision_calls() -> int:
    return int(os.environ.get("JURY_SITE_VISION_CALLS", DEFAULT_VISION_CALLS))


async def add_site(llm, brief, site_url: str, max_pages: int = 4, max_calls: int | None = None,
                   capture=capture_site):
    """Capture the live site, describe its screenshots, and return the brief with them.
    A site that cannot be opened becomes a note, not a failed review."""
    from jury.ingest.site import SiteError
    try:
        cap = await asyncio.to_thread(capture, site_url, max_pages)
    except SiteError as e:
        return brief.model_copy(update={"site_url": site_url, "notes": [*brief.notes, f"live site not captured: {e}"]})
    views, notes = await describe_site(llm, cap, vision_calls() if max_calls is None else max_calls)
    return brief.model_copy(update={"site_url": cap.url, "site": views, "notes": [*brief.notes, *cap.notes, *notes]})
