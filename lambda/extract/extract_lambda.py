"""
Extraction: read object from S3, extract plain text from .txt or .pdf, forward to process queue.
Text is truncated to stay under SQS message size limits.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
from io import BytesIO
from typing import Any

import boto3

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

PROCESS_QUEUE_URL = os.environ["PROCESS_QUEUE_URL"]
# Keep payload under SQS 256 KiB limit (UTF-8 may use multiple bytes per char).
MAX_EXTRACTED_CHARS = int(os.environ.get("MAX_EXTRACTED_CHARS", "80000"))

_sqs = boto3.client("sqs")
_s3 = boto3.client("s3")


def _parse_s3_from_sqs_body(body: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    try:
        outer = json.loads(body)
    except json.JSONDecodeError:
        log.warning("Non-JSON SQS body, skip")
        return out

    detail = outer.get("detail") or {}
    bucket_name = (detail.get("bucket") or {}).get("name")
    object_key = (detail.get("object") or {}).get("key")
    if bucket_name and object_key:
        out.append((bucket_name, urllib.parse.unquote_plus(object_key)))
    else:
        log.warning("EventBridge detail missing bucket/object key, skip")
    return out


def _extract_text_from_object(key: str, data: bytes) -> tuple[str, str]:
    """Return (extracted_text, format_label)."""
    lower = key.lower()
    if lower.endswith(".txt"):
        text = data.decode("utf-8", errors="replace")
        return text, "text"
    if lower.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n".join(parts), "pdf"
    log.warning("Unsupported file type (only .pdf and .txt are supported): %s", key)
    return "", "unsupported"


def lambda_handler(event: dict[str, Any], context: Any) -> None:
    records = event.get("Records", [])
    log.info("Extract invoked with %d record(s)", len(records))
    for record in records:
        body = record.get("body") or ""
        parsed_items = _parse_s3_from_sqs_body(body)
        if not parsed_items:
            log.warning("No parsable S3 object in message body")
        for bucket, key in parsed_items:
            parts = key.split("/", 2)
            document_id = parts[1] if len(parts) >= 2 and parts[0] == "uploads" else ""

            extracted_text = ""
            text_format = ""
            truncated = False
            try:
                obj = _s3.get_object(Bucket=bucket, Key=key)
                raw = obj["Body"].read()
                extracted_text, text_format = _extract_text_from_object(key, raw)
                if len(extracted_text) > MAX_EXTRACTED_CHARS:
                    extracted_text = extracted_text[:MAX_EXTRACTED_CHARS]
                    truncated = True
            except Exception:
                log.exception("Failed to read or parse S3 object %s/%s", bucket, key)
                extracted_text = ""
                text_format = "error"

            payload = {
                "stage": "extract",
                "bucket": bucket,
                "key": key,
                "document_id": document_id,
                "extracted_text": extracted_text,
                "text_format": text_format,
                "text_truncated": truncated,
            }
            _sqs.send_message(
                QueueUrl=PROCESS_QUEUE_URL,
                MessageBody=json.dumps(payload, ensure_ascii=False),
            )
            log.info(
                "Forwarded to process queue: %s chars=%s format=%s truncated=%s",
                document_id or key,
                len(extracted_text),
                text_format,
                truncated,
            )
