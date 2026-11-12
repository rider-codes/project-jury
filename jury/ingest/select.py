"""Pick the files that go into the brief, under hard caps, with secrets redacted."""

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "out", "target", ".next",
    "__pycache__", ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache",
    "coverage", ".idea", ".vscode", "site-packages", "bower_components",
}
LOCKFILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock",
    "Cargo.lock", "go.sum", "Gemfile.lock", "composer.lock", "Pipfile.lock",
}
MANIFESTS = {
    "package.json", "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg",
    "go.mod", "Cargo.toml", "Gemfile", "pom.xml", "build.gradle", "composer.json",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "Makefile",
    ".env.example", ".env.sample", ".gitignore", "tsconfig.json",
}
DOC_PREFIXES = ("readme", "contributing", "license", "code_of_conduct", "security")
# Long files with little review value: kept, but only their opening.
SHORT_PREFIXES = ("changelog", "changes", "history", "license", "code_of_conduct")
SHORT_FILE_CHARS = 1_500
ENTRY_STEMS = {"main", "app", "index", "server", "cli", "__main__", "manage", "lib", "mod"}
SOURCE_EXT = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".rb", ".php",
    ".cs", ".c", ".cpp", ".h", ".swift", ".vue", ".svelte", ".sh", ".sql",
}
TEXT_EXT = SOURCE_EXT | {".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".cfg", ".ini", ".rst", ".html", ".css",
                         ".jinja", ".j2", ".hbs", ".ejs"}

# Folders that hold the product itself, versus folders that hold tooling around it.
# Ranking by role stops e.g. eval/ scripts crowding out the app's own code and UI.
APP_DIRS = {
    "src", "app", "apps", "server", "backend", "frontend", "api", "lib", "pkg", "internal", "cmd",
    "web", "client", "routes", "components", "pages", "public", "static", "templates", "views", "ui",
}
TOOLING_DIRS = {
    "eval", "evals", "scripts", "script", "tools", "tooling", "mockups", "mocks", "docs", "doc",
    "bench", "benchmarks", "notebooks", "migrations", "samples", "sample", "data", "datasets",
}  # not "assets": web apps keep their own JS there (public/assets/)
UI_EXT = {".html", ".tsx", ".jsx", ".vue", ".svelte", ".jinja", ".j2", ".hbs", ".ejs"}
UI_DIRS = {"public", "pages", "components", "templates", "views", "ui", "frontend", "client", "web", "static"}

# Real-looking secrets are replaced before anything goes to a model provider.
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
]


@dataclass
class Caps:
    max_files: int = 40
    max_file_chars: int = 12_000
    max_total_chars: int = 120_000
    max_tree_paths: int = 2_000
    reserved_test_files: int = 3
    reserved_ui_files: int = 3


@dataclass
class Selection:
    files: dict[str, str] = field(default_factory=dict)
    tree: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _is_test(path: str) -> bool:
    return any(k in part.lower() for part in PurePosixPath(path).parts for k in ("test", "spec", "fixture", "example"))


def _role(path: str) -> str:
    """app | tooling | other, from the folders the file sits in."""
    dirs = [d.lower() for d in PurePosixPath(path).parts[:-1]]
    if any(d in TOOLING_DIRS for d in dirs):
        return "tooling"
    if any(d in APP_DIRS for d in dirs):
        return "app"
    return "other"


def _is_ui(path: str) -> bool:
    p = PurePosixPath(path)
    if _is_test(path) or _role(path) == "tooling":
        return False
    return p.suffix in UI_EXT or (p.suffix in SOURCE_EXT and any(d.lower() in UI_DIRS for d in p.parts[:-1]))


def is_skipped(path: str) -> bool:
    return any(part in SKIP_DIRS for part in PurePosixPath(path).parts[:-1])


