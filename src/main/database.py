"""
database.py — SQLite-backed persistent store for flaky test results,
run history, and webhook configuration.
"""

import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("FLAKYSCAN_DB_PATH", "./flakyscan.db")

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    with _lock:
        conn = _connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT UNIQUE NOT NULL,
                    total_runs INTEGER DEFAULT 0,
                    passes INTEGER DEFAULT 0,
                    failures INTEGER DEFAULT 0,
                    failure_rate REAL DEFAULT 0.0,
                    is_flaky INTEGER DEFAULT 0,
                    logs TEXT DEFAULT '',
                    suggested_fix TEXT DEFAULT '',
                    first_seen_at TEXT NOT NULL,
                    last_updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS run_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL,
                    run_batch_id TEXT NOT NULL,
                    total_runs INTEGER DEFAULT 0,
                    passes INTEGER DEFAULT 0,
                    failures INTEGER DEFAULT 0,
                    failure_rate REAL DEFAULT 0.0,
                    is_flaky INTEGER DEFAULT 0,
                    source TEXT DEFAULT 'pytest',
                    recorded_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS webhook_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    type TEXT DEFAULT 'generic',
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_run_history_test
                    ON run_history(test_name);
                CREATE INDEX IF NOT EXISTS idx_run_history_batch
                    ON run_history(run_batch_id);
                CREATE INDEX IF NOT EXISTS idx_run_history_recorded
                    ON run_history(recorded_at);
            """)
            conn.commit()
            logger.info("SQLite database initialized at %s", DB_PATH)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Test results (aggregate / latest)
# ---------------------------------------------------------------------------

def upsert_result(result: dict) -> None:
    """Insert or update a test result by test_name."""
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        conn = _connect()
        try:
            conn.execute("""
                INSERT INTO test_results
                    (test_name, total_runs, passes, failures, failure_rate,
                     is_flaky, logs, suggested_fix, first_seen_at, last_updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(test_name) DO UPDATE SET
                    total_runs = excluded.total_runs,
                    passes = excluded.passes,
                    failures = excluded.failures,
                    failure_rate = excluded.failure_rate,
                    is_flaky = excluded.is_flaky,
                    logs = excluded.logs,
                    suggested_fix = excluded.suggested_fix,
                    last_updated_at = excluded.last_updated_at
            """, (
                result["test_name"],
                result.get("total_runs", 0),
                result.get("passes", 0),
                result.get("failures", 0),
                result.get("failure_rate", 0.0),
                int(result.get("is_flaky", False)),
                result.get("logs", ""),
                result.get("suggested_fix", ""),
                now,
                now,
            ))
            conn.commit()
        finally:
            conn.close()


def get_all_results() -> list[dict]:
    """Return all stored results sorted by failure_rate descending."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM test_results ORDER BY failure_rate DESC"
            ).fetchall()
            return [_row_to_result(r) for r in rows]
        finally:
            conn.close()


def get_all_suggestions() -> list[dict]:
    """Return test_name + suggested_fix for all stored results."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT test_name, suggested_fix FROM test_results ORDER BY failure_rate DESC"
            ).fetchall()
            return [{"test_name": r["test_name"], "suggested_fix": r["suggested_fix"]}
                    for r in rows]
        finally:
            conn.close()


def get_existing_flaky_names() -> set[str]:
    """Return set of test names currently marked as flaky."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT test_name FROM test_results WHERE is_flaky = 1"
            ).fetchall()
            return {r["test_name"] for r in rows}
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Run history (trends)
# ---------------------------------------------------------------------------

