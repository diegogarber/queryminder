#!/bin/sh
# macOS launcher: double-click in Finder, or run from a terminal (arguments are passed on).
cd "$(dirname "$0")" || exit 1
nohup python3 -m queryminder "$@" >/dev/null 2>&1 &
