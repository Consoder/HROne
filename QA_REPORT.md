# QA Report — Attendance API and React UI

**Run date:** 12 October 2026
**Result:** Backend suite: 50/50 passing (5 existing + 45 added edge cases). The initial frontend run exposed two defects; both are documented as fixed in the repair follow-up below. The production frontend build passes.

## Test environment and safety

- API tests ran with Python 3.11 against the disposable MongoDB database `attendance_api_test`.
- QA tests use only `EMP7701`–`EMP7705` and remove only their own attendance and employee records. Each scenario clears its own attendance fixtures so intentionally open shifts cannot leak into another test.
- The separate live app at `127.0.0.1:8000` returned `{"status":"ok"}` from `/health`; the browser UI loaded its sample employee and attendance data. No live punch action was clicked.
- Frontend interaction checks were manual in the local browser at 576px-wide viewport. This is not a substitute for a full automated browser test harness.

## Backend automated coverage

`tests/test_qa_edges.py` adds 45 named tests. Together with the five existing integration tests, the suite passes 50 tests.

| Area | Cases exercised |
|---|---|
| Employee input | Invalid employee-code shape, malformed email, whitespace-only name/department, impossible date, noncanonical clock, equal shift clocks, duplicate code |
| Punch input and time boundaries | Unknown employee, ignored client-derived field, seconds/string/float/bool timestamps, values below/above epoch range, exactly 10-minute grace and 1-second-over boundary |
| Punch lifecycle | Duplicate same-day punch-in, no punch-in, punch-out at same instant, punch-out before punch-in, >24-hour duration, exact 24-hour duration, repeat punch-out |
| Derived attendance rules | Overtime at 29m59s and exactly 30m, half-day just below 4.5h and exactly 4.5h |
| Overnight shifts | Punch at 05:59:59 belongs to the prior attendance date; punch at 06:00 begins the new date |
| Manual correction | Missing record, impossible date, null status, missing/short audit details, absent with supplied punch, cross-day correction, absent correction clears punches and records history |
| Filters and pagination | Strict month syntax, invalid/reversed attendance dates, pagination lower and upper bounds, stable page separation and totals |
| Analytics | No working days before joining, weekend count exclusion, empty unknown-department summary, competition ranking/tied cutoff, invalid leaderboard cutoff, unknown trend department, trend gap filling/weekend null rates, inclusive 92-day trend, rejected 93-day/reversed trend |
| Explain and concurrency | Required explain parameters and unknown endpoint; existing tests cover natural-key indexes and simultaneous punch-in race |

Run it on Windows from the project root:

```powershell
$env:MONGO_DB = 'attendance_api_test'
py -3.11 -m unittest discover -s tests -v
```

## Frontend browser checks

| # | Check | Result |
|---:|---|---|
| 1 | Open local React page and render app shell | Pass |
| 2 | Landing title and subtitle render | Pass |
| 3 | Mesh Lettering kicker is visible | Pass |
| 4 | Grid Rise tile field renders behind hero content | Pass (visual inspection) |
| 5 | API data populates team headcount and employee list | Pass (7 employees) |
| 6 | Recent attendance record displays status and time | Pass |
| 7 | Employee selector expands and exposes available choices | Pass |
| 8 | Switching to another employee refreshes summary and rows | Pass |
| 9 | Switching back restores the original employee data | Pass |
| 10 | Matching status search retains matching attendance row | Pass |
| 11 | No-match search displays an explicit empty state | Pass |
| 12 | Clear search restores the matching rows | Pass |
| 13 | Select February in the month picker | **Fail — invalid `date_to`** |
| 14 | Restore October after the month test | Pass; error clears |
| 15 | Landing call-to-action navigates to `#dashboard` | Pass |
| 16 | Narrow viewport hero and dashboard remain readable | Pass (visual inspection at 576px) |
| 17 | Current-day KPI and punch button agree with API record | **Fail — UTC/IST date mismatch** |

