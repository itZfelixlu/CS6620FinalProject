"""
Processing service (stub): normalizes / enriches payload and forwards to analysis queue.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

ANALYSIS_QUEUE_URL = os.environ["ANALYSIS_QUEUE_URL"]
_sqs = boto3.client("sqs")


def lambda_handler(event: dict[str, Any], context: Any) -> None:
    for record in event.get("Records", []):
        try:
            payload = json.loads(record.get("body") or "{}")
        except json.JSONDecodeError:
            log.warning("Bad JSON, skip")
            continue

        payload["stage"] = "process"
        payload.setdefault("processed", True)
        payload.setdefault(
            "chunks",
            [],
        )
        _sqs.send_message(QueueUrl=ANALYSIS_QUEUE_URL, MessageBody=json.dumps(payload))
        log.info("Forwarded to analysis: %s", payload.get("document_id", ""))
