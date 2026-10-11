# Starter code review

The starter runs, but several ordinary-looking inputs and concurrent requests violate the contract. I recorded the defects below by starter function; line numbers are omitted because the file has since been replaced and line numbers would be misleading.

| # | Where | What is wrong | How to notice | How fixed |
|---|---|---|---|---|
| 1 | `health` | It always reports ready without checking MongoDB. | Stop MongoDB and call `/health`; starter still says `ok`. | Ping MongoDB and return 503 on database failure. |
| 2 | Startup | No indexes are created. Duplicate employee codes and daily attendance records are not database-enforced; large list/analytics queries have no planned indexes. | Race two creates/punch-ins; inspect query plans on a large collection. | Create unique business-key indexes and read-path indexes at startup. |
| 3 | `EmployeeIn` | It lacks contract validation for employee code, email, string lengths, dates, shift times, and equal start/end times. | Send malformed fields or identical shift times. | Add Pydantic field and model validation. |
| 4 | `create_employee` | Check-then-insert is racy; timestamp is naive server-local time; response returns a datetime rather than epoch milliseconds. | Concurrent duplicate requests can both pass the check; inspect response type/time zone. | Insert directly under a unique index, catch duplicate-key as 409, store UTC, serialize to epoch ms. |
| 5 | `list_employees` | `skip = page * page_size` skips page one, `total` ignores the department filter, and results are not sorted. | With 25 employees, request page 1 and compare filtered totals. | Use `(page - 1) * page_size`, count the same filter, and sort by employee code. |
| 6 | `compute_late_minutes` | It uses the punch-in's existing calendar date without converting to IST and does not explicitly apply whole-second truncation. | Use a UTC instant near the IST date boundary or exact grace boundary. | Convert to IST attendance date and calculate strict greater-than-10-minute grace from truncated seconds. |
| 7 | `compute_work_hours` | Built-in `round` uses binary floating point and ties-to-even rather than required decimal half-up. | Test a duration whose hours round exactly at a half-cent boundary. | Use Decimal and `ROUND_HALF_UP` on whole seconds. |
| 8 | `compute_overtime` | It mixes a timezone-aware shift end with a potentially naive punch-out, misses next-day end for overnight shifts, and counts any positive overtime instead of requiring 30 minutes. | Punch out shortly after end, or use an overnight shift. | Build the correct IST shift-end instant and apply the 30-minute threshold. |
| 9 | `create_employee` and `punch_in` | They can expose Mongo `_id`-derived IDs or BSON datetime values not allowed by the public API. | Inspect JSON response fields and types. | Serialize through explicit response helpers; never expose internal IDs. |
| 10 | `punch_in` | Unknown employees cause a server error; arbitrary statuses and bad timestamp formats are accepted; falsey `punched_at` is treated as omitted. | Punch for an unknown code, use `ABSENT`, or pass seconds instead of ms. | Validate strict inputs and status, return 404, and distinguish omitted timestamp from numeric values. |
| 11 | `punch_in` | It uses host-local time for instants and the date, does not apply IST/overnight attendance-day rules, and has a check-then-insert race. | Change host timezone, test early-morning overnight punch, or submit simultaneous duplicate requests. | Normalize to UTC whole seconds, derive R1 date, and rely on the unique `(emp_code,date)` index. |
| 12 | `list_attendance` | It reads the full collection and sorts in Python, which is slow at 100k rows; sort lacks the employee-code tie-breaker; page bounds and date-range order are unchecked. | Load a large dataset, request page 1, or send reversed dates. | Use Mongo sort/skip/limit and filtered count, validate inputs and stable sort. |
| 13 | `list_attendance` | It returns internal IDs and BSON datetimes, and does not supply defaults for legacy missing `history`/`half_day` fields. | Inspect seeded legacy record output. | Normalize legacy defaults and serialize all instant fields, including nested audit changes. |
| 14 | Missing endpoints | Punch-out, correction, all analytics, and explain endpoints are absent. | Call any path listed in the OpenAPI file. | Implemented endpoints and aggregation pipeline builders in the replacement application. |

## Checked and retained

- `load_dotenv()` is appropriate: python-dotenv leaves real environment values in place unless `override=True` is requested.
- The default Mongo URI and database name are explicitly allowed for local convenience; deployment values come from `MONGO_URI` and `MONGO_DB`.
- Employee business identity is `emp_code`; MongoDB `_id` is an internal storage detail and must not be used in the API.
