from jury.room.dedupe import dedupe_questions


def test_merges_reworded_duplicates_and_keeps_all_askers():
    out = dedupe_questions([
        ("senior_engineer", "Does the demo run against real data or a fixture?"),
        ("product_manager", "Is the demo using real data or fixture data?"),
        ("ux_designer", "Who is the target user?"),
    ])
    assert len(out) == 2
    assert out[0].asked_by == ["senior_engineer", "product_manager"]
    assert out[0].text == "Does the demo run against real data or a fixture?"  # first wording kept


def test_distinct_questions_stay_separate():
    out = dedupe_questions([
        ("a", "Is there a CI pipeline in another repo?"),
        ("b", "Which license does this use?"),
    ])
    assert len(out) == 2


def test_same_persona_counted_once():
    out = dedupe_questions([("a", "Is the data real?"), ("a", "Is the data real?")])
    assert len(out) == 1 and out[0].asked_by == ["a"]


def test_most_asked_first_and_ids_sequential():
    out = dedupe_questions([
        ("a", "Which license applies?"),
        ("b", "Does deployment exist anywhere?"),
        ("c", "Is the deployment live anywhere?"),
    ])
    assert out[0].text.startswith("Does deployment")
    assert [q.id for q in out] == ["q1", "q2"]


def test_cap_and_blank_questions():
    distinct = [
        "Which license applies?", "Is there a CI pipeline?", "Who is the target user?",
        "Does deployment exist anywhere?", "Are the tests run automatically?", "What problem does it solve?",
        "How long does setup take?", "Is the data real?",
    ]
    asked = [("p", q) for q in distinct] + [("p", "   ")]
    out = dedupe_questions(asked, limit=6)
    assert len(out) == 6


def test_empty():
    assert dedupe_questions([]) == []
