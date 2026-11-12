"""Turn a written walkthrough into numbered demo steps agents can cite."""

import re

from jury.models import DemoStep

_NUMBERED = re.compile(r"^\s*(?:step\s*)?\d+[.):-]\s+", re.IGNORECASE)
_BULLET = re.compile(r"^\s*[-*]\s+")
MAX_STEPS = 60
MAX_STEP_CHARS = 1_000


def parse_walkthrough(text: str) -> list[DemoStep]:
    """Split on numbered lines or bullets if present, else on blank lines.

    Each step becomes `step-N`. Continuation lines join the step above.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    marked = any(_NUMBERED.match(l) or _BULLET.match(l) for l in lines)
    chunks: list[str] = []
    if marked:
        for line in lines:
            if _NUMBERED.match(line) or _BULLET.match(line):
                chunks.append(_BULLET.sub("", _NUMBERED.sub("", line)).strip())
            elif line.strip() and chunks:
                chunks[-1] += " " + line.strip()
            elif line.strip():
                chunks.append(line.strip())
    else:
        chunks = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip()]
    return [
        DemoStep(ref=f"step-{i}", text=c[:MAX_STEP_CHARS])
        for i, c in enumerate(chunks[:MAX_STEPS], 1)
        if c
    ]
