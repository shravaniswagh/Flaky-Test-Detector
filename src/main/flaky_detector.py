"""
flaky_detector.py — Runs the test suite N times and detects flaky tests.

A test is considered flaky if:
  - It was executed in at least 2 runs
  - It passed in at least one run AND failed in at least one run
"""

import subprocess
import json
import logging
import os
import tempfile
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class FlakyDetector:
    """
    Orchestrates repeated test execution and flaky detection.

    Args:
        test_path (str): Path to the pytest target (file or directory).
        runs (int): Number of times to run the test suite.
    """

    def __init__(self, test_path: str = "src/test/sample_tests.py", runs: int = 5):
        project_root = Path(__file__).resolve().parents[2]
        test_path = Path(test_path)
        self.test_path = (
            test_path
            if test_path.is_absolute()
            else (project_root / test_path)
        )
        self.runs = runs

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> list[dict]:
        """
        Execute the test suite `self.runs` times and return per-test statistics.
        """
        if not self.test_path.exists():
            raise FileNotFoundError(
                f"Test file/directory not found: '{self.test_path}'"
            )

        aggregated: dict[str, dict] = defaultdict(
            lambda: {"pass": 0, "fail": 0, "logs": []}
        )

        for i in range(1, self.runs + 1):
            logger.info("Run %d / %d …", i, self.runs)
            run_results = self._run_once()
            for test_name, outcome in run_results.items():
                if outcome["passed"]:
                    aggregated[test_name]["pass"] += 1
                else:
                    aggregated[test_name]["fail"] += 1
                    aggregated[test_name]["logs"].append(outcome.get("log", ""))

        return self._compute_stats(aggregated)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_once(self) -> dict[str, dict]:
        """Execute pytest once with JSON reporting."""
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as tmp:
            report_path = tmp.name

        try:
            subprocess.run(
                [
                    "python", "-m", "pytest",
                    str(self.test_path),
                    "--json-report",
                    f"--json-report-file={report_path}",
                    "-v",
                    "--tb=short",
                    "--no-header",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            return self._parse_json_report(report_path)
        except subprocess.TimeoutExpired:
            logger.error("Test run timed out after 120 s")
            raise RuntimeError("Test execution timed out.")
        except Exception as exc:
            logger.error("Unexpected error during test run: %s", exc)
            raise RuntimeError(f"Test execution failed: {exc}") from exc
        finally:
            if os.path.exists(report_path):
                os.unlink(report_path)

    @staticmethod
    def _parse_json_report(report_path: str) -> dict[str, dict]:
        """Parse pytest-json-report output and return outcome map."""
        outcomes: dict[str, dict] = {}
        try:
            with open(report_path, "r") as f:
                report = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            logger.warning("Could not parse JSON report: %s", exc)
            return outcomes

        for test in report.get("tests", []):
            node_id = test.get("nodeid", "unknown")
            passed = test.get("outcome", "") == "passed"
            log = ""
            for phase in ("setup", "call", "teardown"):
                phase_data = test.get(phase) or {}
                longrepr = phase_data.get("longrepr") or ""
                if longrepr:
                    log += longrepr + "\n"
            outcomes[node_id] = {"passed": passed, "log": log.strip()}

        return outcomes

    @staticmethod
    def _compute_stats(aggregated: dict) -> list[dict]:
        """Turn raw pass/fail counts into statistics dicts."""
        results = []
        for test_name, counts in aggregated.items():
            total = counts["pass"] + counts["fail"]
            failures = counts["fail"]
            failure_rate = round(failures / total, 4) if total else 0.0
            is_flaky = counts["pass"] > 0 and counts["fail"] > 0

            results.append(
                {
                    "test_name": test_name,
                    "total_runs": total,
                    "passes": counts["pass"],
                    "failures": failures,
                    "failure_rate": failure_rate,
                    "is_flaky": is_flaky,
                    "logs": "\n".join(counts["logs"]),
                }
            )

        results.sort(key=lambda x: (not x["is_flaky"], -x["failure_rate"]))
        return results
