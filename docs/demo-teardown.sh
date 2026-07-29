#!/usr/bin/env bash
# Remove everything docs/demo-setup.sh created.
#
#   ./docs/demo-teardown.sh
#
# Kills the throwaway sshd and stand-in services, stops the host-run stack, and
# deletes /tmp/mudale-demo — including the demo host key and the CLI token that
# was written into env.sh.

set -uo pipefail

DEMO_DIR=/tmp/mudale-demo

pkill -f "$DEMO_DIR/sshd_config"      2>/dev/null && echo "stopped the demo sshd"
pkill -f "mudale-demo-services"       2>/dev/null && echo "stopped the stand-in services"
pkill -f "daphne.*mudale.asgi"        2>/dev/null && echo "stopped the web tier"
pkill -f "manage.py enginectl"        2>/dev/null && echo "stopped the engine"

sleep 1

# Any ssh the engine left behind, in case it was killed before it could stop them.
pkill -f "ssh -N -T -F /dev/null"     2>/dev/null && echo "stopped leftover tunnels"

rm -rf "$DEMO_DIR" && echo "removed $DEMO_DIR"
rm -f /tmp/mudale-web.log /tmp/mudale-engine.log

echo "Done."
