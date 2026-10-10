#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec .venv-v2/bin/uvicorn v2.api:app --host 127.0.0.1 --port 8517 --no-proxy-headers