def priority(path: str) -> int | None:
    """Lower is more important. None means never include the content."""
    p = PurePosixPath(path)
    name, lower = p.name, p.name.lower()
    depth = len(p.parts) - 1
    if name in LOCKFILES or is_skipped(path):
        return None
    if lower.startswith("readme") and depth == 0:
        return 0
    if name in MANIFESTS and depth == 0:
        return 1
    if path.startswith(".github/workflows/") or name in {".gitlab-ci.yml", ".travis.yml"}:
        return 2
    if lower.startswith(("changelog", "changes", "history")):
        return 13 + depth
    if lower.startswith(DOC_PREFIXES) and depth <= 1:
        return 3
    if p.suffix not in TEXT_EXT and name not in MANIFESTS:
        return None
    is_test = _is_test(path)
    role = _role(path)
    # depth inside the app's own folder counts from that folder, so src/x.py ranks like x.py
    app_depth = max(depth - 1, 0) if role == "app" else depth
    if not is_test and role != "tooling" and p.stem.lower() in ENTRY_STEMS and p.suffix in SOURCE_EXT and depth <= 2:
        return 4
    if p.suffix in SOURCE_EXT:
        if is_test:
            return 9 + depth
        if role == "tooling":
            return 12 + depth
        return 5 + app_depth
    if p.suffix in UI_EXT and role != "tooling":
        return 8 + app_depth
    if p.suffix in {".md", ".rst"} and depth <= 2:
        return 14 + depth
    return 20 + depth


def decode_text(raw: bytes) -> str | None:
    if b"\x00" in raw[:2048]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def redact(text: str) -> tuple[str, int]:
    count = 0
    for pat in SECRET_PATTERNS:
        text, n = pat.subn(lambda m: f"[REDACTED_SECRET:{m.group(0)[:4]}]", text)
        count += n
    return text, count


def select_files(paths: list[str], contents: dict[str, bytes], caps: Caps = Caps()) -> Selection:
    sel = Selection()
    visible = [p for p in paths if not is_skipped(p)]
    sel.tree = visible[: caps.max_tree_paths]
    if len(visible) > caps.max_tree_paths:
        sel.notes.append(f"file tree cut to {caps.max_tree_paths} of {len(visible)} paths")

    ranked = sorted(
        (pr, p) for p in visible if p in contents and (pr := priority(p)) is not None
    )
    # Reserve early slots for a few test files and UI files, so the Senior engineer can
    # always judge tests and the UX designer can always see some of the interface.
    tests = set([r for r in ranked if _is_test(r[1])][: caps.reserved_test_files])
    # pages and components first (what a user sees), then UI scripts
    first_screens = {"index", "landing", "home", "login", "signin", "app", "main"}
    ui_ranked = sorted((r for r in ranked if _is_ui(r[1])),
                       key=lambda r: (PurePosixPath(r[1]).suffix not in UI_EXT,
                                      PurePosixPath(r[1]).stem.lower() not in first_screens, r[0], r[1]))
    ui = set(ui_ranked[: caps.reserved_ui_files])
    ranked = sorted(
        (4.5 if r in tests else 4.6 if r in ui else r[0], r[1]) for r in ranked
    )
    total, redacted, truncated, skipped_for_cap = 0, 0, 0, 0
    for _, path in ranked:
        if len(sel.files) >= caps.max_files or total >= caps.max_total_chars:
            skipped_for_cap += 1
            continue
        text = decode_text(contents[path])
        if text is None or not text.strip():
            continue
        text, n = redact(text)
        redacted += n
        per_file = SHORT_FILE_CHARS if PurePosixPath(path).name.lower().startswith(SHORT_PREFIXES) else caps.max_file_chars
        room = min(per_file, caps.max_total_chars - total)
        if len(text) > room:
            text = text[:room] + "\n[... truncated by ingestion ...]"
            truncated += 1
        sel.files[path] = text
        total += len(text)

    if skipped_for_cap:
        sel.notes.append(f"{skipped_for_cap} more files exist but were left out by the size caps; see tree")
    if truncated:
        sel.notes.append(f"{truncated} file(s) truncated to fit the caps")
    if redacted:
        sel.notes.append(f"{redacted} real-looking secret(s) redacted as [REDACTED_SECRET:...]")
    return sel
