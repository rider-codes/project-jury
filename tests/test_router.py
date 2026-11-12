from jury.room.router import Caps, decide

ROOM = ["senior_engineer", "product_manager", "ux_designer", "general_user"]
AGREE = {p: "unsure" for p in ROOM}


def turn(speaker, challenges=(), new_point=True, stance_changed=False, open_question=None):
    return {"speaker": speaker, "challenges": list(challenges), "new_point": new_point,
            "stance_changed": stance_changed, "open_question": open_question}


def test_first_speaker_is_the_most_disputed_stance():
    stances = {**AGREE, "ux_designer": "useful"}  # the only one who disagrees
    d = decide(ROOM, stances, [], set())
    assert (d.action, d.speaker) == ("speak", "ux_designer")
    assert "disputed by 3" in d.reason


def test_no_dispute_falls_back_to_room_order():
    assert decide(ROOM, AGREE, [], set()).speaker == "senior_engineer"


def test_most_challenged_speaks_next():
    turns = [turn("senior_engineer", ["product_manager"]), turn("ux_designer", ["product_manager", "general_user"])]
    d = decide(ROOM, AGREE, turns, set())
    assert d.speaker == "product_manager" and "2 challenges" in d.reason


def test_challenges_reset_once_the_persona_answers():
    turns = [turn("senior_engineer", ["product_manager"]), turn("product_manager", ["general_user"])]
    assert decide(ROOM, AGREE, turns, set()).speaker == "general_user"


def test_last_speaker_never_speaks_twice_in_a_row():
    turns = [turn("ux_designer", ["ux_designer"])]  # self-challenge does not count either
    assert decide(ROOM, AGREE, turns, set()).speaker != "ux_designer"


def test_everyone_speaks_once_before_anyone_speaks_twice():
    turns = [turn("senior_engineer", ["ux_designer"]), turn("ux_designer", ["senior_engineer"])]
    # senior engineer is the most challenged, but product manager and general user are unheard
    assert decide(ROOM, AGREE, turns, set()).speaker in {"product_manager", "general_user"}
    turns += [turn("product_manager"), turn("general_user")]
    assert decide(ROOM, AGREE, turns, set()).speaker == "senior_engineer"  # now challenges count


def test_ends_when_only_last_speaker_has_turns_left():
    room, stances = ["a", "b"], {"a": "unsure", "b": "unsure"}
    # b is at its cap, a has one turn left and did not just speak -> a
    assert decide(room, stances, [turn("a"), turn("b"), turn("b")], set()).speaker == "a"
    # b is at its cap and a just spoke -> a would answer itself, so end
    d = decide(room, stances, [turn("b"), turn("b"), turn("a")], set())
    assert d.action == "end" and "only the last speaker" in d.reason


def test_open_question_routes_to_user_once():
    turns = [turn("senior_engineer", open_question="Is the data real?")]
    d = decide(ROOM, AGREE, turns, set())
    assert (d.action, d.speaker) == ("ask_user", "senior_engineer")
    assert decide(ROOM, AGREE, turns, {0}).action == "speak"  # already asked


def test_debate_questions_are_capped():
    turns = [turn("senior_engineer"), turn("product_manager", open_question="Is it deployed anywhere?")]
    assert decide(ROOM, AGREE, turns, {0}).action == "ask_user"  # 1 asked so far
    assert decide(ROOM, AGREE, turns, {0, 5}).action == "speak"  # 2 asked: cap reached


def test_question_already_asked_is_not_asked_again():
    turns = [turn("general_user", open_question="Who did you build this for?")]
    asked = ["Who is this built for, and what problem does it solve?"]
    assert decide(ROOM, AGREE, turns, set(), asked_texts=asked).action == "speak"
    # seen in the real run: a narrower re-ask of an earlier question
    turns = [turn("product_manager", open_question="Is tasklite actually published on PyPI?")]
    asked = ["Is `tasklite` actually published on PyPI, or must a first-run user clone and install from this repo?"]
    assert decide(ROOM, AGREE, turns, set(), asked_texts=asked).action == "speak"
    assert decide(ROOM, AGREE, turns, set(), asked_texts=["Which license applies?"]).action == "ask_user"


