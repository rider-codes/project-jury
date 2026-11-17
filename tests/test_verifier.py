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


def test_quotes_survive_harmless_rewrites():
    b = BRIEF.model_copy(update={"files": {**BRIEF.files,
        "README.md": "**Live demo**: it's “fast” — run `npm start` then open the app.\n"}})
    for q in ["Live demo: it's \"fast\" - run npm start", "it’s “fast” — run `npm start`",
              "Live demo ... open the app", "Live demo…open the app", "\"run npm start then open\""]:
        assert check_claim(claim("file", "README.md", q), b).ok, q


def test_loose_matching_still_rejects_invented_text():
    b = BRIEF.model_copy(update={"files": {**BRIEF.files, "README.md": "Live demo: run npm start then open the app.\n"}})
    for q in ["Live demo: run yarn start", "open the app ... Live demo", "Live demo ... fully tested", "... ..."]:
        assert not check_claim(claim("file", "README.md", q), b).ok, q


def test_tree_evidence_present_and_absent():
    b = BRIEF.model_copy(update={"tree": ["README.md", "requirements.txt", ".github/workflows/tests.yml", "app/main.py"]})
    assert check_claim(claim("tree", "present", ".github/workflows/tests.yml"), b).ok
    assert check_claim(claim("tree", "absent", "poetry.lock"), b).ok  # the TaskWrite 'no lockfile' claim
    assert not check_claim(claim("tree", "absent", "requirements.txt"), b).ok
    assert not check_claim(claim("tree", "present", "Dockerfile"), b).ok
    assert not check_claim(claim("tree", "maybe", "Dockerfile"), b).ok
    cut = b.model_copy(update={"notes": ["file tree cut to 2000 of 5000 paths"]})
    r = check_claim(claim("tree", "absent", "poetry.lock"), cut)
    assert not r.ok and "cut" in r.problem


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


def test_builder_answer_can_be_cited_by_question_id():
    answers = {"q2": "It is for people who live in the terminal. About 40 people use it weekly."}
    assert check_claim(claim("answer", "q2", "About 40 people use it weekly"), BRIEF, answers).ok
    assert check_claim(claim("answer", "[Q2]", "live in the terminal"), BRIEF, answers).ok
    invented = check_claim(claim("answer", "q2", "thousands of users"), BRIEF, answers)
    assert not invented.ok and "quote not found" in invented.problem


def test_answer_evidence_needs_an_actual_answer():
    skipped = check_claim(claim("answer", "q1", "anything at all"), BRIEF, {"q2": "an answer"})
    assert not skipped.ok and "no answer" in skipped.problem
    assert not check_claim(claim("answer", "q2", "an answer"), BRIEF).ok  # round 1: nothing was asked yet



def test_tree_claims_fail_when_there_is_no_repo():
    """A site-only review has an empty tree; "this file is missing" must not pass by default."""
    from jury.models import Brief, Claim, Evidence
    from jury.verifier import verify_claims
    brief = Brief(project_name="site", repo_url="https://example.com", summary="s", files={}, tree=[])
    claim = Claim(text="There are no tests.", evidence=Evidence(kind="tree", ref="absent", quote="tests/"))
    kept, rejected = verify_claims([claim], brief)
    assert not kept and "no repository" in rejected[0].problem
