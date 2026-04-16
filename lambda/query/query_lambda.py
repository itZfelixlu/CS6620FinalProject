"""
Query Lambda: GET /results, GET /results/{document_id} (DynamoDB; no scans for list/detail).

Deploy with handler `query_lambda.lambda_handler` and code root `lambda/query/`.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import threading
import time
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

RESULTS_TABLE_NAME = os.environ["RESULTS_TABLE_NAME"]
TENANT_ID = os.environ.get("TENANT_ID", "default")
DEFAULT_LIMIT = int(os.environ.get("DEFAULT_PAGE_LIMIT", "25"))
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "120"))
CACHE_ENABLED = os.environ.get("CACHE_ENABLED", "1").strip().lower() in ("1", "true", "yes")
DOCUMENTS_BUCKET_NAME = os.environ.get("DOCUMENTS_BUCKET_NAME", "")

_table = boto3.resource("dynamodb").Table(RESULTS_TABLE_NAME)
_s3 = boto3.client("s3")
_SAFE_TAG = re.compile(r"[^a-z0-9_-]+")

# Cache-aside (Tier 1): in-process dict per warm Lambda execution environment.
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def _cache_key(document_id: str) -> str:
    return f"result:{document_id}"


def _cache_get(key: str) -> dict[str, Any] | None:
    with _cache_lock:
        entry = _cache.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if time.time() >= expires_at:
            del _cache[key]
            return None
        return copy.deepcopy(value)


def _cache_set(key: str, value: dict[str, Any]) -> None:
    with _cache_lock:
        _cache[key] = (time.time() + CACHE_TTL_SECONDS, copy.deepcopy(value))


def _normalize_tag(tag: str) -> str:
    return _SAFE_TAG.sub("_", tag.strip().lower()).strip("_")


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
        "body": json.dumps(body, default=str),
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


def _document_id_from_path(event: dict[str, Any], path: str) -> str | None:
    pp = event.get("pathParameters") or {}
    if "document_id" in pp:
        return str(pp["document_id"]).strip()
    base = path.rstrip("/")
    if base.startswith("/results/") and base != "/results":
        return base.split("/results/", 1)[-1].strip()
    return None


def _clamp_limit(raw: str | None) -> int:
    try:
        n = int(raw) if raw is not None else DEFAULT_LIMIT
    except ValueError:
        n = DEFAULT_LIMIT
    return max(1, min(n, 100))


def _list_by_time(limit: int) -> dict[str, Any]:
    """Recent main result rows only (excludes tag-index rows).

    DynamoDB applies ``Limit`` to items *read* from the index before any filter. Tag-index
    items share the same GSI1 partition, so a document with many tags can consume the whole
    ``Limit`` in tag rows—making older documents look like they disappeared. We page the
    query and keep only main rows (``document_id`` does not start with ``tag#``).
    """
    collected: list[dict[str, Any]] = []
    exclusive_start_key: dict[str, Any] | None = None
    page_reads = min(100, max(limit * 3, 25))
    max_pages = 50

    for _ in range(max_pages):
        kwargs: dict[str, Any] = {
            "IndexName": "GSI1",
            "KeyConditionExpression": Key("tenant_id").eq(TENANT_ID),
            "ScanIndexForward": False,
            "Limit": page_reads,
        }
        if exclusive_start_key:
            kwargs["ExclusiveStartKey"] = exclusive_start_key
        resp = _table.query(**kwargs)
        for it in resp.get("Items", []):
            if str(it.get("document_id", "")).startswith("tag#"):
                continue
            collected.append(it)
            if len(collected) >= limit:
                out = collected[:limit]
                return {"items": out, "count": len(out)}
        exclusive_start_key = resp.get("LastEvaluatedKey")
        if not exclusive_start_key:
            break

    return {"items": collected, "count": len(collected)}


def _list_by_tag(tag: str, limit: int) -> dict[str, Any]:
    t = _normalize_tag(tag)
    if not t:
        return {"items": [], "count": 0, "error": "empty_tag"}

    resp = _table.query(
        IndexName="GSI2",
        KeyConditionExpression=Key("gsi2pk").eq(f"{TENANT_ID}#{t}"),
        ScanIndexForward=False,
        Limit=min(limit * 3, 100),
    )
    refs: list[str] = []
    seen: set[str] = set()
    for row in resp.get("Items", []):
        rid = str(row.get("ref_document_id") or "")
        if rid and rid not in seen:
            seen.add(rid)
            refs.append(rid)
        if len(refs) >= limit:
            break

    if not refs:
        return {"items": [], "count": 0, "tag": t}

    items: list[dict[str, Any]] = []
    for rid in refs:
        got = _table.get_item(Key={"document_id": rid})
        it = got.get("Item")
        if it and not str(it.get("document_id", "")).startswith("tag#"):
            items.append(it)

    return {"items": items[:limit], "count": len(items[:limit]), "tag": t}


def _get_one_from_db(document_id: str) -> dict[str, Any]:
    if document_id.startswith("tag#"):
        return {"error": "invalid_document_id"}
    resp = _table.get_item(Key={"document_id": document_id})
    item = resp.get("Item")
    if not item:
        return {"error": "not_found"}
    if str(item.get("document_id", "")).startswith("tag#"):
        return {"error": "not_found"}
    return {"item": item}


def _delete_one(document_id: str) -> dict[str, Any]:
    if document_id.startswith("tag#"):
        return {"error": "invalid_document_id"}

    got = _table.get_item(Key={"document_id": document_id})
    item = got.get("Item")
    if not item or str(item.get("document_id", "")).startswith("tag#"):
        return {"error": "not_found"}

    bucket = str(item.get("bucket") or "")
    key = str(item.get("key") or "")
    s3_deleted = False
    if DOCUMENTS_BUCKET_NAME and key:
        # Keep deletion scoped to the configured documents bucket.
        b = DOCUMENTS_BUCKET_NAME
        if bucket and bucket != DOCUMENTS_BUCKET_NAME:
            b = bucket
        try:
            _s3.delete_object(Bucket=b, Key=key)
            s3_deleted = True
        except Exception:
            log.exception("S3 delete failed bucket=%s key=%s", b, key)

    _table.delete_item(Key={"document_id": document_id})

    raw_tags = item.get("tags") or []
    if isinstance(raw_tags, list):
        seen: set[str] = set()
        for raw in raw_tags:
            tag = _normalize_tag(str(raw))
            if not tag or tag in seen:
                continue
            seen.add(tag)
            tag_id = f"tag#{TENANT_ID}#{tag}#{document_id}"
            _table.delete_item(Key={"document_id": tag_id})

    ckey = _cache_key(document_id)
    with _cache_lock:
        _cache.pop(ckey, None)

    return {"deleted": True, "document_id": document_id, "s3_deleted": s3_deleted}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    method, path = _parse_route(event)
    if method not in ("GET", "DELETE"):
        return _http_response(405, {"error": "method_not_allowed"})

    qs = event.get("queryStringParameters") or {}
    limit = _clamp_limit(qs.get("limit"))
    tag = (qs.get("tag") or "").strip()

    doc_id = _document_id_from_path(event, path)
    if method == "DELETE":
        if not doc_id:
            return _http_response(400, {"error": "validation_error", "message": "document_id is required"})
        out = _delete_one(doc_id)
        if out.get("error") == "not_found":
            return _http_response(404, {"error": "not_found", "document_id": doc_id})
        if out.get("error") == "invalid_document_id":
            return _http_response(400, {"error": "invalid_document_id"})
        return _http_response(200, out)

    if doc_id:
        ckey = _cache_key(doc_id)
        if CACHE_ENABLED:
            cached = _cache_get(ckey)
            if cached is not None:
                log.info("Cache HIT %s", ckey)
                return _http_response(200, cached, extra_headers={"x-cache": "HIT"})

        out = _get_one_from_db(doc_id)
        if out.get("error") == "not_found":
            return _http_response(404, {"error": "not_found", "document_id": doc_id})
        if out.get("error") == "invalid_document_id":
            return _http_response(400, {"error": "invalid_document_id"})

        item = out["item"]
        if CACHE_ENABLED:
            _cache_set(ckey, item)
            log.info("Cache MISS %s (ttl=%ss)", ckey, CACHE_TTL_SECONDS)
            return _http_response(200, item, extra_headers={"x-cache": "MISS"})
        return _http_response(200, item)

    if not path.rstrip("/").endswith("/results"):
        return _http_response(404, {"error": "not_found", "path": path})

    if tag:
        body = _list_by_tag(tag, limit)
        if body.get("error") == "empty_tag":
            return _http_response(400, {"error": "validation_error", "message": "tag is empty"})
        return _http_response(200, body)

    body = _list_by_time(limit)
    return _http_response(200, body)
