"""Term registry and validated, atomic imports of OSU's section JSON.

Keep each Banner record intact, including every meetingsFaculty entry. The
application's data store is one JSON list per term, not a relational database.
"""
from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_URL = "https://studentregistrationssb.okstate.edu/StudentRegistrationSsb/ssb"
ROOT = Path(__file__).resolve().parent
TERMS = {
    "fall-2026": {"code": "202660", "label": "Fall 2026"},
    "spring-2027": {"code": "202720", "label": "Spring 2027"},
}
DEFAULT_TERM = "fall-2026"
TERM_DATA_PATHS = {term: ROOT / f"{term.replace('-', '_')}_sections.json" for term in TERMS}
REQUESTED_PAGE_SIZE = 500  # Banner caps results at 500, even when more are requested.
REQUEST_TIMEOUT_SECONDS = 30


def require_success(response: Any, step: str) -> None:
    import requests
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        raise RuntimeError(f"{step} failed (HTTP {response.status_code}).") from error


def make_unique_session_id() -> str:
    return secrets.token_hex(4) + str(int(time.time() * 1_000))


def initialize_search(session: Any, unique_session_id: str, term: str) -> None:
    response = session.get(
        f"{BASE_URL}/term/termSelection",
        params={"mepCode": "OSU", "mode": "search"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    require_success(response, "Term selection")
    response = session.post(
        f"{BASE_URL}/term/search", params={"mode": "search"},
        data={"term": term, "uniqueSessionId": unique_session_id},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    require_success(response, "Term search context")


def fetch_page(session: Any, unique_session_id: str, offset: int, term: str) -> dict:
    response = session.get(
        f"{BASE_URL}/searchResults/searchResults",
        params={
            "txt_term": term, "startDatepicker": "", "endDatepicker": "",
            "uniqueSessionId": unique_session_id, "pageOffset": offset,
            "pageMaxSize": REQUESTED_PAGE_SIZE,
            "sortColumn": "courseReferenceNumber", "sortDirection": "asc",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    require_success(response, f"Search-results page at offset {offset}")
    try:
        payload = response.json()
    except ValueError as error:
        raise RuntimeError("OSU returned a non-JSON search response.") from error
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise RuntimeError("OSU did not return successful search results.")
    return payload


def validate_sections(sections: list[dict], term: str) -> None:
    """Reject wrong-term, duplicate or malformed records without flattening meetings."""
    if not isinstance(sections, list) or not sections:
        raise ValueError("Course data must contain a nonempty list of sections.")
    seen = set()
    for section in sections:
        if not isinstance(section, dict) or section.get("term") != term:
            raise ValueError(f"Section data does not match term {term}.")
        crn = section.get("courseReferenceNumber")
        if not isinstance(crn, str) or not crn or crn in seen:
            raise ValueError(f"Missing or duplicate CRN: {crn}")
        seen.add(crn)
        if not section.get("subjectCourse"):
            raise ValueError(f"Missing course for CRN {crn}.")
        meetings = section.get("meetingsFaculty")
        if not isinstance(meetings, list):
            raise ValueError(f"Invalid meetings for CRN {crn}.")
        for meeting in meetings:
            if not isinstance(meeting, dict) or not isinstance(meeting.get("meetingTime"), dict):
                raise ValueError(f"Invalid meeting for CRN {crn}.")
            for record in (meeting, meeting["meetingTime"]):
                if record.get("term", term) != term:
                    raise ValueError(f"Meeting data does not match term {term}.")


def fetch_all_sections(term: str = DEFAULT_TERM) -> list[dict]:
    """Fetch a fresh complete term; never combine an old checkpoint with live pages."""
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    code = TERMS[term]["code"]
    with requests.Session() as session:
        # Retry transient failures on idempotent GETs only.
        session.mount("https://", HTTPAdapter(max_retries=Retry(
            total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods={"GET"},
        )))
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        search_id = make_unique_session_id()
        initialize_search(session, search_id, code)
        sections: list[dict] = []
        expected_total = None
        seen = set()
        while True:
            payload = fetch_page(session, search_id, len(sections), code)
            total = payload.get("totalCount")
            if type(total) is not int or total <= 0:
                raise RuntimeError(f"OSU returned an invalid or empty section count for {term}.")
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise RuntimeError("OSU's section count changed during import; retry a fresh download.")
            page = payload.get("data")
            validate_sections(page, code)
            page_crns = {record["courseReferenceNumber"] for record in page}
            if seen & page_crns:
                raise RuntimeError("OSU returned repeated sections across pages; retry a fresh download.")
            seen.update(page_crns)
            sections.extend(page)
            print(f"{TERMS[term]['label']}: downloaded {len(sections):,} of {total:,} sections.", flush=True)
            if len(sections) > total:
                raise RuntimeError("OSU returned more sections than its reported count.")
            if len(sections) == total:
                return sections


def write_json_atomic(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def import_term(term: str, output_dir: Path | None = None) -> Path:
    """Publish only a complete validated dataset, leaving existing data on failure."""
    sections = fetch_all_sections(term)
    validate_sections(sections, TERMS[term]["code"])
    path = TERM_DATA_PATHS[term]
    if output_dir is not None:
        path = output_dir / path.name
    write_json_atomic(path, sections)
    write_json_atomic(path.with_suffix(".meta.json"), {
        "term": TERMS[term]["code"], "label": TERMS[term]["label"],
        "source": f"{BASE_URL}/classSearch/classSearch",
        "retrievedAt": datetime.now(timezone.utc).isoformat(),
        "totalCount": len(sections),
        "meetingCount": sum(len(s["meetingsFaculty"]) for s in sections),
        "multiMeetingSections": sum(len(s["meetingsFaculty"]) > 1 for s in sections),
    })
    return path


def load_sections(path: Path, term: str | None = None) -> list[dict]:
    sections = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(sections, list):
        raise ValueError("Course data must contain a list of sections.")
    if term is not None:
        validate_sections(sections, TERMS[term]["code"])
    return sections
