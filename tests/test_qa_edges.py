"""High-coverage edge checks for employee, attendance, and analytics contracts.

Run only against the disposable attendance_api_test Mongo database:
  MONGO_DB=attendance_api_test python -m unittest discover -s tests -v
On Windows PowerShell set $env:MONGO_DB before invoking Python.
"""
import os
import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_DB", "attendance_api_test")
from app import main


def epoch(ist_iso: str) -> int:
    """Convert a timestamp carrying its own IST offset to integer epoch milliseconds."""
    return int(datetime.fromisoformat(ist_iso).astimezone(timezone.utc).timestamp() * 1000)


class AttendanceEdgeQa(unittest.TestCase):
    """Probe boundary inputs with only dedicated QA employee records."""

    @classmethod
    def setUpClass(cls):
        """Create a regular and overnight QA employee in the isolated test database."""
        cls.client_context = TestClient(main.app)
        cls.client = cls.client_context.__enter__()
        cls.regular = "EMP7701"
        cls.overnight = "EMP7702"
        cls.joined_late = "EMP7703"
        cls.tie_a = "EMP7704"
        cls.tie_b = "EMP7705"
        cls.codes = [cls.regular, cls.overnight, cls.joined_late, cls.tie_a, cls.tie_b]
        for code in cls.codes:
            main.db.attendance_logs.delete_many({"emp_code": code})
            main.db.employees.delete_many({"emp_code": code})
        cls.create_employee(cls.regular)
        cls.create_employee(cls.overnight, shift_start="22:00", shift_end="06:00")
        cls.create_employee(cls.joined_late, joined_on="2026-11-01")
        cls.create_employee(cls.tie_a)
        cls.create_employee(cls.tie_b)

    @classmethod
    def tearDownClass(cls):
        """Remove only the three records owned by this QA suite."""
        for code in cls.codes:
            main.db.attendance_logs.delete_many({"emp_code": code})
            main.db.employees.delete_many({"emp_code": code})
        cls.client_context.__exit__(None, None, None)

    def setUp(self):
        """Keep each scenario independent so an intentionally open shift cannot leak."""
        main.db.attendance_logs.delete_many({"emp_code": {"$in": self.codes}})

    @classmethod
    def create_employee(cls, code, **overrides):
        """Create the baseline employee then apply the one field varied by a test."""
        data = {
            "emp_code": code, "name": f"QA {code}", "email": f"{code.lower()}@example.test",
            "department": "QA-Team", "shift_start": "09:30", "shift_end": "18:30",
            "joined_on": "2026-01-01",
        }
        data.update(overrides)
        response = cls.client.post("/employees", json=data)
        if response.status_code != 201:
            raise AssertionError(f"QA employee setup failed: {response.status_code} {response.text}")

    def post_in(self, day, clock="09:30:00", code=None):
        """Create one attendance record at an explicit IST instant."""
        return self.client.post("/attendance/punch-in", json={
            "emp_code": code or self.regular,
            "punched_at": epoch(f"{day}T{clock}+05:30"),
        })

    def test_01_employee_code_shape_rejected(self):
        self.assertEqual(self.client.post("/employees", json={"emp_code": "BAD", "name": "X", "email": "x@y.z", "department": "X", "joined_on": "2026-01-01"}).status_code, 422)

    def test_02_malformed_email_rejected(self):
        self.assertEqual(self.client.post("/employees", json={"emp_code": "EMP7791", "name": "X", "email": "not-an-email", "department": "X", "joined_on": "2026-01-01"}).status_code, 422)

    def test_03_whitespace_required_text_rejected(self):
        for field in ("name", "department"):
            body = {"emp_code": "EMP7792", "name": "Valid", "email": "x@y.z", "department": "Valid", "joined_on": "2026-01-01", field: "   "}
            with self.subTest(field=field):
                self.assertEqual(self.client.post("/employees", json=body).status_code, 422)

    def test_04_impossible_join_date_rejected(self):
        self.assertEqual(self.client.post("/employees", json={"emp_code": "EMP7793", "name": "X", "email": "x@y.z", "department": "X", "joined_on": "2026-02-30"}).status_code, 422)

    def test_05_noncanonical_shift_clock_rejected(self):
        self.assertEqual(self.client.post("/employees", json={"emp_code": "EMP7794", "name": "X", "email": "x@y.z", "department": "X", "shift_start": "9:30", "joined_on": "2026-01-01"}).status_code, 422)

    def test_06_equal_shift_start_end_rejected(self):
        self.assertEqual(self.client.post("/employees", json={"emp_code": "EMP7795", "name": "X", "email": "x@y.z", "department": "X", "shift_start": "09:30", "shift_end": "09:30", "joined_on": "2026-01-01"}).status_code, 422)

    def test_07_duplicate_employee_natural_key_conflicts(self):
        response = self.client.post("/employees", json={"emp_code": self.regular, "name": "Duplicate", "email": "dup@example.test", "department": "QA-Team", "joined_on": "2026-01-01"})
        self.assertEqual(response.status_code, 409)

    def test_08_unknown_employee_extra_field_does_not_bypass_contract(self):
        response = self.client.post("/attendance/punch-in", json={"emp_code": "EMP7777", "punched_at": epoch("2026-10-02T09:30:00+05:30"), "late_minutes": 0})
        self.assertEqual(response.status_code, 404)

    def test_09_timestamp_types_and_range_rejected(self):
        base = {"emp_code": self.regular}
        invalid_values = [1783312500, 1783312500000.0, "1783312500000", True, 99_999_999_999, 4_102_444_800_001]
        for value in invalid_values:
            with self.subTest(value=repr(value)):
                self.assertEqual(self.client.post("/attendance/punch-in", json=base | {"punched_at": value}).status_code, 422)

    def test_10_late_grace_exactly_ten_minutes_is_not_late(self):
        response = self.post_in("2026-10-02", "09:40:00")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["late_minutes"], 0)

    def test_11_late_grace_one_second_over_boundary_is_late(self):
        response = self.post_in("2026-10-03", "09:40:01")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["late_minutes"], 10)

    def test_12_duplicate_same_day_punch_conflicts(self):
        self.assertEqual(self.post_in("2026-10-04").status_code, 201)
        self.assertEqual(self.post_in("2026-10-04", "09:31:00").status_code, 409)

    def test_13_punch_out_without_punch_in_is_not_found(self):
        self.assertEqual(self.client.post("/attendance/punch-out", json={"emp_code": self.regular, "punched_at": epoch("2026-10-05T18:00:00+05:30")}).status_code, 404)

    def test_14_punch_out_at_same_instant_rejected(self):
        self.assertEqual(self.post_in("2026-10-06").status_code, 201)
        response = self.client.post("/attendance/punch-out", json={"emp_code": self.regular, "punched_at": epoch("2026-10-06T09:30:00+05:30")})
        self.assertEqual(response.status_code, 422)

    def test_15_punch_out_before_punch_in_rejected(self):
        self.assertEqual(self.post_in("2026-10-07").status_code, 201)
        response = self.client.post("/attendance/punch-out", json={"emp_code": self.regular, "punched_at": epoch("2026-10-07T09:29:59+05:30")})
        self.assertEqual(response.status_code, 404)

    def test_16_punch_out_after_more_than_24_hours_rejected(self):
        self.assertEqual(self.post_in("2026-10-08").status_code, 201)
        response = self.client.post("/attendance/punch-out", json={"emp_code": self.regular, "punched_at": epoch("2026-10-09T09:30:01+05:30")})
        self.assertEqual(response.status_code, 422)

    def test_17_exact_24_hour_shift_duration_is_allowed(self):
        self.assertEqual(self.post_in("2026-10-09").status_code, 201)
        response = self.client.post("/attendance/punch-out", json={"emp_code": self.regular, "punched_at": epoch("2026-10-10T09:30:00+05:30")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["work_hours"], 24.0)

    def test_18_repeat_punch_out_conflicts(self):
        self.assertEqual(self.post_in("2026-10-10").status_code, 201)
        body = {"emp_code": self.regular, "punched_at": epoch("2026-10-10T18:30:00+05:30")}
        self.assertEqual(self.client.post("/attendance/punch-out", json=body).status_code, 200)
        self.assertEqual(self.client.post("/attendance/punch-out", json=body).status_code, 409)

    def test_19_overtime_under_thirty_minutes_is_zero(self):
        self.assertEqual(self.post_in("2026-10-11").status_code, 201)
        response = self.client.post("/attendance/punch-out", json={"emp_code": self.regular, "punched_at": epoch("2026-10-11T18:59:59+05:30")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["overtime_minutes"], 0)

    def test_20_overtime_at_thirty_minutes_is_counted(self):
        self.assertEqual(self.post_in("2026-10-12").status_code, 201)
        response = self.client.post("/attendance/punch-out", json={"emp_code": self.regular, "punched_at": epoch("2026-10-12T19:00:00+05:30")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["overtime_minutes"], 30)

    def test_21_half_day_below_four_and_half_hours(self):
        self.assertEqual(self.post_in("2026-10-13").status_code, 201)
        response = self.client.post("/attendance/punch-out", json={"emp_code": self.regular, "punched_at": epoch("2026-10-13T13:59:24+05:30")})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["half_day"])

    def test_22_full_day_at_four_and_half_hours(self):
        self.assertEqual(self.post_in("2026-10-14").status_code, 201)
        response = self.client.post("/attendance/punch-out", json={"emp_code": self.regular, "punched_at": epoch("2026-10-14T14:00:00+05:30")})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["half_day"])

    def test_23_overnight_early_morning_punch_uses_previous_shift_date(self):
        response = self.post_in("2026-10-15", "05:59:59", self.overnight)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["date"], "2026-10-14")

    def test_24_overnight_end_clock_starts_new_attendance_date(self):
        response = self.post_in("2026-10-16", "06:00:00", self.overnight)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["date"], "2026-10-16")

    def test_25_regularization_unknown_record_is_not_found(self):
        response = self.client.patch(f"/attendance/{self.regular}/2026-10-17", json={"status": "LEAVE", "reason": "Correction", "regularized_by": "qa"})
        self.assertEqual(response.status_code, 404)

    def test_26_regularization_invalid_date_and_null_status_rejected(self):
        body = {"reason": "Correction", "regularized_by": "qa", "status": "LEAVE"}
        self.assertEqual(self.client.patch(f"/attendance/{self.regular}/2026-02-30", json=body).status_code, 422)
        self.assertEqual(self.client.patch(f"/attendance/{self.regular}/2026-10-02", json=body | {"status": None}).status_code, 422)

    def test_27_regularization_needs_audit_reason_and_actor(self):
        self.assertEqual(self.post_in("2026-10-18").status_code, 201)
        for body in ({"status": "WFH", "regularized_by": "qa"}, {"status": "WFH", "reason": "ok", "regularized_by": "qa"}, {"status": "WFH", "reason": "Valid reason", "regularized_by": ""}):
            with self.subTest(body=body):
                self.assertEqual(self.client.patch(f"/attendance/{self.regular}/2026-10-18", json=body).status_code, 422)

    def test_28_regularization_rejects_presence_status_without_instant(self):
        self.assertEqual(self.post_in("2026-10-19").status_code, 201)
        body = {"status": "ABSENT", "punch_in": epoch("2026-10-19T09:30:00+05:30"), "reason": "Set absent", "regularized_by": "qa"}
        response = self.client.patch(f"/attendance/{self.regular}/2026-10-19", json=body)
        self.assertEqual(response.status_code, 422)

    def test_29_regularization_rejects_cross_day_punch(self):
        self.assertEqual(self.post_in("2026-10-20").status_code, 201)
        body = {"punch_in": epoch("2026-10-21T09:30:00+05:30"), "reason": "Fix date", "regularized_by": "qa"}
        self.assertEqual(self.client.patch(f"/attendance/{self.regular}/2026-10-20", json=body).status_code, 422)

    def test_30_regularization_absent_clears_punch_and_audits(self):
        self.assertEqual(self.post_in("2026-10-21").status_code, 201)
        body = {"status": "ABSENT", "reason": "HR confirmed absence", "regularized_by": "qa"}
        result = self.client.patch(f"/attendance/{self.regular}/2026-10-21", json=body)
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.json()["punch_in"])
        self.assertEqual(result.json()["history"][-1]["changes"]["status"]["to"], "ABSENT")

    def test_31_month_format_is_strict(self):
        for value in ("2026-1", "2026-13", "2026-00", "Oct-2026"):
            with self.subTest(month=value):
                self.assertEqual(self.client.get(f"/analytics/employees/{self.regular}/monthly", params={"month": value}).status_code, 422)

    def test_32_future_join_month_has_zero_workdays_and_null_rate(self):
        response = self.client.get(f"/analytics/employees/{self.joined_late}/monthly", params={"month": "2026-10"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["working_days"], 0)
        self.assertIsNone(response.json()["attendance_pct"])

    def test_33_attendance_filter_invalid_dates_and_reversed_range_rejected(self):
        self.assertEqual(self.client.get("/attendance", params={"date_from": "2026-02-30"}).status_code, 422)
        self.assertEqual(self.client.get("/attendance", params={"date_from": "2026-10-22", "date_to": "2026-10-21"}).status_code, 422)

    def test_34_pagination_bounds_are_enforced(self):
        for params in ({"page": 0}, {"page_size": 0}, {"page_size": 101}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get("/employees", params=params).status_code, 422)

    def test_35_attendance_pages_are_stable_and_report_total(self):
        one = self.client.get("/employees", params={"department": "QA-Team", "page": 1, "page_size": 1}).json()
        two = self.client.get("/employees", params={"department": "QA-Team", "page": 2, "page_size": 1}).json()
        self.assertEqual(one["total"], 5)
        self.assertEqual(two["total"], 5)
        self.assertNotEqual(one["items"][0]["emp_code"], two["items"][0]["emp_code"])

    def test_36_department_summary_unknown_department_is_empty(self):
        response = self.client.get("/analytics/departments/summary", params={"month": "2026-10", "department": "QA-missing"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])

    def test_department_summary_counts_zero_log_employees_once(self):
        """Headcount includes eligible employees without logs, but not future hires."""
        self.assertEqual(self.post_in("2026-10-12").status_code, 201)
        punch_out = self.client.post("/attendance/punch-out", json={
            "emp_code": self.regular,
            "punched_at": epoch("2026-10-12T18:30:00+05:30"),
        })
        self.assertEqual(punch_out.status_code, 200)

        response = self.client.get("/analytics/departments/summary", params={
            "month": "2026-10", "department": "QA-Team",
        })
        self.assertEqual(response.status_code, 200)
        row = response.json()["items"][0]
        self.assertEqual(row["headcount"], 4)
        self.assertEqual(row["present_days"], 1)
        self.assertAlmostEqual(row["avg_work_hours"], 9.0)
        self.assertEqual(row["late_count"], 0)

    def test_37_leaderboard_invalid_cutoff_is_rejected(self):
        self.assertEqual(self.client.get("/analytics/leaderboard/late", params={"month": "2026-10", "limit": 0}).status_code, 422)
        self.assertEqual(self.client.get("/analytics/leaderboard/late", params={"month": "2026-10", "limit": 51}).status_code, 422)

    def test_38_department_trend_unknown_department_is_not_found(self):
        response = self.client.get("/analytics/departments/QA-missing/trend", params={"from": "2026-10-01", "to": "2026-10-02"})
        self.assertEqual(response.status_code, 404)

    def test_39_department_trend_range_inclusive_92_days(self):
        response = self.client.get("/analytics/departments/QA-Team/trend", params={"from": "2026-10-01", "to": "2026-12-31"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 92)
        self.assertEqual(response.json()["items"][0]["date"], "2026-10-01")
        self.assertEqual(response.json()["items"][-1]["date"], "2026-12-31")

    def test_40_department_trend_rejects_93_day_and_reversed_ranges(self):
        self.assertEqual(self.client.get("/analytics/departments/QA-Team/trend", params={"from": "2026-10-01", "to": "2027-01-01"}).status_code, 422)
        self.assertEqual(self.client.get("/analytics/departments/QA-Team/trend", params={"from": "2026-10-02", "to": "2026-10-01"}).status_code, 422)

    def test_41_explain_requires_endpoint_specific_parameters(self):
        self.assertEqual(self.client.get("/admin/explain/employee_monthly").status_code, 422)
        self.assertEqual(self.client.get("/admin/explain/not-real").status_code, 422)

    def test_42_epoch_minimum_and_maximum_are_inclusive(self):
        for timestamp in (main.MIN_MS, main.MAX_MS):
            with self.subTest(timestamp=timestamp):
                response = self.client.post("/attendance/punch-in", json={"emp_code": self.regular, "punched_at": timestamp})
                self.assertEqual(response.status_code, 201)

    def test_43_weekend_presence_is_not_counted_in_monthly_workday_rate(self):
        response = self.post_in("2026-10-03")  # Saturday.
        self.assertEqual(response.status_code, 201)
        summary = self.client.get(f"/analytics/employees/{self.regular}/monthly", params={"month": "2026-10"}).json()
        self.assertEqual(summary["present_days"], 0)
        self.assertEqual(summary["attendance_pct"], 0.0)

    def test_44_leaderboard_uses_competition_rank_and_keeps_cutoff_ties(self):
        self.assertEqual(self.post_in("2026-10-02", "10:00:00", self.regular).status_code, 201)
        self.assertEqual(self.post_in("2026-10-03", "10:00:00", self.tie_a).status_code, 201)
        self.assertEqual(self.post_in("2026-10-04", "09:50:00", self.tie_b).status_code, 201)
        top = self.client.get("/analytics/leaderboard/late", params={"month": "2026-10", "limit": 1, "department": "QA-Team"}).json()["items"]
        self.assertEqual([(row["emp_code"], row["rank"]) for row in top], [(self.regular, 1), (self.tie_a, 1)])
        cutoff_two = self.client.get("/analytics/leaderboard/late", params={"month": "2026-10", "limit": 2, "department": "QA-Team"}).json()["items"]
        self.assertEqual([(row["emp_code"], row["rank"]) for row in cutoff_two], [(self.regular, 1), (self.tie_a, 1)])
        cutoff_three = self.client.get("/analytics/leaderboard/late", params={"month": "2026-10", "limit": 3, "department": "QA-Team"}).json()["items"]
        self.assertEqual([(row["emp_code"], row["rank"]) for row in cutoff_three], [(self.regular, 1), (self.tie_a, 1), (self.tie_b, 3)])

    def test_45_trend_fills_empty_days_and_suppresses_weekend_rates(self):
        response = self.client.get("/analytics/departments/QA-Team/trend", params={"from": "2026-10-02", "to": "2026-10-04"})
        self.assertEqual(response.status_code, 200)
        friday, saturday, sunday = response.json()["items"]
        self.assertEqual([row["date"] for row in (friday, saturday, sunday)], ["2026-10-02", "2026-10-03", "2026-10-04"])
        self.assertEqual(friday["attendance_rate"], 0.0)
        self.assertFalse(saturday["is_working_day"])
        self.assertIsNone(saturday["attendance_rate"])
        self.assertIsNone(sunday["attendance_rate"])


if __name__ == "__main__":
    unittest.main()
