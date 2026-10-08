#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# The isolated updater supports the protocol-2 to protocol-3 transition.
exec bash "$HERE/../03-Update.command"
