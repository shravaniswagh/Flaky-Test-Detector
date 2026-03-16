"""
junit_parser.py — Parse JUnit XML test reports (standard CI output format).

Supports output from pytest --junitxml, Jenkins, CircleCI, GitHub Actions, etc.
"""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger(__name__)


class JUnitParser:
    """Parses JUnit XML reports into a normalized list of test outcomes."""

    def parse_file(self, path: str) -> list[dict]:
        """Parse a JUnit XML file and return a list of test outcome dicts."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"JUnit XML file not found: {path}")

        tree = ET.parse(str(file_path))
        root = tree.getroot()
        return self._parse_root(root)

    def parse_string(self, xml_content: str) -> list[dict]:
        """Parse a JUnit XML string and return a list of test outcome dicts."""
        root = ET.fromstring(xml_content)
        return self._parse_root(root)

    def _parse_root(self, root: ET.Element) -> list[dict]:
        """Parse from the root element, handling both <testsuites> and <testsuite>."""
        results = []

        if root.tag == "testsuites":
            for suite in root.findall("testsuite"):
                results.extend(self._parse_suite(suite))
        elif root.tag == "testsuite":
            results.extend(self._parse_suite(root))
        else:
            logger.warning("Unexpected root element: %s", root.tag)

        return results

    def _parse_suite(self, suite: ET.Element) -> list[dict]:
        """Parse a single <testsuite> element."""
        results = []

        for testcase in suite.findall("testcase"):
            name = testcase.get("name", "unknown")
            classname = testcase.get("classname", "")

            # Build test_name like pytest nodeid: classname::name
            if classname:
                test_name = f"{classname}::{name}"
            else:
                test_name = name

            # Check for failure or error
            failure = testcase.find("failure")
            error = testcase.find("error")
            skipped = testcase.find("skipped")

            if skipped is not None:
                continue  # skip skipped tests

            log = ""
            passed = True

            if failure is not None:
                passed = False
                msg = failure.get("message", "")
                text = failure.text or ""
                log = f"{msg}\n{text}".strip()
            elif error is not None:
                passed = False
                msg = error.get("message", "")
                text = error.text or ""
                log = f"{msg}\n{text}".strip()

            results.append({
                "test_name": test_name,
                "passed": passed,
                "log": log,
                "time": float(testcase.get("time", 0)),
            })

        return results


def aggregate_junit_results(all_runs: list[list[dict]]) -> list[dict]:
    """
    Aggregate results from multiple JUnit XML parses into flaky-detection stats.

    Args:
        all_runs: List of parse results, one per run/report.

    Returns:
        List of dicts with test_name, total_runs, passes, failures,
        failure_rate, is_flaky, logs.
    """
    from collections import defaultdict

    aggregated: dict[str, dict] = defaultdict(
        lambda: {"pass": 0, "fail": 0, "logs": []}
    )

    for run in all_runs:
        for test in run:
            name = test["test_name"]
            if test["passed"]:
                aggregated[name]["pass"] += 1
            else:
                aggregated[name]["fail"] += 1
                if test.get("log"):
                    aggregated[name]["logs"].append(test["log"])

    results = []
    for test_name, counts in aggregated.items():
        total = counts["pass"] + counts["fail"]
        failures = counts["fail"]
        failure_rate = round(failures / total, 4) if total else 0.0
        is_flaky = counts["pass"] > 0 and counts["fail"] > 0

        results.append({
            "test_name": test_name,
            "total_runs": total,
            "passes": counts["pass"],
            "failures": failures,
            "failure_rate": failure_rate,
            "is_flaky": is_flaky,
            "logs": "\n".join(counts["logs"]),
        })

    results.sort(key=lambda x: (not x["is_flaky"], -x["failure_rate"]))
    return results
