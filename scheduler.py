"""Reusable scheduling engine for Cowboy Compass."""

from __future__ import annotations

from itertools import combinations, product
from datetime import datetime, timedelta


DAY_LABELS = (
    ("monday", "M"),
    ("tuesday", "T"),
    ("wednesday", "W"),
    ("thursday", "R"),
    ("friday", "F"),
    ("saturday", "S"),
    ("sunday", "U"),
)
CLASS_DAY_PENALTY = 180
CAMPUS = "Stillwater"
EXCLUDED_SCHEDULE_TYPES = {"LAB"}
MEETING_TYPE_NAMES = {"01": "lecture", "02": "lab"}


def is_common_exam(meeting: dict) -> bool:
    """Return whether a meeting is a scheduled common exam."""
    meeting_time = meeting.get("meetingTime") or {}
    description = meeting_time.get("meetingTypeDescription", "")
    meeting_type = meeting_time.get("meetingType", "")
    return description.casefold() == "common exam" or meeting_type == "EXCE"


def instructional_meetings(section: dict):
    """Yield class meetings used by scheduling calculations."""
    return (
        meeting
        for meeting in section.get("meetingsFaculty") or []
        if not is_common_exam(meeting)
    )


def is_eligible_section(section: dict) -> bool:
    """Return whether a section can be offered as a Stillwater option."""
    if (section.get("scheduleTypeDescription") or "").upper() in EXCLUDED_SCHEDULE_TYPES:
        return False

    meetings = section.get("meetingsFaculty") or []
    if not meetings:
        return False

    return any(
        (meeting.get("meetingTime") or {}).get("campusDescription") == CAMPUS
        for meeting in instructional_meetings(section)
    )


def find_course_sections(
    all_sections: list[dict], requested_courses: list[str]
) -> list[dict]:
    """Return eligible sections for any of the requested courses."""
    requested = set(requested_courses)
    return [
        section
        for section in all_sections
        if section.get("subjectCourse", "").upper() in requested
        and is_eligible_section(section)
    ]


def build_course_options(
    all_sections: list[dict], requested_courses: list[str]
) -> list[list[dict]]:
    """Group matching sections by course using one dataset scan."""
    sections_by_course = {course: [] for course in requested_courses}

    for section in find_course_sections(all_sections, requested_courses):
        course = section.get("subjectCourse", "").upper()
        sections_by_course[course].append(section)

    # Copies keep repeated course requests independent if modified later.
    return [sections_by_course[course].copy() for course in requested_courses]


def count_possible_schedules(course_options: list[list[dict]]) -> int:
    """Return the number of one-section-per-course combinations."""
    total = 1
    for sections in course_options:
        total *= len(sections)
    return total if course_options else 0


def generate_schedules(
    course_options: list[list[dict]],
) -> list[tuple[dict, ...]]:
    """Create every schedule by choosing one section from each course."""
    if not course_options or any(not sections for sections in course_options):
        return []
    return list(product(*course_options))


def time_to_minutes(raw_time: str | None) -> int | None:
    """Convert OSU's HHMM time string to minutes after midnight."""
    if not isinstance(raw_time, str) or len(raw_time) != 4:
        return None
    try:
        hour = int(raw_time[:2])
        minute = int(raw_time[2:4])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def meeting_times_overlap(first: dict, second: dict) -> bool:
    """Check all shared days and the dates on which both meetings occur."""
    first_time = first.get("meetingTime") or {}
    second_time = second.get("meetingTime") or {}
    shared_day = any(
        first_time.get(day) and second_time.get(day)
        for day, _ in DAY_LABELS
    )
    if not shared_day:
        return False

    first_start = time_to_minutes(first_time.get("beginTime"))
    first_end = time_to_minutes(first_time.get("endTime"))
    second_start = time_to_minutes(second_time.get("beginTime"))
    second_end = time_to_minutes(second_time.get("endTime"))
    if None in (first_start, first_end, second_start, second_end):
        return False

    if first_start >= first_end or second_start >= second_end:
        return False

    # Missing dates retain the conservative weekly conflict behavior.
    try:
        start_date = max(datetime.strptime(t["startDate"], "%m/%d/%Y").date()
                         for t in (first_time, second_time))
        end_date = min(datetime.strptime(t["endDate"], "%m/%d/%Y").date()
                       for t in (first_time, second_time))
    except (KeyError, TypeError, ValueError):
        pass
    else:
        if not any(
            first_time.get(day) and second_time.get(day)
            and start_date + timedelta(days=(index - start_date.weekday()) % 7) <= end_date
            for index, (day, _) in enumerate(DAY_LABELS)
        ):
            return False

    # Strict inequalities allow back-to-back classes with no overlap.
    return first_start < second_end and second_start < first_end


