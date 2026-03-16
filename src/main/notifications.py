"""
notifications.py — Webhook notifications for flaky test alerts.

Supports Slack incoming webhooks and generic JSON webhooks.
"""

import json
import logging
import threading
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)


class WebhookNotifier:
    """Sends flaky test alerts to configured webhooks."""

    def __init__(self, webhooks: list[dict]):
        """
        Args:
            webhooks: List of webhook config dicts with keys:
                      name, url, type ('slack' | 'generic'), enabled
        """
        self.webhooks = [w for w in webhooks if w.get("enabled", True)]

    def notify_new_flaky_tests(self, new_flaky: list[dict],
                                batch_id: str) -> None:
        """Send alerts for newly detected flaky tests (runs in background thread)."""
        if not new_flaky or not self.webhooks:
            return

        thread = threading.Thread(
            target=self._send_all,
            args=(new_flaky, batch_id),
            daemon=True,
        )
        thread.start()

    def _send_all(self, new_flaky: list[dict], batch_id: str) -> None:
        """Dispatch to all enabled webhooks."""
        for webhook in self.webhooks:
            try:
                wh_type = webhook.get("type", "generic")
                if wh_type == "slack":
                    self._send_slack(webhook["url"], new_flaky, batch_id)
                else:
                    self._send_generic(webhook["url"], new_flaky, batch_id)
                logger.info("Webhook '%s' notified successfully.", webhook.get("name"))
            except Exception:
                logger.exception("Failed to send webhook '%s'", webhook.get("name"))

    def _send_slack(self, url: str, flaky_tests: list[dict],
                    batch_id: str) -> None:
        """Send a Slack Block Kit message."""
        test_lines = []
        for t in flaky_tests[:10]:  # cap at 10 to avoid oversized payload
            rate_pct = round(t.get("failure_rate", 0) * 100, 1)
            name = t["test_name"].split("::")[-1] if "::" in t["test_name"] else t["test_name"]
            fix = t.get("suggested_fix", "")
            line = f"*{name}* — {rate_pct}% failure rate"
            if fix:
                line += f"\n  _{fix[:120]}_"
            test_lines.append(line)

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"New Flaky Tests Detected ({len(flaky_tests)})",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n\n".join(test_lines),
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Batch: `{batch_id}` | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
                    }
                ],
            },
        ]

        resp = requests.post(url, json={"blocks": blocks}, timeout=10)
        resp.raise_for_status()

    def _send_generic(self, url: str, flaky_tests: list[dict],
                      batch_id: str) -> None:
        """Send a generic JSON webhook."""
        payload = {
            "event": "new_flaky_tests",
            "batch_id": batch_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "flaky_count": len(flaky_tests),
            "tests": [
                {
                    "test_name": t["test_name"],
                    "failure_rate": t.get("failure_rate", 0),
                    "suggested_fix": t.get("suggested_fix", ""),
                }
                for t in flaky_tests
            ],
        }

        resp = requests.post(
            url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()


def send_test_notification(webhook: dict) -> dict:
    """Send a test ping to verify webhook connectivity. Returns status dict."""
    url = webhook.get("url", "")
    wh_type = webhook.get("type", "generic")

    try:
        if wh_type == "slack":
            payload = {
                "text": "FlakyScan test notification — webhook is working!",
            }
        else:
            payload = {
                "event": "test_ping",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": "FlakyScan test notification — webhook is working!",
            }

        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return {"success": True, "status_code": resp.status_code}
    except requests.RequestException as exc:
        return {"success": False, "error": str(exc)}
