#!/usr/bin/env bash
set -euo pipefail

cleanup_demo_file() {
  if [[ -n "${DEMO_FILE_PATH:-}" && -f "${DEMO_FILE_PATH}" ]]; then
    rm -f "${DEMO_FILE_PATH}"
  fi
}
trap cleanup_demo_file EXIT

if [[ $# -lt 1 ]]; then
  echo "Usage:"
  echo "  $0 <API_URL> <FILE_PATH> <CONTENT_TYPE>"
  echo "  $0 <API_URL> --demo"
  echo "Example:"
  echo "  $0 https://abc.execute-api.us-east-1.amazonaws.com ./sample.pdf application/pdf"
  echo "  $0 https://abc.execute-api.us-east-1.amazonaws.com --demo"
  exit 1
fi

API_URL="${1%/}"
shift

if [[ "${1:-}" == "--demo" ]]; then
  DEMO_FILE_PATH="$(mktemp /tmp/upload-demo-XXXXXX.txt)"
  printf "demo upload at %s\n" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" > "${DEMO_FILE_PATH}"
  FILE_PATH="${DEMO_FILE_PATH}"
  CONTENT_TYPE="text/plain"
else
  if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <API_URL> <FILE_PATH> <CONTENT_TYPE>"
    echo "Or:    $0 <API_URL> --demo"
    exit 1
  fi
  FILE_PATH="$1"
  CONTENT_TYPE="$2"
fi

FILENAME="$(basename "$FILE_PATH")"

if [[ ! -f "$FILE_PATH" ]]; then
  echo "Error: file not found: $FILE_PATH"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required for JSON parsing."
  exit 1
fi

echo "Requesting presigned upload URL..."
RESP="$(curl -sS -X POST "$API_URL/upload" \
  -H "Content-Type: application/json" \
  -d "{\"filename\":\"$FILENAME\",\"content_type\":\"$CONTENT_TYPE\"}")"

if [[ -z "$RESP" ]]; then
  echo "Error: empty response from $API_URL/upload"
  exit 1
fi

read -r DOC_ID KEY UPLOAD_URL RET_CT <<EOF
$(python3 - "$RESP" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
if "upload_url" not in data:
    print("", "", "", "")
else:
    print(
        data.get("document_id", ""),
        data.get("key", ""),
        data.get("upload_url", ""),
        data.get("content_type", ""),
    )
PY
)
EOF

if [[ -z "$UPLOAD_URL" ]]; then
  echo "Upload request failed. Raw response:"
  echo "$RESP"
  exit 1
fi

echo "Uploading $FILE_PATH to S3..."
HTTP_CODE="$(curl -sS -o /dev/null -w "%{http_code}" \
  -X PUT "$UPLOAD_URL" \
  -H "Content-Type: $RET_CT" \
  --data-binary @"$FILE_PATH")"

if [[ "$HTTP_CODE" != "200" && "$HTTP_CODE" != "204" ]]; then
  echo "Upload failed with HTTP $HTTP_CODE"
  echo "document_id: $DOC_ID"
  echo "key: $KEY"
  exit 1
fi

echo "Upload succeeded."
echo "document_id: $DOC_ID"
echo "key: $KEY"
