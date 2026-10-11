# Design decisions

I created a unique index on employee code so two people cannot receive the same business identity. Attendance has a unique employee-and-date index; it both enforces one record per shift day and safely settles simultaneous punch-ins. A date-and-employee index supports the required attendance list order. Department and join date are indexed for department queries. I did not add a separate status-only index because the main list can filter by several combinations; extra indexes slow every write and should be justified by measured query plans.

If two identical punch-ins arrive together, both try to insert the same employee/date key. MongoDB accepts one. The unique index rejects the other, and the API returns 409 for that request. The check is enforced by the database, so timing cannot create duplicates.

The leaderboard uses MongoDB competition rank. If a tie reaches the limit, every employee with rank at or below the limit is returned; the next rank is skipped. Employee code makes tied rows appear in a stable order.

The department summary starts from employees, then looks up attendance. This keeps employees with no logs in headcount and excludes people who joined after the month. For 100 times the data, I would consider precomputed daily summaries after measuring the real workload, while retaining raw logs for audit and drill-down.
