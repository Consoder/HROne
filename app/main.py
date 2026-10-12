"""Employee Attendance & Analytics API.

The assignment deliberately keeps all code in this file.  The sections below are
ordered for a reader: settings, rules, data conversion, request validation,
database operations, then analytics.  Comments describe business intent.
"""
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from bson import json_util
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError


# .env is convenient locally. Real environment values still win because dotenv
# does not override values that already exist.
load_dotenv()
UTC = timezone.utc
IST = timezone(timedelta(hours=5, minutes=30))
PRESENT = {"PRESENT", "WFH", "ON_DUTY"}
ALL_STATUS = PRESENT | {"ABSENT", "LEAVE"}
MIN_MS, MAX_MS = 100_000_000_000, 4_102_444_800_000
client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), tz_aware=True)
db = client[os.getenv("MONGO_DB", "attendance_db")]


# ---------- Rules and conversion helpers ----------
def fail(message: str) -> None:
    """Use one consistent response for a valid request that breaks a business rule."""
    raise HTTPException(422, message)


def real_date(value: str) -> date:
    """Reject impossible or non-canonical calendar strings before they reach MongoDB."""
    try:
        result = date.fromisoformat(value)
    except (TypeError, ValueError):
        fail("date must be a real YYYY-MM-DD value")
    if result.isoformat() != value:
        fail("date must use YYYY-MM-DD format")
    return result


def real_month(value: str) -> tuple[date, date]:
    """Return the first and final date represented by a YYYY-MM request parameter."""
    try:
        start = datetime.strptime(value, "%Y-%m").date().replace(day=1)
    except (TypeError, ValueError):
        fail("month must use YYYY-MM format")
    if start.strftime("%Y-%m") != value:
        fail("month must use YYYY-MM format")
    return start, ((start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1))


def clock(value: str) -> time:
    """Parse a validated 24-hour shift clock, rather than silently accepting 9:30."""
    try:
        result = datetime.strptime(value, "%H:%M").time()
    except (TypeError, ValueError):
        fail("shift time must use HH:MM in 24-hour format")
    if result.strftime("%H:%M") != value:
        fail("shift time must use HH:MM in 24-hour format")
    return result


def epoch_input(value: Any) -> int:
    """Enforce integer epoch milliseconds: bools, strings, floats and seconds fail."""
    if type(value) is not int or not MIN_MS <= value <= MAX_MS:
        fail("timestamp must be an integer epoch milliseconds value in range")
    return value


def utc_from_ms(value: int) -> datetime:
    """R1: trim milliseconds to a whole UTC second before every calculation/storage."""
    return datetime.fromtimestamp(epoch_input(value) / 1000, UTC).replace(microsecond=0)


def now_second() -> datetime:
    """The only source of a server-generated instant."""
    return datetime.now(UTC).replace(microsecond=0)


def aware_utc(value: datetime) -> datetime:
    """Seeded legacy BSON dates can be naive; consistently interpret those as UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def ms(value: datetime | None) -> int | None:
    """Convert MongoDB BSON datetimes to the API's epoch-millisecond representation."""
    return None if value is None else int(aware_utc(value).timestamp()) * 1000


def overnight(employee: dict[str, Any]) -> bool:
    """A 22:00-06:00 shift ends next day because its end is not after its start."""
    return clock(employee["shift_end"]) <= clock(employee["shift_start"])


def ist_at(day: date, shift_clock: str) -> datetime:
    """Put a shift clock onto an IST calendar day."""
    return datetime.combine(day, clock(shift_clock), IST)


def attendance_day(punch_in: datetime, employee: dict[str, Any]) -> str:
    """R1: map a punch to an IST attendance day, including early overnight punches."""
    local = aware_utc(punch_in).astimezone(IST)
    result = local.date()
    if overnight(employee) and local.timetz().replace(tzinfo=None) < clock(employee["shift_end"]):
        result -= timedelta(days=1)
    return result.isoformat()


def half_up(value: Decimal, format_: str = "0.01") -> float:
    """R4/R8 require decimal half-up, not Python's binary/banker's round."""
    return float(value.quantize(Decimal(format_), rounding=ROUND_HALF_UP))


