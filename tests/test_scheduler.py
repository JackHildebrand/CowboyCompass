import unittest
from itertools import permutations

from scheduler import (
    build_course_options,
    calculate_total_gap,
    generate_schedules,
    rank_schedules,
    remove_conflicting_schedules,
    score_schedule,
    sections_conflict,
)


def meeting(start, end, **days):
    return {"meetingTime": {"beginTime": start, "endTime": end, **days}}


def section(course, crn, meetings):
    return {
        "subjectCourse": course,
        "courseReferenceNumber": crn,
        "scheduleTypeDescription": "Lecture",
        "meetingsFaculty": [
            {**meeting_record, "meetingTime": {**meeting_record["meetingTime"], "campusDescription": "Stillwater"}}
            for meeting_record in meetings
        ],
    }


class SchedulerTests(unittest.TestCase):
    def test_course_options_keep_one_list_per_requested_course(self):
        data = [
            section("CS1113", "A", [meeting("0900", "0950", monday=True)]),
            section("MATH2143", "B", [meeting("1000", "1050", monday=True)]),
        ]
        options = build_course_options(data, ["MATH2143", "CS1113"])
        self.assertEqual([[item["courseReferenceNumber"] for item in group] for group in options], [["B"], ["A"]])

    def test_overlapping_schedules_are_removed(self):
        first = section("CS1113", "A", [meeting("0900", "1000", monday=True)])
        overlap = section("MATH2143", "B", [meeting("0950", "1050", monday=True)])
        back_to_back = section("MATH2143", "C", [meeting("1000", "1050", monday=True)])
        schedules = remove_conflicting_schedules([(first, overlap), (first, back_to_back)])
        self.assertEqual(schedules, [(first, back_to_back)])

    def test_multi_meeting_conflict_is_independent_of_meeting_and_section_order(self):
        first_meetings = [
            meeting("0900", "1000", monday=True),
            meeting("1300", "1400", tuesday=True),
        ]
        second_meetings = [
            meeting("1100", "1200", wednesday=True),
            meeting("1330", "1430", tuesday=True),
        ]
        for first_order in permutations(first_meetings):
            for second_order in permutations(second_meetings):
                first = section("CS1113", "A", first_order)
                second = section("MATH2143", "B", second_order)
                for pair in ((first, second), (second, first)):
                    with self.subTest(pair=pair):
                        self.assertTrue(sections_conflict(*pair))
                        self.assertEqual(remove_conflicting_schedules([pair]), [])

    def test_later_meeting_edge_cases(self):
        first = section("CS1113", "A", [
            meeting("0900", "1000", monday=True),
            meeting("1300", "1400", tuesday=True),
        ])
        cases = [
            ("overlap", meeting("1330", "1430", tuesday=True), True),
            ("identical", meeting("1300", "1400", tuesday=True), True),
            ("contained", meeting("1310", "1350", tuesday=True), True),
            ("contains", meeting("1200", "1500", tuesday=True), True),
            ("touches_before", meeting("1200", "1300", tuesday=True), False),
            ("touches_after", meeting("1400", "1500", tuesday=True), False),
            ("different_day", meeting("1330", "1430", wednesday=True), False),
            ("missing_time", meeting(None, "1430", tuesday=True), False),
            ("invalid_time", meeting("bad", "1430", tuesday=True), False),
            ("exam_code", meeting("1330", "1430", tuesday=True, meetingType="EXCE"), False),
            ("exam_description", meeting("1330", "1430", tuesday=True, meetingTypeDescription="Common Exam"), False),
        ]
        for name, other_meeting, expected in cases:
            second = section("MATH2143", "B", [other_meeting])
            for pair in ((first, second), (second, first)):
                with self.subTest(case=name, pair=pair):
                    self.assertEqual(sections_conflict(*pair), expected)

    def test_empty_or_exam_only_sections_do_not_conflict(self):
        first = section("CS1113", "A", [meeting("0900", "1000", monday=True)])
        for meetings in ([], None, [meeting("0900", "1000", monday=True, meetingType="EXCE")]):
            second = {"meetingsFaculty": meetings}
            for pair in ((first, second), (second, first)):
                with self.subTest(pair=pair):
                    self.assertFalse(sections_conflict(*pair))

    def test_generated_schedules_remove_later_meeting_conflicts_in_any_course_order(self):
        first = section("CS1113", "A", [
            meeting("0900", "1000", monday=True),
            meeting("1300", "1400", tuesday=True),
        ])
        overlap = section("MATH2143", "B", [meeting("1330", "1430", tuesday=True)])
        adjacent = section("MATH2143", "C", [meeting("1400", "1500", tuesday=True)])
        unrelated = section("HIST1103", "D", [meeting("0900", "1000", friday=True)])
        for options in permutations(([first], [overlap, adjacent], [unrelated])):
            with self.subTest(options=options):
                schedules = generate_schedules(options)
                expected = [schedule for schedule in schedules if adjacent in schedule]
                self.assertEqual(remove_conflicting_schedules(schedules), expected)

    def test_campus_filter_checks_later_instructional_meetings(self):
        first = meeting("0900", "0950", monday=True, campusDescription="Off-Campus")
        later = meeting("1300", "1450", tuesday=True, campusDescription="Stillwater")
        item = {"subjectCourse": "CS1113", "meetingsFaculty": [first, later]}
        for order in permutations([first, later]):
            item["meetingsFaculty"] = list(order)
            self.assertEqual(build_course_options([item], ["CS1113"]), [[item]])
        later["meetingTime"]["meetingType"] = "EXCE"
        self.assertEqual(build_course_options([item], ["CS1113"]), [[]])

    def test_standalone_labs_are_excluded_without_dropping_combined_sections(self):
        item = section("PHYS1114", "A", [meeting("0900", "1000", monday=True)])
        for kind in ("LAB", "Lab", "lab"):
            item["scheduleTypeDescription"] = kind
            self.assertEqual(build_course_options([item], ["PHYS1114"]), [[]])
        item["scheduleTypeDescription"] = "Combined lecture and lab"
        self.assertEqual(build_course_options([item], ["PHYS1114"]), [[item]])

    def test_weekend_conflicts_gaps_and_class_days(self):
        first = section("CS1113", "A", [meeting("0900", "1000", saturday=True)])
        overlap = section("MATH2143", "B", [meeting("0930", "1030", saturday=True)])
        later = section("MATH2143", "C", [meeting("1030", "1130", saturday=True)])
        self.assertTrue(sections_conflict(first, overlap))
        self.assertEqual(calculate_total_gap((first, later)), 30)
        self.assertEqual(score_schedule((first, later)), 210)

    def test_meetings_must_share_an_actual_date(self):
        first = section("CS1113", "A", [meeting("0900", "1000", monday=True, startDate="01/11/2027", endDate="03/05/2027")])
        for start, end, expected in [
            ("03/08/2027", "04/30/2027", False),
            ("03/01/2027", "04/30/2027", True),
            ("03/02/2027", "03/05/2027", False),
            (None, None, True),
        ]:
            second = section("MATH2143", "B", [meeting("0930", "1030", monday=True, startDate=start, endDate=end)])
            for pair in ((first, second), (second, first)):
                with self.subTest(start=start, end=end):
                    self.assertEqual(sections_conflict(*pair), expected)

    def test_invalid_intervals_do_not_create_conflicts(self):
        first = section("CS1113", "A", [meeting("0900", "1000", monday=True)])
        for start, end in [("0930", "0930"), ("1000", "0900"), ("09300", "1000")]:
            second = section("MATH2143", "B", [meeting(start, end, monday=True)])
            self.assertFalse(sections_conflict(first, second))

    def test_gap_does_not_cross_weekdays(self):
        monday = section("CS1113", "A", [meeting("0900", "1000", monday=True)])
        tuesday = section("MATH2143", "B", [meeting("1500", "1600", tuesday=True)])
        self.assertEqual(calculate_total_gap((monday, tuesday)), 0)

    def test_ranking_uses_lowest_score_first(self):
        early = section("CS1113", "A", [meeting("0900", "1000", monday=True)])
        close = section("MATH2143", "B", [meeting("1030", "1100", monday=True)])
        far = section("MATH2143", "C", [meeting("1300", "1400", monday=True)])
        ranked = rank_schedules([(early, far), (early, close)])
        self.assertEqual(ranked, [(early, close), (early, far)])
        self.assertLess(score_schedule(ranked[0]), score_schedule(ranked[1]))

    def test_common_exams_are_ignored(self):
        class_meeting = meeting("0900", "0950", monday=True)
        exam_meeting = meeting(
            "1800",
            "1900",
            monday=True,
            meetingType="EXCE",
            meetingTypeDescription="Common Exam",
        )
        first = section("CS1113", "A", [class_meeting, exam_meeting])
        second = section("MATH2143", "B", [meeting("1800", "1900", monday=True)])

        self.assertEqual(remove_conflicting_schedules([(first, second)]), [(first, second)])
        self.assertEqual(calculate_total_gap((first,)), 0)


if __name__ == "__main__":
    unittest.main()
