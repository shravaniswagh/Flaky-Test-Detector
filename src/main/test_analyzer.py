"""
test_analyzer.py — Analyzes failure logs and suggests fixes for flaky tests.

Rules (in priority order):
  1. "timeout"           → suggest adding explicit waits
  2. "connection error"  → suggest mocking network calls
  3. "race condition"    → suggest synchronization / retry logic
  4. "assert"            → suggest checking test data / mock state
  5. "import"            → suggest verifying dependency installation
  6. "resource"          → suggest teardown / cleanup improvements
  7. (default)           → suggest general investigation steps
"""

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

RULES: list[tuple[str, str]] = [
    (
        r"timeout|timed out|read timeout|connection timed out",
        (
            "Add explicit waits or increase timeout thresholds. "
            "Consider using retry decorators (e.g., tenacity) for transient timeouts. "
            "Example: `time.sleep(1)` before the flaky assertion, or use `pytest-timeout` with a higher limit."
        ),
    ),
    (
        r"connection error|connectionrefused|connection refused|network|socket",
        (
            "Mock or stub external network calls to avoid real I/O in tests. "
            "Use `unittest.mock.patch` or `responses` library to intercept HTTP calls. "
            "For integration tests, ensure the service is health-checked before the test runs."
        ),
    ),
    (
        r"race condition|concurrent|threading|multithread|deadlock|lock",
        (
            "Introduce synchronization primitives (threading.Event, asyncio.Lock) or "
            "use retry logic (e.g., wait-and-retry pattern). "
            "If possible, refactor the test to be single-threaded or use proper barriers."
        ),
    ),
    (
        r"assertionerror|assert.*failed|expected.*but got",
        (
            "Verify that test data and mock state are fully reset between runs. "
            "Use pytest fixtures with 'function' scope and ensure teardown cleans up shared state. "
            "Consider using `pytest-randomly` to detect order-dependent failures."
        ),
    ),
    (
        r"importerror|modulenotfounderror|no module named",
        (
            "Verify all dependencies are installed in the test environment. "
            "Check `requirements.txt` and run `pip install -r requirements.txt`. "
            "Ensure the PYTHONPATH includes necessary directories."
        ),
    ),
    (
        r"resource|memoryerror|disk|file not found|filenotfounderror",
        (
            "Improve test teardown to release resources (file handles, DB connections, temp files). "
            "Use `pytest` fixtures with `yield` and cleanup after the yield to guarantee resource release."
        ),
    ),
    (
        r"database|db error|psycopg|sqlalchemy|integrity error",
        (
            "Wrap database interactions in transactions that are rolled back after each test. "
            "Use a dedicated test database and reset state between test runs with fixtures."
        ),
    ),
]

DEFAULT_SUGGESTION = (
    "Investigate the failure logs for environment-specific issues. "
    "Consider isolating the test, adding detailed logging, and reproducing the failure locally "
    "with `pytest -v --tb=long`. Check for test-order dependencies using `pytest-randomly`."
)


class TestAnalyzer:
    """
    Rules-based engine that maps failure log patterns to actionable fix suggestions.
    """

    def suggest_fix(self, log: str, result: dict | None = None) -> str:
        """
        Analyse a failure log string and return a suggestion string.

        Args:
            log:    The combined stderr / traceback from failed test runs.
            result: Optional dict of test statistics (for future ML-based rules).

        Returns:
            A human-readable suggestion string.
        """
        if not log or not log.strip():
            return DEFAULT_SUGGESTION

        log_lower = log.lower()

        for pattern, suggestion in RULES:
            if re.search(pattern, log_lower):
                logger.debug(
                    "Pattern '%s' matched — returning targeted suggestion.", pattern
                )
                return suggestion

        # No specific pattern matched
        logger.debug("No pattern matched for log snippet; using default suggestion.")
        return DEFAULT_SUGGESTION

    def batch_suggest(self, results: list[dict]) -> list[dict]:
        """
        Attach suggestions to a list of result dicts in place.

        Args:
            results: Output of FlakyDetector.run()

        Returns:
            Same list with 'suggested_fix' populated.
        """
        for result in results:
            result["suggested_fix"] = self.suggest_fix(
                result.get("logs", ""), result
            )
        return results
