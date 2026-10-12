# Build log

This file is a plain-language record of how the assignment is built. Each entry states what changed, why it matters, and why that approach was selected.

## 2026-10-11 - Read the assignment kit

**What:** Read the problem statement, OpenAPI contract, MongoDB data model, sample data, starter application, and the two submission templates.

**Why:** The contract is spread across several files. The API contract defines behaviour and rules, while the data-model document defines the exact MongoDB shapes that the grader seeds. Reading only the starter code would miss essential requirements.

**Decision:** Treat `openapi.yaml` and `DATA_MODEL.md` as the source of truth. The starter application is intentionally incomplete and is not treated as the intended design.

## 2026-10-11 - Independent pre-build reviews

**What:** Ran two independent requirement reviews before changing code: Ponytail checked API behaviour, validation, edge cases, and readability; RabbitCode checked MongoDB indexes, aggregation design, races, and query performance.

**Why:** This catches errors early, particularly hidden-test cases such as overnight shifts, timestamps, ties, zero-log employees, and simultaneous requests.

**Decision:** Use database-enforced unique indexes plus atomic conditional updates instead of application-level “check then write” logic. Use MongoDB aggregation pipelines for analytics, rather than fetching records into Python.

## Next implementation steps

1. Replace unsafe starter helpers and request models with validated, documented versions.
2. Add startup indexes and safe API-to-MongoDB conversion helpers.
3. Implement employee and attendance workflows, including race-safe punch-in, punch-out, and regularization.
4. Implement aggregation-based analytics and matching explain plans.
5. Test normal and edge cases, then record every verified result here.

## 2026-10-11 - Rebuilt the application structure

**What:** Replaced the starter `app/main.py` with a single structured implementation. It now has separate sections for time rules, JSON/BSON conversion, request validation, indexes, CRUD workflows, aggregation builders, analytics endpoints, and query explanations.

**Why:** The starter only supported a fragile happy path and left most endpoints unimplemented. The new structure makes it possible for a reader to trace an HTTP request from validation through the business rules to MongoDB.

**Important design choices:**

- Time instants are converted from epoch milliseconds to UTC and trimmed to seconds before calculations. IST is used only for attendance dates and shift clocks.
- MongoDB's unique natural keys and conditional writes, rather than pre-write existence checks, handle simultaneous requests safely.
- Analytics read stored computed values and use aggregation pipelines. They do not rebuild metrics from punch times.
- Every MongoDB-only value is converted at the response boundary, keeping internal storage details out of the public API.

## 2026-10-11 - Patch-tool correction

**What:** The first file-replacement patch was rejected by the editing tool because deletion and addition of the same file must be separate operations.

**Why:** This was a tool-format issue, not a source-code issue. No incomplete code was written by that rejected operation.

**Resolution:** Removed the original starter file and then added the complete replacement in a separate patch.

## 2026-10-11 - First static review corrections

**What:** Corrected the regularization route so its path is exactly `/attendance/{emp_code}/{date}`, as required by the published contract. Corrected department headcount logic in the aggregation pipeline.

**Why:** A differently named route parameter changes the generated API contract. The original first-pass department grouping would have counted attendance rows rather than distinct employees, making headcount too high for anyone with multiple logs.

**Why this fix:** The pipeline now gathers unique employee codes with MongoDB's `$addToSet` and calculates `headcount` from that set. This keeps people with zero logs while counting each employee once.

## 2026-10-11 - Syntax and import verification

**What:** Ran Python 3.11 bytecode compilation successfully after the initial implementation and correction.

**Why:** Compilation confirms that Python can parse every block before database testing begins.

**Result:** Passed with Python 3.11. A full import/server test is currently blocked because FastAPI and PyMongo are not installed in the available Python 3.11 environment. Dependency installation or an existing project virtual environment is needed for the next level of verification.

## 2026-10-11 - Documentation and focused rule checks

