"""
app.py — Flask entry point for the Automated Flaky Test Maintenance Tool.

Endpoints:
  POST /run-tests       — Run the test suite N times and detect flaky tests
  GET  /flaky-tests     — Return all detected flaky tests
  GET  /suggestions     — Return suggested fixes for flaky tests
  POST /ingest-junit    — Ingest JUnit XML reports from CI
  GET  /history/<name>  — Per-test trend data
  GET  /trends          — Aggregate trend data
  GET  /trends/summary  — Newly flaky / resolved / worsened / improved
  GET  /webhooks        — List configured webhooks
  POST /webhooks        — Add a webhook
  DELETE /webhooks/<id> — Remove a webhook
  POST /webhooks/test   — Test a webhook
  GET  /health          — Health check
  GET  /                — Serve the developer dashboard
"""

import os
import logging
import uuid
from flask import Flask, jsonify, request, render_template, abort
from flask_cors import CORS

from flaky_detector import FlakyDetector
from test_analyzer import TestAnalyzer
from junit_parser import JUnitParser, aggregate_junit_results
from notifications import WebhookNotifier, send_test_notification
from database import (
    init_db, get_all_results, get_all_suggestions, upsert_result,
    get_existing_flaky_names, record_run_history,
    get_test_history, get_trend_data, get_trend_summary,
    add_webhook, get_webhooks, delete_webhook,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)
init_db()


# ---------------------------------------------------------------------------
# Routes — Core
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def dashboard():
    """Serve the developer dashboard."""
    return render_template("index.html")


@app.route("/health", methods=["GET"])
def health():
    """Health-check endpoint."""
    return jsonify({"status": "healthy"}), 200


@app.route("/run-tests", methods=["POST"])
def run_tests():
    """
    Run the test suite multiple times and detect flaky tests.

    Optional JSON body:
        { "runs": <int> }          (default: 5, max: 20)
        { "test_path": <str> }     (default: src/test/sample_tests.py)
    """
    body = request.get_json(silent=True) or {}

    runs = body.get("runs", 5)
    test_path = body.get("test_path", "src/test/sample_tests.py")

    if not isinstance(runs, int) or runs < 1 or runs > 20:
        abort(400, description="'runs' must be an integer between 1 and 20.")

    logger.info("Starting test run: %d iteration(s) on '%s'", runs, test_path)

    # Snapshot existing flaky tests before detection
    previously_flaky = get_existing_flaky_names()
    batch_id = str(uuid.uuid4())

    detector = FlakyDetector(test_path=test_path, runs=runs)
    try:
        results = detector.run()
    except FileNotFoundError as exc:
        abort(404, description=str(exc))
    except RuntimeError as exc:
        abort(500, description=str(exc))

    analyzer = TestAnalyzer()
    for result in results:
        result["suggested_fix"] = analyzer.suggest_fix(result.get("logs", ""), result)
        upsert_result(result)
        record_run_history(result["test_name"], batch_id, result, source="pytest")

    # Notify on newly detected flaky tests
    new_flaky = [r for r in results
                 if r.get("is_flaky") and r["test_name"] not in previously_flaky]
    if new_flaky:
        webhooks = get_webhooks()
        notifier = WebhookNotifier(webhooks)
        notifier.notify_new_flaky_tests(new_flaky, batch_id)

    return jsonify({
        "message": "Test run complete.",
        "batch_id": batch_id,
        "total_tests": len(results),
        "flaky_count": sum(1 for r in results if r.get("is_flaky")),
        "results": results,
    }), 200


@app.route("/flaky-tests", methods=["GET"])
def flaky_tests():
    """Return all detected flaky tests from the store."""
    data = get_all_results()
    return jsonify({"count": len(data), "flaky_tests": data}), 200


@app.route("/suggestions", methods=["GET"])
def suggestions():
    """Return all test name -> suggested-fix mappings."""
    data = get_all_suggestions()
    return jsonify({"suggestions": data}), 200


# ---------------------------------------------------------------------------
# Routes — JUnit XML Ingestion
# ---------------------------------------------------------------------------

