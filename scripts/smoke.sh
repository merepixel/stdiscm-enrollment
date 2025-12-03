#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost}"

echo "Waiting for gateway at ${BASE_URL}..."
for i in {1..30}; do
  if curl -sf "${BASE_URL}/api/ping" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "Hitting ping..."
curl -sf "${BASE_URL}/api/ping"
echo
echo "Hitting smoke courses..."
curl -sf "${BASE_URL}/api/smoke/courses"
echo
