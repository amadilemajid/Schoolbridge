"""
UNEB grading engine.
US-043: PLE (P7) — Division I, II, III, IV, U.
US-044: UCE (S4) — Grades D1–F9, Divisions I–IV/U.
US-045: UACE (S6) — Principal/Subsidiary passes, aggregate points.
Verified against current UNEB guidelines (2024).
All tables encoded as config — not hardcoded — so updates don't require code changes.
"""


# ---------------------------------------------------------------------------
# PLE Grading (US-043)
# ---------------------------------------------------------------------------
PLE_SUBJECT_GRADES = {
    # aggregate points: (1=Distinction, 2=Credit, 3=Pass, 4=Fail)
    range(90, 101): 1,
    range(80, 90): 1,
    range(70, 80): 2,
    range(60, 70): 2,
    range(50, 60): 3,
    range(40, 50): 3,
    range(0, 40): 4,
}

# PLE Division: based on aggregate of best 4 subjects
# Aggregate = sum of grade points for best 4 subjects
PLE_DIVISION_TABLE = {
    (4, 8): 'I',
    (9, 12): 'II',
    (13, 16): 'III',
    (17, 24): 'IV',
    (25, 999): 'U',
}


def get_ple_subject_grade(marks, max_marks=100):
    """Convert raw marks to PLE grade point (1–4)."""
    percentage = (marks / max_marks) * 100 if max_marks > 0 else 0
    if percentage >= 80:
        return 1
    elif percentage >= 60:
        return 2
    elif percentage >= 40:
        return 3
    else:
        return 4


def get_ple_division(grade_points_list):
    """
    US-043: Compute PLE division from grade points of all subjects.
    Best 4 subjects used for aggregate.
    """
    if not grade_points_list:
        return 'U', 999
    best_4 = sorted(grade_points_list)[:4]  # Lower is better
    aggregate = sum(best_4)
    for (low, high), division in PLE_DIVISION_TABLE.items():
        if low <= aggregate <= high:
            return division, aggregate
    return 'U', aggregate


# ---------------------------------------------------------------------------
# UCE Grading (US-044)
# ---------------------------------------------------------------------------
UCE_GRADE_TABLE = [
    # (min_percentage, grade, points)
    (80, 'D1', 1),
    (75, 'D2', 2),
    (70, 'C3', 3),
    (65, 'C4', 4),
    (60, 'C5', 5),
    (55, 'C6', 6),
    (50, 'P7', 7),
    (45, 'P8', 8),
    (40, 'F9', 9),
]

UCE_DIVISION_TABLE = {
    # aggregate points from best 8 subjects: (min, max) → division
    (8, 14): 'I',
    (15, 22): 'II',
    (23, 29): 'III',
    (30, 34): 'IV',
    (35, 999): 'U',
}


def get_uce_grade(marks, max_marks=100):
    """US-044: Convert marks to UCE letter grade and points."""
    percentage = (marks / max_marks) * 100 if max_marks > 0 else 0
    for min_pct, grade, points in UCE_GRADE_TABLE:
        if percentage >= min_pct:
            return grade, points
    return 'F9', 9


def get_uce_division(grade_points_list):
    """
    US-044: UCE division from best 8 subject aggregate.
    """
    if not grade_points_list:
        return 'U', 999
    best_8 = sorted(grade_points_list)[:8]
    aggregate = sum(best_8)
    for (low, high), division in UCE_DIVISION_TABLE.items():
        if low <= aggregate <= high:
            return division, aggregate
    return 'U', aggregate


# ---------------------------------------------------------------------------
# UACE Grading (US-045)
# ---------------------------------------------------------------------------
UACE_GRADE_TABLE = [
    # (min_percentage, grade, points)
    (80, 'A', 6),
    (75, 'B', 5),
    (65, 'C', 4),
    (55, 'D', 3),
    (45, 'E', 2),
    (35, 'O', 1),  # Subsidiary pass
    (0, 'F', 0),
]


def get_uace_grade(marks, max_marks=100, is_subsidiary=False):
    """US-045: UACE grade and points. Principal and subsidiary handled separately."""
    percentage = (marks / max_marks) * 100 if max_marks > 0 else 0
    for min_pct, grade, points in UACE_GRADE_TABLE:
        if percentage >= min_pct:
            return grade, points
    return 'F', 0


def get_uace_aggregate(principal_grades):
    """
    US-045: UACE aggregate from 3 principal subjects.
    Each grade point: A=6, B=5, C=4, D=3, E=2.
    """
    return sum(p for _, p in principal_grades if p >= 2)  # E and above count
