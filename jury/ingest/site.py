"""Capture a project's live site with a headless browser.

Public pages only: no logins, no clicks on forms, no submits. The home page plus up to
`max_pages - 1` same-origin pages one click deep, each at desktop and phone width. For each
view: a first-screen screenshot and the visible text, headings, buttons and links. Page text
is data for the reviewers, never instructions.
"""

import ipaddress
import re
import socket
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit, urlunsplit

from jury.models import SiteView

VIEWPORTS = {"desktop": (1280, 800, 1), "phone": (390, 844, 2)}  # width, height, scale
FIRST_TIMEOUT_MS = 30_000
WAKE_SECONDS = 90  # free hosts (Render) answer 502/503 with a "loading" page for up to ~60 s
PAGE_TIMEOUT_MS = 20_000
SETTLE_MS = 4_000  # wait this long at most for the network to go quiet
MAX_TEXT_CHARS = 2_500
MAX_ITEMS = 25
# never follow links that sign in, sign out, buy, delete or download
_SKIP_WORDS = re.compile(r"log-?in|log-?out|sign-?in|sign-?out|sign-?up|register|auth|account|cart|checkout|"
                         r"delete|remove|unsubscribe|admin|oauth", re.I)
_SKIP_EXT = re.compile(r"\.(pdf|zip|gz|tar|png|jpe?g|gif|svg|webp|mp4|mp3|dmg|exe|csv|xlsx?|docx?)$", re.I)


class SiteError(RuntimeError):
    pass


@dataclass
class Shot:
    view: SiteView
    image: bytes  # JPEG of the first screen


@dataclass
class SiteCapture:
    url: str
    shots: list[Shot] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def normalize_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parts = urlsplit(url)
    if not parts.hostname:
        raise SiteError(f"not a web address: {url}")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


