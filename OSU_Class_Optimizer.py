"""Terminal interface for Cowboy Compass."""

from __future__ import annotations

import argparse

from scheduler import (
    DAY_LABELS,
    MEETING_TYPE_NAMES,
    build_course_options,
    calculate_total_gap,
    count_class_days,
    find_course_sections,
    rank_schedules,
    remove_conflicting_schedules,
    generate_schedules,
    score_schedule,
    time_to_minutes,
)

from course_data import DEFAULT_TERM, TERMS, TERM_DATA_PATHS, load_sections

TOP_SCHEDULES_TO_DISPLAY = 10


def format_time(raw_time: str | None) -> str | None:
    """Convert a four-digit time such as '1330' to '1:30 PM'."""
    if not isinstance(raw_time, str) or len(raw_time) < 4:
        return None

    try:
        hour = int(raw_time[:2])
    except (TypeError, ValueError):
        return None

    minute = raw_time[2:]
    if hour == 0:
        hour = 12
        period = "AM"
    elif hour < 12:
        period = "AM"
    elif hour == 12:
        period = "PM"
    else:
        hour -= 12
        period = "PM"
    return f"{hour}:{minute} {period}"


def normalize_course_request(course: str) -> str:
    """Normalize 'cs 1113' and 'CS1113' to the same lookup value."""
    return "".join(course.upper().split())


def get_course_requests() -> list[str]:
    """Prompt until the user enters DONE and return normalized courses."""
    courses: list[str] = []
    print("Enter the courses you want to take in the format: CS 1113.")
    print("Enter DONE when finished.\n")

    while True:
        course = normalize_course_request(input("Course: "))
        if course == "DONE":
            return courses
        if course:
            courses.append(course)


def professor_names(section: dict) -> str:
    """Return the listed professor names for a section."""
    faculty = section.get("faculty") or []
    return ", ".join(person.get("displayName") or "TBA" for person in faculty) or "TBA"


def location_name(meeting_time: dict) -> str:
    """Return a readable building and room label."""
    building = meeting_time.get("buildingDescription") or meeting_time.get("building")
    room = meeting_time.get("room")
    if building and room:
        return f"{building}, Room {room}"
    return building or room or "TBA"


def schedule_calendar(schedule: tuple[dict, ...]) -> dict[str, list[tuple[int, str]]]:
    """Build chronologically sortable calendar entries for a schedule."""
    calendar: dict[str, list[tuple[int, str]]] = {day: [] for day, _ in DAY_LABELS}
    for section in schedule:
        course = section.get("subjectCourse") or "Course TBA"
        title = section.get("courseTitle") or "Title TBA"
        crn = section.get("courseReferenceNumber", "TBA")
        professor = professor_names(section)
        for meeting in section.get("meetingsFaculty") or []:
            meeting_time = meeting.get("meetingTime") or {}
            start = time_to_minutes(meeting_time.get("beginTime"))
            end = time_to_minutes(meeting_time.get("endTime"))
            start_text = format_time(meeting_time.get("beginTime")) or "TBA"
            end_text = format_time(meeting_time.get("endTime")) or "TBA"
            meeting_type = (
                meeting_time.get("meetingTypeDescription")
                or MEETING_TYPE_NAMES.get(meeting.get("category"), "Meeting")
            )
            details = (
                f"{start_text} - {end_text} | {course} {title} | "
                f"{meeting_type} | {location_name(meeting_time)} | "
                f"Professor: {professor} | CRN: {crn}"
            )
            sort_start = start if start is not None else 24 * 60
            for day, _ in DAY_LABELS:
                if meeting_time.get(day):
                    calendar[day].append((sort_start, details))

    for entries in calendar.values():
        entries.sort(key=lambda entry: entry[0])
    return calendar


def display_schedules(schedules: list[tuple[dict, ...]]) -> None:
    """Print every schedule as a full weekly calendar, best score first."""
    ranked_schedules = rank_schedules(schedules)
    schedules_to_display = ranked_schedules[:TOP_SCHEDULES_TO_DISPLAY]
    print(
        f"\nTop {len(schedules_to_display)} schedules "
        f"(of {len(ranked_schedules)}, best score first):"
    )

    for number, schedule in enumerate(schedules_to_display, start=1):
        total_gap = calculate_total_gap(schedule)
        class_days = count_class_days(schedule)
        score = score_schedule(schedule)
        print("\n" + "=" * 90)
        print(
            f"Schedule {number} | Score: {score} | "
            f"Total gap: {total_gap} minutes | Class days: {class_days}"
        )
        print("=" * 90)

        calendar = schedule_calendar(schedule)
        for day, _ in DAY_LABELS:
            print(f"{day.title()}:")
            entries = calendar[day]
            if not entries:
                print("  No classes")
                continue
            for _, details in entries:
                print(f"  {details}")


def meeting_days(meeting_time: dict) -> str:
    """Return a compact meeting-day label such as MWF or TR."""
    return "".join(
        label for day, label in DAY_LABELS if meeting_time.get(day)
    ) or "TBA"


def display_course_section(section: dict) -> None:
    """Print one course section in a readable terminal format."""
    print("CRN:", section.get("courseReferenceNumber", "TBA"))
    seats = section.get("seatsAvailable", "TBA")
    enrollment = section.get("enrollment", "TBA")
    print(f"{seats}/{enrollment} Seats Available")

    meetings = section.get("meetingsFaculty") or []
    if not meetings:
        print("Meeting Times and Locations: TBA")

    for meeting in meetings:
        meeting_time = meeting.get("meetingTime") or {}
        start = format_time(meeting_time.get("beginTime")) or "TBA"
        end = format_time(meeting_time.get("endTime")) or "TBA"
        location_parts = (meeting_time.get("building"), meeting_time.get("room"))
        location = " ".join(part for part in location_parts if part) or "TBA"
        meeting_type = MEETING_TYPE_NAMES.get(meeting.get("category"), "meeting")
        print(
            "Meeting Times and Locations: "
            f"{meeting_days(meeting_time)} | {start} - {end} "
            f"{meeting_type} in {location}"
        )

    faculty = section.get("faculty") or []
    professors = ", ".join(
        person.get("displayName") or "TBA" for person in faculty
    ) or "TBA"
    print("Professor:", professors)
    print()


def display_course_options(
    requested_courses: list[str], course_options: list[list[dict]]
) -> None:
    """Print verification counts followed by all matching sections."""
    print("\nSections found for each requested course:")
    for course, sections in zip(requested_courses, course_options):
        print(f"{course}: {len(sections)} matching sections")

    print()


def main() -> None:
    """Run the interactive course lookup workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--term", choices=TERMS, default=DEFAULT_TERM)
    args = parser.parse_args()
    all_sections = load_sections(TERM_DATA_PATHS[args.term], args.term)
    courses = get_course_requests()
    course_options = build_course_options(all_sections, courses)
    display_course_options(courses, course_options)

    all_schedules = generate_schedules(course_options)
    valid_schedules = remove_conflicting_schedules(all_schedules)
    print(f"Possible schedules: {len(all_schedules):,}")
    print(f"Conflict-free schedules: {len(valid_schedules):,}")
    display_schedules(valid_schedules)


if __name__ == "__main__":
    main()