**What:** Replaced the template contents of `REVIEW.md`, `DECISIONS.md`, and `README.md` with project-specific notes and local run instructions. Tightened input checks for whitespace-only employee names/departments and pagination bounds. Fixed overnight punch-date/time handling and made trend output explicitly return the contract fields.

**Why:** The original templates were still blank, and the starter README described a candidate kit rather than how to run the implementation. Review found that the first code pass had edge cases in overnight handling and response shape.

**Checks:** Python 3.11 compilation passed. Focused helper checks confirmed: 09:40:00 is within grace, 09:40:01 is 10 late minutes, a 22:00-06:00 punch at 00:30 IST belongs to the previous attendance day, and an overnight punch-out at 06:40 IST produces 40 overtime minutes. Epoch booleans are rejected with 422.

**Not verified yet:** Full HTTP endpoint tests and MongoDB aggregation/explain behavior. This machine currently has no detected MongoDB or Docker command. Starlette's test client also reports that its required `httpx2` package is missing.

## 2026-10-11 - Runtime discovery and final local checks

**What:** Confirmed FastAPI, Pydantic, and PyMongo are installed and that `app.main` imports. Confirmed all 11 required HTTP paths register in FastAPI's OpenAPI document. Docker is present but its engine is stopped, so no MongoDB server is available here.

**Why:** Import and route registration catch application wiring errors; the stopped Docker engine explains why database and aggregation behavior cannot be exercised on this machine.

**Correction:** A direct overnight rule check exposed a time-type comparison edge case. The code now compares timezone-free local clock values and uses the contract's strict “earlier than shift_end” boundary. The attendance date and late calculation both use that same boundary.

**Current verification status:** Python 3.11 compilation and application import have passed. Focused helper checks passed for the ordinary grace boundary, overnight overtime, month parsing, and rejection of booleans as timestamps. The first attempt to test an overnight early punch used a UTC instant that converted to 06:00 IST, so it was not an early-punch test; that result is not counted as evidence. Full endpoint, concurrency, aggregation, and explain-plan tests still require a running MongoDB 6.0+ instance. The installed Starlette test client additionally requires `httpx2`.

**Follow-up:** Re-ran the overnight early-punch case with 00:30 IST (2026-07-06T19:00:00Z). It maps to attendance date 2026-07-06 as required. Its 1,590 late minutes are expected for that deliberately early-before-shift test input.

## 2026-10-11 - Final available local verification attempt

**What:** Started Docker Desktop in the background and retried its engine connection. Also ran a focused Python rule-check batch and Python bytecode compilation.

**Why:** MongoDB-backed API tests are the remaining high-value check; the engine must be available for those tests.

**Results:** The focused checks passed for grace boundary, overtime threshold, half-up rounding, page offsets, and overnight attendance date. Python compilation passed. Docker Desktop still has no reachable engine pipe, so MongoDB-backed endpoint, aggregation, concurrency, and explain tests could not run.

**Completion boundary:** Source and assignment documents have first-pass implementations. The project is not proven submission-ready until the database tests run successfully. No correctness claim is made about the aggregation pipelines based only on Python import/compilation.

## 2026-10-11 - MongoDB 7 sample integration run

**What:** Confirmed Docker Engine was available, pulled `mongo:7`, started the already-created `candidate-kit-mongo` container, installed the missing local `httpx2` test-client dependency, and ran the supplied seed data against an isolated `attendance_test` database.

**Why:** This allowed real requests and MongoDB aggregations to be exercised without touching the default database. The separate database name keeps the sample reset scoped to this assignment run.

**Results:** The app started and `/health`, employee listing, attendance listing, employee monthly summary, department summary, leaderboard, department trend, and all five explain routes returned HTTP 200 against the sample set. Monthly and department numbers looked consistent with the supplied examples. Trend returned the requested five filled days, including dates without records.

**Explain caveat:** The seeded database has only 6 employees and 9 attendance rows. MongoDB chose collection scans for those explain requests (0 `IXSCAN`, with `COLLSCAN` entries). That is a normal small-collection planner choice, but it does not prove the required 100k-row plans use indexes. A representative large dataset still needs an explain test, and any scan there must be fixed.

