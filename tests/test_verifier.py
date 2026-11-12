import json
from pathlib import Path

from jury.models import Brief, Claim, Evidence, Verdict
from jury.verifier import check_claim, verify

BRIEF = Brief.model_validate(
    json.loads((Path(__file__).parent.parent / "examples" / "sample_brief.json").read_text(encoding="utf-8"))
)


def claim(kind, ref, quote):
    return Claim(text="x", evidence=Evidence(kind=kind, ref=ref, quote=quote))


def test_file_quote_found():
    assert check_claim(claim("file", "tasklite/cli.py", "DB.write_text(json.dumps(tasks))"), BRIEF).ok


def test_quote_whitespace_and_case_insensitive():
    assert check_claim(claim("file", "README.md", "a TINY   to-do list"), BRIEF).ok


def test_leading_dot_slash_path_accepted():
    assert check_claim(claim("file", "./README.md", "tiny to-do list"), BRIEF).ok


def test_dotfiles_can_be_cited():
    """Regression: lstrip('./') turned .env.example into env.example, so dotfiles always failed."""
    assert check_claim(claim("file", ".env.example", "no settings needed"), BRIEF).ok
    assert check_claim(claim("file", "./.env.example", "no settings needed"), BRIEF).ok
    b = BRIEF.model_copy(update={"files": {**BRIEF.files, ".github/workflows/tests.yml": "run: pytest -q\n",
                                           "requirements.txt": "﻿fastapi>=0.115\nuvicorn>=0.30\n"}})
    assert check_claim(claim("file", ".github/workflows/tests.yml", "run: pytest -q"), b).ok
    # a byte-order mark at the start of a file must not break the first line's quote
    assert check_claim(claim("file", "requirements.txt", "fastapi>=0.115 uvicorn>=0.30"), b).ok


def test_missing_file_rejected():
    c = check_claim(claim("file", "src/app.py", "anything here"), BRIEF)
    assert not c.ok and "file not in brief" in c.problem


def test_invented_quote_rejected():
    c = check_claim(claim("file", "README.md", "fully tested with 95% coverage"), BRIEF)
    assert not c.ok and "quote not found" in c.problem


def test_demo_quote_found():
    assert check_claim(claim("demo", "step-3", "crashes with IndexError"), BRIEF).ok


def test_unknown_demo_step_rejected():
    assert not check_claim(claim("demo", "step-9", "crashes"), BRIEF).ok


def test_short_quote_rejected():
    assert not check_claim(claim("file", "README.md", "a"), BRIEF).ok


def test_duplicate_evidence_kept_once():
    from jury.verifier import verify_claims

    same = [claim("file", "README.md", "tiny to-do list"), claim("file", "./README.md", "Tiny  to-do list")]
    kept, rejected = verify_claims(same, BRIEF)
    assert len(kept) == 1 and rejected == []


def test_verify_keeps_only_passing_claims():
    v = Verdict(
        verdict="unsure",
        headline="h",
        reasons=[
            claim("file", "README.md", "tiny to-do list"),
            claim("file", "README.md", "made up text"),
        ],
        what_would_change_my_mind=[],
    )
    out = verify("senior_engineer", v, BRIEF)
    assert len(out.verdict.reasons) == 1
    assert len(out.rejected) == 1