def test_open_question_beats_the_cap():
    turns = [turn(p) for p in ROOM * 2]
    turns[-1]["open_question"] = "Is it deployed?"
    assert decide(ROOM, AGREE, turns, set()).action == "ask_user"


def test_total_cap_ends_debate():
    caps = Caps(per_agent=3, max_total=5)
    turns = [turn(p) for p in (ROOM + ROOM)[:5]]
    d = decide(ROOM, AGREE, turns, set(), caps=caps)
    assert d.action == "end" and "turn cap reached (5" in d.reason


def test_default_cap_is_two_per_agent_and_at_most_twelve():
    assert Caps().total_for(4) == 8
    assert Caps().total_for(6) == 12
    assert Caps().total_for(8) == 12


def test_per_agent_cap_skips_speakers_who_are_done():
    turns = [turn("senior_engineer"), turn("product_manager", ["senior_engineer"]), turn("senior_engineer"),
             turn("ux_designer", ["senior_engineer"])]
    assert decide(ROOM, AGREE, turns, set()).speaker != "senior_engineer"


def test_stale_full_round_ends_debate():
    turns = [turn("senior_engineer")] + [turn(p, new_point=False) for p in ROOM]
    d = decide(ROOM, AGREE, turns, set())
    assert d.action == "end" and "no new points" in d.reason


def test_stance_change_keeps_debate_alive():
    turns = [turn(p, new_point=False) for p in ROOM]
    turns[2]["stance_changed"] = True
    assert decide(ROOM, AGREE, turns, set()).action == "speak"


def test_user_message_picks_the_addressed_persona():
    turns = [turn("senior_engineer", ["product_manager"])]
    d = decide(ROOM, AGREE, turns, set(), {"to": "general_user", "text": "hi"})
    assert (d.speaker, d.reason) == ("general_user", "the user addressed them")


def test_user_message_to_everyone_uses_normal_rules():
    turns = [turn("senior_engineer", ["product_manager"])]
    assert decide(ROOM, AGREE, turns, set(), {"to": "everyone", "text": "hi"}).speaker == "product_manager"


def test_user_message_to_persona_without_turns_left_is_not_forced():
    turns = [turn("general_user"), turn("senior_engineer"), turn("general_user")]
    d = decide(ROOM, AGREE, turns, set(), {"to": "general_user", "text": "hi"})
    assert d.speaker != "general_user"


def test_low_budget_ends_debate_before_anything_else():
    turns = [turn("senior_engineer", open_question="Is it deployed?")]
    d = decide(ROOM, AGREE, turns, set(), budget_ok=False)
    assert d.action == "end" and "budget" in d.reason


def test_budget_reserve_counts_verdicts_and_summary():
    from jury.llm import Budget
    from jury.room.router import reserve_ok

    class M:
        budget = Budget(max_calls=60, max_tokens=500_000)

    m = M()
    m.budget.calls, m.budget.tokens = 11, 11 * 45_000  # the ledgerline run: ~45k tokens a call
    assert not reserve_ok(m, 4)  # 6 more calls would not fit
    m.budget.max_tokens = 1_200_000
    assert reserve_ok(m, 4)
    m.budget.calls, m.budget.tokens = 0, 0
    assert reserve_ok(m, 4)  # no history yet: nothing to estimate from
    assert reserve_ok(object(), 4)  # models without a budget are never blocked


def test_empty_room_ends():
    assert decide([], {}, [], set()).action == "end"


def test_every_run_ends_within_the_cap():
    """Simulate the router with agents that always make new points and challenge each other."""
    for n in range(1, 7):
        room = ROOM[:n] if n <= 4 else ROOM + ["hiring_manager", "open_source_maintainer"][: n - 4]
        turns: list[dict] = []
        for _ in range(100):
            d = decide(room, AGREE, turns, set())
            if d.action == "end":
                break
            others = [p for p in room if p != d.speaker]
            turns.append(turn(d.speaker, others[:1]))
        assert d.action == "end"
        assert len(turns) <= Caps().total_for(n)