**Still needed:** Race tests, correction/punch-out endpoint tests, invalid-input checks through HTTP, and 100k-row plan/performance checks.

## 2026-10-12 - Workflow races and 100k query-plan verification

**What:** Re-seeded the isolated sample database, ran live API requests with FastAPI's test client, tested concurrent writes, created a separate 1,000-employee/100,000-attendance-row dataset, and checked every explain route against it.

**Why:** The smaller sample can validate output shape and business rules but cannot show whether query plans scale. Concurrent requests are needed to prove the database indexes are doing their job.

**Race results:** With the app lifespan active, startup created both unique indexes. Eight simultaneous identical punch-ins returned one 201 and seven 409 responses. Eight simultaneous punch-outs returned one 200 and seven 409 responses. A repeated employee create returned 409. One regularization returned 200 and appended an audit entry containing only the changed punch and recomputed work-hours values.

**Scale result and fix:** The first 100k dataset accidentally violated the one-record-per-employee/day data rule, so MongoDB correctly refused the unique index. I rebuilt it with unique employee/date pairs. On the valid 100k dataset, the first department-summary explain used a collection scan because the employee index began with department while the unfiltered summary matches by join date. Added a `joined_on` index. The rerun returned 2 `IXSCAN` entries and 0 `COLLSCAN` entries.

**Explain results after the index fix:** attendance list 2 IXSCAN / 0 COLLSCAN; employee monthly 3 / 0; department summary 2 / 0; late leaderboard 2 / 0; department trend 4 / 0.

**Sample output checks:** Sample-backed health, employee list, attendance list, monthly summary, department summary, leaderboard and trend returned 200. Invalid calendar date returned 422; unknown monthly employee returned 404. Trend returned five requested dates including missing-log weekdays.

**Important test setup note:** A `TestClient` used without a context manager did not run FastAPI lifespan, so it did not create indexes and concurrent requests appeared to all succeed. Repeating tests inside `with TestClient(app)` ran startup and produced the expected one-winner race results. Always use the lifespan in local integration tests.

## 2026-10-12 - Reproducible test suite and contract cleanup

**What:** Added `tests/test_api.py` with integration tests for startup indexes, strict timestamps, missing employees, punch-in/out rules, regularization history, and simultaneous punch-in requests. Added `httpx2` to requirements because the installed Starlette test client requires it. Documented the test command and disposable-database precaution in README.

**Why:** Manual shell checks are hard to repeat and easy to forget. A small test suite gives the user a repeatable way to check important behavior after making changes.

**Test result:** `python -m unittest discover -s tests -v` passed all five tests against MongoDB 7 using the isolated `attendance_api_test` database. Python compilation also passed for app and tests.

**Contract correction found while reviewing outputs:** R8 specifies four decimal places for rates. Employee monthly `attendance_pct` was being rounded to two places, so it now rounds to four. Also made explicit `status: null` invalid during regularization while keeping omitted status valid.

**Important scope:** The integration suite is repeatable but intentionally small. The separate 100k-data explain check remains a development procedure rather than a test that runs on every `unittest` invocation.

## 2026-10-12 - Final verification snapshot

**What:** Re-ran Python compilation and all five explain endpoint checks against the valid 100,000-row `attendance_scale` database after the final code changes.

**Result:** All five explain calls returned 200, each had at least one `IXSCAN`, and none contained `COLLSCAN`: attendance list (2/0), employee monthly (3/0), department summary (2/0), late leaderboard (2/0), department trend (4/0). The five automated integration tests also passed immediately before this final explain run.

**Current state:** Local implementation, required documents, and repeatable integration tests are complete. The task kit folder itself is not a Git repository, so publishing a public repository and submitting its link remain external submission steps; no repository was pushed and no form was submitted.

## 2026-10-12 - React Bits landing components setup