## Defects found

### QA-FE-01 — Current-day punch state uses UTC instead of the API's IST attendance date (High)

The UI derives `today` using `new Date().toISOString().slice(0, 10)`, which is a UTC date. The backend assigns attendance dates in Asia/Kolkata. At the observed time shortly after midnight IST on 12 October, the dashboard showed a `PRESENT` record dated 12 October but counted zero present today, said “Ready when you are,” enabled “Check in,” and disabled “Check out.” A user can be offered a duplicate punch-in and cannot use the expected checkout action. Derive the business date in `Asia/Kolkata` consistently with the API.

### QA-FE-02 — Attendance list sends the 31st for every selected month (High)

The UI requests `/attendance?...date_to=${selectedMonth}-31`. Choosing February produced the API validation message `date must be a real YYYY-MM-DD value`; months with 30 days have the same issue. Because the shared refresh fails before updating the summary, the month picker showed February while the attendance percentage remained from October. Compute the actual final calendar day for the selected month and avoid showing stale summary values after a failed refresh.

### Additional code-review observations (not included in the 17 interactive checks)

- **QA-FE-03 — Sidebar navigation changes labels, not page content (Medium).** The sidebar click handler only changes `tab`; the dashboard cards and attendance table are rendered unconditionally. On desktop, choosing Employees, Attendance, or Analytics can highlight that destination and change the heading while leaving the Overview content on screen. The sidebar is hidden at the 576px browser viewport used for manual checks, so this is a source-level finding rather than a clicked browser test.
- **QA-FE-04 — Weekday label is hard-coded to Monday (Low).** The date heading prefixes every date with `MONDAY`, even after the calendar date changes. It happened to be correct on the QA run date, Monday 12 October 2026; derive the weekday from the same business timezone as the date.

## Not exercised

- Check-in/check-out clicks against sample employees were deliberately avoided to prevent changing the visible live sample database. The equivalent API workflow and its boundaries are exercised in the isolated integration suite.
- Print/export was not clicked because it opens the browser's print workflow.
- Frontend keyboard-only navigation, screen-reader behavior, real mobile devices, slow-network timing, and cross-browser rendering need dedicated automated/browser-device coverage.

## Frontend repair follow-up — 2026-10-12

The findings above describe the original QA snapshot. The four frontend defects have since been fixed in `web/src/ui.jsx` / `web/src/style.css`:

- The current business date, weekday, and displayed punch times now consistently use `Asia/Kolkata`; the date rolls over while the page remains open.
- Attendance date ranges use the actual final day of the selected month. February 2026's exact API range (`2026-02-01` through `2026-02-28`) returned HTTP 200.
- Navigation now renders distinct Overview, Employees, Attendance, Analytics, and Settings views. Analytics loads department summary and late-arrival leaderboard data from their API endpoints; mobile navigation remains visible and scrollable.
- Attendance loads every page reported by the API rather than silently stopping at the first 100 rows. Overlapping refresh requests cannot replace newer results with older ones, and failed refreshes clear month-scoped data to avoid stale figures.
- Header weekday is no longer fixed to Monday. The previously inert workspace picker is now a non-button label; Help links to the project README; Settings opens its own view.

**Retest:** The browser rendered the employee directory (7 employees), all-company attendance view (2 current-month records), analytics tables (four departments and empty late-arrival state), and corrected Overview punch state (Asha's current-day check-in is recognized; check-in disabled/check-out available). Production Vite build passed. Backend suite passed all 50 integration/edge tests. The browser automation tool could not reliably dispatch a native `input[type=month]` change using its fill operation, so the February test was confirmed directly against the live API and by reviewing the UI's date-bound construction; physical/native date-picker interaction still deserves a manual click-through.

**Scope note:** No check-in/out or print/export action was triggered during this retest, to avoid changing sample attendance data or opening the system print dialog. Employee correction/audit workflows remain available through the API/Swagger rather than this dashboard UI.