def late_minutes(punch_in: datetime, employee: dict[str, Any], record_date: str) -> int:
    """R2: >10:00 is late; returned minutes are from shift start, floored."""
    shift_day = real_date(record_date)
    local_clock = aware_utc(punch_in).astimezone(IST).timetz().replace(tzinfo=None)
    if overnight(employee) and local_clock < clock(employee["shift_end"]):
        shift_day -= timedelta(days=1)
    start = ist_at(shift_day, employee["shift_start"])
    seconds = int((aware_utc(punch_in).astimezone(IST) - start).total_seconds())
    return seconds // 60 if seconds > 600 else 0


def overtime_minutes(punch_out: datetime, employee: dict[str, Any], record_date: str) -> int:
    """R3: count after shift end only when at least 30 whole minutes."""
    shift_day = real_date(record_date) + timedelta(days=1 if overnight(employee) else 0)
    minutes = int((aware_utc(punch_out).astimezone(IST) - ist_at(shift_day, employee["shift_end"])).total_seconds()) // 60
    return minutes if minutes >= 30 else 0


def calculated(employee: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Calculate only fields owned by the API; analytics later read these stored values."""
    if record["status"] not in PRESENT or not record.get("punch_in"):
        return {"work_hours": None, "late_minutes": 0, "overtime_minutes": 0, "half_day": False}
    data = {"work_hours": None, "late_minutes": late_minutes(record["punch_in"], employee, record["date"]), "overtime_minutes": 0, "half_day": False}
    if record.get("punch_out"):
        seconds = Decimal(int((aware_utc(record["punch_out"]) - aware_utc(record["punch_in"])).total_seconds()))
        work = half_up(seconds / Decimal("3600"))
        data.update(work_hours=work, overtime_minutes=overtime_minutes(record["punch_out"], employee, record["date"]), half_day=work < 4.5)
    return data


def defaults(record: dict[str, Any]) -> dict[str, Any]:
    """Read old seeded documents safely without mutating them or assuming new fields."""
    record.setdefault("history", [])
    record.setdefault("half_day", False)
    record.setdefault("late_minutes", 0)
    record.setdefault("overtime_minutes", 0)
    return record


def employee_out(row: dict[str, Any]) -> dict[str, Any]:
    """Remove MongoDB's private _id and convert created_at at the HTTP boundary."""
    return {key: (ms(value) if key == "created_at" else value) for key, value in row.items() if key != "_id"}


def attendance_out(row: dict[str, Any]) -> dict[str, Any]:
    """Serialize top-level and audit-trail dates without leaking internal BSON values."""
    row = defaults(dict(row))
    result = {key: value for key, value in row.items() if key != "_id"}
    result["punch_in"], result["punch_out"] = ms(row.get("punch_in")), ms(row.get("punch_out"))
    history = []
    for entry in row["history"]:
        changes = {}
        for field, change in entry["changes"].items():
            changes[field] = {"from": ms(change["from"]) if field in {"punch_in", "punch_out"} else change["from"], "to": ms(change["to"]) if field in {"punch_in", "punch_out"} else change["to"]}
        history.append({"at": ms(entry["at"]), "by": entry["by"], "reason": entry["reason"], "changes": changes})
    result["history"] = history
    return result


# ---------- Request validation ----------
class RequestModel(BaseModel):
    """Derived fields are deliberately ignored: clients are not allowed to set them."""
    model_config = ConfigDict(extra="ignore")


class EmployeeIn(RequestModel):
    emp_code: str = Field(pattern=r"^EMP\d{4,6}$")
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department: str = Field(min_length=1, max_length=50)
    shift_start: str = "09:30"
    shift_end: str = "18:30"
    joined_on: str

    @field_validator("name", "department")
    @classmethod
    def text_is_not_whitespace(cls, value: str) -> str:
        """A spaces-only name/department is not a meaningful required value."""
        if not value.strip():
            raise ValueError("value cannot contain only whitespace")
        return value

    @field_validator("shift_start", "shift_end")
    @classmethod
    def shift_is_clock(cls, value: str) -> str:
        clock(value); return value

    @field_validator("joined_on")
    @classmethod
    def joined_is_date(cls, value: str) -> str:
        real_date(value); return value

    @model_validator(mode="after")
    def shift_clocks_differ(self) -> "EmployeeIn":
        if self.shift_start == self.shift_end:
            raise ValueError("shift_start and shift_end must differ")
        return self


class PunchInIn(RequestModel):
    emp_code: str
    punched_at: StrictInt | None = None
    status: Literal["PRESENT", "WFH", "ON_DUTY"] = "PRESENT"
    @field_validator("punched_at")
    @classmethod
    def timestamp_is_valid(cls, value: int | None) -> int | None:
        return epoch_input(value) if value is not None else value


class PunchOutIn(RequestModel):
    emp_code: str
    punched_at: StrictInt | None = None
    @field_validator("punched_at")
    @classmethod
    def timestamp_is_valid(cls, value: int | None) -> int | None:
        return epoch_input(value) if value is not None else value


class RegularizeIn(RequestModel):
    status: Literal["PRESENT", "WFH", "ON_DUTY", "ABSENT", "LEAVE"] | None = None
    punch_in: StrictInt | None = None
    punch_out: StrictInt | None = None
    reason: str = Field(min_length=5, max_length=200)
    regularized_by: str = Field(min_length=1, max_length=50)
    @field_validator("punch_in", "punch_out")
    @classmethod
    def timestamp_is_valid(cls, value: int | None) -> int | None:
        return epoch_input(value) if value is not None else value

    @model_validator(mode="after")
    def reject_null_status(self) -> "RegularizeIn":
        """An omitted status is allowed; explicitly sending null is not a valid status."""
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null")
        return self


# ---------- Database startup and reusable queries ----------
def indexes() -> None:
    """Indexes enforce natural keys and support the most important read paths."""
    db.employees.create_index([("emp_code", ASCENDING)], unique=True, name="employee_code_unique")
    db.employees.create_index([("department", ASCENDING), ("joined_on", ASCENDING)], name="department_joined")
    # The unfiltered department summary starts from every department, so its
    # month-end eligibility test must also have a leading joined_on index.
    db.employees.create_index([("joined_on", ASCENDING)], name="joined_on_lookup")
    db.attendance_logs.create_index([("emp_code", ASCENDING), ("date", ASCENDING)], unique=True, name="employee_date_unique")
    db.attendance_logs.create_index([("date", DESCENDING), ("emp_code", ASCENDING)], name="date_desc_employee")
    # Punch-out selects the newest earlier punch for one employee; this index
    # supports both its employee equality filter and descending punch-time sort.
    db.attendance_logs.create_index([("emp_code", ASCENDING), ("punch_in", DESCENDING)], name="employee_punch_in_desc")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Index creation is idempotent, so a clean clone needs no manual database setup."""
    indexes()
    yield


app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0", lifespan=lifespan)


def employee_or_404(code: str) -> dict[str, Any]:
    """Centralise the employee-exists rule used by all employee-specific endpoints."""
    row = db.employees.find_one({"emp_code": code})
    if not row:
        raise HTTPException(404, "employee not found")
    return row


def skip_for(page: int, size: int) -> int:
    """R10 pagination is one-based, so page 1 must skip zero rows."""
    if page < 1 or size < 1 or size > 100:
        fail("page must be at least 1 and page_size must be from 1 to 100")
    return (page - 1) * size


def list_filter(emp_code: str | None, date_from: str | None, date_to: str | None, status: str | None) -> dict[str, Any]:
    """Share identical filter validation between attendance and its explain endpoint."""
    if date_from: real_date(date_from)
    if date_to: real_date(date_to)
    if date_from and date_to and date_from > date_to: fail("date_from cannot be after date_to")
    if status is not None and status not in ALL_STATUS: fail("invalid status")
    query: dict[str, Any] = {}
    if emp_code is not None: query["emp_code"] = emp_code
    if status is not None: query["status"] = status
    if date_from or date_to:
        query["date"] = ({"$gte": date_from} if date_from else {}) | ({"$lte": date_to} if date_to else {})
    return query


# ---------- CRUD endpoints ----------
@app.get("/health")
def health() -> dict[str, str]:
    """A service is ready only when its required database responds to ping."""
    try: db.command("ping")
    except PyMongoError: raise HTTPException(503, "database unavailable")
    return {"status": "ok"}


@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn) -> dict[str, Any]:
    """Insert directly; the unique index, not a race-prone pre-check, owns uniqueness."""
    row = body.model_dump() | {"created_at": now_second()}
    try: db.employees.insert_one(row)
    except DuplicateKeyError: raise HTTPException(409, "emp_code already exists")
    return employee_out(row)


@app.get("/employees")
def list_employees(department: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    """Sort and page in MongoDB so results are stable and scalable."""
    query = {"department": department} if department is not None else {}
    rows = db.employees.find(query).sort("emp_code", 1).skip(skip_for(page, page_size)).limit(page_size)
    return {"items": [employee_out(row) for row in rows], "total": db.employees.count_documents(query), "page": page, "page_size": page_size}


@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn) -> dict[str, Any]:
    """Create the one allowed record for an employee/day; duplicate key handles races."""
    employee = employee_or_404(body.emp_code)
    punched = utc_from_ms(body.punched_at) if body.punched_at is not None else now_second()
    row = {"emp_code": body.emp_code, "date": attendance_day(punched, employee), "status": body.status, "punch_in": punched, "punch_out": None, "history": []}
    row.update(calculated(employee, row))
    try: db.attendance_logs.insert_one(row)
    except DuplicateKeyError: raise HTTPException(409, "already punched in for this date")
    return attendance_out(row)


@app.post("/attendance/punch-out")
def punch_out(body: PunchOutIn) -> dict[str, Any]:
    """Close the newest eligible record atomically, including an overnight open record."""
    employee = employee_or_404(body.emp_code)
    punched = utc_from_ms(body.punched_at) if body.punched_at is not None else now_second()
    row = db.attendance_logs.find_one({"emp_code": body.emp_code, "punch_in": {"$lte": punched}}, sort=[("punch_in", -1)])
    if not row: raise HTTPException(404, "no punch-in found")
    if row.get("punch_out") is not None: raise HTTPException(409, "attendance record is already punched out")
    duration = int((punched - aware_utc(row["punch_in"])).total_seconds())
    if duration <= 0 or duration > 86400: fail("punch_out must be after punch_in and within 24 hours")
    final = defaults(dict(row)); final["punch_out"] = punched
    updated = db.attendance_logs.find_one_and_update({"_id": row["_id"], "punch_out": None}, {"$set": {"punch_out": punched, **calculated(employee, final)}}, return_document=ReturnDocument.AFTER)
    if not updated: raise HTTPException(409, "attendance record is already punched out")
    return attendance_out(updated)


@app.get("/attendance")
def list_attendance(emp_code: str | None = None, date_from: str | None = None, date_to: str | None = None, status: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    """Never load and sort the entire attendance collection in Python."""
    query = list_filter(emp_code, date_from, date_to, status)
    rows = db.attendance_logs.find(query).sort([("date", -1), ("emp_code", 1)]).skip(skip_for(page, page_size)).limit(page_size)
    return {"items": [attendance_out(row) for row in rows], "total": db.attendance_logs.count_documents(query), "page": page, "page_size": page_size}


@app.patch("/attendance/{emp_code}/{date}")
def regularize(emp_code: str, date: str, body: RegularizeIn) -> dict[str, Any]:
    """Correct a record and append one immutable audit entry without lost updates."""
    real_date(date); employee = employee_or_404(emp_code)
    old = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    if not old: raise HTTPException(404, "attendance record not found")
    fields = body.model_fields_set
    if ("punch_in" in fields and body.punch_in is None) or ("punch_out" in fields and body.punch_out is None): fail("punch times must be epoch milliseconds when supplied")
    new = defaults(dict(old))
    if "status" in fields: new["status"] = body.status
    if "punch_in" in fields: new["punch_in"] = utc_from_ms(body.punch_in)
    if "punch_out" in fields: new["punch_out"] = utc_from_ms(body.punch_out)
    if new["status"] in {"ABSENT", "LEAVE"}:
        if "punch_in" in fields or "punch_out" in fields: fail("ABSENT and LEAVE cannot be supplied with punch times")
        new["punch_in"], new["punch_out"] = None, None
    elif not new.get("punch_in"): fail("a presence status requires punch_in")
    if new.get("punch_in") and attendance_day(new["punch_in"], employee) != date: fail("punch_in must belong to the record attendance date")
    if new.get("punch_out"):
        duration = int((aware_utc(new["punch_out"]) - aware_utc(new["punch_in"])).total_seconds())
        if duration <= 0 or duration > 86400: fail("punch_out must be after punch_in and within 24 hours")
    new.update(calculated(employee, new))
    tracked = ["status", "punch_in", "punch_out", "work_hours", "late_minutes", "overtime_minutes", "half_day"]
    changes = {key: {"from": old.get(key), "to": new.get(key)} for key in tracked if old.get(key) != new.get(key)}
    if not changes: fail("regularization must change at least one value")
    # Matching the previously-read values is optimistic locking: a concurrent
    # correction becomes a visible 409 rather than silently removing audit work.
    lock = {key: old.get(key) for key in tracked}
    audit = {"at": now_second(), "by": body.regularized_by, "reason": body.reason, "changes": changes}
    updated = db.attendance_logs.find_one_and_update({"_id": old["_id"], **lock}, {"$set": {key: new.get(key) for key in tracked}, "$push": {"history": audit}}, return_document=ReturnDocument.AFTER)
    if not updated: raise HTTPException(409, "attendance record changed; retry the correction")
    return attendance_out(updated)


# ---------- Aggregation pipeline builders ----------
def month_match(month: str) -> tuple[date, date, dict[str, Any]]:
    """An index-friendly string range matches the stored YYYY-MM-DD dates."""
    start, end = real_month(month)
    return start, end, {"date": {"$gte": start.isoformat(), "$lte": end.isoformat()}}


def weekday(field: str = "$date") -> dict[str, Any]:
    """Reusable MongoDB predicate for Mon-Fri calendar records."""
    return {"$lte": [{"$isoDayOfWeek": {"$dateFromString": {"dateString": field}}}, 5]}


def employee_month_pipeline(code: str, month: str) -> list[dict[str, Any]]:
    """Read stored derived values for an employee's monthly summary."""
    _, _, dates = month_match(month)
    return [{"$match": {"emp_code": code, **dates}}, {"$set": {"weekday": weekday()}}, {"$group": {"_id": None,
        "present_days": {"$sum": {"$cond": [{"$and": ["$weekday", {"$in": ["$status", list(PRESENT)]}]}, {"$cond": [{"$ifNull": ["$half_day", False]}, .5, 1]}, 0]}},
        "leave_days": {"$sum": {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]}},
        "late_count": {"$sum": {"$cond": [{"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]}, 1, 0]}},
        "total_late_minutes": {"$sum": {"$ifNull": ["$late_minutes", 0]}}, "total_overtime_minutes": {"$sum": {"$ifNull": ["$overtime_minutes", 0]}}}}, {"$project": {"_id": 0, "present_days": {"$round": ["$present_days", 2]}, "leave_days": 1, "late_count": 1, "total_late_minutes": 1, "total_overtime_minutes": 1}}]


@app.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly(emp_code: str, month: str) -> dict[str, Any]:
    """Aggregation supplies log totals; a tiny calendar count supplies working days."""
    employee = employee_or_404(emp_code); start, end, _ = month_match(month)
    total = next(iter(db.attendance_logs.aggregate(employee_month_pipeline(emp_code, month))), {})
    join = max(start, real_date(employee["joined_on"]))
    working = sum(1 for i in range((end - join).days + 1) if join <= end and (join + timedelta(days=i)).weekday() < 5)
    present_days = total.get("present_days", 0)
    # This is a percentage rate, so R8 specifies four decimal places.
    return {"emp_code": emp_code, "month": month, "working_days": working, "present_days": present_days, "leave_days": total.get("leave_days", 0), "late_count": total.get("late_count", 0), "total_late_minutes": total.get("total_late_minutes", 0), "total_overtime_minutes": total.get("total_overtime_minutes", 0), "attendance_pct": half_up(Decimal(str(present_days * 100)) / Decimal(working), "0.0001") if working else None}


def summary_pipeline(month: str, department: str | None) -> list[dict[str, Any]]:
    """Union eligible employees with per-employee log aggregates.

    The employee stream preserves headcount for people with no attendance logs.
    Attendance is scanned once for the month, reduced to one row per employee,
    then joined to employee details instead of running one indexed lookup per
    employee and unwinding every log into the outer department group.
    """
    _, end, dates = month_match(month)
    employees_match: dict[str, Any] = {"joined_on": {"$lte": end.isoformat()}}
    if department is not None:
        employees_match["department"] = department

    present_condition = {"$and": ["$weekday", {"$in": ["$status", list(PRESENT)]}]}
    has_work_hours = {"$and": [
        {"$in": ["$status", list(PRESENT)]},
        {"$ne": [{"$ifNull": ["$work_hours", None]}, None]},
    ]}
    per_employee_logs: list[dict[str, Any]] = [
        {"$match": dates},
        {"$set": {"weekday": weekday()}},
        {"$group": {
            "_id": "$emp_code",
            "present_days": {"$sum": {"$cond": [present_condition, {"$cond": [{"$ifNull": ["$half_day", False]}, .5, 1]}, 0]}},
            "work_hours_sum": {"$sum": {"$cond": [has_work_hours, "$work_hours", 0]}},
            "work_hours_count": {"$sum": {"$cond": [has_work_hours, 1, 0]}},
            "late_count": {"$sum": {"$cond": [{"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]}, 1, 0]}},
            "total_late_minutes": {"$sum": {"$ifNull": ["$late_minutes", 0]}},
            "leave_count": {"$sum": {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]}},
            "on_duty_count": {"$sum": {"$cond": [{"$eq": ["$status", "ON_DUTY"]}, 1, 0]}},
        }},
        {"$lookup": {"from": "employees", "localField": "_id", "foreignField": "emp_code", "as": "employee"}},
        {"$unwind": "$employee"},
        {"$match": {"employee.joined_on": {"$lte": end.isoformat()}}},
    ]
    if department is not None:
        per_employee_logs.append({"$match": {"employee.department": department}})
    per_employee_logs.append({"$project": {
        "_id": 0,
        "department": "$employee.department",
        "headcount": {"$literal": 0},
        "present_days": 1,
        "work_hours_sum": 1,
        "work_hours_count": 1,
        "late_count": 1,
        "total_late_minutes": 1,
        "leave_count": 1,
        "on_duty_count": 1,
    }})

    return [
        {"$match": employees_match},
        {"$project": {"_id": 0, "department": 1, "headcount": {"$literal": 1}, "present_days": {"$literal": 0}, "work_hours_sum": {"$literal": 0}, "work_hours_count": {"$literal": 0}, "late_count": {"$literal": 0}, "total_late_minutes": {"$literal": 0}, "leave_count": {"$literal": 0}, "on_duty_count": {"$literal": 0}}},
        {"$unionWith": {"coll": "attendance_logs", "pipeline": per_employee_logs}},
        {"$group": {
            "_id": "$department",
            "headcount": {"$sum": "$headcount"},
            "present_days": {"$sum": "$present_days"},
            "work_hours_sum": {"$sum": "$work_hours_sum"},
            "work_hours_count": {"$sum": "$work_hours_count"},
            "late_count": {"$sum": "$late_count"},
            "total_late_minutes": {"$sum": "$total_late_minutes"},
            "leave_count": {"$sum": "$leave_count"},
            "on_duty_count": {"$sum": "$on_duty_count"},
        }},
        {"$project": {"_id": 0, "department": "$_id", "headcount": 1, "present_days": 1,
            "avg_work_hours": {"$cond": [{"$gt": ["$work_hours_count", 0]}, {"$divide": ["$work_hours_sum", "$work_hours_count"]}, None]},
            "late_count": 1, "total_late_minutes": 1, "leave_count": 1, "on_duty_count": 1}},
        {"$sort": {"department": 1}},
    ]


@app.get("/analytics/departments/summary")
def department_summary(month: str, department: str | None = None) -> dict[str, Any]:
    """Round only the final reported average, as R8 requires."""
    rows = list(db.employees.aggregate(summary_pipeline(month, department)))
    for row in rows:
        if row["avg_work_hours"] is not None: row["avg_work_hours"] = half_up(Decimal(str(row["avg_work_hours"])))
    return {"month": month, "items": rows}


def leaderboard_pipeline(month: str, limit: int, department: str | None) -> list[dict[str, Any]]:
    """Aggregate attendance per employee before joining names/departments.

    Joining once per punch scales with employees who have records in the month,
    rather than with every attendance document. $rank still runs before limit
    so all ties at the requested cutoff remain included.
    """
    _, _, dates = month_match(month)
    pipeline: list[dict[str, Any]] = [
        {"$match": dates},
        {"$group": {
            "_id": "$emp_code",
            "total_late_minutes": {"$sum": {"$ifNull": ["$late_minutes", 0]}},
            "late_count": {"$sum": {"$cond": [{"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]}, 1, 0]}},
        }},
        {"$match": {"total_late_minutes": {"$gt": 0}}},
        {"$lookup": {"from": "employees", "localField": "_id", "foreignField": "emp_code", "as": "employee"}},
        {"$unwind": "$employee"},
    ]
    if department is not None:
        pipeline.append({"$match": {"employee.department": department}})
    return pipeline + [
        {"$set": {"name": "$employee.name", "department": "$employee.department"}},
        {"$setWindowFields": {"sortBy": {"total_late_minutes": -1}, "output": {"rank": {"$rank": {}}}}},
        {"$match": {"rank": {"$lte": limit}}},
        {"$project": {"_id": 0, "emp_code": "$_id", "name": 1, "department": 1, "total_late_minutes": 1, "late_count": 1, "rank": 1}},
        {"$sort": {"total_late_minutes": -1, "emp_code": 1}},
    ]


@app.get("/analytics/leaderboard/late")
def leaderboard(month: str, limit: int = Query(10, ge=1, le=50), department: str | None = None) -> dict[str, Any]:
    """Return every tied row at the requested cutoff, even if that exceeds limit."""
    return {"month": month, "items": list(db.attendance_logs.aggregate(leaderboard_pipeline(month, limit, department)))}


# The trend endpoint's pipeline is intentionally reused by explain below.  That
# prevents an explain plan from accidentally measuring different work.
def trend_pipeline(department: str, start: date, end: date) -> list[dict[str, Any]]:
    """Use employee/date index lookups, then $densify no-log days in MongoDB.

    Starting from the department's employees avoids joining every matching
    attendance row back to employees. The correlated lookup can use the unique
    (emp_code, date) index and returns only this department's requested logs.
    """
    lo, hi = datetime.combine(start, time.min, UTC), datetime.combine(end + timedelta(days=1), time.min, UTC)
    seed = [{"$match": {"department": department}}, {"$limit": 1}, {"$project": {"day": {"$literal": lo}, "present_count": {"$literal": 0}, "late_count": {"$literal": 0}}}]
    department_logs = [
        {"$match": {"department": department}},
        {"$lookup": {
            "from": "attendance_logs",
            "let": {"employee_code": "$emp_code"},
            "pipeline": [
                {"$match": {"$expr": {"$eq": ["$emp_code", "$$employee_code"]}, "date": {"$gte": start.isoformat(), "$lte": end.isoformat()}}},
                {"$set": {"day": {"$dateFromString": {"dateString": "$date"}}}},
                {"$project": {
                    "_id": 0,
                    "day": 1,
                    "present_count": {"$cond": [{"$in": ["$status", list(PRESENT)]}, {"$cond": [{"$ifNull": ["$half_day", False]}, .5, 1]}, 0]},
                    "late_count": {"$cond": [{"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]}, 1, 0]},
                }},
            ],
            "as": "daily_logs",
        }},
        {"$unwind": "$daily_logs"},
        {"$replaceRoot": {"newRoot": "$daily_logs"}},
    ]
    return seed + [
        {"$unionWith": {"coll": "employees", "pipeline": department_logs}},
        {"$group": {"_id": "$day", "present_count": {"$sum": "$present_count"}, "late_count": {"$sum": "$late_count"}}},
        {"$project": {"_id": 0, "day": "$_id", "present_count": 1, "late_count": 1}},
        {"$densify": {"field": "day", "range": {"step": 1, "unit": "day", "bounds": [lo, hi]}}},
        {"$match": {"day": {"$lt": hi}}},
        {"$set": {"date": {"$dateToString": {"date": "$day", "format": "%Y-%m-%d", "timezone": "UTC"}}, "is_working_day": {"$lte": [{"$isoDayOfWeek": "$day"}, 5]}}},
        {"$lookup": {"from": "employees", "let": {"date": "$date"}, "pipeline": [{"$match": {"department": department}}, {"$match": {"$expr": {"$lte": ["$joined_on", "$$date"]}}}, {"$count": "n"}], "as": "people"}},
        {"$set": {"headcount": {"$ifNull": [{"$first": "$people.n"}, 0]}, "present_count": {"$ifNull": ["$present_count", 0]}, "late_count": {"$ifNull": ["$late_count", 0]}}},
        {"$set": {"attendance_rate": {"$cond": [{"$and": ["$is_working_day", {"$gt": ["$headcount", 0]}]}, {"$divide": ["$present_count", "$headcount"]}, None]}}},
        {"$setWindowFields": {"sortBy": {"day": 1}, "output": {"moving_avg_7d": {"$avg": "$attendance_rate", "window": {"documents": [-6, 0]}}}}},
        {"$project": {"_id": 0, "date": 1, "is_working_day": 1, "headcount": 1, "present_count": 1, "late_count": 1, "attendance_rate": 1, "moving_avg_7d": 1}},
        {"$sort": {"date": 1}},
    ]


@app.get("/analytics/departments/{department}/trend")
def trend(department: str, from_: str = Query(alias="from"), to: str = Query(...)) -> dict[str, Any]:
    """Return every requested calendar day and R8-round rate output to four places."""
    start, end = real_date(from_), real_date(to)
    if end < start or (end - start).days + 1 > 92: fail("date range must be ordered and no longer than 92 days")
    if not db.employees.find_one({"department": department}, {"_id": 1}): raise HTTPException(404, "department not found")
    rows = list(db.employees.aggregate(trend_pipeline(department, start, end)))
    for row in rows:
        for key in ("attendance_rate", "moving_avg_7d"):
            if row[key] is not None: row[key] = half_up(Decimal(str(row[key])), "0.0001")
    return {"department": department, "items": rows}


# ---------- Explain endpoint ----------
@app.get("/admin/explain/{endpoint}")
def explain(endpoint: Literal["attendance_list", "employee_monthly", "department_summary", "late_leaderboard", "department_trend"], emp_code: str | None = None, month: str | None = None, department: str | None = None, limit: int = Query(10, ge=1, le=50), date_from: str | None = None, date_to: str | None = None, status: str | None = None, from_: str | None = Query(None, alias="from"), to: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    """Run executionStats against the exact main query/pipeline the real endpoint uses."""
    if endpoint == "attendance_list":
        command, collection = {"find": "attendance_logs", "filter": list_filter(emp_code, date_from, date_to, status), "sort": {"date": -1, "emp_code": 1}, "skip": skip_for(page, page_size), "limit": page_size}, "attendance_logs"
    elif endpoint == "employee_monthly":
        if not emp_code or not month: fail("employee_monthly requires emp_code and month")
        command, collection = {"aggregate": "attendance_logs", "pipeline": employee_month_pipeline(emp_code, month), "cursor": {}}, "attendance_logs"
    elif endpoint == "department_summary":
        if not month: fail("department_summary requires month")
        command, collection = {"aggregate": "employees", "pipeline": summary_pipeline(month, department), "cursor": {}}, "employees"
    elif endpoint == "late_leaderboard":
        if not month: fail("late_leaderboard requires month")
        command, collection = {"aggregate": "attendance_logs", "pipeline": leaderboard_pipeline(month, limit, department), "cursor": {}}, "attendance_logs"
    else:
        if not department or not from_ or not to: fail("department_trend requires department, from, and to")
        start, end = real_date(from_), real_date(to)
        if end < start or (end - start).days + 1 > 92: fail("date range must be ordered and no longer than 92 days")
        command, collection = {"aggregate": "employees", "pipeline": trend_pipeline(department, start, end), "cursor": {}}, "employees"
    raw = db.command({"explain": command, "verbosity": "executionStats"})
    return {"endpoint": endpoint, "collection": collection, "explain": json_util.loads(json_util.dumps(raw))}