def record_run_history(test_name: str, batch_id: str, stats: dict,
                       source: str = "pytest") -> None:
    """Record a single test's stats for a given batch run."""
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        conn = _connect()
        try:
            conn.execute("""
                INSERT INTO run_history
                    (test_name, run_batch_id, total_runs, passes, failures,
                     failure_rate, is_flaky, source, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                test_name,
                batch_id,
                stats.get("total_runs", 0),
                stats.get("passes", 0),
                stats.get("failures", 0),
                stats.get("failure_rate", 0.0),
                int(stats.get("is_flaky", False)),
                source,
                now,
            ))
            conn.commit()
        finally:
            conn.close()


def get_test_history(test_name: str, limit: int = 50) -> list[dict]:
    """Return time-series of a specific test's runs."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute("""
                SELECT run_batch_id, total_runs, passes, failures,
                       failure_rate, is_flaky, source, recorded_at
                FROM run_history
                WHERE test_name = ?
                ORDER BY recorded_at DESC
                LIMIT ?
            """, (test_name, limit)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_trend_data(days: int = 30) -> list[dict]:
    """Aggregate flaky test count per batch over the last N days."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute("""
                SELECT run_batch_id,
                       MIN(recorded_at) as recorded_at,
                       source,
                       COUNT(DISTINCT test_name) as total_tests,
                       SUM(CASE WHEN is_flaky = 1 THEN 1 ELSE 0 END) as flaky_count
                FROM run_history
                WHERE recorded_at >= datetime('now', ?)
                GROUP BY run_batch_id
                ORDER BY recorded_at ASC
            """, (f"-{days} days",)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_trend_summary() -> dict:
    """Compare last two batches to find newly flaky, resolved, worse, better."""
    with _lock:
        conn = _connect()
        try:
            batches = conn.execute("""
                SELECT DISTINCT run_batch_id, MIN(recorded_at) as t
                FROM run_history
                GROUP BY run_batch_id
                ORDER BY t DESC
                LIMIT 2
            """).fetchall()

            if len(batches) < 2:
                return {"newly_flaky": [], "resolved": [], "worsened": [], "improved": []}

            current_id = batches[0]["run_batch_id"]
            previous_id = batches[1]["run_batch_id"]

            def batch_map(bid):
                rows = conn.execute("""
                    SELECT test_name, failure_rate, is_flaky
                    FROM run_history WHERE run_batch_id = ?
                """, (bid,)).fetchall()
                return {r["test_name"]: dict(r) for r in rows}

            curr = batch_map(current_id)
            prev = batch_map(previous_id)

            newly_flaky = [n for n in curr if curr[n]["is_flaky"] and (n not in prev or not prev[n]["is_flaky"])]
            resolved = [n for n in prev if prev[n]["is_flaky"] and (n not in curr or not curr[n]["is_flaky"])]
            worsened = [n for n in curr if n in prev and curr[n]["failure_rate"] > prev[n]["failure_rate"] + 0.05]
            improved = [n for n in curr if n in prev and curr[n]["failure_rate"] < prev[n]["failure_rate"] - 0.05]

            return {
                "newly_flaky": newly_flaky,
                "resolved": resolved,
                "worsened": worsened,
                "improved": improved,
            }
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Webhook config
# ---------------------------------------------------------------------------

def add_webhook(name: str, url: str, hook_type: str = "generic") -> int:
    """Add a webhook and return its ID."""
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute(
                "INSERT INTO webhook_config (name, url, type, enabled, created_at) VALUES (?, ?, ?, 1, ?)",
                (name, url, hook_type, now),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def get_webhooks() -> list[dict]:
    """Return all configured webhooks."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute("SELECT * FROM webhook_config ORDER BY id").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def delete_webhook(webhook_id: int) -> bool:
    """Delete a webhook by ID. Returns True if found."""
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute("DELETE FROM webhook_config WHERE id = ?", (webhook_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_result(row: sqlite3.Row) -> dict:
    """Convert a test_results row to a dict matching the old in-memory format."""
    return {
        "test_name": row["test_name"],
        "total_runs": row["total_runs"],
        "passes": row["passes"],
        "failures": row["failures"],
        "failure_rate": row["failure_rate"],
        "is_flaky": bool(row["is_flaky"]),
        "logs": row["logs"],
        "suggested_fix": row["suggested_fix"],
        "first_seen_at": row["first_seen_at"],
        "last_updated_at": row["last_updated_at"],
    }
