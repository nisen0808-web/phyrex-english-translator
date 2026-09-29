#!/bin/bash
set -euo pipefail
APP_ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
"$APP_ROOT/.runtime/python/bin/python3" -B -E -s -X utf8 "$APP_ROOT/mac_launcher.py" install
printf '\n安装完成，按回车关闭这个窗口。'
read -r _