def check_public(url: str) -> None:
    """Refuse private, loopback and link-local hosts, so a public deployment cannot be
    pointed at its own network."""
    host = urlsplit(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise SiteError(f"cannot find {host}: {e}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise SiteError(f"{host} is not a public address")


def pick_links(base_url: str, hrefs: list[str], limit: int) -> list[str]:
    """Same-origin pages one click deep, in page order, skipping the page itself,
    sign-in and similar pages, and files."""
    base = urlsplit(base_url)
    seen = {base.path.rstrip("/") or "/"}
    out = []
    for href in hrefs:
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        u = urlsplit(urljoin(base_url, href))
        if u.scheme not in ("http", "https") or u.netloc.lower() != base.netloc.lower():
            continue
        path = u.path.rstrip("/") or "/"
        if path in seen or _SKIP_WORDS.search(path) or _SKIP_EXT.search(path):
            continue
        seen.add(path)
        out.append(urlunsplit((u.scheme, u.netloc, u.path or "/", u.query, "")))
        if len(out) == limit:
            break
    return out


# Runs in the page. Reads only what a visitor can see.
_EXTRACT_JS = """
() => {
  const vis = (el) => {
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const txt = (el) => (el.innerText || el.value || el.getAttribute('aria-label') || el.title || '').replace(/\\s+/g, ' ').trim();
  const all = (sel) => Array.from(document.querySelectorAll(sel)).filter(vis);
  const imgs = all('img');
  const inputs = all('input:not([type=hidden]):not([type=submit]):not([type=button]), textarea, select');
  const labelled = (el) => el.labels?.length || el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.placeholder;
  return {
    title: document.title || '',
    headings: all('h1, h2, h3').map((h) => h.tagName.toLowerCase() + ': ' + txt(h)).filter((h) => h.length > 4),
    buttons: all('button, [role=button], input[type=submit], input[type=button]').map(txt).filter(Boolean),
    links: all('a[href]').map((a) => ({ text: txt(a), href: a.getAttribute('href') })),
    text: (document.body?.innerText || '').replace(/[ \\t]+/g, ' ').replace(/\\n\\s*\\n+/g, '\\n').trim(),
    scroll_width: document.documentElement.scrollWidth,
    inner_width: document.documentElement.clientWidth || window.innerWidth,
    viewport_meta: !!document.querySelector('meta[name=viewport]'),
    images: imgs.length,
    images_no_alt: imgs.filter((i) => !i.hasAttribute('alt')).length,
    inputs: inputs.length,
    inputs_no_label: inputs.filter((i) => !labelled(i)).length,
  };
}
"""


def _uniq(items: list[str], limit: int = MAX_ITEMS) -> list[str]:
    return list(dict.fromkeys(i[:120] for i in items if i))[:limit]


def to_view(ref: str, url: str, width: str, raw: dict) -> SiteView:
    """Turn what the page script read into a SiteView. Plain code, testable without a browser."""
    facts = []
    if width == "phone" and raw.get("viewport_meta") is False:
        facts.append("the page has no mobile viewport tag, so a phone shows the desktop layout "
                     f"shrunk to fit ({raw.get('inner_width')}px wide), with small text")
    if raw.get("scroll_width", 0) > raw.get("inner_width", 0) + 2:
        facts.append(f"the page is wider than the window: {raw['scroll_width']}px of content "
                     f"in a {raw['inner_width']}px window, so it scrolls sideways")
    if raw.get("images_no_alt"):
        facts.append(f"{raw['images_no_alt']} of {raw['images']} visible images have no alt text")
    if raw.get("inputs_no_label"):
        facts.append(f"{raw['inputs_no_label']} of {raw['inputs']} visible form fields have no label")
    if not raw.get("text", "").strip():
        facts.append("the page shows no text")
    links = [f"{l['text'] or '(no text)'} -> {l['href']}" for l in raw.get("links", []) if l.get("href")]
    return SiteView(
        ref=ref, url=url, width=width, title=raw.get("title", "")[:200],
        headings=_uniq(raw.get("headings", [])), buttons=_uniq(raw.get("buttons", [])),
        links=_uniq(links), facts=facts, text=raw.get("text", "")[:MAX_TEXT_CHARS],
    )


def wake(url: str, deadline_s: float = WAKE_SECONDS, wait_s: float = 5.0, get=None) -> None:
    """Wait until the site stops answering 502/503/504, so the capture does not photograph a
    host's "application loading" page. Plain HTTP GETs, no browser."""
    import httpx
    get = get or (lambda u: httpx.get(u, timeout=30, follow_redirects=True).status_code)
    end = time.monotonic() + deadline_s
    while True:
        try:
            status = get(url)
        except Exception:
            status = 503  # connection refused or reset while the host starts
        if status not in (502, 503, 504):
            return
        if time.monotonic() + wait_s > end:
            raise SiteError(f"{url} was still starting up (HTTP {status}) after {deadline_s:.0f} s")
        time.sleep(wait_s)


def _settle(page) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=SETTLE_MS)
    except Exception:
        pass  # pages that poll never go quiet; what is drawn by now is what a visitor sees


def capture_site(url: str, max_pages: int = 4, allow_private: bool = False) -> SiteCapture:
    """Synchronous on purpose: ingestion runs in a worker thread."""
    from playwright.sync_api import Error as PWError
    from playwright.sync_api import sync_playwright

    url = normalize_url(url)
    if not allow_private:
        check_public(url)
    cap = SiteCapture(url=url)
    wake(url)
    with sync_playwright() as pw:
        try:
            # Docker gives /dev/shm only 64 MB, which crashes Chromium; small hosts also have little RAM
            browser = pw.chromium.launch(args=["--disable-dev-shm-usage", "--disable-gpu", "--no-zygote"])
        except PWError as e:
            raise SiteError(f"no headless browser: run `uv run python -m playwright install chromium` ({e})") from e
        try:
            pages = [url]
            for n in range(1, max_pages + 1):
                if n > len(pages):
                    break
                for width, (w, h, scale) in VIEWPORTS.items():
                    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=scale,
                                              is_mobile=width == "phone", has_touch=width == "phone",
                                              accept_downloads=False, java_script_enabled=True)
                    page = ctx.new_page()
                    try:
                        first = n == 1 and width == "desktop"
                        resp = page.goto(pages[n - 1], wait_until="load",
                                         timeout=FIRST_TIMEOUT_MS if first else PAGE_TIMEOUT_MS)
                        _settle(page)
                        if resp is not None and resp.status >= 400:
                            cap.notes.append(f"site page {pages[n - 1]} answered HTTP {resp.status}")
                        if first and urlsplit(page.url).netloc != urlsplit(url).netloc:
                            cap.notes.append(f"the site redirected to another host: {page.url}")
                        raw = page.evaluate(_EXTRACT_JS)
                        view = to_view(f"page-{n}-{width}", page.url, width, raw)
                        image = page.screenshot(type="jpeg", quality=70, full_page=False)
                        cap.shots.append(Shot(view=view, image=image))
                        if first:
                            pages += pick_links(page.url, [l["href"] for l in raw.get("links", [])], max_pages - 1)
                    except PWError as e:
                        if n == 1 and width == "desktop":
                            raise SiteError(f"could not open {url}: {str(e).splitlines()[0]}") from e
                        cap.notes.append(f"site page {pages[n - 1]} at {width} width failed to load")
                    finally:
                        ctx.close()
        finally:
            browser.close()
    if len(pages) == 1:
        cap.notes.append("the site's first page has no same-origin links, so only it was captured")
    _drop_repeated_phone_text(cap)
    return cap


def _drop_repeated_phone_text(cap: SiteCapture) -> None:
    """A phone view whose text matches the desktop view only repeats it in the brief."""
    desktop = {s.view.ref.rsplit("-", 1)[0]: s.view.text for s in cap.shots if s.view.width == "desktop"}
    for s in cap.shots:
        if s.view.width == "phone" and s.view.text == desktop.get(s.view.ref.rsplit("-", 1)[0]):
            s.view.text = ""
