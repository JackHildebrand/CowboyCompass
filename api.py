"""Small local HTTP API that connects the React app to the scheduler."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from course_data import TERM_DATA_PATHS, load_sections

from scheduler import (
    DAY_LABELS,
    MEETING_TYPE_NAMES,
    build_course_options,
    calculate_total_gap,
    count_class_days,
    generate_schedules,
    is_common_exam,
    rank_schedules,
    remove_conflicting_schedules,
    score_schedule,
    time_to_minutes,
)


HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "http://localhost:5173")
TOP_SCHEDULES = 10


def normalize_course(course: Any) -> str:
    return "".join(str(course).upper().split())


def professor_names(section: dict) -> str:
    faculty = section.get("faculty") or []
    return ", ".join(person.get("displayName") or "TBA" for person in faculty) or "TBA"


def location_name(meeting_time: dict) -> str:
    building = meeting_time.get("buildingDescription") or meeting_time.get("building")
    room = meeting_time.get("room")
    if building and room:
        return f"{building}, Room {room}"
    return building or room or "TBA"


def serialize_schedule(schedule: tuple[dict, ...]) -> dict:
    """Convert scheduler records into the shape the React calendar renders."""
    classes = {day: [] for day, _ in DAY_LABELS}

    for section in schedule:
        course = section.get("subjectCourse") or "Course TBA"
        title = section.get("courseTitle") or "Title TBA"
        crn = section.get("courseReferenceNumber", "TBA")
        professor = professor_names(section)
        for meeting in section.get("meetingsFaculty") or []:
            if is_common_exam(meeting):
                continue
            meeting_time = meeting.get("meetingTime") or {}
            start = time_to_minutes(meeting_time.get("beginTime"))
            meeting_type = (
                meeting_time.get("meetingTypeDescription")
                or MEETING_TYPE_NAMES.get(meeting.get("category"), "Meeting")
            )
            class_details = {
                "time": (
                    f"{_format_time(meeting_time.get('beginTime')) or 'TBA'}–"
                    f"{_format_time(meeting_time.get('endTime')) or 'TBA'}"
                ),
                "course": course,
                "title": title,
                "room": location_name(meeting_time),
                "professor": professor,
                "meetingType": meeting_type,
                "crn": str(crn),
                "startDate": meeting_time.get("startDate"),
                "endDate": meeting_time.get("endDate"),
                "sortStart": start if start is not None else 24 * 60,
            }
            for day, _ in DAY_LABELS:
                if meeting_time.get(day):
                    classes[day].append(class_details.copy())

    for entries in classes.values():
        entries.sort(key=lambda entry: entry["sortStart"])
        for entry in entries:
            entry.pop("sortStart", None)

    return {
        "score": score_schedule(schedule),
        "gap": calculate_total_gap(schedule),
        "days": count_class_days(schedule),
        "classes": classes,
    }


def _format_time(raw_time: str | None) -> str | None:
    if not isinstance(raw_time, str) or len(raw_time) < 4:
        return None
    try:
        hour = int(raw_time[:2])
        minute = raw_time[2:4]
    except ValueError:
        return None
    if hour == 0:
        return f"12:{minute} AM"
    if hour < 12:
        return f"{hour}:{minute} AM"
    if hour == 12:
        return f"12:{minute} PM"
    return f"{hour - 12}:{minute} PM"


def create_schedule_response(courses: list[str], term: str = "fall-2026") -> dict:
    try:
        data_path = TERM_DATA_PATHS[term]
    except KeyError as error:
        raise ValueError(f"That term is not available yet: {term}") from error

    all_sections = load_sections(data_path, term)
    course_options = build_course_options(all_sections, courses)
    all_schedules = generate_schedules(course_options)
    valid_schedules = remove_conflicting_schedules(all_schedules)
    ranked_schedules = rank_schedules(valid_schedules)
    return {
        "term": term,
        "requestedCourses": courses,
        "matchCounts": [len(options) for options in course_options],
        "possibleSchedules": len(all_schedules),
        "conflictFreeSchedules": len(valid_schedules),
        "schedules": [serialize_schedule(schedule) for schedule in ranked_schedules[:TOP_SCHEDULES]],
    }


class ScheduleHandler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self._send_json(204, {})

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.path != "/api/schedules":
            self._send_json(404, {"error": "Not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            courses = [normalize_course(course) for course in payload["courses"]]
            term = str(payload.get("term", "fall-2026"))
            courses = [course for course in courses if course]
            if not courses:
                raise ValueError("Add at least one course.")
            self._send_json(200, create_schedule_response(courses, term))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self._send_json(400, {"error": str(error)})
        except (FileNotFoundError, OSError, json.JSONDecodeError) as error:
            self._send_json(500, {"error": str(error)})

    def log_message(self, format: str, *args: Any) -> None:
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), ScheduleHandler)
    print(f"Cowboy Compass API running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAPI stopped.")
    finally:
        server.server_close()
