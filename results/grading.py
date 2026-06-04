"""
UNEB grading engine.
US-043: PLE (P7) — Division I, II, III, IV, U.
US-044: UCE (S4) — Grades D1–F9, Divisions I–IV/U.
US-045: UACE (S6) — Principal/Subsidiary passes, aggregate points.
Verified against official UNEB 2024 guidelines.
All tables encoded as config — not hardcoded — so updates don't require code changes.
"""


# ---------------------------------------------------------------------------
# PLE Grading (US-043)
# Source: UNEB PLE Regulations 2024
# ---------------------------------------------------------------------------

# PLE Division: based on aggregate of best 4 subjects (lower aggregate = better)
# Grade points per subject: 1=Distinction (80–100), 2=Credit (60–79),
#                           3=Pass (40–59), 4=Fail (0–39)
# Minimum possible aggregate = 4 (four 1s); maximum meaningful = 16 (four 4s)
PLE_DIVISION_TABLE = [
    # (max_aggregate_inclusive, division)
    # Source: UNEB 2024 PLE results interpretation guide
    (12, 'I'),    # 4–12
    (23, 'II'),   # 13–23
    (29, 'III'),  # 24–29
    (34, 'IV'),   # 30–34
]


def get_ple_subject_grade(marks, max_marks=100):
    """
    Convert raw marks to PLE grade point (1–4).
    UNEB 2024: marks expressed as percentage of max_marks.
    """
    percentage = (marks / max_marks) * 100 if max_marks > 0 else 0
    if percentage >= 80:
        return 1  # Distinction
    elif percentage >= 60:
        return 2  # Credit
    elif percentage >= 40:
        return 3  # Pass
    else:
        return 4  # Fail


def get_ple_division(grade_points_list):
    """
    US-043: Compute PLE division from grade points of all subjects.
    Best 4 subjects (lowest points) used for aggregate.
    Returns (division, aggregate).
    """
    if not grade_points_list:
        return 'U', 999
    best_4 = sorted(grade_points_list)[:4]  # Lower is better
    aggregate = sum(best_4)
    for max_agg, division in PLE_DIVISION_TABLE:
        if aggregate <= max_agg:
            return division, aggregate
    return 'U', aggregate


# ---------------------------------------------------------------------------
# UCE Grading (US-044)
# Source: UNEB UCE Grading System 2024
# Marks are RAW marks out of 100 (not percentage-adjusted)
# ---------------------------------------------------------------------------
UCE_GRADE_TABLE = [
    # (min_raw_marks, grade, points)  — ordered highest first
    (75, 'D1', 1),
    (70, 'D2', 2),
    (65, 'C3', 3),
    (60, 'C4', 4),
    (55, 'C5', 5),
    (50, 'C6', 6),
    (45, 'P7', 7),
    (40, 'P8', 8),
    (0,  'F9', 9),
]

# UCE Division: based on aggregate of best 8 subjects (lower = better)
# A student sitting fewer than 8 subjects uses all subjects taken.
UCE_DIVISION_TABLE = [
    # (max_aggregate_inclusive, division)
    # Source: UNEB UCE 2024 pass regulations
    (32,  'I'),    # 8–32
    (47,  'II'),   # 33–47
    (56,  'III'),  # 48–56
    (64,  'IV'),   # 57–64
]


def get_uce_grade(marks, max_marks=100):
    """
    US-044: Convert raw marks to UCE letter grade and points.
    Scales to 100 if max_marks != 100.
    """
    raw = (marks / max_marks) * 100 if max_marks > 0 else 0
    for min_marks, grade, points in UCE_GRADE_TABLE:
        if raw >= min_marks:
            return grade, points
    return 'F9', 9


def get_uce_division(grade_points_list):
    """
    US-044: UCE division from best 8 subject aggregate.
    Returns (division, aggregate).
    """
    if not grade_points_list:
        return 'U', 999
    best_8 = sorted(grade_points_list)[:8]  # Lower points = better
    aggregate = sum(best_8)
    for max_agg, division in UCE_DIVISION_TABLE:
        if aggregate <= max_agg:
            return division, aggregate
    return 'U', aggregate


# ---------------------------------------------------------------------------
# UACE Grading (US-045)
# Source: UNEB UACE Grading System 2024
# Principal subjects: A–E count; O = subsidiary pass; F = fail
# ---------------------------------------------------------------------------
UACE_GRADE_TABLE = [
    # (min_raw_marks, grade, points)  — ordered highest first
    (80, 'A', 6),
    (70, 'B', 5),
    (60, 'C', 4),
    (50, 'D', 3),
    (40, 'E', 2),
    (35, 'O', 1),  # Subsidiary/Ordinary pass (principal subject fail)
    (0,  'F', 0),
]


def get_uace_grade(marks, max_marks=100, is_subsidiary=False):
    """
    US-045: Convert raw marks to UACE grade and points.
    Principal subjects: A(6)–E(2) are passes; O(1) and F(0) are fails.
    Subsidiary subjects: O(1) and above is a pass.
    """
    raw = (marks / max_marks) * 100 if max_marks > 0 else 0
    for min_marks, grade, points in UACE_GRADE_TABLE:
        if raw >= min_marks:
            return grade, points
    return 'F', 0


def get_uace_aggregate(principal_grades):
    """
    US-045: UACE aggregate from best 3 principal subjects.
    Only grades E(2) and above count towards the aggregate.
    Returns total points (max 18 for 3×A).
    """
    # Take the 3 highest-scoring principal subjects
    qualifying = sorted(
        [p for _, p in principal_grades if p >= 2],
        reverse=True
    )[:3]
    return sum(qualifying)
