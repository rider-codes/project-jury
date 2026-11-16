"""Keep secrets out of anything shown to a user or written to the event log.

Error text from an HTTP library can quote the request it failed to send, headers
included. Everything that leaves the server as an error or an event goes through
`redact` first.
"""

import os
import re

SECRET_ENV = ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "GITHUB_TOKEN")
HIDDEN = "[hidden]"

# shapes of the keys this project handles, for a secret that is not (or no longer) in the environment
_SHAPES = re.compile(
    r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}"
    r"|sk-[A-Za-z0-9_-]{16,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AIza[0-9A-Za-z_-]{20,}"
)


def redact(text: str) -> str:
    for name in SECRET_ENV:
        value = os.environ.get(name, "").strip()
        if len(value) >= 8:
            text = text.replace(value, HIDDEN)
    return _SHAPES.sub(HIDDEN, text)
