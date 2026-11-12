import io
import tarfile

import pytest

from jury.ingest.brief import assemble
from jury.ingest.demo import parse_walkthrough
from jury.ingest.github import IngestError, RepoMeta, parse_repo_url, read_tarball
from jury.ingest.select import Caps, priority, redact, select_files
from jury.verifier import check_claim
from jury.models import Claim, Evidence


def make_tarball(files: dict[str, bytes], top="owner-repo-abc123") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path, data in files.items():
            info = tarfile.TarInfo(f"{top}/{path}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo(f"{top}/evil-link")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        tar.addfile(link)
    return buf.getvalue()


REPO = {
    "README.md": b"# demo\n\n[![badge](x)](y)\n\nA tool that does a thing.\n",
    "pyproject.toml": b"[project]\nname='demo'\n",
    "uv.lock": b"lock content",
    "src/demo/main.py": b"def main():\n    print('hi')\n",
    "src/demo/util.py": b"x = 1\n",
    "tests/test_main.py": b"def test_x():\n    assert 1\n",
    "node_modules/pkg/index.js": b"junk",
    "assets/logo.png": b"\x89PNG\x00\x00binary",
    ".github/workflows/ci.yml": b"on: push\njobs: {}\n",
    "config.py": b"API_KEY = 'sk-abcdefghijklmnopqrstuvwxyz123456'\n",
}


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/pallets/flask", ("pallets", "flask", None)),
        ("github.com/pallets/flask.git", ("pallets", "flask", None)),
        ("https://github.com/pallets/flask/tree/stable", ("pallets", "flask", "stable")),
        ("https://www.github.com/a-b/c.d/", ("a-b", "c.d", None)),
    ],
)
def test_parse_repo_url(url, expected):
    r = parse_repo_url(url)
    assert (r.owner, r.repo, r.ref) == expected


@pytest.mark.parametrize("url", ["https://gitlab.com/a/b", "not a url", "https://github.com/onlyowner"])
def test_parse_repo_url_rejects(url):
    with pytest.raises(IngestError):
        parse_repo_url(url)


def test_read_tarball_strips_top_dir_and_skips_symlinks():
    paths, contents = read_tarball(make_tarball(REPO))
    assert "README.md" in paths and "src/demo/main.py" in paths
    assert "evil-link" not in paths
    assert all(not p.startswith("owner-repo") for p in paths)


def test_priority_order():
    assert priority("README.md") < priority("pyproject.toml") < priority(".github/workflows/ci.yml")
    assert priority("src/demo/main.py") < priority("src/demo/util.py") < priority("tests/test_main.py")
    assert priority("source/core/Ky.ts") < priority("test-d/hooks.ts")
    assert priority("test/helpers/index.ts") > priority("source/index.ts")
    assert priority("uv.lock") is None
    assert priority("node_modules/pkg/index.js") is None
    assert priority("assets/logo.png") is None


def test_select_skips_junk_and_keeps_lockfile_in_tree():
    paths, contents = read_tarball(make_tarball(REPO))
    sel = select_files(paths, contents)
    assert "uv.lock" in sel.tree  # agents can see a lockfile exists
    assert "uv.lock" not in sel.files
    assert not any(p.startswith("node_modules") for p in sel.tree)
    assert "assets/logo.png" not in sel.files
    assert list(sel.files)[0] == "README.md"


def test_secrets_redacted_before_brief():
    text, n = redact("key = 'sk-abcdefghijklmnopqrstuvwxyz123456' and AKIAABCDEFGHIJKLMNOP")
    assert n == 2 and "abcdefghij" not in text and "[REDACTED_SECRET:sk-a]" in text
    paths, contents = read_tarball(make_tarball(REPO))
    sel = select_files(paths, contents)
    assert "sk-abcdefghijklmnop" not in sel.files["config.py"]
    assert any("redacted" in n for n in sel.notes)


def test_caps_enforced():
    big = {f"src/m{i}.py": b"x = 1\n" * 3000 for i in range(30)}
    big["README.md"] = b"# r\n\nIntro.\n"
    paths, contents = read_tarball(make_tarball(big))
    caps = Caps(max_files=10, max_file_chars=5_000, max_total_chars=30_000)
    sel = select_files(paths, contents, caps)
    assert len(sel.files) <= 10
    assert sum(len(t) for t in sel.files.values()) <= 30_000 + 10 * 40  # + truncation markers
    assert all(len(t) <= 5_000 + 40 for t in sel.files.values())
    assert any("left out" in n for n in sel.notes) and any("truncated" in n for n in sel.notes)


def test_test_files_get_reserved_slots():
    files = {f"src/m{i}.py": b"x = 1\n" * 3000 for i in range(30)}
    files["tests/test_a.py"] = b"def test_a():\n    assert m() == 1\n"
    paths, contents = read_tarball(make_tarball(files))
    sel = select_files(paths, contents, Caps(max_files=10))
    assert "tests/test_a.py" in sel.files


def test_changelog_is_short_and_late():
    files = {"README.md": b"# r\n\nIntro.\n", "CHANGELOG.md": b"v1\n" * 5000, "src/main.py": b"x = 1\n"}
    paths, contents = read_tarball(make_tarball(files))
    sel = select_files(paths, contents)
    assert list(sel.files) == ["README.md", "src/main.py", "CHANGELOG.md"]
    assert len(sel.files["CHANGELOG.md"]) < 1_600


def test_summary_skips_setext_heading():
    files = {"README.md": b"tool (t)\n--------\n\ntool searches files fast.\n"}
    paths, contents = read_tarball(make_tarball(files))
    meta = RepoMeta(description="", default_branch="main", private=False)
    brief = assemble(parse_repo_url("https://github.com/o/tool"), meta, paths, contents)
    assert brief.summary == "tool searches files fast."


def test_parse_walkthrough_numbered():
    steps = parse_walkthrough("1. Open the app\n   it loads fast\n2) Click start\nStep 3: Nothing happens")
    assert [s.ref for s in steps] == ["step-1", "step-2", "step-3"]
    assert steps[0].text == "Open the app it loads fast"
    assert steps[2].text == "Nothing happens"


def test_parse_walkthrough_paragraphs():
    steps = parse_walkthrough("I open it.\n\nI click go and\nit crashes.")
    assert [s.text for s in steps] == ["I open it.", "I click go and it crashes."]


def test_assemble_brief_and_claims_verify_against_it():
    paths, contents = read_tarball(make_tarball(REPO))
    meta = RepoMeta(description="Demo repo.", default_branch="main", private=False)
    brief = assemble(parse_repo_url("https://github.com/owner/repo"), meta, paths, contents, "1. Run it\n2. It prints hi")
    assert brief.summary == "Demo repo. A tool that does a thing."
    assert len(brief.demo) == 2
    ok = check_claim(Claim(text="t", evidence=Evidence(kind="file", ref="src/demo/main.py", quote="print('hi')")), brief)
    assert ok.ok


def test_assemble_notes_missing_demo():
    paths, contents = read_tarball(make_tarball(REPO))
    meta = RepoMeta(description="", default_branch="main", private=False)
    brief = assemble(parse_repo_url("https://github.com/owner/repo"), meta, paths, contents)
    assert "no demo walkthrough was given" in brief.notes
