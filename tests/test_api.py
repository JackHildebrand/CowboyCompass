import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import api
from test_scheduler import meeting, section


class ApiTests(unittest.TestCase):
    def test_spring_uses_its_own_data_and_preserves_later_meetings(self):
        spring = section("CS1113", "20001", [
            meeting("0900", "0950", monday=True),
            meeting("1300", "1450", tuesday=True),
            meeting("1000", "1050", saturday=True),
        ])
        spring["term"] = "202720"
        fall = {**spring, "term": "202660", "courseReferenceNumber": "10001"}
        with tempfile.TemporaryDirectory() as directory:
            paths = {term: Path(directory) / f"{term}.json" for term in ("fall-2026", "spring-2027")}
            paths["fall-2026"].write_text(json.dumps([fall]))
            paths["spring-2027"].write_text(json.dumps([spring]))
            with patch.dict(api.TERM_DATA_PATHS, paths):
                response = api.create_schedule_response(["CS1113"], "spring-2027")
                self.assertEqual(response["term"], "spring-2027")
                self.assertEqual(response["matchCounts"], [1])
                classes = response["schedules"][0]["classes"]
                self.assertEqual(classes["tuesday"][0]["crn"], "20001")
                self.assertEqual(classes["tuesday"][0]["time"], "1:00 PM–2:50 PM")
                self.assertEqual(classes["saturday"][0]["crn"], "20001")
                default = api.create_schedule_response(["CS1113"])
                self.assertEqual(default["schedules"][0]["classes"]["monday"][0]["crn"], "10001")
                paths["spring-2027"].write_text(json.dumps([fall]))
                with self.assertRaisesRegex(ValueError, "does not match"):
                    api.create_schedule_response(["CS1113"], "spring-2027")

    def test_recorded_osu_spring_data_rejects_thursday_lab_conflict(self):
        # Public OSU records retrieved 2026-09-20: CS lecture is MWF,
        # its second meeting is Thursday 13:30-15:20. MATH 20769
        # conflicts only with that second CS meeting.
        fixture = Path(__file__).parent / "fixtures" / "spring_2027.json"
        with patch.dict(api.TERM_DATA_PATHS, {"spring-2027": fixture}):
            result = api.create_schedule_response(["CS1113", "MATH2144"], "spring-2027")
        self.assertEqual(result["matchCounts"], [1, 2])
        self.assertEqual(result["possibleSchedules"], 2)
        self.assertEqual(result["conflictFreeSchedules"], 1)
        thursday = result["schedules"][0]["classes"]["thursday"]
        self.assertEqual({row["crn"] for row in thursday}, {"23813", "20765"})
        self.assertEqual(thursday[-1]["time"], "1:30 PM–3:20 PM")
        self.assertEqual(thursday[-1]["startDate"], "01/11/2027")

    def test_unknown_term_and_missing_data_are_not_silently_replaced(self):
        with self.assertRaises(ValueError):
            api.create_schedule_response(["CS1113"], "spring-2030")
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(api.TERM_DATA_PATHS, {"spring-2027": Path(directory) / "missing.json"}):
                with self.assertRaises(FileNotFoundError):
                    api.create_schedule_response(["CS1113"], "spring-2027")

    def test_api_filters_conflict_in_second_meeting(self):
        records = [
            section("CS1113", "20001", [meeting("0900", "0950", monday=True), meeting("1300", "1450", tuesday=True)]),
            section("MATH2143", "20002", [meeting("1400", "1450", tuesday=True)]),
            section("MATH2143", "20003", [meeting("1450", "1550", tuesday=True)]),
        ]
        with patch("api.load_sections", return_value=records):
            response = api.create_schedule_response(["CS1113", "MATH2143"], "spring-2027")
        self.assertEqual(response["possibleSchedules"], 2)
        self.assertEqual(response["conflictFreeSchedules"], 1)
        self.assertEqual([m["crn"] for m in response["schedules"][0]["classes"]["tuesday"]], ["20001", "20003"])
