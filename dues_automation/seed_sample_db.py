"""Generate a synthetic member roster for trial/dev use.

Every name, phone number, and email here is randomly generated fictional data —
never run this against a real roster file. Real member data should be loaded
through a separate, gitignored import step once the real roster is ready.

Usage:
    python -m dues_automation.seed_sample_db [--count 40] [--seed 42]
"""
import argparse
import random
import string

from dues_automation import config, db, rates

FIRST_NAMES = [
    "Jamie", "Sam", "Alex", "Morgan", "Taylor", "Jordan", "Casey", "Riley",
    "Avery", "Quinn", "Reese", "Skylar", "Drew", "Cameron", "Rowan", "Emerson",
    "Hayden", "Parker", "Finley", "Dakota", "Kai", "Sage", "Blair", "Sydney",
    "Elliot", "Marley", "Peyton", "Remy", "Shawn", "Tatum",
]
LAST_NAMES = [
    "Test", "Example", "Sample", "Fictional", "Demo", "Placeholder", "Doe",
    "Ng", "Patel", "Garcia", "Kim", "Brown", "Nguyen", "Rossi", "Chen",
    "Martin", "Lee", "Okafor", "Silva", "Novak",
]
YEARS = ["Freshman", "Sophomore", "Junior", "Senior"]
MAJORS = [
    "Biomedical Engineering", "Biology", "Chemistry", "Neuroscience",
    "Public Health", "Chemical Engineering", "Psychology", "Biochemistry",
]

STATUS_WEIGHTS = [("active", 0.65), ("pledge", 0.25), ("alumni", 0.10)]


def _weighted_status(rng: random.Random) -> str:
    r = rng.random()
    cumulative = 0.0
    for status, weight in STATUS_WEIGHTS:
        cumulative += weight
        if r <= cumulative:
            return status
    return STATUS_WEIGHTS[-1][0]


def _random_phone(rng: random.Random) -> str:
    return f"555-{rng.randint(100, 999)}-{rng.randint(1000, 9999)}"


def _generate_ut_id(first: str, last: str, rng: random.Random, used_ut_ids: set[str]) -> str:
    """UT Austin EID format: first + middle + last initial, then 3-5 digits.
    Fictional data has no middle name, so a random initial fills that slot."""
    first_initial = first[0].lower()
    last_initial = last[0].lower()
    while True:
        middle_initial = rng.choice(string.ascii_lowercase)
        digit_count = rng.choice([3, 4, 5])
        digits = "".join(rng.choice(string.digits) for _ in range(digit_count))
        ut_id = f"{first_initial}{middle_initial}{last_initial}{digits}"
        if ut_id not in used_ut_ids:
            used_ut_ids.add(ut_id)
            return ut_id


def generate_members(count: int, rng: random.Random) -> list[dict]:
    members = []
    used_names = set()
    used_ut_ids: set[str] = set()
    for _ in range(count):
        while True:
            first = rng.choice(FIRST_NAMES)
            last = rng.choice(LAST_NAMES)
            full_name = f"{first} {last}"
            if full_name not in used_names:
                used_names.add(full_name)
                break
        status = _weighted_status(rng)
        members.append(
            {
                "ut_id": _generate_ut_id(first, last, rng, used_ut_ids),
                "full_name": full_name,
                "email": f"{first.lower()}.{last.lower()}@example.edu",
                "phone": _random_phone(rng),
                "status": status,
                "year": rng.choice(YEARS) if status != "alumni" else "Alumni",
                "major": rng.choice(MAJORS),
                "semester_joined": config.CURRENT_SEMESTER if status == "pledge" else "Fall2024",
            }
        )
    return members


def seed(count: int = 40, seed: int = 42) -> None:
    rng = random.Random(seed)
    db.init_db()
    members = generate_members(count, rng)

    with db.get_connection() as conn:
        conn.execute("DELETE FROM dues_status")
        conn.execute("DELETE FROM payments")
        conn.execute("DELETE FROM members")
        dues_amounts = rates.get_dues_amounts(conn)

        for m in members:
            conn.execute(
                """INSERT INTO members (ut_id, full_name, email, phone, status, year, major, semester_joined)
                   VALUES (:ut_id, :full_name, :email, :phone, :status, :year, :major, :semester_joined)""",
                m,
            )

            # Alumni are excluded from reconciliation entirely — no dues_status row.
            if m["status"] == "alumni":
                continue

            amount_owed = dues_amounts[m["status"]]["semester"]
            conn.execute(
                """INSERT INTO dues_status (member_id, semester, amount_owed, amount_paid)
                   VALUES (?, ?, ?, 0)""",
                (m["ut_id"], config.CURRENT_SEMESTER, amount_owed),
            )

    print(f"Seeded {len(members)} synthetic members into {config.DB_PATH}")
    print(f"  active: {sum(1 for m in members if m['status'] == 'active')}")
    print(f"  pledge: {sum(1 for m in members if m['status'] == 'pledge')}")
    print(f"  alumni: {sum(1 for m in members if m['status'] == 'alumni')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    seed(count=args.count, seed=args.seed)
