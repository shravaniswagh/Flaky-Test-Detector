# Design Document — Automated Test Maintenance Tool

## 1. System Overview

FlakyScan is a DevOps-integrated web service that detects flaky tests, analyzes failure patterns, suggests fixes, and integrates with CI/CD pipelines. It wraps `pytest` with a multi-run execution harness, ingests JUnit XML reports from external CI systems, tracks historical trends in SQLite, and alerts teams via webhooks when new flaky tests appear.

---

## 2. Architecture

```
                    +---------------------------+
                    |    Developer Dashboard    |
                    |  (HTML / CSS / Chart.js)  |
                    |  4 tabs: Dashboard,       |
                    |  Trends, CI, Webhooks     |
                    +------------+--------------+
                                 | HTTP (port 5000 via Docker, 8080 direct)
                    +------------v--------------+
                    |     Flask Backend          |
                    |     (Gunicorn, 2 workers)  |
                    |                            |
                    |  +---------+ +---------+   |
                    |  | Flaky   | | Test    |   |
                    |  |Detector | |Analyzer |   |
                    |  +----+----+ +---------+   |
                    |       |                    |
                    |  +----v----------+         |
                    |  | pytest        |         |
                    |  | (subprocess)  |         |
                    |  +---------------+         |
                    |                            |
                    |  +-------------------+     |
                    |  | JUnit XML Parser  |     | <-- CI reports
                    |  +-------------------+     |
                    |                            |
                    |  +-------------------+     |
                    |  | Webhook Notifier  +-----|---> Slack / Generic
                    |  +-------------------+     |
                    +------------+--------------+
                                 |
                    +------------v--------------+
                    |   SQLite Database          |
                    |   - test_results           |
                    |   - run_history            |
                    |   - webhook_config         |
                    +---------------------------+
```

---

## 3. Component Descriptions

### 3.1 Flask Backend (`src/main/app.py`)

- Entry point; registers all routes and error handlers
- Creates a `FlakyDetector` instance per `/run-tests` request
- Handles JUnit XML ingestion via `/ingest-junit`
- Manages webhook CRUD via `/webhooks` endpoints
- Serves historical trends via `/trends` and `/history/<name>`
- Delegates fix suggestions to `TestAnalyzer`
- Triggers `WebhookNotifier` when new flaky tests are detected

### 3.2 FlakyDetector (`src/main/flaky_detector.py`)

**Algorithm:**
1. Run `pytest <test_path>` with `--json-report` N times (default 5, max 20)
2. Collect per-test pass/fail counts across all runs
3. A test is **flaky** if `pass_count > 0 AND fail_count > 0`
4. Compute `failure_rate = failures / total_runs`
5. Sort results: flaky first, then by descending failure rate

### 3.3 TestAnalyzer (`src/main/test_analyzer.py`)

Rules-based pattern matching engine (regex, case-insensitive):

| Pattern | Root Cause | Suggestion |
|---|---|---|
| `timeout`, `timed out` | Operation deadline exceeded | Add explicit waits, retry decorators |
| `connection error`, `refused` | Network dependency failure | Mock/stub network calls |
| `race condition`, `threading` | Concurrency issue | Add synchronization primitives |
| `assertionerror` | State pollution | Reset test data, use `pytest-randomly` |
| `importerror` | Missing dependency | Verify `requirements.txt` |
| `resource`, `memory` | Resource leak | Improve teardown, use `yield` fixtures |
| `database`, `db error` | DB state corruption | Use transactional rollbacks |
| _(default)_ | Unknown | General investigation steps |

### 3.4 Database (`src/main/database.py`)

SQLite-backed persistent store with three tables:

- **test_results** — Latest aggregate stats per test (UPSERT on test_name)
- **run_history** — One row per test per analysis batch (for trends)
- **webhook_config** — Webhook endpoints with type (slack/generic) and enabled flag

