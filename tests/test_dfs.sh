#!/usr/bin/env bash
# Pruebas de integración E2E del DFS.
# Uso dentro de Docker:
#   docker compose up -d
#   docker compose --profile tools run --rm client bash /app/tests/test_dfs.sh
# Uso local (NameNode + 2 DataNodes en localhost):
#   NAMENODE_URL=http://localhost:8000 ./tests/test_dfs.sh

set -euo pipefail

NAMENODE_URL="${NAMENODE_URL:-http://namenode:8000}"
export NAMENODE_URL
PYTHON="${PYTHON:-python3}"
DFS=( "$PYTHON" -m client.cli --namenode "$NAMENODE_URL" )
MIN_DATANODES="${MIN_DATANODES:-2}"
WORKDIR="${WORKDIR:-/tmp/dfs_test_$$}"
USER="dfs_test_$(date +%s)"
PASS="testpass123"

mkdir -p "$WORKDIR"
trap 'rm -rf "$WORKDIR"' EXIT

log() { echo "[test_dfs] $*"; }
fail() { echo "[test_dfs] FAIL: $*" >&2; exit 1; }

wait_namenode() {
  log "Waiting for NameNode at $NAMENODE_URL ..."
  for i in $(seq 1 60); do
    if "${DFS[@]}" health >/dev/null 2>&1; then
      health="$("${DFS[@]}" health 2>/dev/null || true)"
      alive="$(echo "$health" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('datanodes_alive',0))" 2>/dev/null || echo 0)"
      if [ "${alive:-0}" -ge "$MIN_DATANODES" ]; then
        log "NameNode ready (datanodes_alive=$alive)"
        return 0
      fi
      log "NameNode up, waiting for DataNodes ($alive/$MIN_DATANODES) ..."
    fi
    sleep 2
  done
  fail "NameNode or DataNodes not ready in time"
}

checksum() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    fail "sha256sum or shasum required"
  fi
}

wait_namenode

log "Register and login ($USER)"
"${DFS[@]}" register "$USER" "$PASS" >/dev/null
TOKEN="$("$PYTHON" -c "
import httpx, os
base = os.environ['NAMENODE_URL'].rstrip('/')
r = httpx.post(f'{base}/auth/login', json={'username': '$USER', 'password': '$PASS'}, timeout=30)
r.raise_for_status()
print(r.json()['access_token'])
")"
DFS=( "$PYTHON" -m client.cli --namenode "$NAMENODE_URL" --token "$TOKEN" )

SRC="$WORKDIR/sample.bin"
OUT="$WORKDIR/downloaded.bin"
dd if=/dev/urandom of="$SRC" bs=1024 count=48 status=none 2>/dev/null || \
  "$PYTHON" -c "import os; open('$SRC','wb').write(os.urandom(48*1024))"
HASH_SRC="$(checksum "$SRC")"

log "PUT sample.bin"
"${DFS[@]}" put "$SRC" sample.bin >/dev/null

log "LS"
ls_out="$("${DFS[@]}" ls)"
echo "$ls_out" | grep -q "sample.bin" || fail "sample.bin not in ls output"

log "GET sample.bin"
"${DFS[@]}" get sample.bin "$OUT"
HASH_OUT="$(checksum "$OUT")"
[ "$HASH_SRC" = "$HASH_OUT" ] || fail "checksum mismatch after get"

log "MKDIR projects"
"${DFS[@]}" mkdir projects >/dev/null
echo "$("${DFS[@]}" ls)" | grep -q "projects" || fail "projects directory not listed"

log "RM sample.bin"
"${DFS[@]}" rm sample.bin >/dev/null
ls_after="$("${DFS[@]}" ls)"
echo "$ls_after" | grep -q "sample.bin" && fail "sample.bin still listed after rm"
echo "$ls_after" | grep -q "projects" || fail "projects missing after rm file"

log "RMDIR projects"
"${DFS[@]}" rmdir projects >/dev/null
ls_final="$("${DFS[@]}" ls 2>&1 || true)"
if echo "$ls_final" | grep -qE 'FILE|DIR|sample|projects'; then
  fail "listing not empty after rmdir: $ls_final"
fi

log "ALL TESTS PASSED"