**What:** Added `web/components.json` with the official `@reactbits-starter` and `@reactbits-pro` registry endpoints and Bearer Authorization headers resolved from `${REACTBITS_LICENSE_KEY}`. Added a frontend `.gitignore` so local secrets, installed packages, and generated build output are not committed, plus `.env.local.example` showing the required variable name without containing a real key.

**Why:** The requested Grid Rise, Luminous Type, and Mesh Lettering components are distributed through an authenticated React Bits registry. The secret must stay local while the committed registry configuration remains reusable by the CLI.

**Install attempt:** Started `npx shadcn@latest add @reactbits-starter/grid-rise-tw @reactbits-starter/luminous-type-tw @reactbits-starter/mesh-lettering-tw --yes`. The current shell has no `REACTBITS_LICENSE_KEY`, and `npx` produced no output for over 30 seconds (including a separate CLI version check), so both attempts were stopped. The components were not confirmed installed and have not been represented as installed in the UI.

**Build check:** `npm run build` began transforming but did not return through the npm shim during the check window. Running the local Vite executable directly (`node_modules/.bin/vite.cmd build`) succeeded: 1,907 modules transformed, production assets emitted, exit code 0. Next step: place the valid key in ignored `web/.env.local`, rerun the three registry installs, integrate the imported components in the landing title and hero, then rerun the build.

## 2026-10-12 - Custom landing effects implemented

**What:** Implemented three original React/CSS effects in `web/src/landing-effects.jsx`: Grid Rise uses a small DOM tile field lifted by a pointer-centered ripple; Luminous Type layers dim and spotlight-lit text with a drifting spotlight that follows the pointer over the title; Mesh Lettering uses a slowly animated SVG turbulence/displacement filter for a soft silk-like kicker. Added a people-first attendance hero before the working dashboard and matched its forest-green/mint palette to the existing UI in `web/src/style.css`.

**Why:** The local shell has no React Bits Pro key and the shadcn CLI stalled before providing a registry result. The user then asked for equivalent components from the prompt descriptions, so this implementation avoids the authenticated registry and external component code. It is not represented as an official React Bits Pro installation.

**Verification:** Local Vite production build passed (1,908 modules transformed; exit code 0). Opened `http://127.0.0.1:5173/` and checked the rendered hero plus existing API-backed dashboard content in the browser. The hero title, mesh kicker, responsive layout, and grid backdrop were visible; API-driven employee and attendance sections still rendered below it.

## 2026-10-12 - Backend and frontend edge-case QA

**What:** Added `tests/test_qa_edges.py` with 45 isolated API edge-case tests and `QA_REPORT.md` with the full QA inventory/results. Ran the five existing tests plus all 45 new tests under Python 3.11 against `attendance_api_test`; all 50 pass. The first run exposed fixture leakage between tests that left an open punch behind, so each QA scenario now clears only its own attendance fixtures before running. Additional analytics tests cover competition ranks/ties, weekend attendance, epoch bounds, and trend gap-filling.

**Frontend checks:** Loaded the React app in the browser, checked the landing hero and API data, switched employees, tested match/no-match/clear search, exercised the month picker, restored the default month, and followed the hero CTA. Seventeen manual browser checks were recorded: fifteen pass, two fail. Narrow viewport (576px) layout was visually inspected. No live check-in/out or print action was triggered.

**Bugs found:** `QA_REPORT.md` records two high-severity frontend issues: (1) the browser computes “today” in UTC while API attendance dates use IST, causing an existing current-day punch to look absent and presenting the wrong punch buttons; (2) the month filter always sends day 31, so February and 30-day months fail validation and leave stale analytics visible. Two further source-review observations are documented: sidebar choices change labels but not the shown panel, and the weekday heading is hard-coded to Monday. This was a diagnosis/QA request, so production behavior is unchanged; fixes should be made in a separate implementation step.

**Build/health:** Existing React production build had passed immediately before this QA turn. Live API `/health` returned 200. Browser QA used the running Vite frontend. Backend automated suite is repeatable with `$env:MONGO_DB='attendance_api_test'; py -3.11 -m unittest discover -s tests -v`.