@app.route("/ingest-junit", methods=["POST"])
def ingest_junit():
    """
    Ingest one or more JUnit XML report files from CI systems.

    Accepts multipart file upload with field name 'files'.
    Optional form field: 'batch_id' (auto-generated if not provided).
    """
    files = request.files.getlist("files")
    if not files:
        abort(400, description="No files uploaded. Use field name 'files'.")

    batch_id = request.form.get("batch_id", str(uuid.uuid4()))
    parser = JUnitParser()

    all_runs = []
    for f in files:
        try:
            content = f.read().decode("utf-8")
            run_results = parser.parse_string(content)
            all_runs.append(run_results)
        except Exception as exc:
            logger.warning("Failed to parse file '%s': %s", f.filename, exc)
            continue

    if not all_runs:
        abort(400, description="No valid JUnit XML files could be parsed.")

    # Aggregate across all uploaded reports
    results = aggregate_junit_results(all_runs)

    # Snapshot existing flaky tests
    previously_flaky = get_existing_flaky_names()

    analyzer = TestAnalyzer()
    for result in results:
        result["suggested_fix"] = analyzer.suggest_fix(result.get("logs", ""), result)
        upsert_result(result)
        record_run_history(result["test_name"], batch_id, result, source="junit_xml")

    # Notify on newly detected flaky tests
    new_flaky = [r for r in results
                 if r.get("is_flaky") and r["test_name"] not in previously_flaky]
    if new_flaky:
        webhooks = get_webhooks()
        notifier = WebhookNotifier(webhooks)
        notifier.notify_new_flaky_tests(new_flaky, batch_id)

    return jsonify({
        "message": "JUnit reports ingested.",
        "batch_id": batch_id,
        "files_parsed": len(all_runs),
        "total_tests": len(results),
        "flaky_count": sum(1 for r in results if r.get("is_flaky")),
        "results": results,
    }), 200


# ---------------------------------------------------------------------------
# Routes — History & Trends
# ---------------------------------------------------------------------------

@app.route("/history/<path:test_name>", methods=["GET"])
def test_history(test_name: str):
    """Return time-series run history for a specific test."""
    limit = request.args.get("limit", 50, type=int)
    data = get_test_history(test_name, limit=limit)
    return jsonify({"test_name": test_name, "history": data}), 200


@app.route("/trends", methods=["GET"])
def trends():
    """Return aggregate flaky test count over time."""
    days = request.args.get("days", 30, type=int)
    data = get_trend_data(days=days)
    return jsonify({"days": days, "trends": data}), 200


@app.route("/trends/summary", methods=["GET"])
def trends_summary():
    """Compare last two batches: newly flaky, resolved, worsened, improved."""
    data = get_trend_summary()
    return jsonify(data), 200


# ---------------------------------------------------------------------------
# Routes — Webhooks
# ---------------------------------------------------------------------------

@app.route("/webhooks", methods=["GET"])
def list_webhooks():
    """List all configured webhooks."""
    data = get_webhooks()
    return jsonify({"webhooks": data}), 200


@app.route("/webhooks", methods=["POST"])
def create_webhook():
    """Add a new webhook configuration."""
    body = request.get_json(silent=True) or {}
    name = body.get("name")
    url = body.get("url")
    hook_type = body.get("type", "generic")

    if not name or not url:
        abort(400, description="'name' and 'url' are required.")
    if hook_type not in ("slack", "generic"):
        abort(400, description="'type' must be 'slack' or 'generic'.")

    wh_id = add_webhook(name, url, hook_type)
    return jsonify({"message": "Webhook added.", "id": wh_id}), 201


@app.route("/webhooks/<int:webhook_id>", methods=["DELETE"])
def remove_webhook(webhook_id: int):
    """Delete a webhook by ID."""
    if delete_webhook(webhook_id):
        return jsonify({"message": "Webhook deleted."}), 200
    abort(404, description="Webhook not found.")


@app.route("/webhooks/test", methods=["POST"])
def test_webhook():
    """Send a test notification to verify a webhook."""
    body = request.get_json(silent=True) or {}
    url = body.get("url")
    hook_type = body.get("type", "generic")

    if not url:
        abort(400, description="'url' is required.")

    result = send_test_notification({"url": url, "type": hook_type})
    status = 200 if result["success"] else 502
    return jsonify(result), status


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(400)
def bad_request(err):
    return jsonify({"error": "Bad Request", "message": str(err.description)}), 400

@app.errorhandler(404)
def not_found(err):
    return jsonify({"error": "Not Found", "message": str(err.description)}), 404

@app.errorhandler(500)
def server_error(err):
    return jsonify({"error": "Internal Server Error", "message": str(err.description)}), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", 8080))
    debug = os.getenv("FLASK_ENV", "production") == "development"
    logger.info("Starting FlakyScan on %s:%d", host, port)
    app.run(host=host, port=port, debug=debug)
