from dues_automation.match import find_best_match

MEMBERS = [
    {"ut_id": "jat1001", "full_name": "Jamie Test"},
    {"ut_id": "sbe2002", "full_name": "Sam Example"},
    {"ut_id": "cxs3003", "full_name": "Casey Sample"},
]


def test_exact_name_is_confident():
    result = find_best_match("Jamie Test", MEMBERS)
    assert result.member_id == "jat1001"
    assert result.is_confident is True


def test_typo_still_matches_confidently():
    result = find_best_match("Jaime Test", MEMBERS)  # transposed letters
    assert result.member_id == "jat1001"
    assert result.is_confident is True


def test_first_name_only_is_candidate_but_not_confident():
    # "Sam" alone shouldn't confidently resolve to "Sam Example" — it should
    # surface as a low-confidence candidate (member_id populated so a human
    # can review the guess) rather than being auto-committed as a real match.
    result = find_best_match("Sam", MEMBERS, threshold=95)
    assert result.has_candidate is True
    assert result.is_confident is False
    assert result.member_id == "sbe2002"  # the best guess, for review — not auto-committed


def test_unrelated_name_has_no_candidate():
    result = find_best_match("Zzyzx Qwerty", MEMBERS, floor=60)
    assert result.has_candidate is False
    assert result.member_id is None


def test_empty_name_returns_no_match():
    result = find_best_match(None, MEMBERS)
    assert result.has_candidate is False
    assert result.is_confident is False


def test_empty_roster_returns_no_match():
    result = find_best_match("Jamie Test", [])
    assert result.has_candidate is False
