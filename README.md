# Employee Attendance and Analytics API

A FastAPI service for employee records, attendance punch-in/punch-out, HR corrections with an audit trail, and attendance analytics. Implementation is in `app/main.py` as required by the assignment. The design and each build step are explained in `LOG.md`.

## Run locally

Use Python 3.11 or newer and MongoDB 6.0 or newer. Set `MONGO_URI` and `MONGO_DB` in your environment (or a local `.env` file). For a local Docker MongoDB, start MongoDB separately; this project intentionally does not include a Dockerfile.

```bash
python -m venv .venv
# Activate .venv for your operating system, then:
pip install -r requirements.txt
python sample_seed.py
uvicorn app.main:app --port 8000
```

The sample seed script replaces the contents of the two sample collections, so point it only at a disposable development database. MongoDB 6.0+ is required; department trend uses MongoDB's `$densify` aggregation stage.

## Run the automated checks

Start a disposable MongoDB, then set `MONGO_DB` to a test-only database name before running:

```bash
python -m unittest discover -s tests -v
```

The tests remove and recreate only their own fixtures (`EMP9988` and `EMP7701`–`EMP7705`). Do not point them at a database containing real employees with those codes. The expanded boundary suite and its results are in `tests/test_qa_edges.py` and `QA_REPORT.md`. The 100,000-row query-plan dataset used during development is generated separately and is not required by this workflow suite.

## Project notes

- `openapi.yaml` and `DATA_MODEL.md` define the expected API and data rules.
- `REVIEW.md` records defects found in the original starter.
- `DECISIONS.md` explains the main implementation choices.
- `QA_REPORT.md` records backend edge coverage, browser checks, and frontend fixes/remaining manual checks.
- `LOG.md` records each build and verification step in plain language.

The supplied sample data is small. The implementation has also been checked against a generated 100,000-row database for explain plans; see `LOG.md` for the exact results and remaining limits.

## Submission hygiene

Submit the repository publicly as the assignment requests. Do not commit `.env`, credentials, or a virtual environment. Keep the assignment and solution off other public sites until the date specified in the assignment email.
