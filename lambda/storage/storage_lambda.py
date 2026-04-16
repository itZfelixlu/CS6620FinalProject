"""
Storage service: terminal pipeline step that persists final outputs to DynamoDB.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import boto3

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

RESULTS_TABLE_NAME = os.environ["RESULTS_TABLE_NAME"]
TENANT_ID = os.environ.get("TENANT_ID", "default")
_table = boto3.resource("dynamodb").Table(RESULTS_TABLE_NAME)
_SAFE_TAG = re.compile(r"[^a-z0-9_-]+")


def _normalize_tag(tag: str) -> str:
    return _SAFE_TAG.sub("_", tag.strip().lower()).strip("_")


def lambda_handler(event: dict[str, Any], context: Any) -> None:
    for record in event.get("Records", []):
        try:
            payload = json.loads(record.get("body") or "{}")
        except json.JSONDecodeError:
            log.warning("Bad JSON, skip")
            continue

        payload["stage"] = "storage"
        now = int(time.time())
        document_id = str(payload.get("document_id") or "")
        if not document_id:
            log.warning("Missing document_id, skip write")
            continue

        item = {
            "document_id": document_id,
            "item_type": "result",
            "tenant_id": TENANT_ID,
            "created_at": now,
            "bucket": payload.get("bucket", ""),
            "key": payload.get("key", ""),
            "status": "completed",
            "summary": payload.get("summary", ""),
            "tags": payload.get("tags", []),
            "key_points": payload.get("key_points", []),
        }
        _table.put_item(Item=item)

        # Write one lightweight tag-index item per tag for GSI2 query access.
        raw_tags = payload.get("tags", [])
        if isinstance(raw_tags, list):
            seen_tags: set[str] = set()
            for raw_tag in raw_tags:
                tag = _normalize_tag(str(raw_tag))
                if not tag or tag in seen_tags:
                    continue
                seen_tags.add(tag)
                tag_item = {
                    "document_id": f"tag#{TENANT_ID}#{tag}#{document_id}",
                    "item_type": "tag_index",
                    "ref_document_id": document_id,
                    "tenant_id": TENANT_ID,
                    "created_at": now,
                    "gsi2pk": f"{TENANT_ID}#{tag}",
                    "gsi2sk": now,
                    "tag": tag,
                }
                _table.put_item(Item=tag_item)

        log.info(
            "Persisted result document_id=%s key=%s tags=%s",
            document_id,
            payload.get("key"),
            payload.get("tags", []),
        )
