"""
Upload Lambda: POST /upload returns a presigned S3 PUT URL; GET /health for checks.

Deploy with handler `upload_lambda.lambda_handler` and code root `lambda/upload/`.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import uuid
from typing import Any

import boto3

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

DOCUMENTS_BUCKET_NAME = os.environ["DOCUMENTS_BUCKET_NAME"]
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
PRESIGN_EXPIRES_SECONDS = int(os.environ.get("PRESIGN_EXPIRES_SECONDS", "900"))

_s3 = boto3.client("s3")

_ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "text/plain",
    }
)
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_filename(name: str) -> str:
    base = name.strip() or "document"
    base = base.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    base = _SAFE_NAME.sub("_", base)[:180]
    return base or "document"


def _create_presigned_upload(filename: str, content_type: str) -> dict[str, Any]:
    ct = (content_type or "").strip().lower()
    if ct not in _ALLOWED_CONTENT_TYPES:
        raise ValueError(
            "Incorrect document type. Only PDF (application/pdf) and plain text "
            "(text/plain / .txt) are allowed."
        )

    document_id = str(uuid.uuid4())
    safe = _sanitize_filename(filename)
    key = f"uploads/{document_id}/{safe}"

    upload_url = _s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": DOCUMENTS_BUCKET_NAME,
            "Key": key,
            "ContentType": ct,
        },
        ExpiresIn=PRESIGN_EXPIRES_SECONDS,
        HttpMethod="PUT",
    )

    return {
        "document_id": document_id,
        "bucket": DOCUMENTS_BUCKET_NAME,
        "key": key,
        "content_type": ct,
        "upload_url": upload_url,
        "expires_in": PRESIGN_EXPIRES_SECONDS,
        "max_upload_bytes": MAX_UPLOAD_BYTES,
    }


def _http_response(
    status_code: int,
    body: dict[str, Any],
    *,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {
        "content-type": "application/json",
        "access-control-allow-origin": "*",
    }
    if extra_headers:
        headers.update(extra_headers)
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body),
    }


def _parse_route(event: dict[str, Any]) -> tuple[str, str]:
    rc = event.get("requestContext") or {}
    if "http" in rc:
        method = rc["http"]["method"].upper()
        path = event.get("rawPath") or rc["http"].get("path") or "/"
        return method, path
    method = (event.get("httpMethod") or "GET").upper()
    path = event.get("path") or "/"
    return method, path


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    method, path = _parse_route(event)

    if method == "GET" and path.rstrip("/").endswith("/health"):
        return _http_response(200, {"status": "ok", "service": "upload"})

    if method != "POST" or not path.rstrip("/").endswith("/upload"):
        return _http_response(
            404,
            {"error": "not_found", "message": f"No route for {method} {path}"},
        )

    body_raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body_raw = base64.b64decode(body_raw).decode("utf-8", errors="replace")

    try:
        payload = json.loads(body_raw) if body_raw else {}
    except json.JSONDecodeError:
        return _http_response(400, {"error": "invalid_json", "message": "Body must be JSON"})

    filename = str(payload.get("filename") or "document").strip()
    content_type = str(payload.get("content_type") or "").strip()
    if not content_type:
        return _http_response(
            400,
            {"error": "validation_error", "message": "content_type is required"},
        )

    try:
        result = _create_presigned_upload(filename, content_type)
    except ValueError as e:
        return _http_response(400, {"error": "validation_error", "message": str(e)})
    except Exception:
        log.exception("Failed to create presigned upload")
        return _http_response(
            500,
            {"error": "internal_error", "message": "Could not prepare upload"},
        )

    return _http_response(
        201,
        {
            "document_id": result["document_id"],
            "bucket": result["bucket"],
            "key": result["key"],
            "content_type": result["content_type"],
            "upload_url": result["upload_url"],
            "expires_in": result["expires_in"],
            "max_upload_bytes": result["max_upload_bytes"],
            "instructions": (
                "HTTP PUT the raw file bytes to upload_url with header "
                "Content-Type set exactly to the returned content_type."
            ),
        },
    )