## 2026-10-12 - Frontend defects repaired and verified

**What changed:** Replaced UTC-based current date with an Asia/Kolkata business date (including live midnight rollover), calculated valid month-end days for attendance filters, and made check-in times render in IST. Added actual Employees, Attendance, Analytics, and Settings pages behind the existing sidebar. Analytics now requests the department summary and late leaderboard endpoints. The attendance view loads all result pages instead of silently truncating at 100 records. Refreshes are sequence-guarded to prevent stale responses from overwriting newer month/employee selections; failed refreshes clear stale month data. Made mobile navigation reachable and changed inert workspace/help/settings controls into a label or working destinations.

**Why:** The QA snapshot exposed date/punch disagreement, invalid short-month queries, misleading navigation, and the hard-coded weekday. A first-page-only data request also would have hidden records once a workspace exceeded 100 logs. These fixes address the reported UI breakage and make the visible navigation destinations real.

**Checks:** Rendered and inspected the Overview (correct current-day punch state), Employees (7 directory rows), Attendance (all-company rows), and Analytics (four department summaries plus the empty leaderboard state) in the browser. Confirmed February 2026's real date range returns HTTP 200. Browser automation's `fill` operation did not reliably trigger the native month input's React change event, so its month-picker interaction needs a manual native-picker click-through. Vite production build passed (1,908 modules). Python integration/edge test suite passed all 50 tests against the isolated `attendance_api_test` database.

**Known UI scope:** No sample punch was created/closed as part of browser verification. The UI does not yet expose manual attendance correction/audit editing; that workflow remains available through the documented API/Swagger. Print/export opens the browser print workflow and was not invoked.

## 2026-10-12 - Custom HROne visual marks

**What:** Replaced the generic sidebar and KPI icons with original CSS-drawn marks: an orbit for Overview, a small people cluster for Employees/headcount, attendance ripples for Attendance, signal bars for Analytics, and distinct check/flame/bloom marks for the attendance metrics. Kept compact familiar symbols on utility actions where recognition matters.

**Why:** The stock icon set made the interface feel generic. These small marks use the existing HROne green palette with a warm accent, add personality without adding image assets or dependencies, and keep labels available for accessibility.

**Verification:** Vite production build passed (1,908 modules transformed). Confirmed the app still renders its four navigation destinations and attendance data in the live browser.

## 2026-10-12 - More expressive visuals and block-by-block motion

**What:** Brightened the visual system with softly tinted page lighting, richer hero gradients, colorful elevated KPI badges, and more dimensional panels. Added staggered entrance animations for the hero, page heading, each KPI, dashboard panels, analytics cards, data rows, and footer. Navigation glyphs and the check-in clock have subtle idle motion. Switching page tabs remounts the content stage so each destination gets its entrance sequence. Reduced-motion preferences disable the motion.

**Why:** The prior restrained colors and mostly static surfaces still felt plain; the request was for a more energetic page and animation as each section loads. The movement is brief and staggered to create a clear reading order, while respecting accessibility preferences.

**Verification:** Vite production build passed (1,908 modules transformed). Animations use CSS only; no additional runtime packages or image assets were introduced.

## 2026-10-12 - Stronger visual redesign after feedback

**What:** Changed the art direction to an after-hours greenhouse: deep forest sidebar with citrus active states, warm paper workspace, a more luminous green hero with a large orbit motif, oversized editorial headline, colorful differentiated KPI cards, and softer but higher-contrast panels. Added more dimensional hover states and retained staggered entrance motion on page blocks and data rows.

**Why:** The user said the previous icon/motion polish still looked boring. This update changes the overall palette, surfaces, proportions, and contrast rather than only adding more decorative icons. Existing route behavior and data display remain in place.

**Verification:** Vite production build passed (1,908 modules transformed). Checked the live browser accessibility snapshot after hot reload: Overview and API-backed attendance content remain rendered; reduced-motion support remains enabled.

