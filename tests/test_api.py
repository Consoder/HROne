"""Focused contract tests. Run against a disposable MongoDB database.

These tests intentionally use TestClient as a context manager so app startup
creates the indexes before endpoint/race assertions begin.
"""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_DB", "attendance_api_test")
from app import main


def epoch(value: str) -> int:
    """Convert an explicit UTC instant into the API's integer milliseconds."""
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp() * 1000)


class AttendanceApiTests(unittest.TestCase):
    """Exercise input rules, workflows, and indexes against MongoDB."""

    @classmethod
    def setUpClass(cls) -> None:
        """Use one isolated database and remove only records created by this suite."""
        cls.client_context = TestClient(main.app)
        cls.client = cls.client_context.__enter__()
        cls.code = "EMP9988"
        main.db.attendance_logs.delete_many({"emp_code": cls.code})
        main.db.employees.delete_many({"emp_code": cls.code})
        response = cls.client.post("/employees", json={
            "emp_code": cls.code, "name": "Test Employee", "email": "test9988@example.com",
            "department": "Test", "shift_start": "09:30", "shift_end": "18:30", "joined_on": "2026-01-01",
        })
        if response.status_code != 201:
            raise AssertionError(response.text)

    @classmethod
    def tearDownClass(cls) -> None:
        """Remove this suite's fixtures and close the startup-managed test client."""
        main.db.attendance_logs.delete_many({"emp_code": cls.code})
        main.db.employees.delete_many({"emp_code": cls.code})
        cls.client_context.__exit__(None, None, None)

    def test_invalid_timestamp_and_missing_employee(self) -> None:
        """Reject seconds-looking timestamps and distinguish unknown employees."""
        self.assertEqual(self.client.post("/attendance/punch-in", json={"emp_code": self.code, "punched_at": 1783312500}).status_code, 422)
        self.assertEqual(self.client.post("/attendance/punch-in", json={"emp_code": "EMP1111"}).status_code, 404)

    def test_punch_in_and_out_business_rules(self) -> None:
        """Check late grace, overnight-safe timestamps, output types, and duplicate conflicts."""
        response = self.client.post("/attendance/punch-in", json={"emp_code": self.code, "punched_at": epoch("2026-10-12T04:10:01")})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["late_minutes"], 10)
        self.assertIsInstance(response.json()["punch_in"], int)
        duplicate = self.client.post("/attendance/punch-in", json={"emp_code": self.code, "punched_at": epoch("2026-10-12T04:10:01")})
        self.assertEqual(duplicate.status_code, 409)
        closed = self.client.post("/attendance/punch-out", json={"emp_code": self.code, "punched_at": epoch("2026-10-12T13:00:01")})
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.json()["overtime_minutes"], 0)

    def test_regularization_appends_only_actual_changes(self) -> None:
        """A correction recomputes derived values and records a single audit entry."""
        response = self.client.patch(f"/attendance/{self.code}/2026-10-12", json={
            "punch_in": epoch("2026-10-12T04:00:00"), "reason": "Fix test time", "regularized_by": "test-runner",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["history"]), 1)
        self.assertEqual(set(response.json()["history"][0]["changes"]), {"punch_in", "work_hours", "late_minutes"})
        self.assertEqual(self.client.patch(f"/attendance/{self.code}/2026-10-12", json={
            "reason": "No change", "regularized_by": "test-runner",
        }).status_code, 422)

    def test_simultaneous_punch_ins_have_one_winner(self) -> None:
        """Prove that the database natural-key index settles a real request race."""
        request = {"emp_code": self.code, "punched_at": epoch("2026-10-13T04:00:00")}

        def send_request(_: int) -> int:
            return self.client.post("/attendance/punch-in", json=request).status_code

        with ThreadPoolExecutor(max_workers=8) as workers:
            statuses = list(workers.map(send_request, range(8)))
        self.assertEqual(statuses.count(201), 1)
        self.assertEqual(statuses.count(409), 7)

    def test_database_unique_indexes_exist(self) -> None:
        """The startup indexes are the foundation for race safety and query plans."""
        self.assertIn("employee_code_unique", main.db.employees.index_information())
        self.assertIn("employee_date_unique", main.db.attendance_logs.index_information())
        self.assertIn("department_summary_cover", main.db.attendance_logs.index_information())
        self.assertIn("employee_punch_in_desc", main.db.attendance_logs.index_information())


if __name__ == "__main__":
    unittest.main()
