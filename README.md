# Automated Test Maintenance Tool

A DevOps-integrated system that **detects flaky tests**, **suggests fixes**, and plugs into **CI/CD pipelines** — with a live dashboard, historical trend tracking, webhook alerts, and JUnit XML ingestion from any CI system.

---

## Table of Contents

- [Problem Statement](#problem-statement)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [DevOps Features](#devops-features)
- [Tech Stack](#tech-stack)
- [Quick Start (Docker)](#quick-start-docker)
- [Quick Start (Local)](#quick-start-local)
- [Testing the Project](#testing-the-project)
- [API Reference](#api-reference)
- [CI/CD Pipeline](#cicd-pipeline)
- [Dashboard](#dashboard)
- [Project Structure](#project-structure)

---

## Problem Statement

**Flaky tests** — tests that sometimes pass and sometimes fail without any code changes — are one of the biggest productivity drains in software engineering. They erode developer trust in the test suite, cause false CI failures, and waste hours of debugging time.

This tool **automates the detection, analysis, and reporting of flaky tests** across your CI/CD pipeline:

1. **Detect** — Run tests multiple times or ingest CI reports to identify inconsistent tests
2. **Analyze** — Pattern-match failure logs to determine root causes (timeouts, race conditions, network issues, etc.)
3. **Suggest** — Provide actionable fix recommendations for each flaky test
4. **Track** — Store historical data so you can see trends over time (getting better or worse?)
5. **Alert** — Notify your team via Slack or webhook when new flaky tests appear

---

## How It Works

### Detection Algorithm

```
For each test in the suite:
    Run pytest N times (default: 5)
    Count passes and failures per test

    If passes > 0 AND failures > 0:
        Mark as FLAKY
        failure_rate = failures / total_runs

    Analyze failure logs against rule patterns
    Attach suggested fix
    Store in SQLite database
    Notify webhooks if newly flaky
```

### What Makes a Test "Flaky"

A test is flaky if it **both passes and fails** across multiple identical runs. The tool computes a `failure_rate` (0.0 to 1.0) and sorts tests by severity.

### Analysis Engine

The rule-based analyzer matches failure logs against patterns:

| Pattern Detected | Root Cause | Suggested Fix |
|---|---|---|
| `timeout`, `timed out` | Operation exceeds deadline | Add retry decorators, increase timeout thresholds |
| `connection error`, `refused` | Network dependency failure | Mock/stub external calls with `unittest.mock` |
| `race condition`, `threading` | Concurrency issue | Add synchronization primitives, use barriers |
| `assertionerror` | State pollution between tests | Reset fixtures, use `pytest-randomly` |
| `importerror` | Missing dependency | Verify `requirements.txt`, check `PYTHONPATH` |
| `resource`, `memory` | Resource leak | Improve teardown, use `yield` fixtures |
| `database`, `db error` | DB state corruption | Use transactional rollbacks, reset DB between tests |

---

## Architecture

```
                    +---------------------------+
                    |    Developer Dashboard    |
                    |  (HTML / CSS / Chart.js)  |
                    +------------+--------------+
                                 | HTTP
                    +------------v--------------+
                    |     Flask Backend          |
                    |     (Gunicorn, 2 workers)  |
                    |                            |
                    |  +--------+  +---------+   |
                    |  | Flaky  |  | Test    |   |
                    |  |Detector|  |Analyzer |   |
                    |  +---+----+  +---------+   |
                    |      |                     |
                    |  +---v-----------+         |
                    |  | pytest        |         |
                    |  | (subprocess)  |         |
                    |  +---------------+         |
                    |                            |
                    |  +-------------------+     |
                    |  | JUnit XML Parser  |     |  <-- CI reports (GitHub Actions,
                    |  +-------------------+     |      Jenkins, GitLab CI)
                    |                            |
                    |  +-------------------+     |
                    |  | Webhook Notifier  +-----|----> Slack / Generic webhooks
                    |  +-------------------+     |
                    +------------+--------------+
                                 |
                    +------------v--------------+
                    |   SQLite Database          |
                    |   - test_results           |
                    |   - run_history (trends)   |
                    |   - webhook_config         |
                    +---------------------------+
```

### Data Flow

```
1. Trigger (dashboard button OR CI pipeline)
         |
         v
2. Execute tests (pytest subprocess) OR ingest JUnit XML from CI
         |
         v
3. Aggregate results: count passes/failures per test across runs
         |
         v
4. Classify: flaky (passes > 0 AND failures > 0) or stable
         |
         v
5. Analyze: match failure logs against rule patterns -> suggested fix
         |
         v
6. Persist: upsert into SQLite (test_results + run_history)
         |
         v
7. Notify: send webhook alerts for newly detected flaky tests
         |
         v
8. Display: dashboard renders KPIs, charts, table, trends
```

---

## DevOps Features

### CI/CD Integration

The tool is designed to fit into existing CI/CD pipelines:

| Feature | Description |
|---|---|
| **GitHub Actions Pipeline** | 5-job CI: lint, test, flaky detection, Docker build, security scan |
| **Scheduled Weekly Scan** | Cron workflow runs flaky detection every Monday, auto-creates GitHub issues |
| **Jenkinsfile** | Full Jenkins pipeline with JUnit report archiving |
| **JUnit XML Ingestion** | Upload test reports from any CI system via `POST /ingest-junit` |
| **PR Comments** | CI automatically comments flaky test results on pull requests |

### How CI Integration Works

```
  CI Pipeline (GitHub Actions / Jenkins / GitLab CI)
       |
       |  1. Run pytest --junitxml=results.xml
       |  2. Upload results to FlakyScan:
       |     curl -X POST http://flakyscan/ingest-junit -F "files=@results.xml"
       |
       v
  FlakyScan ingests report, detects flaky tests, sends Slack alerts
```

### Persistent Storage

SQLite database with three tables — survives container restarts via Docker volume:

- **test_results** — Latest aggregate stats per test (failure rate, flaky status, suggested fix)
- **run_history** — One row per test per analysis run (for historical trends)
- **webhook_config** — Slack and generic webhook configurations

### Webhook Notifications

Get alerted when new flaky tests are detected:

- **Slack** — Rich Block Kit messages with test names, failure rates, and fixes
- **Generic JSON** — POST to any endpoint (PagerDuty, Discord, custom systems)

### Historical Trend Tracking

- Track flaky test count over time (line chart)
- Compare consecutive runs: newly flaky, resolved, worsened, improved
- Per-test history with failure rate timeline

---

## Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| Backend | Python 3.11, Flask 3.0 | Web framework, API endpoints |
| Test Execution | pytest 8.3 + pytest-json-report | Run tests, collect JSON results |
| Database | SQLite (stdlib) | Persistent storage, zero-config |
| Frontend | HTML, CSS, Chart.js 4.4 | Dashboard with charts and tables |
| Server | Gunicorn | Production WSGI server |
| Containerization | Docker, Docker Compose | Consistent deployment |
| CI/CD | GitHub Actions, Jenkins | Automated pipelines |
| Notifications | requests library | Webhook delivery (Slack, generic) |
| Report Parsing | xml.etree.ElementTree | JUnit XML ingestion |
| Security Scanning | Bandit, Safety | SAST and dependency vulnerability checks |

---

## Quick Start (Docker)

**Prerequisites:** Docker >= 20.x, Docker Compose >= 2.x

```bash
# 1. Clone the repository
git clone https://github.com/yourorg/devopsprojectflakytestmaintenancetool.git
cd devopsprojectflakytestmaintenancetool

# 2. Build and start the container
docker compose -f infrastructure/docker/docker-compose.yml up --build -d

# 3. Open the dashboard
open http://localhost:5000        # macOS
# or visit http://localhost:5000 in your browser

# 4. Verify health
curl http://localhost:5000/health
# Expected: {"status": "healthy"}
```

### Docker Commands Reference

```bash
# View logs
docker compose -f infrastructure/docker/docker-compose.yml logs -f

# Stop
docker compose -f infrastructure/docker/docker-compose.yml down

# Stop and remove persisted data
docker compose -f infrastructure/docker/docker-compose.yml down -v
```

| Service | URL |
|---|---|
| Dashboard | http://localhost:5000 |
| Health Check | http://localhost:5000/health |

---

## Quick Start (Local)

**Prerequisites:** Python >= 3.11

```bash
# 1. Clone and enter the repo
git clone https://github.com/yourorg/devopsprojectflakytestmaintenancetool.git
cd devopsprojectflakytestmaintenancetool

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the server
PYTHONPATH=src/main python3 src/main/app.py

# 5. Open dashboard
open http://localhost:8080
```

---

## Testing the Project

Follow these steps to verify all features work end-to-end.

### Step 1: Start the Application

**Option A — Docker (recommended):**
```bash
docker compose -f infrastructure/docker/docker-compose.yml up --build -d
export BASE_URL=http://localhost:5000
```

**Option B — Local:**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src/main python3 src/main/app.py &
export BASE_URL=http://localhost:8000
```

### Step 2: Verify Health Check

```bash
curl -s $BASE_URL/health
```
Expected output:
```json
{"status": "healthy"}
```

### Step 3: Run Flaky Test Detection

```bash
curl -s -X POST $BASE_URL/run-tests \
  -H "Content-Type: application/json" \
  -d '{"runs": 3}' | python3 -m json.tool
```
Expected output (numbers will vary due to randomness):
```json
{
    "message": "Test run complete.",
    "batch_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "total_tests": 18,
    "flaky_count": 5,
    "results": [ ... ]
}
```
You should see `flaky_count > 0` — these are the flaky tests the tool detected.

### Step 4: View Detected Flaky Tests

```bash
curl -s $BASE_URL/flaky-tests | python3 -m json.tool
```
Shows all tests with their failure rates, flaky status, and logs.

### Step 5: View Fix Suggestions

```bash
curl -s $BASE_URL/suggestions | python3 -m json.tool
```
Each flaky test has a targeted suggestion based on its failure pattern.

### Step 6: Test JUnit XML Ingestion (CI Integration)

Create a sample JUnit report and upload it:

```bash
# Create a sample JUnit XML file (simulating CI output)
cat > /tmp/junit-report.xml << 'EOF'
<?xml version="1.0"?>
<testsuite name="ci-pipeline" tests="4" failures="2">
  <testcase classname="TestCheckout" name="test_payment_success" time="0.5"/>
  <testcase classname="TestCheckout" name="test_payment_timeout" time="5.0">
    <failure message="timeout">Payment gateway timed out after 5s</failure>
  </testcase>
  <testcase classname="TestAuth" name="test_login" time="0.3"/>
  <testcase classname="TestAuth" name="test_session_expired" time="1.2">
    <failure message="race condition">Session token expired mid-request</failure>
  </testcase>
</testsuite>
EOF

# Upload to FlakyScan
curl -s -X POST $BASE_URL/ingest-junit \
  -F "files=@/tmp/junit-report.xml" | python3 -m json.tool
```
Expected: `files_parsed: 1`, `total_tests: 4`, and appropriate suggestions for each failure.

### Step 7: Check Historical Trends

```bash
# View trends (flaky count over time)
curl -s "$BASE_URL/trends?days=30" | python3 -m json.tool

# View trend summary (newly flaky, resolved, worsened, improved)
curl -s $BASE_URL/trends/summary | python3 -m json.tool
```

### Step 8: Test Webhook Configuration

```bash
# Add a webhook
curl -s -X POST $BASE_URL/webhooks \
  -H "Content-Type: application/json" \
  -d '{"name": "team-alerts", "url": "https://httpbin.org/post", "type": "generic"}' \
  | python3 -m json.tool

# List webhooks
curl -s $BASE_URL/webhooks | python3 -m json.tool

# Delete a webhook (replace 1 with actual ID)
curl -s -X DELETE $BASE_URL/webhooks/1 | python3 -m json.tool
```

### Step 9: View the Dashboard

Open your browser to:
- **Docker:** http://localhost:5000
- **Local:** http://localhost:8080

You should see:
1. **Dashboard tab** — KPI cards (total, flaky, avg rate, stable), bar chart, pie chart, searchable table
2. **Trends tab** — Line chart of flaky count over time, trend summary cards
3. **CI Integration tab** — Drag-and-drop JUnit XML upload, CI pipeline setup examples
4. **Webhooks tab** — Add/test/delete webhook configurations

Click **Run Tests** on the dashboard to trigger detection from the UI.

### Step 10: Run the Sample Tests Directly

```bash
# Activate venv if not already
source .venv/bin/activate

# Run once — you'll see some tests fail
PYTHONPATH=src/main python3 -m pytest src/test/sample_tests.py -v --tb=short

# Run again — different tests may fail (that's flakiness!)
PYTHONPATH=src/main python3 -m pytest src/test/sample_tests.py -v --tb=short
```

### Step 11: Verify Docker Build

```bash
docker build -f infrastructure/docker/Dockerfile -t flakyscan:test .
docker run -d --name flakyscan-verify -p 9090:8080 flakyscan:test
sleep 4
curl -s http://localhost:9090/health
docker stop flakyscan-verify && docker rm flakyscan-verify
```

### Cleanup

```bash
# Docker
docker compose -f infrastructure/docker/docker-compose.yml down -v

# Local
deactivate  # exit venv
rm -f flakyscan.db
```

---

## API Reference

### Core Endpoints

| Method | Endpoint | Description | Body |
|---|---|---|---|
| `GET` | `/` | Dashboard UI | — |
| `GET` | `/health` | Health check | — |
| `POST` | `/run-tests` | Run flaky detection | `{"runs": 5, "test_path": "src/test/sample_tests.py"}` |
| `GET` | `/flaky-tests` | All test results | — |
| `GET` | `/suggestions` | Fix suggestions | — |

### CI Integration

| Method | Endpoint | Description | Body |
|---|---|---|---|
| `POST` | `/ingest-junit` | Upload JUnit XML reports | Multipart: `files=@report.xml` |

### Trends & History

| Method | Endpoint | Description | Params |
|---|---|---|---|
| `GET` | `/trends` | Flaky count over time | `?days=30` |
| `GET` | `/trends/summary` | Compare last 2 runs | — |
| `GET` | `/history/<test_name>` | Per-test history | `?limit=50` |

### Webhooks

| Method | Endpoint | Description | Body |
|---|---|---|---|
| `GET` | `/webhooks` | List all webhooks | — |
| `POST` | `/webhooks` | Add a webhook | `{"name": "...", "url": "...", "type": "slack\|generic"}` |
| `DELETE` | `/webhooks/<id>` | Delete a webhook | — |
| `POST` | `/webhooks/test` | Test a webhook | `{"url": "...", "type": "slack\|generic"}` |

---

## CI/CD Pipeline

### GitHub Actions (`.github/workflows/ci.yml`)

Triggered on push/PR to `main`. Five jobs:

```
lint ──> test ──> flaky-detection
  │        │
  └────────┴──> docker-build ──> security-scan
```

| Job | What It Does |
|---|---|
| **Lint** | flake8 + pylint on source code |
| **Test** | Run pytest with JUnit output, publish test report |
| **Flaky Detection** | Run flaky detector (3 iterations), warn on PR if flaky tests found |
| **Docker Build** | Build image, run health check on container |
| **Security Scan** | Bandit (SAST) + Safety (dependency vulnerabilities) |

### Scheduled Scan (`.github/workflows/flaky-report.yml`)

- Runs every Monday at 6 AM UTC (or manual trigger)
- Executes 5-iteration flaky detection
- Uploads report as artifact
- Auto-creates/updates a GitHub issue labeled `flaky-tests`

### Jenkinsfile

Same stages as GitHub Actions — setup, lint, test (with JUnit archiving), flaky detection, Docker build, health check.

---

## Dashboard

The dashboard has four tabs:

### Dashboard Tab
- **KPI Cards** — Total tests, flaky count, average failure rate, stable count
- **Failure Rate Chart** — Bar chart showing top 12 tests by failure rate
- **Distribution Chart** — Doughnut chart of flaky vs stable tests
- **Test Table** — Searchable, sortable, filterable table with status badges and fix suggestions

### Trends Tab
- **Line Chart** — Flaky test count and total tests over time
- **Trend Summary** — Cards showing newly flaky, resolved, worsened, improved tests between runs

### CI Integration Tab
- **JUnit Upload** — Drag-and-drop area for uploading XML reports from CI
- **Setup Examples** — Copy-paste snippets for GitHub Actions, Jenkins, GitLab CI

### Webhooks Tab
- **Webhook Management** — Add, test, and delete Slack or generic webhook endpoints

---

## Project Structure

```
devopsprojectflakytestmaintenancetool/
|
+-- src/
|   +-- main/
|   |   +-- app.py                  # Flask backend (all API routes)
|   |   +-- flaky_detector.py       # Multi-run pytest execution + flaky detection
|   |   +-- test_analyzer.py        # Rules-based failure log analysis
|   |   +-- database.py             # SQLite persistence (results, history, webhooks)
|   |   +-- junit_parser.py         # JUnit XML report parser
|   |   +-- notifications.py        # Webhook notifier (Slack + generic)
|   |   +-- templates/
|   |   |   +-- index.html          # Dashboard HTML (4 tabs)
|   |   +-- static/
|   |       +-- app.js              # Dashboard JavaScript
|   |       +-- styles.css          # Dashboard styling
|   +-- test/
|       +-- sample_tests.py         # Realistic flaky + stable test samples
|       +-- conftest.py             # Shared pytest fixtures
|
+-- infrastructure/
|   +-- docker/
|       +-- Dockerfile              # Python 3.11-slim, Gunicorn, non-root user
|       +-- docker-compose.yml      # App service + persistent volume
|
+-- .github/
|   +-- workflows/
|       +-- ci.yml                  # CI/CD pipeline (lint, test, detect, build, scan)
|       +-- flaky-report.yml        # Scheduled weekly flaky test scan
|
+-- Jenkinsfile                     # Jenkins pipeline (alternative to GitHub Actions)
+-- requirements.txt                # Production dependencies
+-- requirements-dev.txt            # Dev/CI dependencies (linters, security tools)
+-- docs/
|   +-- designdocument.md           # Architecture and design spec
+-- README.md                       # This file
```

---

## License

MIT
