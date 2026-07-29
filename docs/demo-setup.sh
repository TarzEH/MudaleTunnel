#!/usr/bin/env bash
# Stand up the environment docs/demo.tape records against.
#
#   ./docs/demo-setup.sh && vhs docs/demo.tape
#
# Creates a throwaway sshd on 127.0.0.1:2222 to act as the foothold, and two
# local HTTP services to stand in for things behind it. Everything lives in
# /tmp/mudale-demo and is removed by docs/demo-teardown.sh.
#
# This exists so the recording is real. The alternative — scripting fake output —
# would make the demo a claim about the tool rather than a recording of it.

set -euo pipefail

DEMO_DIR=/tmp/mudale-demo
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$REPO_ROOT/backend"

mkdir -p "$DEMO_DIR"
cd "$DEMO_DIR"

# ── The foothold ────────────────────────────────────────────────────────

if [[ ! -f hostkey ]]; then
  ssh-keygen -q -t ed25519 -f hostkey -N ''
  ssh-keygen -q -t ed25519 -f jumpkey -N ''
  cp jumpkey.pub authorized_keys
  chmod 600 hostkey jumpkey authorized_keys
fi

cat > sshd_config <<EOF
Port 2222
ListenAddress 127.0.0.1
HostKey $DEMO_DIR/hostkey
AuthorizedKeysFile $DEMO_DIR/authorized_keys
PasswordAuthentication no
UsePAM no
PubkeyAuthentication yes
StrictModes no
AllowTcpForwarding yes
EOF

pkill -f "$DEMO_DIR/sshd_config" 2>/dev/null || true
/usr/sbin/sshd -f "$DEMO_DIR/sshd_config" -D -e > "$DEMO_DIR/sshd.log" 2>&1 &

# ── Services to find behind it ──────────────────────────────────────────

pkill -f "mudale-demo-services" 2>/dev/null || true
python3 -c "
import http.server, socketserver, threading, time
# marker: mudale-demo-services
for port in (8081, 9090):
    def serve(p=port):
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(('127.0.0.1', p), http.server.SimpleHTTPRequestHandler) as s:
            s.serve_forever()
    threading.Thread(target=serve, daemon=True).start()
time.sleep(86400)
" > /dev/null 2>&1 &

sleep 2

# ── The control plane ───────────────────────────────────────────────────

cd "$BACKEND"
export MUDALE_SECRET_KEY="${MUDALE_SECRET_KEY:-demo-secret}"
export MUDALE_DB_PASSWORD="${MUDALE_DB_PASSWORD:-mudale-dev-password}"
export DJANGO_SETTINGS_MODULE=mudale.settings.dev
export MUDALE_DEMO_CREDENTIALS=operator:mudale-demo-2026

./.venv/bin/python manage.py migrate --noinput > /dev/null

# A legible recording needs an empty slate.
./.venv/bin/python - <<'PY'
import django; django.setup()
from apps.scans.models import Scan
from apps.tunnels.models import Tunnel
Tunnel.objects.all().delete()
Scan.objects.all().delete()
PY

TOKEN="$(./.venv/bin/python manage.py seed_demo --cidr 127.0.0.0/8 | grep -o 'mdlt_[A-Za-z0-9_-]*')"

cat > "$DEMO_DIR/env.sh" <<EOF
export MUDALE_URL=http://127.0.0.1:8000
export MUDALE_TOKEN=$TOKEN
export MUDALE_FORCE_COLOR=1
export PATH=$BACKEND/.venv/bin:\$PATH
export PS1='\$ '
EOF

pkill -f "daphne.*mudale.asgi" 2>/dev/null || true
pkill -f "manage.py enginectl" 2>/dev/null || true
sleep 1

nohup ./.venv/bin/python -m daphne -b 127.0.0.1 -p 8000 mudale.asgi:application \
  > /tmp/mudale-web.log 2>&1 &
nohup ./.venv/bin/python manage.py enginectl --interval 2 \
  > /tmp/mudale-engine.log 2>&1 &

sleep 5

echo "Ready. Foothold on 127.0.0.1:2222, dashboard on http://127.0.0.1:8000"
echo "Now run:  vhs docs/demo.tape"
