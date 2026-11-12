"""Optional access code for a public deployment (JURY_ACCESS_CODE).

When set, every /api route except the few below needs a cookie that /api/login sets
after checking the code. Without it, anyone who finds the URL could spend the
model quota. EventSource sends cookies on the same origin, so the live stream works.
"""

import hashlib
import hmac
import os

from fastapi import Request
from fastapi.responses import JSONResponse

COOKIE = "jury_access"
OPEN_PATHS = {"/api/health", "/api/login", "/api/session"}


def access_code() -> str:
    return os.environ.get("JURY_ACCESS_CODE", "").strip()


def token_for(code: str) -> str:
    return hashlib.sha256(f"project-jury:{code}".encode()).hexdigest()


def has_access(request: Request) -> bool:
    code = access_code()
    if not code:
        return True
    return hmac.compare_digest(request.cookies.get(COOKIE, ""), token_for(code))


async def gate(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in OPEN_PATHS and request.method != "OPTIONS" and not has_access(request):
        return JSONResponse({"detail": "access code required"}, status_code=401)
    return await call_next(request)
