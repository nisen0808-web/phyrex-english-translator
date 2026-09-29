#!/bin/bash
set -euo pipefail
APP_ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
exec "$APP_ROOT/.runtime/python/bin/python3" -B -E -s -X utf8 "$APP_ROOT/native_host.py" "$@"