def sections_conflict(first: dict, second: dict) -> bool:
    """Return whether any meeting in two sections overlaps."""
    first_meetings = instructional_meetings(first)
    # Reuse the inner meetings for every meeting in the first section.
    second_meetings = tuple(instructional_meetings(second))
    return any(
        meeting_times_overlap(first_meeting, second_meeting)
        for first_meeting in first_meetings
        for second_meeting in second_meetings
    )


def schedule_has_conflict(schedule: tuple[dict, ...]) -> bool:
    """Return whether any pair of courses in a schedule overlaps."""
    return any(sections_conflict(first, second) for first, second in combinations(schedule, 2))


def remove_conflicting_schedules(
    schedules: list[tuple[dict, ...]],
) -> list[tuple[dict, ...]]:
    """Keep only schedules with no overlapping course meetings."""
    return [schedule for schedule in schedules if not schedule_has_conflict(schedule)]


def calculate_daily_gaps(schedule: tuple[dict, ...]) -> dict[str, int]:
    """Return idle minutes between meetings for each weekday in a schedule."""
    meetings_by_day: dict[str, list[tuple[int, int]]] = {
        day: [] for day, _ in DAY_LABELS
    }

    for section in schedule:
        for meeting in instructional_meetings(section):
            meeting_time = meeting.get("meetingTime") or {}
            start = time_to_minutes(meeting_time.get("beginTime"))
            end = time_to_minutes(meeting_time.get("endTime"))
            if start is None or end is None or start >= end:
                continue

            for day, _ in DAY_LABELS:
                if meeting_time.get(day):
                    meetings_by_day[day].append((start, end))

    daily_gaps: dict[str, int] = {}
    for day, intervals in meetings_by_day.items():
        intervals.sort()
        gap = 0
        occupied_until: int | None = None
        for start, end in intervals:
            if occupied_until is not None and start > occupied_until:
                gap += start - occupied_until
            occupied_until = max(occupied_until or end, end)
        daily_gaps[day] = gap
    return daily_gaps


def calculate_total_gap(schedule: tuple[dict, ...]) -> int:
    """Return total idle minutes across all weekdays in a schedule."""
    return sum(calculate_daily_gaps(schedule).values())


def count_class_days(schedule: tuple[dict, ...]) -> int:
    """Return the number of weekdays on which a schedule has class."""
    days_with_class = set()
    for section in schedule:
        for meeting in instructional_meetings(section):
            meeting_time = meeting.get("meetingTime") or {}
            for day, _ in DAY_LABELS:
                if meeting_time.get(day):
                    days_with_class.add(day)
    return len(days_with_class)


def score_schedule(schedule: tuple[dict, ...]) -> int:
    """Return a score where lower means a more desirable schedule."""
    gap_minutes = calculate_total_gap(schedule)
    class_days = count_class_days(schedule)
    return gap_minutes + class_days * CLASS_DAY_PENALTY


def rank_schedules(
    schedules: list[tuple[dict, ...]],
) -> list[tuple[dict, ...]]:
    """Return schedules ordered from lowest score to highest score."""
    return sorted(schedules, key=score_schedule)
