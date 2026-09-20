import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from course_data import fetch_all_sections, fetch_page, import_term, validate_sections


def record(crn="20001", term="202720"):
    return {"term": term, "courseReferenceNumber": crn, "subjectCourse": "CS1113",
            "meetingsFaculty": [
                {"meetingTime": {"term": term, "beginTime": "0900", "endTime": "0950", "monday": True}},
                {"meetingTime": {"term": term, "beginTime": "1400", "endTime": "1550", "tuesday": True}},
            ]}


def page(records, total):
    return {"success": True, "totalCount": total, "data": records}


class ImportTests(unittest.TestCase):
    def fetch(self, pages):
        with patch("course_data.initialize_search") as initialize, patch("course_data.fetch_page", side_effect=pages) as fetch:
            result = fetch_all_sections("spring-2027")
            self.assertEqual(initialize.call_args.args[2], "202720")
            self.assertTrue(all(call.args[3] == "202720" for call in fetch.call_args_list))
            return result, [call.args[2] for call in fetch.call_args_list]

    def test_pagination_uses_actual_page_lengths_and_preserves_all_meetings(self):
        records = [record(str(i)) for i in range(3)]
        result, offsets = self.fetch([page(records[:2], 3), page(records[2:], 3)])
        self.assertEqual(result, records)
        self.assertEqual(offsets, [0, 2])
        self.assertEqual(len(result[0]["meetingsFaculty"]), 2)

    def test_rejects_incomplete_duplicate_wrong_term_and_changing_results(self):
        cases = [
            [page([], 0)],
            [page([record()], 2), page([], 2)],
            [page([record()], 2), page([record()], 2)],
            [page([record(), record()], 2)],
            [page([record(term="202660")], 1)],
            [page([record()], 2), page([record("20002")], 3)],
            [page([record(), record("20002")], 1)],
            [{"success": True, "data": [record()]}],
        ]
        for pages in cases:
            with self.subTest(pages=pages), self.assertRaises((ValueError, RuntimeError)):
                self.fetch(pages)

    def test_json_failures_and_unsuccessful_responses(self):
        session = Mock()
        for payload in ({"success": False}, [], {"data": []}):
            session.get.return_value.json.return_value = payload
            with self.subTest(payload=payload), self.assertRaises(RuntimeError):
                fetch_page(session, "id", 0, "202720")
        session.get.return_value.json.side_effect = ValueError("not JSON")
        with self.assertRaisesRegex(RuntimeError, "non-JSON"):
            fetch_page(session, "id", 0, "202720")

    def test_malformed_meetings_and_wrong_nested_terms_are_rejected(self):
        for meetings in (None, [None], [{"meetingTime": None}], [{"meetingTime": {"term": "202660"}}]):
            item = record()
            item["meetingsFaculty"] = meetings
            with self.subTest(meetings=meetings), self.assertRaises(ValueError):
                validate_sections([item], "202720")

    def test_import_keeps_other_term_and_existing_file_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fall = root / "fall_2026_sections.json"
            spring = root / "spring_2027_sections.json"
            fall.write_text("fall sentinel")
            spring.write_text("spring sentinel")
            with patch("course_data.fetch_all_sections", side_effect=RuntimeError("interrupted")):
                with self.assertRaises(RuntimeError):
                    import_term("spring-2027", root)
            self.assertEqual(spring.read_text(), "spring sentinel")
            records = [record()]
            with patch("course_data.fetch_all_sections", return_value=records):
                self.assertEqual(import_term("spring-2027", root), spring)
            self.assertEqual(json.loads(spring.read_text()), records)
            self.assertEqual(fall.read_text(), "fall sentinel")
            metadata = json.loads(spring.with_suffix(".meta.json").read_text())
            self.assertEqual(metadata["term"], "202720")
            self.assertEqual(metadata["multiMeetingSections"], 1)
            self.assertEqual(list(root.glob("*.tmp")), [])

    def test_build_prepares_both_terms_by_default(self):
        import prepare_render_data
        with patch("sys.argv", ["prepare_render_data.py"]), patch("prepare_render_data.import_term", return_value=Path("data.json")) as download:
            prepare_render_data.main()
        self.assertEqual([c.args[0] for c in download.call_args_list], ["fall-2026", "spring-2027"])
