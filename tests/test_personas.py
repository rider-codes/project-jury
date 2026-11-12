from jury.agent import system_message
from jury.personas import PERSONA_DIR, load_all

EXPECTED = {
    "senior_engineer",
    "product_manager",
    "ux_designer",
    "general_user",
    "hiring_manager",
    "open_source_maintainer",
}


def test_all_six_personas_load():
    personas = load_all()
    assert set(personas) == EXPECTED


def test_ids_match_filenames():
    for stem, p in load_all().items():
        assert p.id == stem


def test_senior_engineer_is_mid_tier_and_checks_secrets():
    p = load_all()["senior_engineer"]
    assert p.model.value == "mid"
    text = " ".join(f"{r.check} {r.fail_when}" for r in p.rubric).lower()
    assert ".env" in text or "secret" in text or "key" in text


def test_others_are_cheap_tier():
    for pid, p in load_all().items():
        if pid != "senior_engineer":
            assert p.model.value == "cheap", pid


def test_rubric_sizes_and_prompt_builds():
    for p in load_all().values():
        assert 5 <= len(p.rubric) <= 7, p.id
        assert 3 <= len(p.question_triggers) <= 5, p.id
        msg = system_message(p)
        assert p.verdict_question not in ("",) and "Rules you always follow" in msg


def test_persona_dir_has_no_security_reviewer():
    assert not (PERSONA_DIR / "security_reviewer.yaml").exists()
