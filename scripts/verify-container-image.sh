#!/usr/bin/env bash
set -euo pipefail

image_tag="${1:-kinetix:ci-verify}"
trap 'docker image rm "$image_tag" >/dev/null 2>&1 || true' EXIT

docker build --pull --tag "$image_tag" .
docker run --rm --entrypoint sh "$image_tag" -c '
  test ! -e /app/backend/.env &&
  test ! -e /app/.env &&
  test ! -e /app/backend/kinetix.db
'
echo "Container builds without local environment or database files."