## 2026-10-12 - Removed hero orbit circles

**What:** Removed the large concentric/orbit decoration from the “Attendance, in rhythm” hero, including its mobile-specific styling and motion. Kept the interactive tile field and headline effects.

**Why:** The user asked for the circles in that hero to be removed.

**Verification:** Vite production build passed (1,908 modules transformed).

## 2026-10-12 - GitHub submission phases

**Phase 1 — Isolate:** The assignment directory previously resolved to `C:\Users\Kartik` as its Git root. Initialized Git metadata inside `candidate_kit` so commits can only contain this assignment. Added `.gitignore` entries for secrets, Python caches/virtual environments, frontend dependencies/build output, and the original `PROBLEM_STATEMENT.docx`.

**Phase 2 — Verify:** Re-ran `py -3.11 -m unittest discover -s tests -v` against `attendance_api_test` (50 tests passed) and `web\\node_modules\\.bin\\vite.cmd build` from `web/` (production build passed). Confirmed the GitHub target `Consoder/HROne` is public and empty before initial publication. Staged the implementation, required documents, tests, sample data, and optional `web/` app. No real environment files or credentials were found; `.env.local.example` contains only a placeholder.

**Phase 3 — Commit:** `git add -A`, `git diff --cached --check`, and one initial commit on `main`. The exact staged file list was reviewed before commit.

**Phase 4 — Publish:** Pushed `main` to `https://github.com/Consoder/HROne.git`. The initial implementation commit `27d2695` was confirmed as the remote `main` ref with `git ls-remote`; GitHub's public contents API lists the expected root documents and `app/`, `tests/`, `sample_data/`, and `web/` directories. The required assignment form has not been submitted; that remains the final human submission step.

## 2026-10-12 - Read-only HTTP load test

**What:** Added `tests/load_test.py`, a standard-library concurrent GET load harness, and ran it against a separate Uvicorn process on port 8010 connected to the generated `attendance_scale` MongoDB 7 database (1,000 employees, 100,000 logs). All routes were warmed up before timing. The suite does not issue write requests.

**Profiles/results:** One client, one seven-route pass: 7/7 HTTP 200, 20.636 seconds end-to-end, 0.34 requests/s; largest observed request was late leaderboard at 12.24 seconds. Five concurrent clients, four passes each: 140/140 HTTP 200, zero errors, 145.111 seconds, 0.96 requests/s. Overall latency p50/p95/p99 was 94.8/23,546.1/23,940.3 ms. Per-route p50: health 15 ms, employees 38 ms, attendance list 95 ms, employee monthly 38 ms, department summary 4,692 ms, late leaderboard 22,551 ms, department trend 8,428 ms.

**Conclusion:** Functional availability held under this modest read concurrency, but analytics response times are too high to call the load test a performance pass. IXSCAN explain results are not a substitute for runtime latency. No latency target was supplied, so this result identifies a bottleneck rather than a formal SLO failure.

**Limits:** Local synthetic-data benchmark only; not a sustained soak test or production-capacity certification. The harness expects the existing generated `attendance_scale` database; its generator was not included. Server process on port 8010 was stopped after both runs.

## 2026-10-12 - Analytics pipeline performance refactor and re-test

**What changed:** Grouped attendance logs by employee before joining employee metadata in the late-arrival leaderboard and department summary. Reworked department trend to start from one department's employee set and use the `(emp_code, date)` index to fetch only in-range logs. The summary pipeline separately unions eligible employee rows (so people with no logs still count in headcount) with per-employee monthly attendance totals. Added a regression test covering zero-log headcount and excluding future joiners.

**Why:** The first 100k-row read-load run identified repeated per-log employee joins as expensive in leaderboard and trend. Grouping earlier limits metadata joins. The trend's department-first approach avoids fetching unrelated teams' rows. The summary rewrite was attempted to avoid per-employee correlated attendance lookups while preserving the no-attendance headcount rule.

