"""Section 5.4 — fuzzy member matching.

Matches a name parsed from a transaction against the known member roster.
Confident matches (score >= threshold) are safe to auto-link. Below-threshold
matches are never silently guessed — they're returned with a candidate so the
caller can write them to `payments` flagged for manual review, but they must
never be auto-committed as confirmed dues. Below MATCH_FLOOR, the best guess
is judged too implausible to even suggest — that's treated as no match at all,
so the pipeline never invents a member link out of a handful of shared letters.
"""
from dataclasses import dataclass

from thefuzz import fuzz

from dues_automation.config import FUZZY_MATCH_THRESHOLD

MATCH_FLOOR = 40


@dataclass
class MatchResult:
    member_id: str | None  # the matched member's ut_id
    matched_name: str | None
    confidence: float       # 0.0-1.0
    is_confident: bool      # True if confidence >= threshold, safe to auto-link
    has_candidate: bool     # True if any plausible (even if low-confidence) candidate exists


def find_best_match(
    name: str | None,
    members: list[dict],
    threshold: int = FUZZY_MATCH_THRESHOLD,
    floor: int = MATCH_FLOOR,
) -> MatchResult:
    if not name or not members:
        return MatchResult(member_id=None, matched_name=None, confidence=0.0, is_confident=False, has_candidate=False)

    best_member = None
    best_score = -1
    for member in members:
        score = fuzz.token_sort_ratio(name, member["full_name"])
        if score > best_score:
            best_score = score
            best_member = member

    confidence = best_score / 100.0

    if best_score < floor:
        return MatchResult(member_id=None, matched_name=None, confidence=confidence, is_confident=False, has_candidate=False)

    is_confident = best_score >= threshold
    return MatchResult(
        member_id=best_member["ut_id"],
        matched_name=best_member["full_name"],
        confidence=confidence,
        is_confident=is_confident,
        has_candidate=True,
    )
