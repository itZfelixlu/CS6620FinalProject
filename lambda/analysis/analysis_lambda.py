"""
Analysis: keyword / topic matching against a configurable tag list (case-insensitive substring).
Uses extracted_text from the extract stage. Summary describes scan results; tags hold matches.
key_points is left empty (reserved for a future LLM step).
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import boto3

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

STORAGE_QUEUE_URL = os.environ["STORAGE_QUEUE_URL"]
_sqs = boto3.client("sqs")

_WS = re.compile(r"\s+")


def _load_tag_list() -> list[str]:
    """Load keywords from TAG_LIST_JSON (optional, small overrides) or keyword_tags.json next to handler."""
    raw = (os.environ.get("TAG_LIST_JSON") or "").strip()
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("TAG_LIST_JSON invalid JSON; falling back to keyword_tags.json")
        else:
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
            log.warning("TAG_LIST_JSON must be a JSON array; falling back to keyword_tags.json")

    path = Path(__file__).resolve().parent / "keyword_tags.json"
    if path.is_file():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            log.warning("Could not read keyword_tags.json: %s", e)
            return []
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
        log.warning("keyword_tags.json must be a JSON array")
        return []

    log.warning("No keyword_tags.json next to handler and no valid TAG_LIST_JSON")
    return []


def _normalize_for_match(text: str) -> str:
    return _WS.sub(" ", text.lower()).strip()


def _match_tags(haystack_norm: str, tags: list[str]) -> list[str]:
    """Return tags whose phrase appears as a substring (after lower + whitespace collapse)."""
    matched: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        needle = _normalize_for_match(tag)
        if not needle:
            continue
        if needle in haystack_norm and tag not in seen:
            matched.append(tag)
            seen.add(tag)
    return matched


def lambda_handler(event: dict[str, Any], context: Any) -> None:
    tag_list = _load_tag_list()

    for record in event.get("Records", []):
        try:
            payload = json.loads(record.get("body") or "{}")
        except json.JSONDecodeError:
            log.warning("Bad JSON, skip")
            continue

        payload["stage"] = "analysis"
        text = str(payload.get("extracted_text") or "")
        hay = _normalize_for_match(text)

        if not hay:
            payload["summary"] = (
                "No extractable text was found (empty file, unsupported format, or read error). "
                "Try a .txt or .pdf file."
            )
            payload["tags"] = ["no_extractable_text"]
            payload["key_points"] = []
        else:
            matched = _match_tags(hay, tag_list)
            if not matched:
                payload["summary"] = (
                    f"No phrases from the configured topic list ({len(tag_list)} entries) "
                    "appeared in this document. Add phrases in config/keyword_tags.json and redeploy."
                )
                payload["tags"] = ["no_keyword_match"]
                payload["key_points"] = []
            else:
                shown = ", ".join(matched[:12])
                more = f" (+{len(matched) - 12} more)" if len(matched) > 12 else ""
                payload["summary"] = (
                    f"Keyword scan found {len(matched)} matching topic(s) from your list: "
                    f"{shown}{more}."
                )
                payload["tags"] = matched
                payload["key_points"] = []

        _sqs.send_message(
            QueueUrl=STORAGE_QUEUE_URL,
            MessageBody=json.dumps(payload, ensure_ascii=False),
        )
        log.info(
            "Forwarded to storage: %s tags=%s",
            payload.get("document_id", ""),
            payload.get("tags"),
        )
