"""Fetch a public GitHub repo as one tarball and read it in memory (never extracted to disk)."""

import io
import re
import tarfile
from dataclasses import dataclass

import httpx

API = "https://api.github.com"
MAX_TARBALL_BYTES = 50 * 1024 * 1024

_URL_RE = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/tree/([^/?#]+))?/?(?:[?#].*)?$")


class IngestError(RuntimeError):
    pass


@dataclass
class RepoRef:
    owner: str
    repo: str
    ref: str | None = None

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}"


@dataclass
class RepoMeta:
    description: str
    default_branch: str
    private: bool


def parse_repo_url(url: str) -> RepoRef:
    m = _URL_RE.match(url.strip())
    if not m:
        raise IngestError(f"not a GitHub repo URL: {url}")
    return RepoRef(owner=m.group(1), repo=m.group(2), ref=m.group(3))


def _headers(token: str | None) -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "project-jury"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _raise_for(resp: httpx.Response, what: str) -> None:
    if resp.status_code == 404:
        raise IngestError(f"{what}: not found (private repos are not supported in v1)")
    if resp.status_code in (403, 429):
        raise IngestError(f"{what}: GitHub rate limit or access denied; set GITHUB_TOKEN")
    if resp.status_code >= 400:
        raise IngestError(f"{what}: HTTP {resp.status_code}")


def fetch_meta(ref: RepoRef, token: str | None, client: httpx.Client) -> RepoMeta:
    resp = client.get(f"{API}/repos/{ref.owner}/{ref.repo}", headers=_headers(token))
    _raise_for(resp, ref.url)
    data = resp.json()
    if data.get("private"):
        raise IngestError("private repos are not supported in v1")
    return RepoMeta(
        description=data.get("description") or "",
        default_branch=data.get("default_branch") or "main",
        private=bool(data.get("private")),
    )


def fetch_tarball(ref: RepoRef, branch: str, token: str | None, client: httpx.Client) -> bytes:
    url = f"{API}/repos/{ref.owner}/{ref.repo}/tarball/{branch}"
    buf = bytearray()
    with client.stream("GET", url, headers=_headers(token), follow_redirects=True) as resp:
        _raise_for(resp, f"{ref.url} tarball")
        for chunk in resp.iter_bytes():
            buf.extend(chunk)
            if len(buf) > MAX_TARBALL_BYTES:
                raise IngestError(f"repo tarball is over {MAX_TARBALL_BYTES // (1024 * 1024)} MB")
    return bytes(buf)


def read_tarball(data: bytes, max_file_bytes: int = 1_000_000) -> tuple[list[str], dict[str, bytes]]:
    """Return (all paths, {path: bytes} for regular files under max_file_bytes).

    GitHub tarballs wrap everything in one top folder; it is stripped. Symlinks and
    other special members are skipped. Nothing is written to disk.
    """
    paths: list[str] = []
    contents: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            parts = member.name.split("/", 1)
            if len(parts) < 2 or not parts[1]:
                continue
            path = parts[1]
            paths.append(path)
            if member.size <= max_file_bytes:
                f = tar.extractfile(member)
                if f is not None:
                    contents[path] = f.read()
    return sorted(paths), contents


def download_repo(url: str, token: str | None = None) -> tuple[RepoRef, RepoMeta, list[str], dict[str, bytes]]:
    ref = parse_repo_url(url)
    with httpx.Client(timeout=60.0) as client:
        meta = fetch_meta(ref, token, client)
        data = fetch_tarball(ref, ref.ref or meta.default_branch, token, client)
    paths, contents = read_tarball(data)
    return ref, meta, paths, contents