**Checks:** Python 3.11 integration/edge suite: 51/51 passed against `attendance_api_test`. Re-ran the same GET-only load profiles on a fresh Uvicorn process using the updated module and `attendance_scale` (1,000 employees / 100,000 logs). The source was verified through the summary explain command before timing. At 5 clients × 4 passes: 140/140 HTTP 200, 4.44 req/s, overall p50 144.6 ms / p95 4,785.6 ms / p99 6,425.0 ms. Per-route p50s: health 25.9 ms, employees 42.8 ms, attendance list 142.9 ms, employee monthly 45.0 ms, department summary 4,544.8 ms, leaderboard 1,845.1 ms, trend 709.8 ms. Versus the original profile, leaderboard and trend p50 improved about 92%; the summary improved only about 3% and remains the main latency issue.

**Honest status:** All requests completed successfully, but because no acceptance latency target was specified and department summary remains slow at this synthetic scale, this should be reported as a functional load pass with substantial analytics improvements—not a complete performance pass. The summary pipeline rewrite preserves headcount and metric semantics in tests, but its measured performance does not justify claiming success for that endpoint. More work would require profiling realistic dataset distributions and likely changing the data/index strategy; avoid adding denormalized or cached summary state without an explicit consistency design.

**Benchmark caveat:** An intermediate post-change run reused a server process imported before the new summary source. Its summary explain showed the old pipeline, so that run is excluded from the report. The benchmark server was restarted and the updated `$unionWith` pipeline confirmed before collecting the figures above.

## 2026-10-12 - Independent Ponytail and Rabbitcode review

**What:** Asked both available review agents to inspect the pushed `ab62ba6` backend for correctness, MongoDB query plans, and performance risks. They made no file edits. No separately connected external optimization-platform integration was available; the connected Code Review tool only reads CI checks for an existing pull request.

**Findings checked against current source:** Both reviewers repeated a summary-pipeline `$push`/`$$REMOVE` warning, but that describes the pre-refactor pipeline; current `summary_pipeline()` uses `$sum` plus a count to compute the average and creates no large work array. Ponytail also flagged negative late minutes, but current `late_minutes()` already returns zero unless the punch is more than the 10-minute grace threshold, so this is not a current defect. Their trend/lookup comments likewise referred to an older pipeline shape. These stale findings were not applied.

**Actionable remaining recommendation:** Rabbitcode identified that punch-out searches by `{emp_code, punch_in <= punched}` and sorts by `punch_in` descending, while startup currently has no `{emp_code, punch_in}` index. This may scan/sort one employee's historical records. Measure this path on a growing history before adding the extra index, since each index also adds storage and write cost. A status-led attendance-list index is similarly workload-dependent. Neither index was added during this review-only request.

**Result:** Both agents agree the core aggregation/race-safety design is sound, but reviews must be reconciled against the current commit: several findings were stale. No code changes were made; this review summary is the only project-file update for this step.

## 2026-10-12 - Addressed current review optimization

**What changed:** Added `employee_punch_in_desc` on `(emp_code, punch_in descending)` for the punch-out query, plus a startup-index regression assertion. Added an explicit 09:29:59 early-arrival test to protect zero late minutes. Updated `DECISIONS.md` to explain the new index and current summary pipeline structure.

**Why:** The punch-out filter/sort has no useful prefix in the prior indexes, so it could scan an employee's history and sort candidates. The compound index matches the equality predicate followed by the requested newest-first range ordering. Early arrival was already handled correctly; a direct test prevents regression and closes the coverage gap.

**Checks:** All 52 Python integration/edge tests passed against the isolated `attendance_api_test` database. MongoDB `executionStats` for the punch-out find/sort/limit query showed `IXSCAN` with `employee_punch_in_desc`, no collection scan, and a top-level `LIMIT`. The extra index adds storage and per-write maintenance, accepted to support this core punch-out operation. No latency claim is made for this query beyond its indexed plan; the 100k GET benchmark does not exercise punch-out writes.
