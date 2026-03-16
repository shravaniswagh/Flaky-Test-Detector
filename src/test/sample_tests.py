"""
sample_tests.py — Deliberately flaky tests demonstrating realistic failure patterns.

These tests simulate real-world flakiness (file I/O races, API timeouts,
database contention, timing issues) so the FlakyDetector can identify them.
"""

import os
import random
import sqlite3
import tempfile
import threading
import time
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Flaky: File I/O Race Conditions
# ---------------------------------------------------------------------------

class TestFileIOFlakiness:
    """Tests that demonstrate file system race conditions."""

    def test_read_temp_file_race(self, tmp_path):
        """
        Simulates a race where another process deletes a temp file
        before it can be read. Flaky ~30% of the time.
        """
        target = tmp_path / "shared_data.txt"
        target.write_text("important data")

        # Simulate another process sometimes deleting the file
        if random.random() < 0.3:
            target.unlink()

        assert target.read_text() == "important data"

    def test_concurrent_file_write(self, tmp_path):
        """
        Two threads write to the same file — content assertion
        sometimes fails due to interleaving.
        """
        target = tmp_path / "counter.txt"
        target.write_text("0")

        def writer(value):
            time.sleep(random.uniform(0, 0.01))
            target.write_text(str(value))

        t1 = threading.Thread(target=writer, args=(1,))
        t2 = threading.Thread(target=writer, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Expect 2 but sometimes get 1 due to race
        assert target.read_text() == "2"


# ---------------------------------------------------------------------------
# Flaky: API / Network Calls
# ---------------------------------------------------------------------------

class TestAPIFlakiness:
    """Tests that simulate unreliable external API calls."""

    def test_external_api_timeout(self):
        """
        Simulates an API call that randomly times out.
        Fails ~35% of the time.
        """
        import requests as req_module

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        def flaky_get(*args, **kwargs):
            if random.random() < 0.35:
                raise req_module.exceptions.Timeout(
                    "timeout: API did not respond within 5s"
                )
            return mock_response

        with patch.object(req_module, "get", side_effect=flaky_get):
            resp = req_module.get("https://api.example.com/health", timeout=5)
            assert resp.status_code == 200

    def test_api_returns_partial_data(self):
        """
        Simulates an API that sometimes returns incomplete JSON.
        Fails ~30% of the time.
        """
        def mock_fetch():
            if random.random() < 0.3:
                return {"users": []}  # empty — missing expected data
            return {"users": [{"id": 1, "name": "alice"}]}

        result = mock_fetch()
        assert len(result["users"]) > 0, "Expected non-empty user list from API"
        assert "name" in result["users"][0]

    def test_api_rate_limited(self):
        """
        Simulates an API that intermittently returns 429 Too Many Requests.
        Fails ~25% of the time.
        """
        mock_response = MagicMock()

        if random.random() < 0.25:
            mock_response.status_code = 429
            mock_response.json.return_value = {"error": "rate limited"}
        else:
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": [1, 2, 3]}

        assert mock_response.status_code == 200, (
            "connection error: API returned 429 Too Many Requests"
        )


# ---------------------------------------------------------------------------
# Flaky: Database Contention
# ---------------------------------------------------------------------------

class TestDatabaseFlakiness:
    """Tests that simulate database-related flakiness."""

    def test_sqlite_concurrent_writes(self, tmp_path):
        """
        Two threads INSERT into the same SQLite database simultaneously.
        Sometimes hits 'database is locked' error.
        """
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, val TEXT)")
        conn.commit()
        conn.close()

        errors = []

        def insert_row(row_id, value):
            try:
                c = sqlite3.connect(db_path, timeout=0.1)
                c.execute("INSERT INTO items VALUES (?, ?)", (row_id, value))
                c.commit()
                c.close()
            except sqlite3.OperationalError as e:
                errors.append(str(e))

        t1 = threading.Thread(target=insert_row, args=(1, "alpha"))
        t2 = threading.Thread(target=insert_row, args=(2, "beta"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0, f"database error: {errors}"

    def test_stale_db_connection(self):
        """
        Simulates a connection that randomly becomes stale/closed.
        Fails ~30% of the time.
        """
        if random.random() < 0.3:
            raise ConnectionError(
                "connection error: database connection pool exhausted — "
                "stale connection returned after idle timeout"
            )

        result = {"id": 42, "name": "test_record"}
        assert result["id"] == 42


# ---------------------------------------------------------------------------
# Flaky: Timing / Race Conditions
# ---------------------------------------------------------------------------

class TestTimingFlakiness:
    """Tests sensitive to execution timing."""

    def test_cache_expiry_race(self):
        """
        Sets a value with very short TTL, then reads it.
        Sometimes the TTL expires between write and read.
        """
        cache = {}
        ttl_ms = 5  # 5ms TTL

        cache["key"] = {"value": "data", "expires": time.time() + ttl_ms / 1000}

        # Simulate variable processing delay
        time.sleep(random.uniform(0.002, 0.008))

        entry = cache.get("key")
        assert entry is not None
        if time.time() > entry["expires"]:
            raise TimeoutError("timeout: cache entry expired before read")

        assert entry["value"] == "data"

    def test_operation_within_deadline(self):
        """
        Simulates an operation that must complete within a deadline.
        Fails ~30% when random delay exceeds threshold.
        """
        deadline_ms = 100
        delay = random.uniform(0, 150)
        time.sleep(delay / 1000)

        if delay > deadline_ms:
            raise TimeoutError(
                f"timeout: operation took {delay:.0f}ms, exceeded {deadline_ms}ms deadline"
            )
        assert True

    def test_async_callback_ordering(self):
        """
        Fires two callbacks with short timers — order is non-deterministic.
        Sometimes fails when callbacks arrive out of order.
        """
        results = []

        def callback(label, delay):
            time.sleep(delay)
            results.append(label)

        t1 = threading.Thread(target=callback, args=("first", random.uniform(0, 0.01)))
        t2 = threading.Thread(target=callback, args=("second", random.uniform(0, 0.01)))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results[0] == "first", (
            "race condition detected: callbacks arrived out of order"
        )


# ---------------------------------------------------------------------------
# Flaky: Resource & Environment
# ---------------------------------------------------------------------------

class TestResourceFlakiness:
    """Tests that simulate resource exhaustion / environment issues."""

    def test_memory_pressure_simulation(self):
        """
        Simulates a test that intermittently fails under memory pressure.
        Fails ~25% of the time.
        """
        if random.random() < 0.25:
            raise MemoryError(
                "resource error: insufficient memory to allocate tensor buffer"
            )
        data = [i * 2 for i in range(100)]
        assert len(data) == 100

    def test_env_variable_dependency(self):
        """
        Depends on an env variable that is sometimes unset in CI.
        Fails ~20% of the time.
        """
        # Simulate env inconsistency
        if random.random() < 0.2:
            os.environ.pop("TEST_API_KEY", None)
        else:
            os.environ["TEST_API_KEY"] = "test-key-12345"

        api_key = os.environ.get("TEST_API_KEY")
        assert api_key is not None, (
            "resource error: TEST_API_KEY not set in environment"
        )


# ---------------------------------------------------------------------------
# Stable tests (for contrast — these should NEVER be flagged as flaky)
# ---------------------------------------------------------------------------

class TestStableOperations:
    """Always-passing tests to verify the detector correctly ignores them."""

    def test_addition(self):
        assert 1 + 1 == 2

    def test_string_concatenation(self):
        assert "hello" + " " + "world" == "hello world"

    def test_list_length(self):
        data = [1, 2, 3, 4, 5]
        assert len(data) == 5

    def test_dict_access(self):
        config = {"host": "localhost", "port": 5432}
        assert config["port"] == 5432

    def test_set_operations(self):
        a = {1, 2, 3}
        b = {2, 3, 4}
        assert a & b == {2, 3}

    def test_string_methods(self):
        assert "  hello  ".strip() == "hello"
        assert "hello world".split() == ["hello", "world"]
