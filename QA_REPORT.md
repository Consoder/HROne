# QA Report — Attendance API and React UI

**Run date:** 12 October 2026
**Result:** Backend suite: 52/52 passing (5 existing + 47 added edge cases). The initial frontend run exposed two defects; both are documented as fixed in the repair follow-up below. The production frontend build passes.

## Test environment and safety

- API tests ran with Python 3.11 against the disposable MongoDB database `attendance_api_test`.
- QA tests use only `EMP7701`–`EMP7705` and remove only their own attendance and employee records. Each scenario clears its own attendance fixtures so intentionally open shifts cannot leak into another test.
- The separate live app at `127.0.0.1:8000` returned `{"status":"ok"}` from `/health`; the browser UI loaded its sample employee and attendance data. No live punch action was clicked.
- Frontend interaction checks were manual in the local browser at 576px-wide viewport. This is not a substitute for a full automated browser test harness.

## Backend automated coverage

`tests/test_qa_edges.py` adds 47 named tests. Together with the five existing integration tests, the suite passes 52 tests.

| Area | Cases exercised |
|---|---|
| Employee input | Invalid employee-code shape, malformed email, whitespace-only name/department, impossible date, noncanonical clock, equal shift clocks, duplicate code |
| Punch input and time boundaries | Unknown employee, ignored client-derived field, seconds/string/float/bool timestamps, values below/above epoch range, early arrival, exactly 10-minute grace and 1-second-over boundary |
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

## HTTP load check — 2026-10-12

Ran `tests/load_test.py` against a separate Uvicorn process on port 8010, configured to use the synthetic `attendance_scale` database (1,000 employees and 100,000 attendance rows; explain reported MongoDB 8.3.2). All measured requests were read-only GETs. Seven route families were exercised: health, employees, attendance list, employee monthly, department summary, late leaderboard, and a seven-day department trend. The original baseline used the pre-refactor pipelines. The first attempted post-change run accidentally reused an already-imported process, so it is excluded; the server was restarted and the optimized source was confirmed in `/admin/explain/department_summary` before the results below.

| Profile | Timed requests | HTTP errors | Duration | Throughput | Overall p50 | Overall p95 | Overall p99 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 client × 1 route pass | 7 | 0 | 20.636 s | 0.34 req/s | 51.2 ms | 12,238.9 ms | 12,238.9 ms |
| 5 clients × 4 route passes | 140 | 0 | 145.111 s | 0.96 req/s | 94.8 ms | 23,546.1 ms | 23,940.3 ms |

After refactoring and restarting the server from the updated code, the same request profiles produced:

| Profile | Timed requests | HTTP errors | Duration | Throughput | Overall p50 | Overall p95 | Overall p99 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 client × 1 route pass | 7 | 0 | 3.971 s | 1.76 req/s | 40.5 ms | 2,435.7 ms | 2,435.7 ms |
| 5 clients × 4 route passes | 140 | 0 | 31.504 s | 4.44 req/s | 144.6 ms | 4,785.6 ms | 6,425.0 ms |

Optimized 5-client per-route p50s were: health 25.9 ms, employees 42.8 ms, attendance list 142.9 ms, employee monthly 45.0 ms, department summary 4,544.8 ms, late leaderboard 1,845.1 ms, and department trend 709.8 ms. Compared with the original 5-client baseline, leaderboard p50 improved about 92% and trend p50 about 92%; department summary improved only about 3%, and remains the dominant bottleneck. The refactor did not materially improve the summary, so it should not be described as a full performance pass. All 140 requests returned HTTP 200 with valid JSON; no load errors occurred.

The 5-client per-route p50 latencies were: health 15 ms, employees 38 ms, attendance list 95 ms, employee monthly 38 ms, department summary 4,692 ms, late leaderboard 22,551 ms, department trend 8,428 ms. Every request returned HTTP 200, but the analytical endpoints are a major latency bottleneck even at this modest concurrency; the 22.6-second leaderboard p50 and 8.4-second trend p50 make this a correctness pass but not a performance pass under the measured profile. Single-client observations were also slow for those aggregations: department summary 2.67 s, leaderboard 12.24 s, trend 5.63 s. The indexed explain plans therefore do not imply acceptable runtime.

**Conclusion and limits:** This is a functional HTTP-success pass, but not a complete latency pass: no formal latency threshold was supplied, and summary remains ~4.5 s p50 at 5 clients. This is a local development benchmark, not production capacity/SLO certification. It uses only GET traffic and does not model internet/network latency, multi-process deployment, write contention, or a sustained soak test. The harness expects the existing synthetic database; its generator is not included in the submission.

### Department-summary follow-up — covering index

Added the date-leading `department_summary_cover` index over `date`, `emp_code`, `status`, `half_day`, `work_hours`, and `late_minutes`. These are the fields read by the month match and grouping stages. On the 100k synthetic database, the summary's execution plan now uses `PROJECTION_COVERED` with `IXSCAN`, examines 31,000 keys and zero attendance documents for January, and the index occupies 2.74 MB.

Repeated the same warmed GET profiles after starting a fresh server with the index:

| Profile | Timed requests | HTTP errors | Duration | Throughput | Overall p50 | Overall p95 | Overall p99 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 client × 1 route pass | 7 | 0 | 1.451 s | 4.82 req/s | 61.0 ms | 856.4 ms | 856.4 ms |
| 5 clients × 4 route passes | 140 | 0 | 14.517 s | 9.64 req/s | 58.7 ms | 1,980.2 ms | 2,858.5 ms |

At 5 clients, department-summary p50/p95 was 1,949.9/2,858.5 ms, down from 4,544.8/6,425.0 ms immediately before this index (about 57% p50 improvement). The test returned 140/140 valid HTTP 200 responses. The wider index increases write and storage costs; at this dataset it is about 2.74 MB. The endpoint is materially faster but still the slowest route, so no unspecified latency target is claimed as passed.