Thread-safe via `threading.Lock`. WAL mode for concurrent reads. Configurable path via `FLAKYSCAN_DB_PATH` environment variable.

### 3.5 JUnit XML Parser (`src/main/junit_parser.py`)

Parses standard JUnit XML reports (from pytest, Jenkins, GitHub Actions, GitLab CI, etc.):

- Handles both `<testsuites>` and `<testsuite>` root elements
- Extracts test name, class name, pass/fail status, failure messages and stack traces
- Skips `<skipped>` test cases
- `aggregate_junit_results()` combines multiple reports for cross-run flaky detection

### 3.6 Webhook Notifier (`src/main/notifications.py`)

- Sends alerts to all enabled webhooks when new flaky tests are detected
- Runs in a background thread to avoid blocking the API response
- **Slack** — Rich Block Kit messages with test names, failure rates, and fixes
- **Generic** — JSON POST with event type, batch ID, timestamp, and test details

---

## 4. Data Flow

### Detection via pytest

```
POST /run-tests { "runs": 5 }
  |
  +-- Snapshot existing flaky test names from DB
  +-- Generate batch_id (UUID)
  +-- FlakyDetector.run()
  |     +-- loop N times: subprocess pytest -> JSON report
  |     +-- aggregate pass/fail counts per test
  |     +-- _compute_stats() -> list[dict]
  |
  +-- TestAnalyzer: attach suggested_fix to each result
  +-- For each result:
  |     +-- upsert_result() into test_results table
  |     +-- record_run_history() into run_history table
  |
  +-- Compare: find newly flaky tests (not in previous snapshot)
  +-- WebhookNotifier: alert on new flaky tests
  +-- Return JSON response
```

### Ingestion from CI

```
POST /ingest-junit (multipart file upload)
  |
  +-- Parse each uploaded XML with JUnitParser
  +-- aggregate_junit_results() across all files
  +-- Same flow as above: analyze, persist, notify
```

---

## 5. CI/CD Integration Design

### GitHub Actions Pipeline

```
push/PR to main
  |
  +-- lint (flake8 + pylint)
  |     |
  +-----+-- test (pytest + JUnit report + test-reporter)
  |     |     |
  |     |     +-- flaky-detection (3 iterations, PR comment)
  |     |
  +-----+-- docker-build (build image + health check)
  |
  +-- security-scan (bandit + safety)
```

### Scheduled Weekly Scan

- Cron: Monday 6 AM UTC
- Runs 5-iteration flaky detection
- Uploads report artifact
- Auto-creates/updates GitHub issue with `flaky-tests` label

### Jenkins Pipeline

Stages: Setup -> Lint -> Unit Tests (JUnit archiving) -> Flaky Detection -> Docker Build -> Health Check

### CI Report Ingestion Flow

Any CI system can send results to FlakyScan:

```bash
# In your CI pipeline, after running tests:
pytest --junitxml=results.xml || true
curl -X POST http://flakyscan-host/ingest-junit -F "files=@results.xml"
```

---

## 6. Security Design

- **Non-root container**: Dockerfile uses `appuser` (uid 1000)
- **No secrets in images**: Configuration via environment variables
- **Security scanning**: Bandit (SAST) + Safety (dependency vulnerabilities) in CI
- **CORS**: `flask-cors` configured for cross-origin requests
- **Error handling**: All exceptions caught and sanitized before returning to client
- **Input validation**: Runs parameter bounded (1-20), file upload type checking

---

## 7. Persistence & Scalability

- **SQLite** chosen for zero-config deployment (no external DB required)
- **Docker volume** (`flakyscan_data`) ensures data survives container restarts
- **WAL mode** enables concurrent reads during writes
- **Thread lock** serializes write operations for safety
- **Gunicorn** with 2 workers + 4 threads handles ~8 concurrent requests
- For higher scale: swap SQLite for PostgreSQL, add Celery + Redis for async test runs
