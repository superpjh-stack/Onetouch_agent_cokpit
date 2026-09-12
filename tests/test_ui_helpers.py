from onetouch_agent import OnetouchRepository, QUESTION_GROUPS, quote_snapshot, risk_label, user_question_history


def test_cockpit_helpers(tmp_path):
    repo = OnetouchRepository(tmp_path / "demo.db")
    stable = quote_snapshot(repo, "QT-260904-001")
    manual = quote_snapshot(repo, "QT-260904-003")
    assert risk_label(stable) == ("안정", "🟢")
    assert risk_label(manual) == ("높음", "🔴")
    assert set(QUESTION_GROUPS) == {"견적 DB", "지식문서", "판정 규칙"}
    assert all(len(questions) == 10 for questions in QUESTION_GROUPS.values())
    assert user_question_history([{"role": "user", "content": "견적", "created_at": "10:00"}]) == [{"content": "견적", "created_at": "10:00"}]
